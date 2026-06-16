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
from apps.utils.decorators import monitor_performance
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from django.core.cache import cache
logger = logging.getLogger(__name__)
EMAIL_HOST_USER     = os.getenv('EMAIL_USER','ahmed09887766554@gmail.com')


# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #

@shared_task(bind=True, max_retries=3, default_retry_delay=60,rate_limit='10/m')
def send_order_confirmation_email(self, order_id, customer_email, customer_name, total_price):
    subject = f'Order confirmation #{order_id}'
    message = (
        f'Hello {customer_name},\n\n'
        f'Your order has been received successfully!\n'
        f'Total: ${total_price}\n\n'
        f'Thank you for shopping with us.'
    )
    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.EMAIL_HOST_USER, # توحيد الإعدادات
            recipient_list=[customer_email],
            fail_silently=False,
        )
        
        if sent_count == 0:
            raise Exception("Mail server accepted 0 emails.")
            
        logger.info("Confirmation email sent to %s for order #%d", customer_email, order_id)
        return f"Email sent to {customer_email} for order #{order_id}"

    except Exception as exc:
        logger.error("Failed to send email for order #%d: %s", order_id, exc)
        raise self.retry(exc=exc)



# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #

BATCH_SIZE = 500  
@shared_task(name="apps.orders.tasks.daily_sales_batch_processing")
@monitor_performance  
def daily_sales_batch_processing():
    
    try:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=1) # نطاق التقرير هو آخر 24 ساعة
        
        logger.info("Starting daily report generation for %s", start_date.date())

        product_csv = _build_inventory_csv()
        orders_csv, revenue, items_sold = _build_sales_csv(start_date, end_date)
        chart_png, chart_count = _build_top_products_chart(start_date, end_date)

        summary = (
            f"Daily Store Report\n"
            f"-------------------\n"
            f"Date   : {start_date.date()}\n"
            f"Revenue: ${revenue}\n"
            f"Units sold: {items_sold}\n"
            f"Products in stock: {Product.objects.count()}\n"
        )

        email = EmailMessage(
            subject=f"Daily Report — {start_date.date()}",
            body=summary,
            from_email=settings.EMAIL_HOST_USER,
            to=[settings.EMAIL_HOST_USER], 
        )
        email.attach('inventory_daily.csv', product_csv.getvalue(), 'text/csv')
        email.attach('sales_daily.csv', orders_csv.getvalue(), 'text/csv')
        email.attach('top_products_daily.png', chart_png.getvalue(), 'image/png')
        email.send()

        product_csv.close()
        orders_csv.close()
        chart_png.close()

        logger.info("Daily report sent successfully. Revenue: $%.2f", revenue)
        return f"Daily report sent. Revenue: ${revenue}"

    finally:
        cache.delete("daily_report_is_running")
        logger.info("Daily report lock released.")



# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #


@shared_task(name="apps.orders.tasks.generate_weekly_report")
@monitor_performance  
def generate_weekly_report():
    try:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)

        logger.info("Starting weekly report generation for period starting %s", start_date.date())

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

        product_csv.close()
        orders_csv.close()
        chart_png.close()

        return f"Weekly report sent. Top-{chart_count} products chart included."

    finally:
        cache.delete("weekly_report_is_running")
        logger.info("Weekly report lock released.")


# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #

@monitor_performance 
def _build_inventory_csv() -> io.StringIO:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['ID', 'Name', 'Stock', 'Price', 'Version', 'Created'])

    for product in Product.objects.all().order_by('id').iterator(chunk_size=BATCH_SIZE):
        writer.writerow([
            product.id, product.name, product.stock,
            product.price, product.version, product.created_at,
        ])
    return buf


# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #

@monitor_performance
def _build_sales_csv(start_date, end_date):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Order ID', 'Customer', 'Product', 'Qty', 'Status', 'Total', 'Date'])

    orders = (
        Order.objects
        .filter(created_at__range=(start_date, end_date))
        .prefetch_related('items__product')
        .order_by('id')
    )

    revenue = 0
    items_sold = 0
    for order in orders.iterator(chunk_size=BATCH_SIZE):
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

# ------------------------------------------------------------------ #
###################################                                 #
# ------------------------------------------------------------------ #

@monitor_performance  
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