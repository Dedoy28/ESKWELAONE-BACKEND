# eskwelaone-backend/students/permissions.py (Updated)

from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow only 'admin' to use POST, PUT, PATCH, DELETE.
    Allows all authenticated users to use GET (read).
    """

    def has_permission(self, request, view):
        # 1. Allow read permissions (GET, HEAD, OPTIONS) for any authenticated user.
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # 2. Write permissions (POST, PUT, PATCH, DELETE) are ONLY allowed to 'admin'.
        # Assuming your custom User model has a 'role' field.
        if request.user and request.user.is_authenticated:
            # --- MODIFICATION: Check for strictly 'admin' role ---
            return request.user.role == 'admin'
        
        return False