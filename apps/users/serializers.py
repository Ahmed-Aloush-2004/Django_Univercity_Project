from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password','wallet_balance']
        extra_kwargs = {
            'password': {'write_only': True},
            'wallet_balance':{'read_only':True}
        }