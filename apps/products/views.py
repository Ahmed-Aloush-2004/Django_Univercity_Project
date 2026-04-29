from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from .models import Product
from .serializers import ProductSerializer
from .services import ProductService

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    
    
    
    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        quantity = int(request.data.get('quantity', 1))
        
        try:
            # استخدام المعاملات لضمان مبدأ ACID (تنجح كلها أو تفشل كلها) 
            with transaction.atomic():
                ProductService.update_stock_safely(pk, quantity)
                # هنا يمكنك إضافة مهام أخرى مثل إنشاء الفاتورة
                return Response({"message": "تم الشراء بنجاح"}, status=status.HTTP_200_OK)
        
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "حدث تضارب في البيانات، حاول مرة أخرى"}, status=status.HTTP_409_CONFLICT)