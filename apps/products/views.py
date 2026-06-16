from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import DatabaseError, transaction
from .models import Product
from .serializers import ProductSerializer
from .services import ProductService
from ..users.permissions import IsAdminOrReadOnlyOrPurchase
from my_site.core.pagination import ProductsPagination
from django.core.cache import cache 
import logging


logger = logging.getLogger("apps.products")

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('id')
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnlyOrPurchase]
    pagination_class = ProductsPagination
    logger.info("ProductViewSet initialized")
    def list(self, request, *args, **kwargs):
        import time
        
        page = self.paginate_queryset(self.queryset)
        if page is not None:
            cache_keys = [f"product:{p.id}" for p in page]
            cached_products_dict = cache.get_many(cache_keys) 
            
            paginated_products = []
            products_to_cache = {}

            for p in page:
                key = f"product:{p.id}"
                if key in cached_products_dict:
                    paginated_products.append(cached_products_dict[key])
                else:
                    p_data = ProductSerializer(p).data
                    paginated_products.append(p_data)
                    products_to_cache[key] = p_data
            
            if products_to_cache:
                cache.set_many(products_to_cache, timeout=900)
                
            logger.info("Returning paginated product list with distributed caching")
            return self.get_paginated_response(paginated_products)

        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    """
    =============================================================
    """
    def retrieve(self, request, *args, **kwargs):
        product_id = kwargs.get('pk')
        data = ProductService.get_product_by_id(product_id)

        if data is None:
            return Response(
                {"error": "product not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        print(f"Product retrieved: {data['name']} (ID: {product_id})")
        ProductService.track_product_view(product_id)
        return Response(data)
    """
    =============================================================
    """   
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = ProductService.create_product(serializer.validated_data)
        ProductService.invalidate_trending_cache() 
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)
    """
    =============================================================
    """
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        product_id = kwargs.get('pk')
        ProductService._invalidate(product_id)     
        ProductService.invalidate_trending_cache()
        return response
    """
    =============================================================
    """
    def destroy(self, request, *args, **kwargs):
        product_id = kwargs.get('pk')
        response = super().destroy(request, *args, **kwargs)
        ProductService._invalidate(product_id)      
        ProductService.invalidate_trending_cache()
        return response

    """
    =============================================================
    """

    @action(detail=False, methods=['get'])
    def trending(self, request):
        data = ProductService.get_trending_products()
        logger.info("Trending products endpoint called")
        return Response(data)

    """
    =============================================================
    """

    @action(detail=False, methods=['get'])
    def most_viewed(self, request):
        data = ProductService.get_most_viewed_products()
        logger.info("Most-viewed products endpoint called")
        return Response(data)

    """
    =============================================================
    """

   
        