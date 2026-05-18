from django.contrib import admin
from .models import Product

# تسجيل مودل المنتجات لتظهر في لوحة تحكم الأدمن
admin.site.register(Product)