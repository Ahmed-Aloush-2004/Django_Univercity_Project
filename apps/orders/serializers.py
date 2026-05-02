from rest_framework import serializers
from .models.order import Order, OrderItem
# from .models.order_item import OrderItem
from .services import OrderService

class OrderProductSerializer(serializers.ModelSerializer):
    # We point this to OrderItem so we can access both the product details AND quantity
    product_name = serializers.ReadOnlyField(source='product.name')
    product_id = serializers.ReadOnlyField(source='product.id')

    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    # This shows the data in GET requests
    items = OrderProductSerializer(many=True, read_only=True)
    
    # Add this line to enforce the choices defined in the Model
    # status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES, required=False)
    
    # This handles the incoming data in POST/PUT requests
    # We name it 'products' to match your Postman JSON key
    products = serializers.ListField(write_only=True)

    class Meta:
        model = Order
        fields = ['id', 'customer_name', 'items', 'products', 'order_price', 'status']
        read_only_fields = ['customer_name']


    def validate_products(self, value):
        """
        التحكم في السعة: منع معالجة قائمة منتجات ضخمة جداً في طلب واحد
        """
        MAX_ITEMS = 50 # يمكنك تغيير الرقم حسب سعة سيرفرك
        if len(value) > MAX_ITEMS:
            raise serializers.ValidationError(f"لا يمكن معالجة أكثر من {MAX_ITEMS} منتج في الطلب الواحد.")
        return value

    def create(self, validated_data):
        # Now we pop 'products' which contains your list from Postman
        products_data = validated_data.pop('products')  
        customer_name = validated_data.get('customer_name')
        order_price = validated_data.get('order_price')

        return OrderService.create_order_with_stock(
            customer_name,
            products_data,
            order_price
        )
        

    
    def update(self, instance, validated_data):
        # 1. Handle Product/Price updates if "products" is in the request
        products_data = validated_data.pop('products', None)
        new_order_price = validated_data.get('order_price', instance.order_price)
        customer_name = validated_data.get('customer_name')

        if products_data is not None:
            OrderService.update_order_items(
                order_id=instance.id, 
                customer_name=customer_name,
                new_products_data=products_data, 
                new_order_price=new_order_price
            )
        
        # Refresh the instance from DB to show updated values in response
        instance.refresh_from_db()
        return instance