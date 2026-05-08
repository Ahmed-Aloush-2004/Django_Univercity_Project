from django.urls import path
from .views import CartDetailView, AddToCartView, UpdateCartItemView

urlpatterns = [
    # لعرض محتويات السلة
    path('', CartDetailView.as_view(), name='cart-detail'),
    
    # لإضافة منتج جديد للسلة
    path('add/', AddToCartView.as_view(), name='cart-add'),
    
    # لتحديث كمية منتج معين أو حذفه باستخدام معرف العنصر (item_id)
    path('item/<int:item_id>/', UpdateCartItemView.as_view(), name='cart-update'),
]