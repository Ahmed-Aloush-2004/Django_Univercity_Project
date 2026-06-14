import time
import random
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import F
from apps.products.models import Product
from apps.products.serializers import ProductSerializer
import logging

PRODUCT_CACHE_TTL = 900  # 15 minutes

# ------------------------------------------------------------------ #
#  Requirement 6 — Extra caching strategies                            #
#  (trending / most-viewed products + distributed view counters)      #
# ------------------------------------------------------------------ #
TRENDING_CACHE_KEY = "products:trending"
TRENDING_CACHE_TTL = 600          # 10 minutes — aggregation over OrderItem is expensive

MOST_VIEWED_CACHE_KEY = "products:most_viewed"
MOST_VIEWED_CACHE_TTL = 300       # 5 minutes

VIEW_COUNT_KEY_PREFIX = "product:views:"  # per-product Redis counter (no TTL)

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

    @staticmethod
    def invalidate_trending_cache() -> None:
        """
        Drops the cached "trending products" snapshot.

        Called by OrderService whenever an order's status changes to/from
        'completed', since that is the data the trending aggregation is
        based on. Without this, a newly-completed order would not be
        reflected in /trending/ until the TTL (10 min) expires.
        """
        cache.delete(TRENDING_CACHE_KEY)

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
    #  Requirement 6b — Most-viewed products (atomic Redis counters)       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def track_product_view(product_id: int) -> None:
        """
        Increments a per-product view counter directly in Redis.

        cache.incr() maps to Redis' INCR command, which is atomic at the
        Redis server level. Thousands of concurrent product-detail requests
        can call this at the same time and no increment will be lost —
        this is "Concurrent Access & Data Integrity" (Requirement 1)
        applied to an analytics counter instead of the database.
        """
        key = f"{VIEW_COUNT_KEY_PREFIX}{product_id}"
        try:
            cache.incr(key)
        except ValueError:
            # Key does not exist yet — initialize it.
            cache.set(key, 1, timeout=None)

    @staticmethod
    def get_most_viewed_products(limit: int = 10):
        """
        Returns the top-`limit` products ordered by view count.

        The per-product counters live in Redis with no expiry (so they
        keep accumulating), but the *ranked list* itself is cached for a
        short TTL because building it requires reading one counter per
        product — an O(n) Redis round trip that we don't want to repeat
        on every request to the homepage.
        """
        cached = cache.get(MOST_VIEWED_CACHE_KEY)
        logger.info(f"Checking cache for most-viewed products: {cached is not None}")
        if cached is not None:
            logger.info("Most-viewed products served from cache")
            return cached

        logger.info("Most-viewed products cache miss — recomputing ranking")

        ranked = []
        for product in Product.objects.all().only("id", "name", "price"):
            views = cache.get(f"{VIEW_COUNT_KEY_PREFIX}{product.id}") or 0
            if views:
                ranked.append((product, int(views)))

        ranked.sort(key=lambda pair: pair[1], reverse=True)

        data = [
            {
                "id": product.id,
                "name": product.name,
                "price": str(product.price),
                "views": views,
            }
            for product, views in ranked[:limit]
        ]

        cache.set(MOST_VIEWED_CACHE_KEY, data, MOST_VIEWED_CACHE_TTL)
        logger.info(f"Most-viewed products computed and cached ({len(data)} items)")
        return data

    # ------------------------------------------------------------------ #
    #  Requirement 6a — Trending / best-selling products                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_trending_products(limit: int = 10, days: int = 7):
        """
        Returns the top-`limit` best-selling products over the last `days`
        days, based on completed orders.

        Why cache this?
          The query joins OrderItem -> Order, filters by date range and
          status, then GROUP BY product with SUM(quantity) — a relatively
          heavy aggregation. Trending data does not need to be perfectly
          real-time, so we cache the computed ranking for TRENDING_CACHE_TTL
          and serve every request straight from Redis until it expires or
          OrderService invalidates it on order completion.
        """
        cached = cache.get(TRENDING_CACHE_KEY)
        if cached is not None:
            logger.info("Trending products served from cache")
            return cached

        logger.info("Trending products cache miss — recomputing ranking")

        # Local import avoids a circular import between products <-> orders
        from django.db.models import Sum
        from django.utils import timezone
        from datetime import timedelta
        from apps.orders.models import OrderItem

        since = timezone.now() - timedelta(days=days)

        top_items = (
            OrderItem.objects
            .filter(order__created_at__gte=since, order__status="completed")
            .values("product_id", "product__name", "product__price")
            .annotate(total_sold=Sum("quantity"))
            .order_by("-total_sold")[:limit]
        )

        data = [
            {
                "id": item["product_id"],
                "name": item["product__name"],
                "price": str(item["product__price"]),
                "total_sold": item["total_sold"],
            }
            for item in top_items
        ]

        cache.set(TRENDING_CACHE_KEY, data, TRENDING_CACHE_TTL)
        logger.info(f"Trending products computed and cached ({len(data)} items)")
        return data


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
