from celery import shared_task
from django.core.mail import send_mail,EmailMessage
from django.conf import settings
import logging
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, F
from apps.orders.models import Order ,OrderItem
from apps.products.models import Product
import io
import csv
import matplotlib.pyplot as plt


logger = logging.getLogger(__name__)


@shared_task(name="apps.orders.tasks.daily_sales_chunk_processing")
def daily_sales_chunk_processing():

    today = timezone.now().date()
    logger.info(f"بدء جرد ومعالجة مبيعات يوم {today} على دفعات...")

    result = Order.objects.filter(
        created_at__date=today, 
        status='completed'
    ).aggregate(total_revenue=Sum('order_price'))

    total_daily_processed_revenue = result['total_revenue'] or 0
        
    logger.info(f"تم الانتهاء من الجرد اليومي. إجمالي مبيعات اليوم المحسوبة: {total_daily_processed_revenue}$")
    return f"Successfully processed daily sales for date {today}. Total: {total_daily_processed_revenue}$"
    
"""
============================================================
"""
@shared_task(name="apps.orders.tasks.generate_full_weekly_report")
def generate_full_weekly_report():

    print('this is the full report task')
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    product_output = _generate_inventory_csv()
    order_output, total_revenue, total_items_sold = _generate_sales_csv(start_date, end_date)
    img_buffer, top_products_count = _generate_top_products_chart(start_date, end_date)


    summary = f"""
    التقرير الأسبوعي المحدث للمتجر:
    -----------------------------------
    الفترة: من {start_date.date()} إلى {end_date.date()}
    إجمالي الأرباح (المكتملة): {total_revenue} $
    إجمالي عدد القطع المباعة: {total_items_sold}
    حالة المخزون: تم تضمين كافة المنتجات وعددها ({Product.objects.count()})
    -----------------------------------
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

    return f"Full Updated Report Sent for {top_products_count} top products."

"""
============================================================
"""

def _generate_inventory_csv():
    product_output = io.StringIO()
    product_writer = csv.writer(product_output)
    product_writer.writerow(['ID', 'Product Name', 'Current Stock', 'Price', 'Version', 'Created At'])
    
    all_products = Product.objects.all().order_by('id').iterator(chunk_size=500)
    for prod in all_products:
        product_writer.writerow([
            prod.id, prod.name, prod.stock, prod.price, prod.version, prod.created_at
        ])
    return product_output

"""
============================================================
"""

def _generate_sales_csv(start_date, end_date):
    order_output = io.StringIO()
    order_writer = csv.writer(order_output)
    order_writer.writerow(['Order ID', 'Customer', 'Product', 'Quantity', 'Status', 'Order Total Price', 'Date'])
    
    orders = Order.objects.filter(
        created_at__range=(start_date, end_date)
    ).prefetch_related('items__product').order_by('-id')
    
    total_revenue = 0
    total_items_sold = 0
    
    for order in orders:
        for item in order.items.all():
            order_writer.writerow([
                order.id, order.customer_name, item.product.name, 
                item.quantity, order.status, order.order_price, 
                order.created_at.strftime('%Y-%m-%d %H:%M')
            ])
            if order.status == 'completed':
                total_items_sold += item.quantity
        
        if order.status == 'completed':
            total_revenue += order.order_price
            
    return order_output, total_revenue, total_items_sold

"""
============================================================
"""
def _generate_top_products_chart(start_date, end_date):
   
    top_selling_items = (
        OrderItem.objects.filter(order__created_at__range=(start_date, end_date), order__status='completed')
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )
    
    names = [item['product__name'] for item in top_selling_items]
    qtys = [item['total_qty'] for item in top_selling_items]

    fig, ax = plt.subplots(figsize=(10, 6))

    plt.cla()
    plt.clf()
    
    fig = plt.figure(figsize=(10, 6))

    import matplotlib
    cmap = matplotlib.colormaps['tab10']
    colors = [cmap(i) for i in range(len(names))]
    bars = ax.bar(names, qtys, color=colors)
    
    ax.set_title('Top 5 Selling Products (Last 7 Days)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Product Name', fontsize=12)
    ax.set_ylabel('Quantity Sold', fontsize=12)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + 0.1, yval, ha='center', va='bottom', fontweight='bold')

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight')
   

    plt.close(fig)
    img_buffer.seek(0)
    
    return img_buffer, len(names)

