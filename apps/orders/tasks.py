from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
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