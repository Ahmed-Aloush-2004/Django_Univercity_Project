from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from my_site.core.pagination import OrderPagination
from .models import Order
from .serializers import OrderSerializer
from .services import OrderService
from rest_framework.throttling import UserRateThrottle
from django.db import DatabaseError
import logging

logger = logging.getLogger("apps.orders")

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OrderPagination
    throttle_classes = [UserRateThrottle]

    def get_serializer_class(self):
        if self.action == 'update_items' and self.request.method in ['PATCH', 'PUT']:
            from .serializers import UpdateOrderItemsSerializer
            return UpdateOrderItemsSerializer
        return super().get_serializer_class()
    
    def get_queryset(self):
        base_queryset = Order.objects.all().prefetch_related('items__product')
        if self.request.user.is_staff or self.request.user.is_superuser:
            return base_queryset
        return base_queryset.filter(customer_name=self.request.user.username)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        if request.user.is_staff or request.user.is_superuser:
            logger.info("Order list returned for admin user=%s", request.user.username)
        else:
            logger.info("Order list returned for customer user=%s", request.user.username)
            
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    """
    ============================================================
    """

    def create(self, request, *args, **kwargs):
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        products_data = serializer.validated_data.get('products') 
        order_price = serializer.validated_data.get('order_price')
        customer_name = request.user.username  
        strategy = request.query_params.get('strategy', 'pessimistic')
        if strategy not in ['atomic', 'optimistic', 'pessimistic']:
            logger.warning("Order create rejected: unsupported strategy '%s'", strategy)
            return Response(
                {"error": "الاستراتيجية المطلوبة غير مدعومة. اختر: atomic, optimistic, أو pessimistic."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            order = OrderService.create_order_with_stock(
                customer_name=customer_name,
                products_data=products_data,
                order_price=order_price,
                stock_strategy=strategy
            )
            response_serializer = self.get_serializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            logger.warning("Order create failed for user=%s: %s", customer_name, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DatabaseError as e:
            logger.error("Order create DB conflict for user=%s: %s", customer_name, e)
            return Response({"error": "فشلت العملية بسبب ضغط متزامن، يرجى المحاولة مجدداً."}, status=status.HTTP_409_CONFLICT)
        
    """
    ============================================================
    """
    @action(detail=True, methods=['patch'])
    def update_items(self, request, pk=None):
        customer_name = request.user.username
        order_obj = self.get_object()

        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        new_products_data = serializer.validated_data.get('products')
        new_order_price = serializer.validated_data.get('order_price')

        if not new_products_data or new_order_price is None:
            return Response({"error": "Products and order_price are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = OrderService.update_order_items(
                order_id=order_obj.id,
                customer_name=customer_name,
                new_products_data=new_products_data,
                new_order_price=new_order_price
            )
            return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DatabaseError as e:
            return Response({"error": "تعذر تعديل الطلب بسبب تعارض متزامن. أعد المحاولة."}, status=status.HTTP_409_CONFLICT)
    """
    ============================================================
    """
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order_obj = self.get_object()
        
        serializer = OrderSerializer(order_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get('status')

        if not new_status:
            return Response({"error": "Status field is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        if not request.user.is_staff and new_status != 'cancelled':
            return Response({"error": "كمستخدم عادي، يمكنك فقط إلغاء الطلب."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            order = OrderService.update_order_status(order_obj.id, new_status)
            return Response(OrderSerializer(order).data) # 🔥 استخدام السيريالايزر الصحيح للرد
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)    
        except DatabaseError as e:
            return Response({"error": "خطأ في تحديث الحالة تزامناً مع عمليات أخرى."}, status=status.HTTP_409_CONFLICT)
    """
    ============================================================
    """
    @action(detail=False, methods=['get'])
    def stats(self, request):
        if not request.user.is_staff and not request.user.is_superuser:
            logger.warning("Forbidden sales-stats attempt by user=%s", request.user.username)
            return Response(
                {"error": "هذه البيانات متاحة للمشرفين فقط."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = OrderService.get_sales_stats()
        return Response(data)
    
    """
    ============================================================
    """  

    def update(self, request, *args, **kwargs):
        return Response(
            {"error": "التعديل الشامل غير مسموح. يرجى استخدام نقاط النهاية المخصصة لتعديل المنتجات أو الحالة."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    def partial_update(self, request, *args, **kwargs):
        return Response(
            {"error": "يرجى استخدام /update_items/ أو /update_status/ للتعديل."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    def destroy(self, request, *args, **kwargs):
        return Response(
            {"error": "لا يمكن حذف الطلبات بعد إنشائها، يمكنك إلغاؤها فقط عبر تغيير الحالة."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )