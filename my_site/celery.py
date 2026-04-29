import os
from celery import Celery

# 1. تحديد إعدادات Django الافتراضية لبرنامج celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')

app = Celery('my_site')

# 2. استخدام سلسلة نصية هنا يعني أن العامل (worker) لا يضطر إلى تسلسل كائن الإعدادات
# 'CELERY' يعني أن جميع مفاتيح الإعدادات المتعلقة بـ celery يجب أن تبدأ بهذا الاسم
app.config_from_object('django.conf:settings', namespace='CELERY')

# 3. تحميل المهام (tasks) من جميع تطبيقات Django المسجلة تلقائياً
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')