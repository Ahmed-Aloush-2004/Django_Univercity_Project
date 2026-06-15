from rest_framework import serializers
from .models import Order, OrderItem
# from .models.order_item import OrderItem
from .services import OrderService

class OrderProductSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_id = serializers.ReadOnlyField(source='product.id')

    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'quantity']

"""
============================================================
"""
class OrderSerializer(serializers.ModelSerializer):
    items = OrderProductSerializer(many=True, read_only=True)
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES, required=False)
    products = serializers.ListField(write_only=True)

    class Meta:
        model = Order
        fields = ['id', 'customer_name', 'items', 'products', 'order_price', 'status']
        read_only_fields = ['customer_name']
    
    def validate_products(self, value):
        
        MAX_ITEMS = 50 
        if len(value) > MAX_ITEMS:
            raise serializers.ValidationError(f"لا يمكن معالجة أكثر من {MAX_ITEMS} منتج في الطلب الواحد.")
        return value
    """
    ============================================================
    """
class UpdateOrderItemsSerializer(serializers.Serializer):
    products = serializers.ListField(child=serializers.DictField(), required=True)
    order_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)

    def validate_products(self, value):
        if len(value) > 50:
            raise serializers.ValidationError("لا يمكن إضافة أكثر من 50 منتج.")
        return value