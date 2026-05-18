import time
from django.db import transaction, DatabaseError
from django.shortcuts import get_object_or_404

from apps.carts.models import Cart
from .models import Order, OrderItem
from apps.products.services import ProductService
from apps.products.models import Product
from apps.users.models import User
from my_site.tasks import send_order_confirmation_email 
from django.db.models import F


class OrderService:


    @staticmethod
    def get_user_orders(customer_name):
        """Retrieve all orders for a specific customer name."""
        return Order.objects.filter(customer_name=customer_name, status='pending').order_by('-id').prefetch_related('items__product')
    
    """
    ============================================================
    """
    @staticmethod
    def _calculate_total_price(products_data):

        product_ids = [item['id'] for item in products_data]
        products = Product.objects.filter(id__in=product_ids)
        
        products_map = {prod.id: prod for prod in products}
        total_price = 0
        
        for item in products_data:
            p_id = item['id']
            if p_id not in products_map:
                raise ValueError(f"المنتج ذو المعرف {p_id} غير موجود.")
            
            product = products_map[p_id]
            total_price += (product.price * item['quantity'])
            
        return total_price

    """
    ============================================================
    """
    @staticmethod
    def _adjust_product_stock(old_item, new_qty):
        """تعديل كمية منتج موجود مسبقاً"""
        diff = new_qty - old_item.quantity
        if diff > 0:
            ProductService.update_stock_Atomic(old_item.product_id, diff, update_type='decrease')
        elif diff < 0:
            ProductService.update_stock_Atomic(old_item.product_id, abs(diff), update_type='increase')
        
        old_item.quantity = new_qty
        old_item.save()
    """
    ============================================================
    """
    @staticmethod
    def _add_new_product_to_order(order, product, qty):
        """تابع مستقل: مخصص لإضافة منتج جديد تماماً للطلب وخصم مخزونه"""
        ProductService.update_stock_Atomic(product.id, qty, update_type='decrease')
        OrderItem.objects.create(order=order, product=product, quantity=qty)
    

    """
    ============================================================
    """
    @staticmethod
    def _deleted_item_stock(existing_item):
        """تابع مستقل: مخصص لإلغاء منتج تماماً وإعادة كميته بالكامل للمستودع"""
        ProductService.update_stock_Atomic(existing_item.product_id, existing_item.quantity, update_type='increase')
        existing_item.delete()
    """
    ============================================================
    """
    @staticmethod
    def _process_wallet_payment(user, new_order_price, total_calculated_price):
        """تابع مستقل: مخصص حصرياً للرقابة المالية وخصم الرصيد من المحفظة"""
        if float(new_order_price) != float(total_calculated_price):
            raise ValueError("السعر الإجمالي المقدم لا يتطابق مع السعر .")

        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        locked_user = User.objects.select_for_update().get(id=user.id)

        if locked_user.wallet_balance < total_calculated_price:
            raise ValueError("رصيد المحفظة غير كافٍ لتغطية التعديلات الجديدة.")

        locked_user.wallet_balance = F('wallet_balance') - total_calculated_price
        locked_user.save()
        
        locked_user.refresh_from_db()
        
        user.wallet_balance = locked_user.wallet_balance
        
    """
    ============================================================
    """
    @staticmethod
    @transaction.atomic
    def create_order_with_stock(customer_name, products_data, order_price, stock_strategy='pessimistic'):

        user = User.objects.select_for_update().filter(username=customer_name).first()
        if not user:
            raise ValueError("المستخدم غير موجود")
        
        sorted_products = sorted(products_data, key=lambda x: x['id'])

        total_calculated_price = OrderService._calculate_total_price(sorted_products)

        OrderService._process_wallet_payment(user, order_price, total_calculated_price)

        order = Order.objects.create(
            customer_name=customer_name,
            order_price=total_calculated_price)

        for item in sorted_products:
            # الفحص بناءً على الباراميتر القادم من الـ View
            if stock_strategy == 'atomic':
                ProductService.update_stock_Atomic(item['id'], item['quantity'], update_type='decrease')
                product = Product.objects.get(id=item['id'])
            elif stock_strategy == 'optimistic':
                ProductService.update_stock_optimistic(item['id'], item['quantity'])
                product = Product.objects.get(id=item['id'])
            else: # pessimistic
                product = ProductService.update_stock_pessimistic(item['id'], item['quantity'])
                
            OrderItem.objects.create(order=order, product=product, quantity=item['quantity'])

            
        Cart.objects.filter(user=user).delete()
        if user.email:
            transaction.on_commit(lambda: send_order_confirmation_email.delay(
                order_id=order.id,
                customer_email=user.email,
                customer_name=user.username,
                total_price=float(order.order_price)
            ))
            
        return order
    """
    ============================================================
    """
    @transaction.atomic
    def update_order_items(order_id, customer_name, new_products_data, new_order_price):
       
        order = get_object_or_404(Order, id=order_id)
        if order.status != 'pending':
            raise ValueError("Only pending orders can be updated.")

        user = User.objects.select_for_update().filter(username=customer_name).first()
        if not user:
            raise ValueError("المستخدم غير موجود.")
        
        #  ترتيب المنتجات لمنع  Deadlock 
        sorted_new_products = sorted(new_products_data, key=lambda x: x['id'])
        new_product_ids = [item['id'] for item in sorted_new_products]

        # بناء خارطة المنتجات القديمة للمقارنة
        existing_items = {item.product_id: item for item in order.items.all()}
        total_calculated_price = 0

        #اضافة او تعديل 
        for item_data in sorted_new_products:
            p_id = item_data['id']
            new_qty = item_data['quantity']
            product = get_object_or_404(Product, id=p_id)

            if p_id in existing_items:
                OrderService._adjust_product_stock(existing_items[p_id], new_qty)
            else:
                OrderService._add_new_product_to_order(order, product, new_qty)

            total_calculated_price += (product.price * new_qty)

        # حذف منيج من الطلب 
        for p_id in sorted(list(existing_items.keys())):
            existing_item = existing_items[p_id]
            if p_id not in new_product_ids:
                OrderService._deleted_item_stock(existing_item)

        OrderService._process_wallet_payment(user, new_order_price, total_calculated_price)
        order.order_price = total_calculated_price
        order.save()
                
        return order

    
    """
    ============================================================
    """
    @staticmethod
    @transaction.atomic
    def update_order_status(order_id, new_status):
        order = get_object_or_404(Order, id=order_id)
        
        valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

        if new_status == order.status: 
            return order

        if new_status == 'cancelled' and order.status != 'cancelled':
            for item in order.items.all():
                ProductService.update_stock_Atomic(item.product.id, item.quantity, update_type='increase')
        
        if order.status == 'cancelled' and new_status != 'cancelled':
            raise ValueError("Cannot move an order out of 'cancelled' status.")

        order.status = new_status
        order.save()
        return order
    
    """
    ============================================================
    """
    
    