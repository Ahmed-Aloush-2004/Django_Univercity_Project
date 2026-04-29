from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from .models import User

class AuthService:
    @staticmethod
    def register_user(data):
        """Handle user registration with hashed password."""
        data['password'] = make_password(data['password'])
        user = User.objects.create(**data)
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
        token.blacklist()

    @staticmethod
    def reset_password(user, new_password):
        """Update password safely."""
        user.set_password(new_password)
        user.save()