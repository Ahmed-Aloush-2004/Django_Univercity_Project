from rest_framework import serializers
from .models import Cart, CartItem
from ..products.serializers import ProductSerializer 

class CartItemSerializer(serializers.ModelSerializer):
    # عرض بيانات المنتج ككائن متداخل بناءً على ProductSerializer الخاص بك
    product = ProductSerializer(read_only=True)

    class Meta:
        model = CartItem
        # قمنا بإزالة total_price من هنا كما طلبت
        fields = ['id', 'product', 'quantity']

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    # تغيير المسمى من grand_total إلى total_price
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        # استخدام المسمى الجديد في الحقول
        fields = ['id', 'user', 'items', 'total_price', 'updated_at']

    def get_total_price(self, obj):
        # حساب الإجمالي الكلي لجميع العناصر في السلة
        return sum(item.quantity * item.product.price for item in obj.items.all())