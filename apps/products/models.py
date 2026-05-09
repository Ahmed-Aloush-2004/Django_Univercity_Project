from django.db import models
from django.core.cache import cache

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
   
    # حقل إضافي لتتبع النسخة من أجل التحكم في التزامن
    version = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    
    
    def save(self, *args, **kwargs):
        # مسح الكاش عند أي عملية حفظ
        cache.delete('all_products_list')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # مسح الكاش عند الحذف
        cache.delete('all_products_list')
        super().delete(*args, **kwargs)