import io
import csv
import logging
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from apps.orders.models import Order, OrderItem
from apps.products.models import Product

logger = logging.getLogger(__name__)
EMAIL_HOST_USER     = os.getenv('EMAIL_USER','ahmed09887766554@gmail.com')

# ------------------------------------------------------------------ #
#  Requirement 3 — Asynchronous Queue                                  #
# ------------------------------------------------------------------ #

@shared_task(bind=True, max_retries=3, default_retry_delay=60,rate_limit='10/m')
def send_order_confirmation_email(self, order_id, customer_email, customer_name, total_price):
    """
    Asynchronous task: sends an order-confirmation email after the DB transaction commits.

    Why asynchronous?
      The HTTP response is returned to the user immediately after the DB commit.
      Email delivery (SMTP round-trip, possible retries) happens in the background
      via a Celery worker, so the user is never kept waiting for the mail server.

    Reliability: bind=True + max_retries=3 means the task automatically retries
    up to 3 times (with a 60-second delay) if the SMTP server is temporarily unavailable.
    """
    subject = f'Order confirmation #{order_id}'
    message = (
        f'Hello {customer_name},\n\n'
        f'Your order has been received successfully!\n'
        f'Total: ${total_price}\n\n'
        f'Thank you for shopping with us.'
    )
    try:
        send_mail(
            subject,
            message,
            # settings.EMAIL_HOST_USER,
            EMAIL_HOST_USER,
            [customer_email],
            fail_silently=False,
        )
        logger.info("Confirmation email sent to %s for order #%d", customer_email, order_id)
        return f"Email sent to {customer_email} for order #{order_id}"

    except Exception as exc:
        logger.error("Failed to send email for order #%d: %s", order_id, exc)
        raise self.retry(exc=exc)


# ------------------------------------------------------------------ #
#  Requirement 4 — Batch Processing                                    #
# ------------------------------------------------------------------ #

BATCH_SIZE = 500  # number of rows processed per chunk


@shared_task(name="apps.orders.tasks.daily_sales_batch_processing")
def daily_sales_batch_processing():
    """
    Batch processing task: processes today's completed orders in chunks of
    BATCH_SIZE rows rather than loading the entire result-set into memory.

    Why chunked?
      For a high-volume store, today's orders could be hundreds of thousands
      of rows. Loading them all at once would exhaust RAM.  Processing in
      fixed-size batches keeps memory usage flat and allows the DB server
      to release locks progressively.

    Technique: offset-based pagination over an ordered queryset.
    """
    today = timezone.now().date()
    logger.info("Starting daily batch processing for %s", today)

    base_qs = (
        Order.objects
        .filter(created_at__date=today, status='completed')
        .order_by('id')          # stable ordering is required for correct pagination
    )

    total_revenue = 0
    total_orders = 0
    offset = 0

    while True:
        batch = list(base_qs[offset: offset + BATCH_SIZE])

        if not batch:
            break

        for order in batch:
            total_revenue += order.order_price
            total_orders += 1

        logger.info(
            "Processed batch: orders %d–%d (running total: %d orders, $%.2f revenue)",
            offset + 1,
            offset + len(batch),
            total_orders,
            total_revenue,
        )

        offset += BATCH_SIZE

    logger.info(
        "Daily batch processing complete for %s: %d orders, $%.2f total revenue.",
        today,
        total_orders,
        total_revenue,
    )
    return {
        "date": str(today),
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
    }


@shared_task(name="apps.orders.tasks.generate_weekly_report")
def generate_weekly_report():
    """
    Generates a weekly sales report and emails it to the admin.

    Memory-safe techniques used:
      - Product inventory: iterator(chunk_size=BATCH_SIZE) streams rows without
        loading the whole table into memory.
      - Orders: prefetch_related prevents N+1 queries when iterating items.
    """
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    product_csv = _build_inventory_csv()
    orders_csv, revenue, items_sold = _build_sales_csv(start_date, end_date)
    chart_png, chart_count = _build_top_products_chart(start_date, end_date)

    summary = (
        f"Weekly Store Report\n"
        f"-------------------\n"
        f"Period : {start_date.date()} → {end_date.date()}\n"
        f"Revenue: ${revenue}\n"
        f"Units sold: {items_sold}\n"
        f"Products in stock: {Product.objects.count()}\n"
    )

    email = EmailMessage(
        subject=f"Weekly report — {start_date.date()}",
        body=summary,
        from_email=settings.EMAIL_HOST_USER,
        to=[settings.EMAIL_HOST_USER],
    )
    email.attach('inventory.csv', product_csv.getvalue(), 'text/csv')
    email.attach('sales.csv', orders_csv.getvalue(), 'text/csv')
    email.attach('top_products.png', chart_png.getvalue(), 'image/png')
    email.send()

    return f"Weekly report sent. Top-{chart_count} products chart included."


# ------------------------------------------------------------------ #
#  Private helpers for weekly report                                   #
# ------------------------------------------------------------------ #

def _build_inventory_csv() -> io.StringIO:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['ID', 'Name', 'Stock', 'Price', 'Version', 'Created'])

    # iterator() streams rows in chunks — no full table in memory
    for product in Product.objects.all().order_by('id').iterator(chunk_size=BATCH_SIZE):
        writer.writerow([
            product.id, product.name, product.stock,
            product.price, product.version, product.created_at,
        ])
    return buf


def _build_sales_csv(start_date, end_date):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Order ID', 'Customer', 'Product', 'Qty', 'Status', 'Total', 'Date'])

    orders = (
        Order.objects
        .filter(created_at__range=(start_date, end_date))
        .prefetch_related('items__product')   # prevents N+1
        .order_by('id')
    )

    revenue = 0
    items_sold = 0

    for order in orders:
        for item in order.items.all():
            writer.writerow([
                order.id, order.customer_name, item.product.name,
                item.quantity, order.status, order.order_price,
                order.created_at.strftime('%Y-%m-%d %H:%M'),
            ])
            if order.status == 'completed':
                items_sold += item.quantity
        if order.status == 'completed':
            revenue += order.order_price

    return buf, revenue, items_sold


def _build_top_products_chart(start_date, end_date):
    top = (
        OrderItem.objects
        .filter(order__created_at__range=(start_date, end_date), order__status='completed')
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )

    names = [row['product__name'] for row in top]
    quantities = [row['total_qty'] for row in top]

    fig, ax = plt.subplots(figsize=(10, 6))
    cmap = matplotlib.colormaps['tab10']
    colors = [cmap(i) for i in range(len(names))]
    bars = ax.bar(names, quantities, color=colors)

    ax.set_title('Top 5 Products — Last 7 Days', fontsize=14, fontweight='bold')
    ax.set_xlabel('Product')
    ax.set_ylabel('Units Sold')
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.1, h,
                ha='center', va='bottom', fontweight='bold')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    return buf, len(names)
