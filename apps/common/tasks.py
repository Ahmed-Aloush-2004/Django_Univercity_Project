import io
import csv
import logging
import tempfile
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail, EmailMessage
from django.db.models import Sum
from django.conf import settings
from django.core.cache import cache
from celery import shared_task

# حل مشكلة الواجهة الرسومية لـ Matplotlib في السيرفرات الخلفية (Docker/Linux)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from apps.orders.models import Order, OrderItem
from apps.products.models import Product

logger = logging.getLogger(__name__)
BATCH_SIZE = 500  

# ================================================================== #
# 1. مهمة إرسال تأكيد الطلب فوراً للمشتري (مع ميزة إعادة المحاولة التلقائية)
# ================================================================== #
@shared_task(bind=True, max_retries=3, default_retry_delay=60, rate_limit='10/m')
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
            from_email=settings.EMAIL_HOST_USER, 
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


# ================================================================== #
# 2. مهمة الجرد اليومي السريع (حساب الأرباح مباشرة في الداتا بيز)
# ================================================================== #
@shared_task(name="apps.orders.tasks.daily_sales_chunk_processing")
def daily_sales_chunk_processing():
    today = timezone.now().date()
    logger.info(f"بدء جرد ومعالجة مبيعات يوم {today}...")

    # حساب الإجمالي بـ Query واحد سريع جداً داخل الداتا بيز
    result = Order.objects.filter(
        created_at__date=today, 
        status='completed'
    ).aggregate(total_revenue=Sum('order_price'))

    total_daily_processed_revenue = result['total_revenue'] or 0
    
    logger.info(f"تم الانتهاء من الجرد اليومي. إجمالي مبيعات اليوم المحسوبة: {total_daily_processed_revenue}$")
    return f"Successfully processed daily sales for date {today}. Total: {total_daily_processed_revenue}$"


# ================================================================== #
# 3. مهمة التقرير اليومي الشامل (إيميل + ملفات CSV مفرغة على القرص + رسم بياني)
# ================================================================== #
@shared_task(name="apps.orders.tasks.daily_sales_batch_processing")
def daily_sales_batch_processing():
    try:
        # قفل تفادي التشغيل المزدوج للمهة بنفس الوقت
        if not cache.add("daily_report_is_running", True, timeout=3600):
            logger.warning("Daily report task is already running. Skipping.")
            return "Skipped: Already running."

        end_date = timezone.now()
        start_date = end_date - timedelta(days=1)
        logger.info("Starting daily report generation for %s", start_date.date())

        # توليد الملفات بأمان على القرص وليس بالـ RAM
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', encoding='utf-8') as prod_file, \
             tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', encoding='utf-8') as sales_file:
            
            _build_inventory_csv(prod_file)
            revenue, items_sold = _build_sales_csv(start_date, end_date, sales_file)
            chart_png, chart_count = _build_top_products_chart(start_date, end_date, title="Top 5 Products — Daily Report")

            summary = (
                f"Daily Store Report\n"
                f"-------------------\n"
                f"Date   : {start_date.date()}\n"
                f"Revenue: ${revenue:,.2f}\n"
                f"Units sold: {items_sold}\n"
                f"Products in stock: {Product.objects.count()}\n"
            )

            email = EmailMessage(
                subject=f"Daily Report — {start_date.date()}",
                body=summary,
                from_email=settings.EMAIL_HOST_USER,
                to=[settings.EMAIL_HOST_USER], 
            )
            
            email.attach_file(prod_file.name, 'text/csv')
            email.attach_file(sales_file.name, 'text/csv')
            email.attach('top_products_daily.png', chart_png.getvalue(), 'image/png')
            email.send()
            chart_png.close()

        logger.info("Daily report sent successfully. Revenue: $%.2f", revenue)
        return f"Daily report sent. Revenue: ${revenue}"
    finally:
        cache.delete("daily_report_is_running")


