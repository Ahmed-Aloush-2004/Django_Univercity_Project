from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import DatabaseError, transaction
from .models import Product
from .serializers import ProductSerializer
from .services import ProductService
from ..users.permissions import IsAdminOrReadOnlyOrPurchase
from ...my_site.pagination import ProductsPagination
from django.core.cache import cache 

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('id')
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnlyOrPurchase]
    pagination_class = ProductsPagination
    
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
            return self.get_paginated_response(serializer.data)
        
        queryset = self.queryset[:100]
        serializer = self.get_serializer(queryset, many=True)
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
    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        strategy = request.query_params.get('strategy', 'atomic')
        quantity = int(request.data.get('quantity', 1))
        try:
            
            if strategy == 'atomic':
                ProductService.update_stock_Atomic(pk, quantity)
                
            elif strategy == 'optimistic':
                ProductService.update_stock_optimistic(pk, quantity)
                
            elif strategy == 'pessimistic':
                ProductService.update_stock_pessimistic(pk, quantity)
                
            else:
                return Response({"error":"الاستراتيجية المطلوبة غير مدعومة." }, status=status.HTTP_400_BAD_REQUEST)
                
            return Response({"message": f"تم الشراء بنجاح باستخدام استراتيجية: {strategy}"}, status=status.HTTP_200_OK)
        
        except (ValueError, DatabaseError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
        