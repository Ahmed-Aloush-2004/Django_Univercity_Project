from rest_framework import permissions

class IsAdminOrReadOnlyOrPurchase(permissions.BasePermission):
    def has_permission(self, request, view):
        #  إذا كان الطلب مجرد قراءة 
        if view.action in ['list', 'retrieve', 'trending', 'most_viewed']:
            return True 
            
        # 2. إذا كان الطلب عملية شراء
        if view.action == 'purchase':
            return bool(request.user and request.user.is_authenticated)
            
        # أي عملية ثانية (create, update, destroy)
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))