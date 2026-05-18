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
    def create(self, validated_data):
        products_data = validated_data.pop('products')  
        customer_name = self.context['request'].user.username
        order_price = validated_data.get('order_price')

        return OrderService.create_order_with_stock(
            customer_name,
            products_data,
            order_price
        )
    """
    ============================================================
    """ 

    def update(self, instance, validated_data):
        products_data = validated_data.pop('products', None)
        new_order_price = validated_data.get('order_price', instance.order_price)

        if products_data is not None:
            OrderService.update_order_items(
                order_id=instance.id, 
                customer_name=instance.customer_name,
                new_products_data=products_data, 
                new_order_price=new_order_price
            )
        
        instance.refresh_from_db()
        return instance
    """
    ============================================================
    """