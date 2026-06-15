from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import CartSerializer
from .services import CartService
from .models import Cart, CartItem
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger("apps.carts")



class CartDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart = Cart.objects.prefetch_related('items__product').filter(user=request.user).first()
        if not cart:
            cart = CartService.get_or_create_cart(request.user)
            cart._prefetched_objects_cache = {'items': CartItem.objects.none()}
            logger.info("Cart created for user=%s", request.user.username)
        serializer = CartSerializer(cart)
        logger.info("Cart fetched for user=%s", request.user.username)
        return Response(serializer.data)
    
"""
============================================================
"""

class AddToCartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        if not product_id:
            logger.warning("Add-to-cart rejected for user=%s: missing product_id", request.user.username)
            return Response({"error": "Product ID required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            CartService.add_to_cart(request.user, product_id, quantity)
            return Response({"message": "Item added to cart"}, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            logger.warning("Add-to-cart failed for user=%s: %s", request.user.username, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

"""
============================================================
"""
class UpdateCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, item_id):
        quantity = request.data.get('quantity')
        
        if quantity is None:
            logger.warning("Cart-item update rejected for user=%s: missing quantity", request.user.username)
            return Response({"error": "Quantity required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = CartService.update_item_quantity(request.user, item_id, quantity)
        except ValidationError as e:
            logger.warning("Cart-item update failed for user=%s: %s", request.user.username, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if result is None:
            return Response({"message": "Item removed from cart"}, status=status.HTTP_200_OK)
            
        return Response({"message": "Cart updated"}, status=status.HTTP_200_OK)
