from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from .models import User
import logging
from decimal import Decimal
from django.db.models import F
logger = logging.getLogger("apps.users")

class AuthService:
    @staticmethod
    def register_user(data):
        """Handle user registration with hashed password."""
        password = data.pop('password', None)
        user = User.objects.create_user(password=password, **data)
        logger.info(f"User registered successfully: {user.email}")
        return user

    @staticmethod
    def get_tokens_for_user(user):
        """Manually generate Access and Refresh tokens."""
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    @staticmethod
    def login_user(email, password):
        """Authenticate user and return tokens."""
        user = authenticate(email=email, password=password)
        if user:
            return AuthService.get_tokens_for_user(user)
        return None

    @staticmethod
    def logout_user(refresh_token):
        """Blacklist the refresh token to logout."""
        token = RefreshToken(refresh_token)
        user = token.user
        token.blacklist()
        logger.info(f"User logged out: {user.email}")

    @staticmethod
    def reset_password(user, new_password):
        """Update password safely."""
        user.set_password(new_password)
        user.save()
    
    @staticmethod
    def deposit_wallet(user, amount: Decimal):
        if amount <= 0:
            raise ValueError("يجب أن يكون مبلغ الشحن أكبر من الصفر.")
        
        User.objects.filter(id=user.id).update(wallet_balance=F('wallet_balance') + amount)
        
        user.refresh_from_db()
        return user