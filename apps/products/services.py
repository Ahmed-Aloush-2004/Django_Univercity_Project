import time
import random
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import F
from apps.products.models import Product
from apps.products.serializers import ProductSerializer
import logging

PRODUCT_CACHE_TTL = 900  # 15 minutes

logger = logging.getLogger("apps.products")

class ProductService:
    """
    Handles all product business logic including three stock-update strategies:

    1. Atomic  — single UPDATE with a WHERE stock >= quantity guard.
                 No lock held; safe under high concurrency; best default.

    2. Optimistic — read version → compute new stock → UPDATE WHERE version=old.
                    Retries on collision (Race Condition proof without a DB-level lock).

    3. Pessimistic — SELECT … FOR UPDATE acquires a row-level lock before reading.
                     Guarantees no other transaction can change the row until commit.
    """

    # ------------------------------------------------------------------ #
    #  Cache helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cache_key(product_id: int) -> str:
        return f"product:{product_id}"

    @staticmethod
    def _invalidate(product_id: int) -> None:
        cache.delete(ProductService._cache_key(product_id))

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_product_by_id(product_id: int):
        """Return serialized product data; served from Redis when available."""
        key = ProductService._cache_key(product_id)
        logger.info(f"Fetching product: {product_id}")
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            product = Product.objects.get(id=product_id)
            data = ProductSerializer(product).data
            cache.set(key, data, PRODUCT_CACHE_TTL)
            logger.info(f"Product fetched and cached: {product_id}")
            return data
        except Product.DoesNotExist:
            logger.warning(f"Product not found: {product_id}")
            return None

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_product(data: dict) -> Product:
        product = Product.objects.create(**data)
        key = ProductService._cache_key(product.id)
        cache.set(key, ProductSerializer(product).data, PRODUCT_CACHE_TTL)
        logger.info(f"Product created and cached: {product.id}")
        return product

    # ------------------------------------------------------------------ #
    #  Strategy 1 — Atomic F-expression update (Race Condition proof)     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def update_stock_Atomic(product_id: int, quantity: int, update_type: str = 'decrease') -> bool:
        """
        Issues a single atomic SQL UPDATE.

        For decreases: WHERE stock >= quantity ensures we never go negative,
        and the conditional check happens inside the DB engine — not in Python —
        so concurrent requests cannot both read the same value and both succeed.

        Synchronization point: database-level atomic compare-and-update.
        No Python-level lock is needed.
        """
        if update_type not in ('decrease', 'increase'):
            raise ValueError("update_type must be 'decrease' or 'increase'")

        qs = Product.objects.filter(id=product_id)

        if update_type == 'decrease':
            # The stock__gte=quantity filter acts as the Race Condition guard.
            # If two threads both read stock=1 and try to decrement by 1,
            # only one UPDATE will match (the other sees stock=0 < quantity).
            qs = qs.filter(stock__gte=quantity)
            rows = qs.update(stock=F('stock') - quantity)
        else:
            rows = qs.update(stock=F('stock') + quantity)

        if rows == 0:
            raise DatabaseError(
                f"Atomic update failed: insufficient stock or product not found (ID: {product_id})"
            )

        ProductService._invalidate(product_id)
        logger.info(f"Stock updated for product: {product_id}")
        return True

    # ------------------------------------------------------------------ #
    #  Strategy 2 — Optimistic Locking (version field)                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def update_stock_optimistic(product_id: int, quantity: int, max_retries: int = 3) -> bool:
        """
        Optimistic Locking: read the current version, compute the new stock,
        then UPDATE only if the version has not changed since we read it.

        If another thread modified the row in the meantime (updated_count == 0),
        we wait a tiny random back-off and retry.

        Synchronization point: version field acts as a compare-and-swap token.
        """
        for attempt in range(max_retries):
            try:
                product = Product.objects.get(id=product_id)
                current_version = product.version

                if product.stock < quantity:
                    raise ValueError(f"Insufficient stock for product: {product.name}")

                new_stock = product.stock - quantity

                updated_count = Product.objects.filter(
                    id=product_id,
                    version=current_version          # only matches if nobody else changed it
                ).update(
                    stock=new_stock,
                    version=current_version + 1      # advance the version token
                )

                if updated_count > 0:
                    logger.info(f"Stock updated for product: {product_id}")
                    ProductService._invalidate(product_id)
                    return True

                # Another thread beat us — back off and retry
                time.sleep(random.uniform(0.01, 0.05))

            except Product.DoesNotExist:
                logger.warning(f"Product not found: {product_id}")
                raise DatabaseError("Product not found")

        raise DatabaseError(
            "Optimistic locking failed after max retries — high concurrent write pressure (Race Condition detected)."
        )

    # ------------------------------------------------------------------ #
    #  Strategy 3 — Pessimistic Locking (SELECT FOR UPDATE)               #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def update_stock_pessimistic(product_id: int, quantity: int) -> Product:
        """
        Pessimistic Locking: immediately acquires a row-level exclusive lock
        via SELECT … FOR UPDATE.

        No other transaction can read-for-update or write this row until the
        current transaction commits, which completely prevents Race Conditions
        at the cost of reduced concurrency.

        Synchronization point: PostgreSQL row-level lock held for the
        duration of the enclosing @transaction.atomic block.
        """
        try:
            product = Product.objects.select_for_update().get(id=product_id)

            if product.stock < quantity:
                raise ValueError(f"Insufficient stock for product: {product.name}")

            product.stock -= quantity
            product.save()

            logger.info(f"Stock updated for product: {product_id}")
            ProductService._invalidate(product_id)
            return product

        except Product.DoesNotExist:
            logger.warning(f"Product not found: {product_id}")
            raise DatabaseError("Product not found")
