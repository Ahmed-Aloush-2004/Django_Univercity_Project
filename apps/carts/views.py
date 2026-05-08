from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import CartSerializer
from .services import CartService
from .models import Cart

class CartDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # التحسين هنا: استخدام prefetch_related لجلب المنتجات في استعلام واحد فقط
        # هذا يمنع مشكلة الـ N+1 ويجعل استجابة الـ API سريعة جداً
        cart = Cart.objects.prefetch_related('items__product').filter(user=request.user).first()
        
        if not cart:
            cart = CartService.get_or_create_cart(request.user)
            
        serializer = CartSerializer(cart)
        return Response(serializer.data)

class AddToCartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        if not product_id:
            return Response({"error": "Product ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            CartService.add_to_cart(request.user, product_id, quantity)
            return Response({"message": "Item added to cart"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class UpdateCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, item_id):
        quantity = request.data.get('quantity')
        
        if quantity is None:
            return Response({"error": "Quantity required"}, status=status.HTTP_400_BAD_REQUEST)
        
        result = CartService.update_item_quantity(request.user, item_id, quantity)
        
        if result is None:
            return Response({"message": "Item removed from cart"}, status=status.HTTP_200_OK)
            
        return Response({"message": "Cart updated"}, status=status.HTTP_200_OK)