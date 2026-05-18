from django.urls import path
from .views import CartDetailView, AddToCartView, UpdateCartItemView

urlpatterns = [
    path('', CartDetailView.as_view(), name='cart-detail'),
    path('add/', AddToCartView.as_view(), name='cart-add'),
    path('item/<int:item_id>/', UpdateCartItemView.as_view(), name='cart-update'),
]