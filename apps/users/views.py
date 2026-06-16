from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .services import AuthService
from .serializers import UserSerializer
import logging
from decimal import Decimal, InvalidOperation 

logger = logging.getLogger("apps.users")


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = AuthService.register_user(serializer.validated_data)
            tokens = AuthService.get_tokens_for_user(user)
            return Response({"user": UserSerializer(user).data, "tokens": tokens}, status=status.HTTP_201_CREATED)
        logger.warning("Registration validation failed: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from django.contrib.auth import get_user_model
User = get_user_model()

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        tokens = AuthService.login_user(email, password)
        
        if tokens:
            logger.info("User logged in: %s", email)
            
            user_obj = User.objects.get(email=email)
            
            user_data = UserSerializer(user_obj).context
            
            response_data = {
                "user": UserSerializer(user_obj).data,
                "tokens": tokens
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        logger.warning("Failed login attempt for email: %s", email)
        return Response({"error": "Invalid Credentials"}, status=status.HTTP_401_UNAUTHORIZED)
    
    
class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)
                
            AuthService.logout_user(refresh_token)
            return Response({"message": "Successfully logged out"}, status=status.HTTP_205_RESET_CONTENT)  
        except Exception as e:
            logger.error("Logout error: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class ResetPassword(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            new_password = request.data.get("new_password")
            if not new_password:
                return Response({"error": "New password is required"}, status=status.HTTP_400_BAD_REQUEST)

            AuthService.reset_password(request.user, new_password)
            logger.info("Password reset for user: %s", request.user.email)

            return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("Password reset error for user=%s: %s", request.user.email, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class DepositWalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        amount = request.data.get('amount')
        if amount is None:
            return Response({"error": " amount is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount_decimal = Decimal(str(amount))
            
            user = AuthService.deposit_wallet(request.user, amount_decimal)
            
            logger.info("User %s topped up wallet by %s", user.email, amount_decimal)
            return Response({
                "message": "The wallet has been successfully charged.",
                "current_balance": float(user.wallet_balance)
            }, status=status.HTTP_200_OK)
            
        except (ValueError, InvalidOperation):
            return Response({"error": "not valid"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Wallet deposit error for user=%s: %s", request.user.email, e, exc_info=True)
            return Response({"error": f"An error occurred while processing your request. Please try again later {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)