from concurrent.futures import wait

from django.db.models import F
from django.db import transaction, DatabaseError
from .models import Product
import time


class ProductService:
    @staticmethod
    def get_all_products():
        return Product.objects.all()

    @staticmethod
    def create_product(data):
        return Product.objects.create(**data)

    # this is the Optimistic Locking implementation, but it has a problem that if there are many concurrent updates, it will cause many retries and can lead to performance issues. 
    # @staticmethod
    # def update_stock_safely(product_id, quantity, update_type='decrease'):
    #     """
    #     Optimistic Locking implementation.
    #     """

    #     product = Product.objects.get(id=product_id)
    #     current_version = product.version

    #     if update_type not in ['decrease', 'increase']:
    #         raise ValueError("نوع التحديث غير مسموح به") 

    #     # Calculate new stock value before updating
    #     if update_type == 'decrease':
    #         if product.stock < quantity:
    #             raise ValueError(f"المخزون غير كافٍ للمنتج: {product.name}")
    #         new_stock = product.stock - quantity
    #     else:
    #         new_stock = product.stock + quantity

    #     # # --- أضف هذا السطر مؤقتاً للاختبار ---
    #     # print(f"قيد المعالجة للإصدار: {current_version}... انتظر 10 ثوانٍ")
    #     # time.sleep(10)
        
        
    #     # Perform the update only if version matches
    #     updated_count = Product.objects.filter(
    #         id=product_id, 
    #         version=current_version
    #     ).update(
    #         stock=new_stock,
    #         version=current_version + 1
    #     )
    #     print('this is the update count : ',updated_count)

    #     if updated_count == 0:
    #         # This triggers the retry logic in the OrderService
    #         raise DatabaseError("Race condition detected: Product was modified by another user.")
        
    #     return True
    
    
    @staticmethod
    def update_stock_safely(product_id, quantity, update_type='decrease'):
        """
        Atomic Update implementation (The best for E-commerce stock).
        """

        if update_type not in ['decrease', 'increase']:
            raise ValueError("نوع التحديث غير مسموح به")

        # نجهز الاستعلام
        queryset = Product.objects.filter(id=product_id)

        if update_type == 'decrease':
            # الشرط الأهم: نقص المخزون فقط إذا كان أكبر من أو يساوي الكمية المطلوبة
            # هذا يمنع حدوث Race Condition ويضمن عدم وجود مخزون سالب
            queryset = queryset.filter(stock__gte=quantity)
            
            # التحديث الذري باستخدام F expression
            updated_count = queryset.update(stock=F('stock') - quantity)
        else:
            # في حالة الزيادة، لا نحتاج لشرط الفحص
            updated_count = queryset.update(stock=F('stock') + quantity)

        # التحقق مما إذا تم التحديث
        if updated_count == 0:
            # إذا كان الـ count صفر، فهذا يعني إما المنتج غير موجود 
            # أو أن المخزون غير كافٍ (في حالة الـ decrease)
            raise DatabaseError(f"فشلت العملية: المخزون غير كافٍ أو المنتج غير موجود (ID: {product_id})")

        return True
    
    