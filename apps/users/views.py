from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .services import AuthService
from .serializers import UserSerializer

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = AuthService.register_user(serializer.validated_data)
            tokens = AuthService.get_tokens_for_user(user)
            return Response({"user": UserSerializer(user).data, "tokens": tokens}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        tokens = AuthService.login_user(email, password)
        
        if tokens:
            return Response(tokens, status=status.HTTP_200_OK)
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
            # This will print the actual error (e.g., "Token is blacklisted") to your console
            print(f"Logout Error: {str(e)}") 
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class ResetPassword(APIView):
    # This view requires a valid Access Token in the header
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            new_password = request.data.get("new_password")
            if not new_password:
                return Response({"error": "New password is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Use the user attached to the token automatically
            AuthService.reset_password(request.user, new_password)

            return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)