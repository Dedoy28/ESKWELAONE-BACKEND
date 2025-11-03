# api/views.py

from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
# Import UserProfile from the students app
from students.models import UserProfile
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import UserSerializer 

# ⭐️ --- 1. ADD THIS NEW PERMISSION CLASS --- ⭐️
class IsAdminOrRegistrar(permissions.BasePermission):
    """
    Allows access only to Admin or Registrar users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.profile.role in ['admin', 'registrar']
        except UserProfile.DoesNotExist:
            return False

# =====================
# Register Endpoint
# =====================
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        username = request.data.get("username")
        password = request.data.get("password")
        role = request.data.get("role")

        if not email or not username or not password or not role:
            return Response({"detail": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST)

        if role not in dict(UserProfile.ROLE_CHOICES):
            return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({"detail": "Email already exists"}, status=status.HTTP_400_BAD_REQUEST)

        is_staff = role == "admin"
        try:
            user = User.objects.create_user(username=username, email=email, password=password, is_staff=is_staff)
            UserProfile.objects.create(user=user, role=role)
        except Exception as e:
            return Response({"detail": f"Error creating user: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"detail": f"User {username} with role {role} created successfully"}, status=status.HTTP_201_CREATED)


# =====================
# Login Endpoint (Corrected)
# =====================
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response({"detail": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"detail": "Invalid email or password"}, status=status.HTTP_401_UNAUTHORIZED)

        user_auth = authenticate(username=user.username, password=password)
        if not user_auth:
            return Response({"detail": "Invalid email or password"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            profile = UserProfile.objects.select_related('user').get(user=user_auth)
        except UserProfile.DoesNotExist:
            print(f"Error: UserProfile not found for user {user_auth.id}")
            return Response({"detail": "User profile data missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        refresh = RefreshToken.for_user(user_auth)
        response_data = {
            "id": user_auth.id,
            "name": user_auth.get_full_name() or user_auth.username,
            "email": user_auth.email,
            "role": profile.role,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
        print(f"Login successful for {profile.role} {user_auth.id}.")
        return Response(response_data, status=status.HTTP_200_OK)


# =====================
# Test Endpoint (Corrected)
# =====================
class TestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile_info = "No profile found."
        try:
            profile = UserProfile.objects.get(user=request.user)
            profile_info = f"Role: {profile.role}"
        except UserProfile.DoesNotExist:
            pass
        return Response({"message": f"Hello, {request.user.username}! You are authenticated. {profile_info}"})


# 👇 --- THIS IS THE FIX ---
# =====================
# User List Endpoint
# =====================
class UserListView(generics.ListAPIView):
    """
    Lists users, allows filtering by profile role.
    Example: /api/users/?profile__role=teacher
    """
    queryset = User.objects.all().select_related('profile').order_by('username')
    serializer_class = UserSerializer 
    
    # ⭐️ --- 2. USE THE NEW PERMISSION CLASS --- ⭐️
    permission_classes = [IsAdminOrRegistrar] # Changed from IsAdminUser
    
    filter_backends = [DjangoFilterBackend]
    # This allows filtering like ?profile__role=teacher
    filterset_fields = ['profile__role']