# ================================================================== #
# 4. مهمة التقرير الأسبوعي الشامل (إيميل + ملفات CSV مفرغة على القرص + رسم بياني)
# ================================================================== #
@shared_task(name="apps.orders.tasks.generate_full_weekly_report")
def generate_weekly_report():
    try:
        if not cache.add("weekly_report_is_running", True, timeout=3600):
            logger.warning("Weekly report task is already running. Skipping.")
            return "Skipped: Already running."

        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        logger.info("Starting weekly report generation for period starting %s", start_date.date())

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', encoding='utf-8') as prod_file, \
             tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', encoding='utf-8') as sales_file:
            
            _build_inventory_csv(prod_file)
            revenue, items_sold = _build_sales_csv(start_date, end_date, sales_file)
            chart_png, chart_count = _build_top_products_chart(start_date, end_date, title="Top 5 Products — Weekly Report")

            summary = (
                f"Weekly Store Report\n"
                f"-------------------\n"
                f"Period : {start_date.date()} → {end_date.date()}\n"
                f"Revenue: ${revenue:,.2f}\n"
                f"Units sold: {items_sold}\n"
                f"Products in stock: {Product.objects.count()}\n"
            )

            email = EmailMessage(
                subject=f"Weekly report — {start_date.date()}",
                body=summary,
                from_email=settings.EMAIL_HOST_USER,
                to=[settings.EMAIL_HOST_USER], 
            )
            email.attach_file(prod_file.name, 'text/csv')
            email.attach_file(sales_file.name, 'text/csv')
            email.attach('top_products.png', chart_png.getvalue(), 'image/png')
            email.send()
            chart_png.close()

        return f"Weekly report sent. Top-{chart_count} products chart included."
    finally:
        cache.delete("weekly_report_is_running")


# ================================================================== #
# الدوال المساعدة المحسنة والمحمية (Helper Functions)
# ================================================================== #

def _build_inventory_csv(file_object):
    writer = csv.writer(file_object)
    writer.writerow(['ID', 'Name', 'Stock', 'Price', 'Version', 'Created'])

    # جلب قيم خام تفادياً لثقل كائنات الـ ORM
    products_data = (
        Product.objects.order_by('id')
        .values_list('id', 'name', 'stock', 'price', 'version', 'created_at')
        .iterator(chunk_size=BATCH_SIZE)
    )
    for row in products_data:
        writer.writerow(row)
    file_object.flush()


def _build_sales_csv(start_date, end_date, file_object):
    writer = csv.writer(file_object)
    writer.writerow(['Order ID', 'Customer', 'Product', 'Qty', 'Status', 'Total', 'Date'])

    # الاستعلام الصريح من الـ OrderItem لمنع الـ N+1 Queries تماماً
    sales_data = (
        OrderItem.objects.filter(order__created_at__range=(start_date, end_date))
        .select_related('order', 'product')
        .order_by('order_id')
        .values_list(
            'order_id', 'order__customer_name', 'product__name', 
            'quantity', 'order__status', 'order__order_price', 'order__created_at'
        )
        .iterator(chunk_size=BATCH_SIZE)
    )

    revenue = 0
    items_sold = 0
    last_processed_order_id = None

    for row in sales_data:
        order_id, customer, prod_name, qty, status, order_price, created_at = row
        
        writer.writerow([
            order_id, customer, prod_name, qty, status, order_price,
            created_at.strftime('%Y-%m-%d %H:%M')
        ])

        if status == 'completed':
            items_sold += qty
            # جمع قيمة الطلب مرة واحدة فقط لمنع التكرار بسبب الـ Items المتعددة
            if order_id != last_processed_order_id:
                revenue += order_price
                last_processed_order_id = order_id

    file_object.flush()
    return float(revenue), items_sold


def _build_top_products_chart(start_date, end_date, title):
    top = (
        OrderItem.objects
        .filter(order__created_at__range=(start_date, end_date), order__status='completed')
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )

    names = [row['product__name'] for row in top]
    quantities = [row['total_qty'] for row in top]

    # الأسلوب الصحيح للرسم كـ Object-Oriented لمنع تداخل أو مسح الصور
    fig, ax = plt.subplots(figsize=(10, 6))
    cmap = matplotlib.colormaps['tab10']
    colors = [cmap(i) for i in range(len(names))]
    bars = ax.bar(names, quantities, color=colors)

    ax.set_title(title, fontsize=14, fontweight='bold') 
    ax.set_xlabel('Product')
    ax.set_ylabel('Units Sold')
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.1, int(h),
                ha='center', va='bottom', fontweight='bold')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)  # إغلاق الـ Figure لتحرير الذاكرة فوراً
    buf.seek(0)

    return buf, len(names)