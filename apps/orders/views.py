from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from .models.order import Order
from .serializers import OrderSerializer
from .services import OrderService
from rest_framework.throttling import UserRateThrottle

class OrderPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().prefetch_related('items__product')
    serializer_class = OrderSerializer
    # Obligatory access token check
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OrderPagination
    # تحقيق متطلب التحكم في السعة (Capacity Control)
    # يمنع المستخدم من إغراق النظام بطلبات متوازية مفرطة
    throttle_classes = [UserRateThrottle]

    def perform_create(self, serializer):
        # Automatically take the name from the request.user
        # This replaces needing to send 'customer_name' in the JSON body
        serializer.save(customer_name=self.request.user.username)

    @action(detail=False, methods=['get'])
    def get_by_user(self, request):
        # Use the logged-in user's name instead of a query parameter for better security
        customer_name = request.user.username
        orders = OrderService.get_user_orders(customer_name)
        
        # Apply pagination to the action
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True) 
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)


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


