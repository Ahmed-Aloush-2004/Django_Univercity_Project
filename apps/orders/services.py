import time
from django.db import transaction, DatabaseError
from django.shortcuts import get_object_or_404
from .models.order import Order, OrderItem
from apps.products.services import ProductService
from apps.products.models import Product
# from celery import shared_task




class OrderService:
    
    @staticmethod
    def get_user_orders(customer_name):
        """Retrieve all orders for a specific customer name."""
        return Order.objects.filter(customer_name=customer_name, status='pending').order_by('-id').prefetch_related('items__product')



    @staticmethod
    @transaction.atomic
    def update_order_items(order_id, new_products_data,new_order_price):
        """
        Updates products in an order:
        - Adjusts stock for modified quantities.
        - Removes products no longer in the list (restores stock).
        - Adds new products (deducts stock).
        """
        order = get_object_or_404(Order, id=order_id)
        
        if order.status != 'pending':
            raise ValueError("Only pending orders can be updated.")

        # 1. Map existing items for easy comparison {product_id: OrderItem_object}
        existing_items = {item.product_id: item for item in order.items.all()}
        new_product_ids = [item['id'] for item in new_products_data]
        
        total_calculated_price = 0

        # 2. Process: Add or Update
        for item_data in new_products_data:
            p_id = item_data['id']
            new_qty = item_data['quantity']
            product = get_object_or_404(Product, id=p_id)

            if p_id in existing_items:
                # RECONCILE QUANTITY
                old_item = existing_items[p_id]
                diff = new_qty - old_item.quantity
                
                if diff > 0: # Need more stock
                    ProductService.update_stock_safely(p_id, diff, update_type='decrease')
                elif diff < 0: # Return excess to stock
                    ProductService.update_stock_safely(p_id, abs(diff), update_type='increase')
                
                old_item.quantity = new_qty
                old_item.save()
            else:
                # ADD NEW PRODUCT
                ProductService.update_stock_safely(p_id, new_qty, update_type='decrease')
                OrderItem.objects.create(order=order, product=product, quantity=new_qty)
            
            total_calculated_price += (product.price * new_qty)

        # 3. Process: Delete (Items in DB but not in the new request)
        for p_id, existing_item in existing_items.items():
            if p_id not in new_product_ids:
                # Return all stock for this deleted item
                ProductService.update_stock_safely(p_id, existing_item.quantity, update_type='increase')
                existing_item.delete()

        if(new_order_price != total_calculated_price):
            raise ValueError("السعر الإجمالي المقدم لا يتطابق مع السعر المحسوب بناءً على المنتجات والكميات.")

        # 4. Update total price and finalize
        order.order_price = total_calculated_price
        order.save()
        return order

    # --- Previous methods below ---
    
    @staticmethod
    def create_order_with_stock(customer_name, products_data, order_price):
        
        return OrderService._execute_order_creation(customer_name, products_data, order_price)
                
       
       
        # # max_retries = 3
        # # for attempt in range(max_retries):
        #     try:
        #         print('this is the time Now!!!!! : ',time.time())
        #         return OrderService._execute_order_creation(customer_name, products_data, order_price)
        #     except DatabaseError:
        #             if attempt == max_retries - 1: raise 
        #             time.sleep(0.1)
                

    
    @staticmethod
    @transaction.atomic
    def _execute_order_creation(customer_name, products_data, order_price):
        # Create order with dummy price first
        order = Order.objects.create(customer_name=customer_name, order_price=0)
        total_calculated_price = 0

        for item in products_data:
            p_id = item['id']
            qty = item['quantity']
            product = get_object_or_404(Product, id=p_id)
            
            # Stock check and deduction
            ProductService.update_stock_safely(p_id, qty, update_type='decrease')
            OrderItem.objects.create(order=order, product=product, quantity=qty)
            total_calculated_price += (product.price * qty)

        # Integrity Check: Does the calculated price match the user's provided price?
        if float(order_price) != float(total_calculated_price):
            raise ValueError(f"Price mismatch! Calculated: {total_calculated_price}, Provided: {order_price}")

        order.order_price = total_calculated_price
        order.save()
        return order

    @staticmethod
    @transaction.atomic
    def update_order_status(order_id, new_status):
        order = get_object_or_404(Order, id=order_id)
        
        # Validation: Check if the new_status is in the allowed list
        valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

        if new_status == order.status: 
            return order

        # Handle stock restoration if cancelled
        if new_status == 'cancelled' and order.status != 'cancelled':
            for item in order.items.all():
                ProductService.update_stock_safely(item.product.id, item.quantity, update_type='increase')
        
        # Prevent re-activating a cancelled order if that's your business rule
        if order.status == 'cancelled' and new_status != 'cancelled':
            raise ValueError("Cannot move an order out of 'cancelled' status.")

        order.status = new_status
        order.save()
        return order
    
    
    
    
    