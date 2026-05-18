from rest_framework import serializers
from .models import Cart, CartItem
from ..products.serializers import ProductSerializer 
from django.db.models import Sum, F


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity']
"""
============================================================
"""

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total_price', 'updated_at']

    def get_total_price(self, obj):
        if hasattr(obj, 'annotated_total_price'):
            return obj.annotated_total_price or 0

        if obj.items.is_cached if hasattr(obj.items, 'is_cached') else True:
            return sum(item.quantity * item.product.price for item in obj.items.all())

        result = obj.items.aggregate(total=Sum(F('quantity') * F('product__price')))
        return result['total'] or 0