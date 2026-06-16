from django.db import transaction, DatabaseError
from django.shortcuts import get_object_or_404
from django.db.models import F
from django.core.cache import cache
from apps.carts.models import Cart
from apps.products.models import Product
from apps.products.services import ProductService
from apps.users.models import User
from apps.orders.models import Order, OrderItem
from apps.common.tasks import send_order_confirmation_email
import logging
from apps.utils.decorators import monitor_performance
import time
logger = logging.getLogger("apps.orders")

SALES_STATS_CACHE_KEY = "orders:sales_stats"
SALES_STATS_CACHE_TTL = 300  

class OrderService:
    """
    ==========================حساب السعر الإجمالي==================================
    """
    @staticmethod
    def _calculate_total_price(products_data: list) -> float:
        ids = [item['id'] for item in products_data]
        products_map = {p.id: p for p in Product.objects.filter(id__in=ids)}

        total = 0
        for item in products_data:
            product = products_map.get(item['id'])
            if product is None:
                logger.warning("Order rejected: product ID %s does not exist.", item['id'])
                raise ValueError(f"Product with ID {item['id']} does not exist.")
            total += product.price * item['quantity']

        return total
    """
    ============================خصم الرصيد من المحفظة================================
    """ 

    @staticmethod
    def _deduct_wallet(user: User, expected_price: float, calculated_price: float) -> None:
        if float(expected_price) != float(calculated_price):
            logger.warning(
                "Price mismatch for user %s: expected=%.2f calculated=%.2f",
                user.username, float(expected_price), float(calculated_price),
            )
            raise ValueError(
                "Price mismatch: the submitted total does not match the server-calculated total."
            )

        rows_updated = (
            User.objects
            .filter(id=user.id, wallet_balance__gte=calculated_price)
            .update(wallet_balance=F('wallet_balance') - calculated_price)
        )

        if rows_updated == 0:
            current = User.objects.filter(id=user.id).values('wallet_balance').first()
            if current is None:
                logger.warning("Wallet deduction failed: user %s not found.", user.username)
                raise ValueError("User not found.")
            logger.warning(
                "Insufficient wallet balance for user %s: available=%.2f required=%.2f",
                user.username, current['wallet_balance'], float(calculated_price),
            )
            raise ValueError(
                f"Insufficient wallet balance. "
                f"Available: ${current['wallet_balance']:.2f}, "
                f"Required: ${calculated_price:.2f}."
            )

        user.wallet_balance = User.objects.filter(id=user.id).values_list('wallet_balance', flat=True).first()
        logger.info(
            "Wallet deducted for user %s: -%.2f (new balance: %.2f)",
            user.username, float(calculated_price), float(user.wallet_balance),
        )

    """
    ============================تعديل كمية منتج عند تعديل الطلب================================
    """

    @staticmethod
    def _adjust_item_stock(existing_item: OrderItem, new_qty: int) -> None:
        diff = new_qty - existing_item.quantity
        if diff > 0:
            ProductService.update_stock_Atomic(existing_item.product_id, diff, update_type='decrease')
        elif diff < 0:
            ProductService.update_stock_Atomic(existing_item.product_id, abs(diff), update_type='increase')
        existing_item.quantity = new_qty
        existing_item.save()
    """
    =============================إضافة منتج جديد للطلب===============================
    """
    @staticmethod
    def _add_item(order: Order, product: Product, qty: int) -> None:
        ProductService.update_stock_Atomic(product.id, qty, update_type='decrease')
        OrderItem.objects.create(order=order, product=product, quantity=qty)
    """
    =============================حذف منتج من الطلب===============================
    """
    @staticmethod
    def _remove_item(item: OrderItem) -> None:
        ProductService.update_stock_Atomic(item.product_id, item.quantity, update_type='increase')
        item.delete()
    """
    ============================جلب طلبات المستخدم المعلقة================================
    """
    @staticmethod
    def get_user_orders(username: str):
        return (
            Order.objects
            .filter(customer_name=username, status='pending')
            .order_by('-id')
            .prefetch_related('items__product')
        )
    """
    =============================إنشاء طلب جديد===============================
    """
    @staticmethod
    @monitor_performance
    def create_order_with_stock(customer_name: str, products_data: list, order_price: float, stock_strategy: str = 'pessimistic') -> Order:
        if stock_strategy not in ('atomic', 'optimistic', 'pessimistic'):
            raise ValueError("stock_strategy must be 'atomic', 'optimistic', or 'pessimistic'.")

        logger.info("Creating order for user=%s items=%d strategy=%s", customer_name, len(products_data), stock_strategy)

        # Redis lock to prevent double-clicking
        lock_key = f"checkout_lock_user_{customer_name}"

        with cache.lock(lock_key, timeout=30, blocking_timeout=10):
            
            sorted_items = sorted(products_data, key=lambda x: x['id'])
            product_ids = [item['id'] for item in sorted_items]

            MAX_RETRIES = 3
            RETRY_DELAY = 0.1  

            for attempt in range(MAX_RETRIES):
                try:
                    with transaction.atomic():
                        if stock_strategy == 'pessimistic':
                            products_inside_db = list(Product.objects.select_for_update().filter(id__in=product_ids).order_by('id'))
                            user = User.objects.select_for_update().filter(username=customer_name).first()
                        else:
                            user = User.objects.select_for_update().filter(username=customer_name).first()
                        if not user:
                            raise ValueError("User not found.")

                        total = OrderService._calculate_total_price(sorted_items)
                        OrderService._deduct_wallet(user, order_price, total)

                        order = Order.objects.create(customer_name=customer_name, order_price=total)

                        for item in sorted_items:
                            if stock_strategy == 'atomic':
                                success = ProductService.update_stock_Atomic(item['id'], item['quantity'], update_type='decrease')
                                if not success:
                                    raise ValueError(f"Product ID {item['id']} is out of stock or insufficient quantity.")
                                product = Product.objects.get(id=item['id'])

                            elif stock_strategy == 'optimistic':
                                ProductService.update_stock_optimistic(item['id'], item['quantity'])
                                product = Product.objects.get(id=item['id'])

                            else: 
                                product = ProductService.update_stock_pessimistic(item['id'], item['quantity'])

                            OrderItem.objects.create(order=order, product=product, quantity=item['quantity'])

                        Cart.objects.filter(user=user).delete()

                        if user.email:
                            transaction.on_commit(
                                lambda: send_order_confirmation_email.delay(
                                    order_id=order.id,
                                    customer_email=user.email,
                                    customer_name=user.username,
                                    total_price=float(order.order_price),
                                )
                            )
                        logger.info("Order #%d created successfully on attempt %d", order.id, attempt + 1)
                        return order 

                except (DatabaseError, ValueError) as e:
                    if isinstance(e, ValueError) and "out of stock" in str(e):
                        raise e
                    
                    logger.warning("Attempt %d failed due to concurrency/database conflict: %s. Retrying...", attempt + 1, e)
                    
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)  
                    else:
                        logger.error("All retries exhausted for user=%s. Order creation failed.", customer_name)
                        raise DatabaseError("The operation failed due to heavy concurrent server load. Please try again.")
                    
    """
    ============================تعديل محتويات طلب معلق================================
    """
    @staticmethod
    @monitor_performance
    def update_order_items(
        order_id: int,
        customer_name: str,
        new_products_data: list,
        new_order_price: float,
    ) -> Order:
        
        lock_key = f"order_update_lock_{order_id}"
        
        with cache.lock(lock_key, timeout=20, blocking_timeout=5):
            with transaction.atomic():
                
                order = get_object_or_404(Order.objects.select_for_update(), id=order_id)
                if order.status != 'pending':
                    raise ValueError("Only pending orders can be updated.")

                user = User.objects.select_for_update().filter(username=customer_name).first()
                if not user:
                    raise ValueError("User not found.")

                sorted_new = sorted(new_products_data, key=lambda x: x['id'])
                new_ids = {item['id'] for item in sorted_new}
                
                products_map = {p.id: p for p in Product.objects.filter(id__in=new_ids)}
                existing_map = {item.product_id: item for item in order.items.all()}
                
                total = 0

                for item_data in sorted_new:
                    p_id = item_data['id']
                    new_qty = item_data['quantity']
                    
                    product = products_map.get(p_id)
                    if not product:
                        raise ValueError(f"Product ID {p_id} not found.")

                    if p_id in existing_map:
                        OrderService._adjust_item_stock(existing_map[p_id], new_qty)
                    else:
                        OrderService._add_item(order, product, new_qty)
                        
                    total += product.price * new_qty

                for p_id in sorted(existing_map.keys()):
                    if p_id not in new_ids:
                        OrderService._remove_item(existing_map[p_id])

                if float(new_order_price) != float(total):
                    raise ValueError("Price mismatch with server calculated total.")

                OrderService._deduct_wallet(user, new_order_price, total)
                order.order_price = total
                order.save()
                logger.info("Order #%d updated successfully.", order.id)
                return order
    """
    ==========================تعديل حالة الطلب وإلغاءه ==================================
    """
    @staticmethod
    @monitor_performance
    def update_order_status(order_id: int, new_status: str) -> Order:
        lock_key = f"order_status_lock_{order_id}"
        
        with cache.lock(lock_key, timeout=15, blocking_timeout=5):
            with transaction.atomic():
                
                order = get_object_or_404(Order.objects.select_for_update(), id=order_id)
                
                valid = [choice[0] for choice in Order.STATUS_CHOICES]
                if new_status not in valid:
                    raise ValueError("Invalid status.")
                    
                if new_status == order.status:
                    return order

                old_status = order.status

                if new_status == 'cancelled' and old_status != 'cancelled':
                    for item in order.items.select_related('product').all():
                        ProductService.update_stock_Atomic(
                            item.product_id, item.quantity, update_type='increase'
                        )
                    
                    User.objects.filter(username=order.customer_name).update(
                        wallet_balance=F('wallet_balance') + order.order_price
                    )
                    logger.info("Refunded %.2f to user %s due to order cancellation.", float(order.order_price), order.customer_name)

                order.status = new_status
                order.save()

                if 'completed' in (old_status, new_status):
                    ProductService.invalidate_trending_cache()
                    cache.delete(SALES_STATS_CACHE_KEY)

                return order
    
    """
    ==========================لوحة الإحصائيات المالية==================================
    """
    @staticmethod
    def get_sales_stats():
        cached = cache.get(SALES_STATS_CACHE_KEY)
        if cached is not None:
            logger.info("Sales stats served from cache")
            return cached

        logger.info("Sales stats cache miss — recomputing aggregation")

        from django.db.models import Sum, Count, Avg

        stats = Order.objects.filter(status='completed').aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('order_price'),
            avg_order_value=Avg('order_price'),
        )

        data = {
            "total_completed_orders": stats["total_orders"] or 0,
            "total_revenue": float(stats["total_revenue"] or 0),
            "avg_order_value": float(stats["avg_order_value"] or 0),
        }

        cache.set(SALES_STATS_CACHE_KEY, data, SALES_STATS_CACHE_TTL)
        logger.info("Sales stats computed and cached: %s", data)
        return data
