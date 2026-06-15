from rest_framework import permissions

class IsAdminOrReadOnlyOrPurchase(permissions.BasePermission):
    def has_permission(self, request, view):
        if view.action in ['list', 'retrieve', 'trending', 'most_viewed']:
            return True 
            
        if view.action == 'purchase':
            return bool(request.user and request.user.is_authenticated)
            
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))