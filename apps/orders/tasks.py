from celery import shared_task
from django.core.mail import send_mail,EmailMessage
from django.conf import settings
import logging
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, F
from .models.order import Order ,OrderItem
from apps.products.models import Product
import io
import csv
import matplotlib.pyplot as plt








logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
# @shared_task()
def send_order_confirmation_email(self, order_id, customer_email, customer_name, total_price):
    """
    مهمة خلفية لإرسال بريد تأكيد الطلب.
    استخدمنا bind=True لإتاحة إمكانية إعادة المحاولة في حال فشل سيرفر الإيميل.
    """
    subject = f'تأكيد الطلب رقم #{order_id}'
    message = f'أهلاً {customer_name}،\n\nتم استلام طلبك بنجاح!\nإجمالي المبلغ: {total_price}$\n\nشكرًا لتسوقك معنا.'
    email_from = settings.EMAIL_HOST_USER
    recipient_list = [customer_email]

    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        return f"Email sent to {customer_email} for order {order_id}"
    except Exception as exc:
        # في حال فشل الإرسال (مثلاً مشكلة في الشبكة)، يحاول مرة أخرى بعد 60 ثانية
        logger.error(f"Error sending email: {exc}")
        raise self.retry(exc=exc, countdown=60)
    
    




@shared_task(name="apps.orders.tasks.generate_full_weekly_report")
def generate_full_weekly_report():
    print('this is the full report task')
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    # --- 1. تقرير المنتجات (Inventory Report) ---
    product_output = io.StringIO()
    product_writer = csv.writer(product_output)
    product_writer.writerow(['ID', 'Product Name', 'Current Stock', 'Price', 'Version', 'Created At'])
    
    # استخدام iterator لتطبيق مبدأ Capacity Control
    all_products = Product.objects.all().iterator(chunk_size=500)
    for prod in all_products:
        product_writer.writerow([
            prod.id, prod.name, prod.stock, prod.price, prod.version, prod.created_at
        ])

    # --- 2. تقرير الطلبات التفصيلي (Detailed Sales Report) ---
    order_output = io.StringIO()
    order_writer = csv.writer(order_output)
    order_writer.writerow(['Order ID', 'Customer', 'Product', 'Quantity', 'Status', 'Order Total Price', 'Date'])
    
    # نستخدم prefetch_related لتحسين الأداء وتجنب N+1 query
    orders = Order.objects.filter(
        created_at__range=(start_date, end_date)
    ).prefetch_related('items__product').iterator(chunk_size=500)
    
    total_revenue = 0
    total_items_sold = 0
    
    for order in orders:
        for item in order.items.all():
            order_writer.writerow([
                order.id, 
                order.customer_name, 
                item.product.name, 
                item.quantity, 
                order.status,
                order.order_price, 
                order.created_at.strftime('%Y-%m-%d %H:%M')
            ])
            if order.status == 'completed':
                total_items_sold += item.quantity
        
        if order.status == 'completed':
            total_revenue += order.order_price

    # --- 3. الرسم البياني الملون (Enhanced Data Storytelling) ---
    top_selling_items = (
        OrderItem.objects.filter(order__created_at__range=(start_date, end_date), order__status='completed')
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )
    
    names = [item['product__name'] for item in top_selling_items]
    qtys = [item['total_qty'] for item in top_selling_items]

    plt.figure(figsize=(10, 6))
    
    # استخدام لوحة ألوان متنوعة (Tab10) ليعطي كل عمود لوناً مختلفاً تلقائياً
    colors = plt.cm.tab10.colors[:len(names)] 
    
    bars = plt.bar(names, qtys, color=colors)
    
    plt.title('Top 5 Selling Products (Last 7 Days)', fontsize=14, fontweight='bold')
    plt.xlabel('Product Name', fontsize=12)
    plt.ylabel('Quantity Sold', fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    # إضافة الأرقام فوق كل عمود لتسهيل القراءة السريعة
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + 0.1, yval, ha='center', va='bottom', fontweight='bold')

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight')
    plt.close()
    img_buffer.seek(0)

    # --- 4. إعداد وإرسال الإيميل ---
    summary = f"""
    التقرير الأسبوعي المحدث للمتجر:
    -----------------------------------
    الفترة: من {start_date.date()} إلى {end_date.date()}
    إجمالي الأرباح (المكتملة): {total_revenue} $
    إجمالي عدد القطع المباعة: {total_items_sold}
    حالة المخزون: تم تضمين كافة المنتجات وعددها ({Product.objects.count()})
    -----------------------------------
    تم توليد هذا التقرير آلياً عبر نظام معالجة البيانات في الخلفية (Batch Processing).
    """

    email = EmailMessage(
        subject=f'تقرير المبيعات والمخزون المحدث - {start_date.date()}',
        body=summary,
        from_email='ahmed09887766554@gmail.com',
        to=['ahmedalloushgpt@gmail.com'],
    )

    email.attach('inventory_status.csv', product_output.getvalue(), 'text/csv')
    email.attach('weekly_sales_details.csv', order_output.getvalue(), 'text/csv')
    email.attach('top_products_chart.png', img_buffer.getvalue(), 'image/png')
    
    email.send()

    return f"Full Updated Report Sent for {len(names)} top products."