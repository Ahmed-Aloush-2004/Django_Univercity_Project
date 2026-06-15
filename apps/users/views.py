from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .services import AuthService
from .serializers import UserSerializer
import logging

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
            
            # 🎯 1. جلب كائن المستخدم من قاعدة البيانات عبر الـ email
            user_obj = User.objects.get(email=email)
            
            # 🎯 2. تحويل بيانات المستخدم إلى JSON (ستتضمن المحفظة تلقائياً)
            user_data = UserSerializer(user_obj).context
            
            # 🎯 3. دمج التوكنات مع بيانات المستخدم والمحفظة في استجابة واحدة
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


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from decimal import Decimal, InvalidOperation 
import logging

logger = logging.getLogger("apps.users")

class DepositWalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        
        if amount is None:
            return Response({"error": "حقل amount مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            amount_decimal = Decimal(str(amount))
            
            user = AuthService.deposit_wallet(request.user, amount_decimal)
            
            logger.info("User %s topped up wallet by %s", user.email, amount_decimal)
            return Response({
                "message": "تم شحن المحفظة بنجاح.",
                "current_balance": float(user.wallet_balance)
            }, status=status.HTTP_200_OK)
            
        except (ValueError, InvalidOperation):
            return Response({"error": "يرجى إدخال مبلغ مالي صحيح (رقمي)."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Wallet deposit error for user=%s: %s", request.user.email, e, exc_info=True)
            return Response({"error": f"حدث خطأ داخلي: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)