from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import DatabaseError, transaction
from .models import Product
from .serializers import ProductSerializer
from .services import ProductService
from ..users.permissions import IsAdminOrReadOnlyOrPurchase
from my_site.pagination import ProductsPagination
from django.core.cache import cache 
import logging


logger = logging.getLogger("apps.products")



class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('id')
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnlyOrPurchase]
    pagination_class = ProductsPagination
    
    logger.info("ProductViewSet initialized")
    # logger.warning("Invalid password")
    # logger.error("Database error")
    
    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.queryset)
        if page is not None:
            cache_keys = [f"product:{p.id}" for p in page]
            
            #  جلب المنتجات المتاحة في الكاش بطلب واحد فقط (Bulk Get)
            cached_products_dict = cache.get_many(cache_keys)
            
            paginated_products = []
            products_to_cache = {}

            for p in page:
                key = f"product:{p.id}"
                # إذا المنتج موجود في الكاش نأخذه فوراً
                if key in cached_products_dict:
                    paginated_products.append(cached_products_dict[key])
                else:
                    p_data = ProductSerializer(p).data
                    paginated_products.append(p_data)
                    products_to_cache[key] = p_data
            
            # إذا كان هناك منتجات غير موجود بالكاش نرفعها للكاش دفعة واحدة (Bulk Set) لتوفير الوقت
            if products_to_cache:
                cache.set_many(products_to_cache, timeout=900)
                
            serializer = self.get_serializer(paginated_products, many=True)
            logger.info("Returning paginated product list with caching")
            return self.get_paginated_response(serializer.data)
        
        queryset = self.queryset[:100]
        serializer = self.get_serializer(queryset, many=True)
        logger.error("Pagination failed, returning first 100 products without pagination")
    
        return Response(
            {
                "message": "Pagination failed",
                "results": serializer.data
            }, 
            status=status.HTTP_200_OK
        )
    """
    =============================================================
    """

    def retrieve(self, request, *args, **kwargs):
        """
        Single product lookup.

        Served through ProductService.get_product_by_id(), which is a
        Redis cache-aside read (Requirement 6 — Distributed Caching):
        cache hit -> no DB query at all; cache miss -> one DB query,
        then the result is cached for PRODUCT_CACHE_TTL.

        Every successful lookup also increments that product's view
        counter (track_product_view), which feeds the /most_viewed/
        ranking below.
        """
        product_id = kwargs.get('pk')
        data = ProductService.get_product_by_id(product_id)

        if data is None:
            return Response(
                {"error": "المنتج غير موجود."},
                status=status.HTTP_404_NOT_FOUND,
            )
        print(f"Product retrieved: {data['name']} (ID: {product_id})")
        ProductService.track_product_view(product_id)
        return Response(data)

    """
    =============================================================
    """

    @action(detail=False, methods=['get'])
    def trending(self, request):
        """
        Requirement 6a — Trending / best-selling products.

        Returns the top products by units sold over the last 7 days
        (completed orders only). The ranking is computed once and cached
        in Redis for TRENDING_CACHE_TTL, so repeated hits to this endpoint
        don't repeatedly run the underlying GROUP BY / SUM query.
        """
        data = ProductService.get_trending_products()
        logger.info("Trending products endpoint called")
        return Response(data)

    """
    =============================================================
    """

    @action(detail=False, methods=['get'])
    def most_viewed(self, request):
        """
        Requirement 6b — Most-viewed products.

        Returns the top products by view count, where each view is
        tracked via an atomic Redis counter (see retrieve() above) and
        the ranked list itself is cached for MOST_VIEWED_CACHE_TTL.
        """
        data = ProductService.get_most_viewed_products()
        logger.info("Most-viewed products endpoint called")
        return Response(data)

    """
    =============================================================
    """

    # @action(detail=True, methods=['post'])
    # def purchase(self, request, pk=None):
    #     strategy = request.query_params.get('strategy', 'atomic')
    #     quantity = int(request.data.get('quantity', 1))
    #     try:
            
    #         if strategy == 'atomic':
    #             ProductService.update_stock_Atomic(pk, quantity)
                
    #         elif strategy == 'optimistic':
    #             ProductService.update_stock_optimistic(pk, quantity)
                
    #         elif strategy == 'pessimistic':
    #             ProductService.update_stock_pessimistic(pk, quantity)
                
    #         else:
    #             return Response({"error":"الاستراتيجية المطلوبة غير مدعومة." }, status=status.HTTP_400_BAD_REQUEST)
                
    #         return Response({"message": f"تم الشراء بنجاح باستخدام استراتيجية: {strategy}"}, status=status.HTTP_200_OK)
        
    #     except (ValueError, DatabaseError) as e:
    #         return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
        