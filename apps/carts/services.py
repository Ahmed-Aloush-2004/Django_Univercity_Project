from .models import Cart, CartItem
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

class CartService:
    @staticmethod
    def get_or_create_cart(user):
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    @staticmethod
    def add_to_cart(user, product_id, quantity=1):
        cart = CartService.get_or_create_cart(user)
        # التأكد من أن الكمية رقم صحيح وموجب
        qty = int(quantity)
        if qty <= 0:
            raise ValidationError("الكمية يجب أن تكون أكبر من صفر")

        item, created = CartItem.objects.get_or_create(cart=cart, product_id=product_id)
        
        if not created:
            item.quantity += qty
        else:
            item.quantity = qty
        
        item.save()
        return item

    @staticmethod
    def update_item_quantity(user, item_id, quantity):
        # البحث عن العنصر والتأكد أنه ينتمي لسلة المستخدم الحالي
        item = get_object_or_404(CartItem, id=item_id, cart__user=user)
        
        qty = int(quantity)
        if qty <= 0:
            item.delete()
            return None
            
        item.quantity = qty
        item.save()
        return item