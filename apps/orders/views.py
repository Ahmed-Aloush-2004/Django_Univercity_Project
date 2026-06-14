from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from my_site.pagination import OrderPagination
from .models import Order
from .serializers import OrderSerializer
from .services import OrderService
from rest_framework.throttling import UserRateThrottle
from django.db import DatabaseError
import logging

logger = logging.getLogger("apps.orders")


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().prefetch_related('items__product')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OrderPagination
    throttle_classes = [UserRateThrottle]


    def list(self, request, *args, **kwargs):
        if not request.user.is_staff and not request.user.is_superuser:
            logger.warning(
                "Forbidden order-list attempt by user=%s", request.user.username
            )
            return Response(
                {"error": "ليس لديك الصلاحية لعرض كافة طلبات النظام."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        page = self.paginate_queryset(self.queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            logger.info("Order list returned for admin user=%s", request.user.username)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(self.queryset, many=True)
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

    @action(detail=False, methods=['get'])
    def get_by_user(self, request):
        customer_name = request.user.username
        orders = OrderService.get_user_orders(customer_name)
        logger.info("Fetching pending orders for user=%s", customer_name)

        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True) 
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)
    """
    ============================================================
    """

    @action(detail=True, methods=['patch'])
    def update_items(self, request, pk=None):
        customer_name = request.user.username
        new_products_data = request.data.get('products_data') or request.data.get('products')
        new_order_price = request.data.get('order_price')
        
        if not new_products_data or new_order_price is None:
            return Response({"error": "Products and order_price are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = OrderService.update_order_items(
                order_id=pk,
                customer_name=customer_name,
                new_products_data=new_products_data,
                new_order_price=new_order_price
            )
            return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)
        except ValueError as e:
            logger.warning("Order #%s items-update failed for user=%s: %s", pk, customer_name, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DatabaseError as e:
            logger.error("Order #%s items-update DB conflict for user=%s: %s", pk, customer_name, e)
            return Response({"error": "تعذر تعديل الطلب بسبب تعارض متزامن. أعد المحاولة."}, status=status.HTTP_409_CONFLICT)
    """
    ============================================================
    """
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        # 1. Use the serializer to validate that the status is one of the valid choices
        serializer = self.get_serializer(data=request.data, partial=True)
        
        # This will throw a 400 error if status is "fjkds23"
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data.get('status')
        
        if not new_status:
            return Response({"error": "Status field is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_staff and new_status != 'cancelled':
            logger.warning(
                "Forbidden status-update attempt by user=%s on order #%s to '%s'",
                request.user.username, pk, new_status,
            )
            return Response(
                {"error": "كمستخدم عادي، يمكنك فقط إلغاء الطلب (cancelled). الحالات الأخرى للمشرفين فقط."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            order = OrderService.update_order_status(pk, new_status)
            
            return Response(self.get_serializer(order).data)
        except ValueError as e:
            logger.warning("Order #%s status-update failed: %s", pk, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)    
        except DatabaseError as e:
            logger.error("Order #%s status-update DB conflict: %s", pk, e)
            return Response({"error": "خطأ في تحديث الحالة تزامناً مع عمليات أخرى."}, status=status.HTTP_409_CONFLICT)
    """
    ============================================================
    """

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Requirement 6c — Sales-stats dashboard (admin only).

        Returns total completed orders, total revenue, and average order
        value. The aggregation is cached by OrderService.get_sales_stats()
        and invalidated automatically whenever an order's status changes
        to/from 'completed'.
        """
        if not request.user.is_staff and not request.user.is_superuser:
            logger.warning("Forbidden sales-stats attempt by user=%s", request.user.username)
            return Response(
                {"error": "هذه البيانات متاحة للمشرفين فقط."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = OrderService.get_sales_stats()
        return Response(data)
    def update(self, request, *args, **kwargs):
        """تعطيل التعديل الشامل الافتراضي (PUT)"""
        return Response(
            {"error": "التعديل الشامل غير مسموح. يرجى استخدام نقاط النهاية المخصصة لتعديل المنتجات أو الحالة."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def partial_update(self, request, *args, **kwargs):
        """تعطيل التعديل الجزئي الافتراضي (PATCH العام) لفرض الـ actions المخصصة"""
        return Response(
            {"error": "يرجى استخدام /update_items/ أو /update_status/ للتعديل."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    

    def destroy(self, request, *args, **kwargs):
        """منع حذف الطلبات تماماً من قاعدة البيانات لحفظ السجلات المادية"""
        return Response(
            {"error": "لا يمكن حذف الطلبات بعد إنشائها، يمكنك إلغاؤها فقط عبر تغيير الحالة."}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )