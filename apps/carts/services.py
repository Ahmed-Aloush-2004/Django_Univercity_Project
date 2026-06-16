from .models import Cart, CartItem
from django.db import models, transaction, IntegrityError
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.core.cache import cache
import logging

logger = logging.getLogger("apps.carts")

class CartService:
    @staticmethod
    def get_or_create_cart(user):
        cart, created = Cart.objects.get_or_create(user=user)
        return cart
    """
    ============================================================
    """
    @staticmethod
    def add_to_cart(user, product_id, quantity=1):

        cart = CartService.get_or_create_cart(user)
        qty = int(quantity)
        if qty <= 0:
            logger.warning("Add-to-cart rejected for user=%s: non-positive quantity %s", user.username, quantity)
            raise ValidationError("الكمية يجب أن تكون أكبر من صفر")

        try:
            item = CartItem.objects.get(cart=cart, product_id=product_id)
            current_quantity = item.quantity
            new_quantity = current_quantity + qty
            
            updated = CartItem.objects.filter(
                id=item.id, 
                quantity=current_quantity
            ).update(quantity=new_quantity)
            if not updated:
                logger.warning(
                    "Optimistic lock conflict adding product=%s to cart for user=%s",
                    product_id, user.username,
                )
                raise ValidationError("فشلت العملية بسبب تحديث متزامن للسلة، يرجى إعادة المحاولة.")
            
            item.quantity = new_quantity
            logger.info(
                "Cart item updated: user=%s product=%s qty=%d -> %d",
                user.username, product_id, current_quantity, new_quantity,
            )
            return item

        except CartItem.DoesNotExist:
            try:
                item, created = CartItem.objects.get_or_create(
                    cart=cart, 
                    product_id=product_id, 
                    defaults={'quantity': qty}
                )
                if not created:
                    # إذا كانت موجودة فجأة بسبب خيط آخر، نقوم بتحديثها
                    CartItem.objects.filter(id=item.id).update(quantity=models.F('quantity') + qty)
                    item.refresh_from_db()
                logger.info("Product %s added to cart for user=%s (qty=%d)", product_id, user.username, qty)
                return item
            except IntegrityError:
                logger.error("IntegrityError adding product=%s to cart for user=%s", product_id, user.username)
                raise ValidationError("حدث تعارض أثناء إضافة المنتج، يرجى المحاولة مجدداً.")
            

    """
    ============================================================
    """
    @staticmethod
    @transaction.atomic
    def update_item_quantity(user, item_id, quantity):

        item = CartItem.objects.select_for_update().select_related('cart').filter(
            id=item_id,
            cart__user=user
        ).first()
        if not item:
            logger.warning("Cart-item update failed: item=%s not found for user=%s", item_id, user.username)
            raise ValidationError("هذا العنصر غير موجود أو لا تملك صلاحية تعديله.")
        qty = int(quantity)
        if qty <= 0:
            logger.info("Cart item %s removed for user=%s (quantity set to %s)", item_id, user.username, quantity)
            item.delete()
            return None
            
        item.quantity = qty
        item.save()
        logger.info("Cart item %s updated to qty=%d for user=%s", item_id, qty, user.username)
        return item