# backend/students/routing.py
from django.urls import re_path
from . import consumers



websocket_urlpatterns = [
    re_path(r'ws/students/?$', consumers.StudentListConsumer.as_asgi()),
    re_path(r'ws/students/(?P<student_id>\w+)/?$', consumers.StudentConsumer.as_asgi()),
    re_path(r'ws/attendance/?$', consumers.AttendanceConsumer.as_asgi()),
    re_path(r'ws/reports/?$', consumers.ReportConsumer.as_asgi()),
    re_path(r'ws/clinic/?$', consumers.ClinicConsumer.as_asgi()),
    re_path(r'ws/behavior/?$', consumers.BehaviorConsumer.as_asgi()),
    re_path(r'ws/dashboard-updates/?$', consumers.DashboardConsumer.as_asgi()),
]