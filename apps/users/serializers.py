from rest_framework import serializers
from .models import User
from decimal import Decimal

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password','wallet_balance']
        extra_kwargs = {
            'password': {'write_only': True},
            'wallet_balance':{'read_only':True}
        }

class DepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        min_value=Decimal('0.01'),
        error_messages={
            'required': 'حقل amount مطلوب.',
            'invalid': 'يرجى إدخال مبلغ مالي صحيح (رقمي).',
            'min_value': 'يجب أن يكون مبلغ الشحن أكبر من الصفر.'
        }
    )        