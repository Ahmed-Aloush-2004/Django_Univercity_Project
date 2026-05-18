from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from my_site.pagination import OrderPagination
from .models import Order
from .serializers import OrderSerializer
from .services import OrderService
from rest_framework.throttling import UserRateThrottle
from django.db import DatabaseError

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().prefetch_related('items__product')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OrderPagination
    throttle_classes = [UserRateThrottle]

    def create(self, request, *args, **kwargs):
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        products_data = serializer.validated_data.get('products_data') # تأكدي من اسم الحقل بالسيريالايزر عندك
        order_price = serializer.validated_data.get('order_price')
        customer_name = request.user.username  # حماية أمنية: جلب الاسم من التوكن وليس من الـ JSON المرسل
        
        try:
            order = OrderService.create_order_with_stock(
                customer_name=customer_name,
                products_data=products_data,
                order_price=order_price
            )
            response_serializer = self.get_serializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DatabaseError as e:
            return Response({"error": "فشلت العملية بسبب ضغط متزامن، يرجى المحاولة مجدداً."}, status=status.HTTP_409_CONFLICT)
        
    """
    ============================================================
    """

    @action(detail=False, methods=['get'])
    def get_by_user(self, request):
        customer_name = request.user.username
        orders = OrderService.get_user_orders(customer_name)
        
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
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DatabaseError as e:
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

        try:
            # 2. Only pass the status to the service
            order = OrderService.update_order_status(pk, new_status)
            
            # Return the updated order
            return Response(self.get_serializer(order).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)    
        except DatabaseError as e:
            return Response({"error": "خطأ في تحديث الحالة تزامناً مع عمليات أخرى."}, status=status.HTTP_409_CONFLICT)
    """
    ============================================================
    """
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