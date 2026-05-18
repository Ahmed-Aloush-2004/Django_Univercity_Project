from celery import shared_task
from django.core.mail import send_mail,EmailMessage
from django.conf import settings
import logging
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, F
from apps.orders.models import Order ,OrderItem
from apps.products.models import Product


logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_order_confirmation_email(self, order_id, customer_email, customer_name, total_price):
    
    subject = f'تأكيد الطلب رقم #{order_id}'
    message = f'أهلاً {customer_name}،\n\nتم استلام طلبك بنجاح!\nإجمالي المبلغ: {total_price}$\n\nشكرًا لتسوقك معنا.'
    email_from = settings.EMAIL_HOST_USER
    recipient_list = [customer_email]

    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        return f"Email sent to {customer_email} for order {order_id}"
    except Exception as exc:
        # محاولة مرة اخرى بعد 60 ثانية
        logger.error(f"Error sending email: {exc}")
        raise self.retry(exc=exc, countdown=60)
    
"""
============================================================
"""
