from django.db import transaction, DatabaseError
from django.shortcuts import get_object_or_404
from django.db.models import F

from apps.carts.models import Cart
from apps.products.models import Product
from apps.products.services import ProductService
from apps.users.models import User
from apps.orders.models import Order, OrderItem
# from mysite.tasks import send_order_confirmation_email
from my_site.tasks import send_order_confirmation_email

class OrderService:
    """
    Handles order lifecycle: creation, item updates, and status changes.

    Every multi-step operation (stock deduction + wallet deduction + order row
    insertion) runs inside a single @transaction.atomic block so that the whole
    compound action either commits or rolls back — satisfying the ACID requirement.

    Deadlock prevention: products are always processed in ascending ID order so
    that concurrent transactions acquire row locks in a consistent sequence.
    """

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _calculate_total_price(products_data: list) -> float:
        """
        Fetch all involved products in one query and calculate the total.
        Raises ValueError if any product ID does not exist.
        """
        ids = [item['id'] for item in products_data]
        products_map = {p.id: p for p in Product.objects.filter(id__in=ids)}

        total = 0
        for item in products_data:
            product = products_map.get(item['id'])
            if product is None:
                raise ValueError(f"Product with ID {item['id']} does not exist.")
            total += product.price * item['quantity']

        return total


    @staticmethod
    def _deduct_wallet(user: User, expected_price: float, calculated_price: float) -> None:
        """
        Validate price integrity then atomically deduct from the wallet.

        WHY NOT select_for_update() here?
        ----------------------------------
        select_for_update() acquires a row-level lock that is held for the
        entire surrounding @transaction.atomic block — which includes all the
        stock deduction steps. Under high load this means one slow stock update
        keeps the user row locked unnecessarily long, reducing throughput.

        BETTER APPROACH — atomic conditional UPDATE:
        --------------------------------------------
        We issue a single SQL UPDATE with a WHERE wallet_balance >= price guard,
        exactly like the Atomic stock strategy. The DB engine evaluates the
        condition and performs the deduction in one indivisible operation.

        If two orders from the same user arrive simultaneously:
          - Both read wallet_balance = 100 in Python.
          - Both issue:  UPDATE ... SET wallet_balance = wallet_balance - 80
                         WHERE id = X AND wallet_balance >= 80
          - The first UPDATE succeeds (rows_updated = 1).
          - By the time the second UPDATE runs, wallet_balance = 20 < 80,
            so the WHERE clause fails (rows_updated = 0) → ValueError raised.

        No lock held between the check and the write — the atomicity is
        guaranteed entirely by the DB engine's single-statement execution.

        Synchronization point: atomic SQL UPDATE with conditional WHERE clause.
        """
        if float(expected_price) != float(calculated_price):
            raise ValueError(
                "Price mismatch: the submitted total does not match the server-calculated total."
            )

        rows_updated = (
            User.objects
            .filter(id=user.id, wallet_balance__gte=calculated_price)
            .update(wallet_balance=F('wallet_balance') - calculated_price)
        )

        if rows_updated == 0:
            # Either the user doesn't exist or the balance was insufficient.
            # Re-read to give a precise error message (no lock needed here).
            current = User.objects.filter(id=user.id).values('wallet_balance').first()
            if current is None:
                raise ValueError("User not found.")
            raise ValueError(
                f"Insufficient wallet balance. "
                f"Available: ${current['wallet_balance']:.2f}, "
                f"Required: ${calculated_price:.2f}."
            )

        # Sync the in-memory object so the caller sees the updated balance
        user.wallet_balance = User.objects.filter(id=user.id).values_list('wallet_balance', flat=True).first()





    @staticmethod
    def _adjust_item_stock(existing_item: OrderItem, new_qty: int) -> None:
        """Reconcile stock for a product whose quantity changed in an order update."""
        diff = new_qty - existing_item.quantity
        if diff > 0:
            ProductService.update_stock_Atomic(existing_item.product_id, diff, update_type='decrease')
        elif diff < 0:
            ProductService.update_stock_Atomic(existing_item.product_id, abs(diff), update_type='increase')
        existing_item.quantity = new_qty
        existing_item.save()

    @staticmethod
    def _add_item(order: Order, product: Product, qty: int) -> None:
        """Deduct stock and create a new OrderItem row."""
        ProductService.update_stock_Atomic(product.id, qty, update_type='decrease')
        OrderItem.objects.create(order=order, product=product, quantity=qty)

    @staticmethod
    def _remove_item(item: OrderItem) -> None:
        """Return stock to inventory and delete the OrderItem row."""
        ProductService.update_stock_Atomic(item.product_id, item.quantity, update_type='increase')
        item.delete()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_user_orders(username: str):
        return (
            Order.objects
            .filter(customer_name=username, status='pending')
            .order_by('-id')
            .prefetch_related('items__product')
        )

    @staticmethod
    @transaction.atomic
    def create_order_with_stock(
        customer_name: str,
        products_data: list,
        order_price: float,
        stock_strategy: str = 'pessimistic',
    ) -> Order:
        """
        Create a new order as a single atomic transaction:
          1. Lock the user row (prevents concurrent wallet overdrafts).
          2. Calculate and validate the total price.
          3. Deduct wallet balance.
          4. Deduct stock for each product (strategy-dependent).
          5. Create Order + OrderItem rows.
          6. Clear the user's cart.
          7. Enqueue the confirmation email after commit.

        Products are sorted by ID before processing to guarantee a consistent
        lock-acquisition order and prevent deadlocks under concurrent load.

        Synchronization points:
          - User row locked via SELECT FOR UPDATE (wallet protection).
          - Stock locked via the chosen stock_strategy.
          - All DB writes wrapped in @transaction.atomic (ACID guarantee).
        """
        if stock_strategy not in ('atomic', 'optimistic', 'pessimistic'):
            raise ValueError("stock_strategy must be 'atomic', 'optimistic', or 'pessimistic'.")

        user = User.objects.select_for_update().filter(username=customer_name).first()
        if not user:
            raise ValueError("User not found.")

        # Sort by ID → consistent lock order → no deadlocks
        sorted_items = sorted(products_data, key=lambda x: x['id'])

        total = OrderService._calculate_total_price(sorted_items)
        OrderService._deduct_wallet(user, order_price, total)

        order = Order.objects.create(customer_name=customer_name, order_price=total)

        for item in sorted_items:
            if stock_strategy == 'atomic':
                ProductService.update_stock_Atomic(item['id'], item['quantity'], update_type='decrease')
                product = Product.objects.get(id=item['id'])
            elif stock_strategy == 'optimistic':
                ProductService.update_stock_optimistic(item['id'], item['quantity'])
                product = Product.objects.get(id=item['id'])
            else:  # pessimistic (default)
                product = ProductService.update_stock_pessimistic(item['id'], item['quantity'])

            OrderItem.objects.create(order=order, product=product, quantity=item['quantity'])

        Cart.objects.filter(user=user).delete()

        # on_commit ensures the email is only sent after the transaction commits,
        # so the worker will always find the order in the DB when it processes the task.
        if user.email:
            transaction.on_commit(
                lambda: send_order_confirmation_email.delay(
                    order_id=order.id,
                    customer_email=user.email,
                    customer_name=user.username,
                    total_price=float(order.order_price),
                )
            )

        return order

    @staticmethod
    @transaction.atomic
    def update_order_items(
        order_id: int,
        customer_name: str,
        new_products_data: list,
        new_order_price: float,
    ) -> Order:
        """
        Update an existing pending order's items atomically.

        Synchronization points:
          - User row locked via SELECT FOR UPDATE.
          - Products processed in ascending ID order (deadlock prevention).
          - Entire operation in @transaction.atomic.
        """
        order = get_object_or_404(Order, id=order_id)

        if order.status != 'pending':
            raise ValueError("Only pending orders can be updated.")

        user = User.objects.select_for_update().filter(username=customer_name).first()
        if not user:
            raise ValueError("User not found.")

        # Sort incoming items by ID for consistent lock ordering
        sorted_new = sorted(new_products_data, key=lambda x: x['id'])
        new_ids = {item['id'] for item in sorted_new}

        existing_map = {item.product_id: item for item in order.items.all()}
        total = 0

        # Add or update items
        for item_data in sorted_new:
            p_id = item_data['id']
            new_qty = item_data['quantity']
            product = get_object_or_404(Product, id=p_id)

            if p_id in existing_map:
                OrderService._adjust_item_stock(existing_map[p_id], new_qty)
            else:
                OrderService._add_item(order, product, new_qty)

            total += product.price * new_qty

        # Remove items no longer in the list (also sorted for consistent lock order)
        for p_id in sorted(existing_map.keys()):
            if p_id not in new_ids:
                OrderService._remove_item(existing_map[p_id])

        OrderService._deduct_wallet(user, new_order_price, total)
        order.order_price = total
        order.save()
        return order

    @staticmethod
    @transaction.atomic
    def update_order_status(order_id: int, new_status: str) -> Order:
        order = get_object_or_404(Order, id=order_id)

        valid = [choice[0] for choice in Order.STATUS_CHOICES]
        if new_status not in valid:
            raise ValueError(f"Invalid status. Valid choices: {', '.join(valid)}")

        if new_status == order.status:
            return order

        # When cancelling, restore all product stock
        if new_status == 'cancelled' and order.status != 'cancelled':
            for item in order.items.select_related('product').all():
                ProductService.update_stock_Atomic(
                    item.product_id, item.quantity, update_type='increase'
                )

        order.status = new_status
        order.save()
        return order
