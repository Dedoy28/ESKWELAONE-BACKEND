# backend/urls.py

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
# 👇 --- Updated imports ---
from api.views import RegisterView, LoginView, TestView, UserListView # Added UserListView
# --- End updated imports ---
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

def home(request):
    return JsonResponse({
        "message": "Welcome to the API!",
        "available_endpoints": [
            "/api/register/",
            "/api/login/",
            "/api/token/",
            "/api/token/refresh/",
            "/api/test/",
            "/api/users/", # 👈 Added users endpoint
            "/api/students/",
            # Add other specific student endpoints from students.urls if needed
            "/api/enrollments/",
            "/api/sections/",
            "/api/subjects/",
            "/api/teacher-classes/",
            "/api/teacher/my-classes/",
            # End student endpoints
            "/api/attendance/",
            "/api/attendance/report/",
            # "/api/ocr/"  <-- REMOVED THIS LINE
        ]
    })

urlpatterns = [
    path("", home),
    path("admin/", admin.site.urls),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/register/", RegisterView.as_view(), name="register"),
    path("api/login/", LoginView.as_view(), name="login"),
    path("api/test/", TestView.as_view(), name="test"),
    # 👇 --- ADDED THIS LINE for the user list ---
    path("api/users/", UserListView.as_view(), name="user-list"),
    # --- END ADDED LINE ---
    path("api/", include("students.urls")), # Includes subjects, sections, classes, enrollments etc.
    # path("api/ocr/", include("ocrapp.urls")), <-- REMOVED THIS LINE
]