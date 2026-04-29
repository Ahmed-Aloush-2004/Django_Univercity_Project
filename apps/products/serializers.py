from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__' # أو حدد الحقول ['id', 'name', 'price']
        # fields = ['id', 'name', 'price','stock','description']