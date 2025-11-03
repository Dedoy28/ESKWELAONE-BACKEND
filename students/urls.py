# /backend/students/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views 

# --- ⭐️ IMPORT THE NEW VIEW FUNCTION ⭐️ ---
from .views import (
    StudentListCreateView,
    StudentRetrieveUpdateDestroyView,
    toggle_student_status, 
    AttendanceListCreateView,
    AttendanceRetrieveUpdateDestroyView,
    AttendanceReportView,
    AdminAttendanceReportView,
    EnrollmentListCreateView,
    EnrollmentRetrieveUpdateDestroyView,
    StudentGradesView,
    ClinicVisitListCreateView,
    ClinicVisitRetrieveUpdateDestroyView,
    BehaviorRecordListCreateView,
    BehaviorRecordRetrieveUpdateDestroyView,
    SectionListCreateView,
    SectionDetailView,
    SubjectListCreateView,
    SubjectDetailView,
    TeacherClassListCreateView,
    TeacherClassDetailView,
    TeacherDashboardView,
    TeacherClassRosterView,
    StudentSf10DetailView,
    GradeSettingsViewSet,
    enroll_all_students_in_class,
    ClassAttendanceView,
    dashboard_stats # ⭐️ --- 1. ADD THIS IMPORT --- ⭐️
)

router = DefaultRouter()
router.register(r'settings/grade-locks', GradeSettingsViewSet, basename='grade-locks')

urlpatterns = [
    path("", include(router.urls)),
    
    # ⭐️ --- 2. ADD THIS NEW DASHBOARD URL --- ⭐️
    # This creates the endpoint: /api/dashboard/stats/
    path("dashboard/stats/", views.dashboard_stats, name="dashboard-stats"),

    path("students/", StudentListCreateView.as_view(), name="student-list-create"),
    path("students/<int:pk>/", StudentRetrieveUpdateDestroyView.as_view(), name="student-detail"),
    
    path("students/<int:pk>/toggle-status/", views.toggle_student_status, name="student-toggle-status"),

    path("students/<str:student_id>/sf10/", StudentSf10DetailView.as_view(), name="student-sf10-detail"),
    path("attendance/", AttendanceListCreateView.as_view(), name="attendance-list-create"),
    path("attendance/<int:pk>/", AttendanceRetrieveUpdateDestroyView.as_view(), name="attendance-detail"),
    path("attendance/report/", AttendanceReportView.as_view(), name="attendance-report"),
    
    path("admin/attendance-report/", AdminAttendanceReportView.as_view(), name="admin-attendance-report"),

    path("enrollments/", EnrollmentListCreateView.as_view(), name="enrollment-list-create"),
    path("enrollments/<int:pk>/", EnrollmentRetrieveUpdateDestroyView.as_view(), name="enrollment-detail"),
    path("students/<int:pk>/grades/", StudentGradesView.as_view(), name="student-grades"),
    path("clinic-visits/", ClinicVisitListCreateView.as_view(), name="clinic-visit-list-create"),
    path("clinic-visits/<int:pk>/", ClinicVisitRetrieveUpdateDestroyView.as_view(), name="clinic-visit-detail"),
    path("behavior-records/", BehaviorRecordListCreateView.as_view(), name="behavior-record-list-create"),
    path("behavior-records/<int:pk>/", BehaviorRecordRetrieveUpdateDestroyView.as_view(), name="behavior-record-detail"),
    path("subjects/", SubjectListCreateView.as_view(), name="subject-list-create"),
    path("subjects/<int:pk>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("sections/", SectionListCreateView.as_view(), name="section-list-create"),
    path("sections/<int:pk>/", SectionDetailView.as_view(), name="section-detail"),
    path("teacher-classes/", TeacherClassListCreateView.as_view(), name="teacher-class-list-create"),
    path("teacher-classes/<int:pk>/", TeacherClassDetailView.as_view(), name="teacher-class-detail"),
    path("teacher/my-classes/", TeacherDashboardView.as_view(), name="teacher-dashboard"),
    path("teacher/class-roster/<int:class_id>/", TeacherClassRosterView.as_view(), name="teacher-class-roster"),

    path("teacher-classes/<int:class_pk>/enroll-all/", views.enroll_all_students_in_class, name="teacher-class-enroll-all"),
    
    # This creates the new API endpoint: /api/attendance/class/5/
    path("attendance/class/<int:class_pk>/", views.ClassAttendanceView.as_view(), name="class-attendance"),
]