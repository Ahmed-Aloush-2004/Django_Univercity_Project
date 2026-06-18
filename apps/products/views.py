
import time
import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.core.cache import cache

from .models import Product
from .serializers import ProductSerializer
from .services import ProductService
from ..users.permissions import IsAdminOrReadOnlyOrPurchase
from my_site.core.pagination import ProductsPagination

logger = logging.getLogger("apps.products")

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('id')
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnlyOrPurchase]
    pagination_class = ProductsPagination
    logger.info("ProductViewSet initialized")

    def list(self, request, *args, **kwargs):
        # 1. جلب محددات الـ Pagination الديناميكية لإنشاء مفتاح فريد لكل صفحة
        page_num = request.query_params.get('page', 1)
        
        # إنشاء مفتاح كاش فريد مخصص لهذه الصفحة تحديداً لمنع التداخل بين الصفحات
        page_cache_key = f"products:list:page_{page_num}"
        page_lock_key = f"{page_cache_key}:lock"

        # 2. محاولة جلب الاستجابة بالكامل من الكاش (بما في ذلك روابط الصفحة التالية والسابقة والعدد الإجمالي)
        cached_response_data = cache.get(page_cache_key)
        if cached_response_data is not None:
            logger.info(f"Returning fully cached product list for page {page_num}")
            return Response(cached_response_data, status=status.HTTP_200_OK)

        logger.info(f"Cache miss for product list page {page_num}. Acquiring lock.")

        # 3. حماية الكاش من تدفق المستخدمين (Cache Stampede Protection):
        # طلب واحد فقط سيقوم بالبناء والحفظ، والـ 99 طلب الآخرين سينتظرون النتيجة.
        lock_acquired = cache.add(page_lock_key, "locked", timeout=15)

        if lock_acquired:
            try:
                # الريكويست الفائز يقوم بالعمليات الثقيلة ويضرب الداتابيز مرة واحدة للصفحة
                queryset = self.filter_queryset(self.get_queryset())
                page = self.paginate_queryset(queryset)
                
                if page is not None:
                    # جلب تفاصيل المنتجات الموزعة بالاعتماد على الكاش الداخلي لكل منتج لزيادة السرعة
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

                    # تحديث كاش المنتجات الفردية إذا كان هناك نواقص
                    if products_to_cache:
                        cache.set_many(products_to_cache, timeout=900)

                    # الحصول على الهيكل النهائي للاستجابة المصفحة (Pagination Response Object)
                    paginated_response = self.get_paginated_response(paginated_products)
                    
                    # حفظ بيانات الاستجابة بالكامل في كاش الصفحة لـ 15 دقيقة
                    cache.set(page_cache_key, paginated_response.data, timeout=900)
                    
                    logger.info(f"Computed, cached, and returning product list for page {page_num}")
                    return paginated_response

                # في حال عدم وجود Pagination (إجراء احتياطي)
                serializer = self.get_serializer(queryset, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)
            finally:
                # إزالة القفل لتمكين التحديثات القادمة بسلاسة
                cache.delete(page_lock_key)
        else:
            # الطلبات الأخرى المنتظرة تدخل في حلقة تفقد للكاش
            logger.info(f"Waiting for list page lock to release for page {page_num}")
            for _ in range(60):  # الانتظار بحد أقصى 6 ثوانٍ
                time.sleep(0.1)
                cached_response_data = cache.get(page_cache_key)
                if cached_response_data is not None:
                    return Response(cached_response_data, status=status.HTTP_200_OK)

            # حماية قصوى في حال تخطي وقت الانتظار: يتم تقديم الطلب مباشرة من الداتابيز دون التسبب في تعليق المستخدم
            logger.warning(f"Lock timeout for list page {page_num}, hitting DB directly.")
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    """ ============================================================= """
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

    """ ============================================================= """
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = ProductService.create_product(serializer.validated_data)
        ProductService.invalidate_trending_cache()
        
        # عند إنشاء منتج جديد، نقوم بمسح كاش صفحات القوائم لكي تظهر البيانات المحدثة للمستخدمين فوراً
        cache.delete_pattern("products:list:page_*")
        
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)

    """ ============================================================= """
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        product_id = kwargs.get('pk')
        ProductService._invalidate(product_id)
        ProductService.invalidate_trending_cache()
        
        # مسح كاش صفحات القوائم لضمان تحديث الأسعار أو البيانات المعدلة في القائمة
        cache.delete_pattern("products:list:page_*")
        return response

    """ ============================================================= """
    def destroy(self, request, *args, **kwargs):
        product_id = kwargs.get('pk')
        response = super().destroy(request, *args, **kwargs)
        ProductService._invalidate(product_id)
        ProductService.invalidate_trending_cache()
        
        # مسح كاش القوائم عند الحذف لمنع ظهور منتجات محذوفة بالصفحات
        cache.delete_pattern("products:list:page_*")
        return response

    """ ============================================================= """
    @action(detail=False, methods=['get'])
    def trending(self, request):
        data = ProductService.get_trending_products()
        logger.info("Trending products endpoint called")
        return Response(data)

    """ ============================================================= """
    @action(detail=False, methods=['get'])
    def most_viewed(self, request):
        data = ProductService.get_most_viewed_products()
        logger.info("Most-viewed products endpoint called")
        return Response(data)
        
        