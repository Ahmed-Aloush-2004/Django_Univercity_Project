from .models import Cart, CartItem
from django.db import models, transaction, IntegrityError
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

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
            raise ValidationError("الكمية يجب أن تكون أكبر من صفر")

        try:
            item = CartItem.objects.get(cart=cart, product_id=product_id)
            current_quantity = item.quantity
            new_quantity = current_quantity + qty
            
            # القفل التفاؤلي
            updated = CartItem.objects.filter(
                id=item.id, 
                quantity=current_quantity
            ).update(quantity=new_quantity)
            if not updated:
                raise ValidationError("فشلت العملية بسبب تحديث متزامن للسلة، يرجى إعادة المحاولة.")
            
            item.quantity = new_quantity
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
                return item
            except IntegrityError:
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
            raise ValidationError("هذا العنصر غير موجود أو لا تملك صلاحية تعديله.")
        qty = int(quantity)
        if qty <= 0:
            item.delete()
            return None
            
        item.quantity = qty
        item.save()
        return item