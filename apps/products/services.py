import random
from django.core.cache import cache 
from .models import Product
from django.db.models import F
from django.db import DatabaseError,transaction
import time
from .serializers import ProductSerializer

class ProductService:
    
    @staticmethod
    def get_product_by_id(product_id):
        """
        جلب منتج واحد: إذا موجود بالكاش بنجيبه، إذا لاء بنقرأه من الداتابيز وبنكشه
        """
        cache_key = f"product:{product_id}"
        product = cache.get(cache_key)
        
        if product is None:
            try:
                product = Product.objects.get(id=product_id)
                product_data = ProductSerializer(product).data
                cache.set(cache_key, product_data, 900)
            except Product.DoesNotExist:
                return None
        return product
    """
    =============================================================
    """
    @staticmethod
    def create_product(data):
        product = Product.objects.create(**data)
        cache_key = f"product:{product.id}"
        cache.set(cache_key, product, 900)
        return product

    """
    =============================================================
    """
    @staticmethod
    def update_stock_Atomic(product_id, quantity, update_type='decrease'):
        """
        Atomic Update implementation 
        """

        if update_type not in ['decrease', 'increase']:
            raise ValueError("نوع التحديث غير مسموح به")

        queryset = Product.objects.filter(id=product_id)

        if update_type == 'decrease':
            queryset = queryset.filter(stock__gte=quantity)
            
            updated_count = queryset.update(stock=F('stock') - quantity)
        else:
            updated_count = queryset.update(stock=F('stock') + quantity)

        # التحقق مما إذا تم التحديث
        if updated_count == 0:
            raise DatabaseError(f"فشلت العملية: المخزون غير كافٍ أو المنتج غير موجود (ID: {product_id})")

        cache.delete(f"product:{product_id}")
        return True   
    
    """
    =============================================================
    """

    @staticmethod
    def update_stock_optimistic(product_id, quantity, max_retries=3):
        """
        تطبيق القفل التفاؤلي
        """
        for attempt in range(max_retries):
            try:
                product = Product.objects.get(id=product_id)
                current_version = product.version

                if product.stock < quantity:
                    raise ValueError(f"المخزون غير كافٍ للمنتج: {product.name}")

                new_stock = product.stock - quantity
                updated_count = Product.objects.filter(
                    id=product_id, 
                    version=current_version
                ).update(
                    stock=new_stock,
                    version=current_version + 1 
                )
                
                if updated_count > 0:
                    cache.delete(f"product:{product_id}")
                    return True
                
                time.sleep(random.uniform(0.01, 0.03))
            except Product.DoesNotExist:
                raise DatabaseError("المنتج غير موجود")
                
        raise DatabaseError("فشلت العملية بسبب ضغط التعديلات المتزامنة (Race Condition).")
        
    """
        =============================================================
    """    

    @staticmethod
    @transaction.atomic #القفل التشاؤمي 
    def update_stock_pessimistic(product_id, quantity):
        """
        تطبيق القفل التشاؤمي 
        """
        try:
            #  تقوم بقفل السطر في قاعدة البيانات فوراً وتمنع أي خيط آخر من تعديله
            product = Product.objects.select_for_update().get(id=product_id)
            
            if product.stock < quantity:
                raise ValueError(f"المخزون غير كافٍ للمنتج: {product.name}")
            
            product.stock -= quantity

            product.save()
            cache.delete(f"product:{product_id}")
            return product
        except Product.DoesNotExist:
            raise DatabaseError("المنتج غير موجود")
        
    """
    =============================================================
    """