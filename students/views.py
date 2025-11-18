# backend/students/views.py
# ⭐️ FINAL VERSION: Includes Batch Promotion, Smart Attendance, and PDF Exports ⭐️

from rest_framework import generics, permissions, filters, status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.timezone import now 
from django.db.models import Q, Count, Prefetch, F
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
import logging 
import pandas as pd
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
import io

# --- PDF IMPORTS ---
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# --- MODEL IMPORTS ---
from .models import (
    Student,
    AttendanceRecord,
    ClinicVisit,
    BehaviorRecord,
    Section,
    UserProfile,
    Subject,
    TeacherClass,
    Enrollment,
    GradeSettings,
    SectionEnrollment 
)
# --- SERIALIZER IMPORTS ---
from .serializers import (
    StudentSerializer,
    AttendanceSerializer,
    AttendanceListSerializer,
    AdminAttendanceSerializer,
    ClinicVisitSerializer,
    BehaviorRecordSerializer,
    SectionSerializer,
    SubjectSerializer,
    TeacherClassSerializer,
    EnrollmentSerializer,
    StudentGradesSerializer,
    StudentSf10Serializer,
    GradeSettingsSerializer,
    StudentImportSerializer 
)

logger = logging.getLogger(__name__) 

# ===================================================================
# ⭐️ CUSTOM PERMISSIONS ⭐️
# ===================================================================

class IsAdminOrRegistrar(permissions.BasePermission):
    def has_permission(self, request, view):
        try:
            return request.user.profile.role in ['admin', 'registrar']
        except UserProfile.DoesNotExist:
            return False

class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        try:
            return request.user.profile.role == 'teacher'
        except UserProfile.DoesNotExist:
            return False

class IsAdminOrRegistrarOrTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.profile.role in ['admin', 'registrar', 'teacher']
        except UserProfile.DoesNotExist:
            return False

class IsAdminOrRegistrarOrTeacherOrGuidance(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.profile.role in ['admin', 'registrar', 'teacher', 'guidance_counselor', 'nurse']
        except UserProfile.DoesNotExist:
            return False

class IsEnrolledTeacherOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        try:
            if request.user.profile.role in ['admin', 'registrar']:
                return True
        except UserProfile.DoesNotExist:
            pass
        if isinstance(obj, Enrollment):
            return obj.teacher_class and obj.teacher_class.teacher == request.user
        if isinstance(obj, TeacherClass):
            return obj.teacher == request.user
        return False

class IsAssignedTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            if request.user.profile.role in ['admin', 'registrar']:
                return True
        except UserProfile.DoesNotExist:
            pass 
        class_pk = view.kwargs.get('class_pk')
        if not class_pk:
            return False
        try:
            teacher_class = TeacherClass.objects.get(pk=class_pk)
            return teacher_class.teacher == request.user
        except TeacherClass.DoesNotExist:
            return False


# ===================================================================
# ⭐️ STUDENT VIEWS ⭐️
# ===================================================================

class StudentListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'is_active': ['exact'],
        'gender': ['exact'],
        'section_enrollments__section__grade': ['exact'],
        'section_enrollments__section__name': ['exact'],
        'section_enrollments__school_year': ['exact'],
    }
    search_fields = ['lrn', 'first_name', 'last_name', 'email']
    ordering_fields = ["last_name", "first_name", "lrn"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        user = self.request.user
        queryset = Student.objects.all().prefetch_related(
            Prefetch(
                'section_enrollments',
                queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
                to_attr='active_enrollment' 
            )
        )
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrRegistrar()]
        return super().get_permissions()

class StudentRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Student.objects.all().prefetch_related(
        'section_enrollments__section', 
        'enrollments__teacher_class__subject', 
    )
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminOrRegistrar()]
        return super().get_permissions()


# ===================================================================
# ⭐️ ATTENDANCE VIEWS ⭐️
# ===================================================================

class AttendanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'status': ['exact'], 
        'quarter': ['exact'],
        'date': ['exact', 'gte', 'lte', 'range'],
        'student__section_enrollments__section__grade': ['exact'],
        'student__section_enrollments__section__name': ['exact'],
    }
    ordering_fields = ["date", "student__last_name"]
    ordering = ["-date"]

    def get_serializer_class(self):
        return AttendanceListSerializer if self.request.method == "GET" else AttendanceSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = AttendanceRecord.objects.all().select_related(
            "student", 
            "teacher_class__subject",
        ).prefetch_related(
            Prefetch(
                'student__section_enrollments',
                queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
                to_attr='current_enrollment_prefetch'
            )
        ).order_by("-date")

        try:
            profile = user.profile
            if profile.role in ['admin', 'registrar']:
                return queryset
            elif profile.role == 'teacher':
                return queryset.filter(teacher_class__teacher=user)
        except UserProfile.DoesNotExist:
            return AttendanceRecord.objects.none()
        
        return AttendanceRecord.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        teacher_class = serializer.validated_data.get('teacher_class')
        try:
            profile = user.profile
            if profile.role in ['admin', 'registrar']:
                serializer.save() 
                return
            if profile.role == 'teacher':
                if teacher_class and teacher_class.teacher == user:
                    serializer.save()
                    return
                else:
                    raise PermissionDenied("You can only create attendance records for your assigned classes.")
        except UserProfile.DoesNotExist:
            raise PermissionDenied("User profile not found.")
        raise PermissionDenied("You do not have permission to create this record.")

class AttendanceRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = AttendanceRecord.objects.all().select_related("student")
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]

# ===================================================================
# ⭐️ CLASS ATTENDANCE VIEW ⭐️
# ===================================================================
class ClassAttendanceView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAssignedTeacher]

    def get(self, request, class_pk):
        date_str = request.query_params.get('date')
        student_id_str = request.query_params.get('student')

        if student_id_str:
            try:
                student = get_object_or_404(Student, id=student_id_str)
                history_records = AttendanceRecord.objects.filter(
                    teacher_class_id=class_pk,
                    student=student
                ).order_by('-date')
                
                serializer = AttendanceListSerializer(history_records, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)
            
            except Student.DoesNotExist:
                 return Response(
                    {"error": f"Student with ID {student_id_str} not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not date_str:
            date_str = now().strftime('%Y-%m-%d')
        
        roster = Enrollment.objects.filter(
            teacher_class_id=class_pk,
            student__is_active=True
        ).select_related('student').order_by('student__last_name', 'student__first_name')
        
        existing_records = AttendanceRecord.objects.filter(
            teacher_class_id=class_pk,
            date=date_str
        )
        
        attendance_map = {record.student_id: {"id": record.id, "status": record.status, "updated_at": record.updated_at.isoformat()} for record in existing_records}
        
        roster_with_attendance = []
        for enrollment in roster:
            student = enrollment.student
            record_data = attendance_map.get(student.pk)
            roster_with_attendance.append({
                "student_id": student.pk,
                "name": f"{student.last_name}, {student.first_name}",
                "lrn": student.lrn,
                "id": record_data.get("id") if record_data else None,
                "status": record_data.get("status") if record_data else "Absent",
                "updated_at": record_data.get("updated_at") if record_data else None
            })
            
        return Response(roster_with_attendance, status=status.HTTP_200_OK)

    def post(self, request, class_pk):
        attendance_data = request.data.get('attendance_data')
        date_str = request.data.get('date')
        quarter = request.data.get('quarter')

        if not all([attendance_data, date_str, quarter]):
            return Response({"error": "Missing 'attendance_data', 'date', or 'quarter'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            teacher_class = TeacherClass.objects.get(pk=class_pk)
        except TeacherClass.DoesNotExist:
            return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

        saved_records_data = []
        for item in attendance_data:
            student_id = item.get('student_id')
            new_status = item.get('status')
            if not student_id or not new_status:
                continue 

            try:
                record, created = AttendanceRecord.objects.update_or_create(
                    teacher_class=teacher_class,
                    student_id=student_id,
                    date=date_str,
                    defaults={'status': new_status, 'quarter': quarter}
                )
                serializer = AttendanceSerializer(record)
                saved_records_data.append(serializer.data)
            except Exception as e:
                logger.error(f"Error saving attendance for student {student_id}: {e}")
                return Response({"error": f"Failed to save for student {student_id}: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        return Response({"status": "Attendance saved", "records": saved_records_data}, status=status.HTTP_201_CREATED)

# ===================================================================
# ⭐️ REPORT VIEWS ⭐️
# ===================================================================

class AdminAttendanceReportView(generics.ListAPIView):
    serializer_class = AdminAttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'date': ['exact', 'range', 'gte', 'lte'],
        'quarter': ['exact'],
        'status': ['exact'],
        'student__section_enrollments__section__grade': ['exact'],
        'student__section_enrollments__section__name': ['exact'],
        'teacher_class__subject__name': ['exact'],
    }
    search_fields = [
        'student__last_name', 'student__first_name', 'student__lrn',
        'teacher_class__subject__name', 'teacher_class__section__name',
        'teacher_class__teacher__username'
    ]
    ordering_fields = ['date', 'student__last_name', 'teacher_class__subject__name']
    ordering = ['-date']

    def get_queryset(self):
        return AttendanceRecord.objects.all().select_related(
            'student',
            'teacher_class__subject',
            'teacher_class__teacher'
        ).prefetch_related(
            Prefetch(
                'student__section_enrollments',
                queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
                to_attr='current_enrollment_prefetch'
            )
        )

class AttendanceReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]

    def get(self, request, *args, **kwargs):
        grade = request.query_params.get("grade")
        section_name = request.query_params.get("section")
        quarter = request.query_params.get("quarter")
        school_year = request.query_params.get("school_year")

        if not quarter or not school_year:
            return Response({"error": "Quarter and School Year are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quarter_int = int(quarter)
        except (ValueError, TypeError):
            return Response({"error": "Quarter must be a valid number."}, status=status.HTTP_400_BAD_REQUEST)

        enrollments_qs = SectionEnrollment.objects.filter(
            school_year=school_year, 
            student__is_active=True
        ).select_related('student', 'section').order_by(
            "student__gender", "student__last_name", "student__first_name"
        )
        
        if grade and grade != 'all':
            enrollments_qs = enrollments_qs.filter(section__grade=grade)
        if section_name and section_name != 'all':
            enrollments_qs = enrollments_qs.filter(section__name__iexact=section_name)

        student_ids = list(enrollments_qs.values_list('student_id', flat=True))

        records = AttendanceRecord.objects.filter(
            student_id__in=student_ids,
            quarter=quarter_int,
            teacher_class__academic_year=school_year 
        ).select_related("student")

        att_map = {}
        for r in records:
            sid = r.student_id
            date_str = str(r.date)
            att_map.setdefault(sid, {})[date_str] = r.status

        data = []
        for enrollment in enrollments_qs:
            s = enrollment.student
            student_att = att_map.get(s.id, {})
            
            present_count = sum(1 for v in student_att.values() if v == "Present")
            absent_count = sum(1 for v in student_att.values() if v == "Absent")
            late_count = sum(1 for v in student_att.values() if v == "Late")
            excused_count = sum(1 for v in student_att.values() if v == "Excused")
            total_days = len(student_att)

            row = {
                "student_pk": s.pk, 
                "student_id": s.lrn, 
                "name": f"{s.last_name}, {s.first_name}", "gender": s.gender,
                "grade": enrollment.section.grade, 
                "section": enrollment.section.name, 
                "attendance": student_att,
                "present_count": present_count,
                "absent_count": absent_count,
                "late_count": late_count,
                "excused_count": excused_count,
                "total_days": total_days,
            }
            data.append(row)

        return Response({"school_year": school_year, "quarter": quarter, "students": data})

# ===================================================================
# ⭐️ GRADE/ENROLLMENT VIEWS ⭐️
# ===================================================================

class EnrollmentListCreateView(generics.ListCreateAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = [
        "student", "teacher_class", "teacher_class__academic_year",
        "teacher_class__subject", "teacher_class__section",
        "teacher_class__section__grade" 
    ]
    search_fields = ["student__lrn", "student__first_name", "student__last_name", "teacher_class__subject__name"]
    ordering_fields = ["teacher_class__academic_year", "teacher_class__subject__name", "student__last_name"]
    ordering = ["student__last_name", "teacher_class__subject__name"]

    def get_queryset(self):
        user = self.request.user
        queryset = Enrollment.objects.all().select_related(
            "student", "teacher_class__subject",
            "teacher_class__teacher", "teacher_class__section"
        )
        try:
            profile = user.profile
            if profile.role in ['admin', 'registrar']: return queryset
            elif profile.role == 'teacher': return queryset.filter(teacher_class__teacher=user)
        except UserProfile.DoesNotExist: pass
        return Enrollment.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        teacher_class = serializer.validated_data.get('teacher_class')
        try:
            profile = user.profile
            if profile.role in ['admin', 'registrar']:
                serializer.save()
                return
            elif profile.role == 'teacher':
                if teacher_class and teacher_class.teacher == user:
                    serializer.save()
                    return
                else:
                    raise PermissionDenied("You can only create enrollments for your assigned classes.")
        except UserProfile.DoesNotExist:
            raise PermissionDenied("User profile not found.")
        raise PermissionDenied("You do not have permission to create this enrollment.")

class EnrollmentRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Enrollment.objects.all().select_related("student", "teacher_class__subject", "teacher_class__teacher", "teacher_class__section")
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnrolledTeacherOrAdmin]

    def _check_finalized_and_lock_status(self, instance, request_data):
        user = self.request.user
        is_admin_or_registrar = False
        try:
            if user.profile.role in ['admin', 'registrar']:
                is_admin_or_registrar = True
        except UserProfile.DoesNotExist:
            pass
        if instance.is_finalized and not is_admin_or_registrar:
            raise PermissionDenied("Cannot modify or delete a finalized grade record.")
        if not is_admin_or_registrar:
            try:
                global_locks = GradeSettings.objects.first() 
                if not global_locks:
                    raise PermissionDenied("Grade settings not configured. Please contact the administrator.")
                quarter_lock_map = {
                    'q1': global_locks.q1_open,
                    'q2': global_locks.q2_open,
                    'q3': global_locks.q3_open,
                    'q4': global_locks.q4_open,
                }
                for field, is_open in quarter_lock_map.items():
                    if field in request_data and not is_open:
                        raise PermissionDenied(f"Quarter {field.upper()} is currently locked by the administrator.")
            except Exception as e:
                raise PermissionDenied(str(e))

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        self._check_finalized_and_lock_status(instance, request.data) 
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        updated_instance = serializer.save() 
        
        if getattr(updated_instance, '_prefetched_objects_cache', None):
            updated_instance._prefetched_objects_cache = {}

        return_serializer = self.get_serializer(updated_instance)
        return Response(return_serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_finalized:
            is_admin_or_registrar = False
            try:
                is_admin_or_registrar = self.request.user.profile.role in ['admin', 'registrar']
            except UserProfile.DoesNotExist:
                pass
            if not is_admin_or_registrar:
                raise PermissionDenied("Cannot modify or delete a finalized grade record.")
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

# ===================================================================
# ⭐️ BATCH SAVE VIEW ⭐️
# ===================================================================

class BatchUpdateGradesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]

    def patch(self, request, *args, **kwargs):
        user = request.user
        data = request.data

        if not isinstance(data, list):
            return Response(
                {"error": "Request body must be a list of grade objects."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            profile = user.profile
            is_admin_or_registrar = profile.role in ['admin', 'registrar']
            is_teacher = profile.role == 'teacher'
        except UserProfile.DoesNotExist:
            return Response({"error": "User profile not found."}, status=status.HTTP_403_FORBIDDEN)

        global_locks = GradeSettings.objects.first()
        if not global_locks:
            return Response(
                {"error": "Grade settings not configured. Please contact the administrator."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        quarter_lock_map = {
            'q1': global_locks.q1_open,
            'q2': global_locks.q2_open,
            'q3': global_locks.q3_open,
            'q4': global_locks.q4_open,
        }

        updated_records = []
        errors = []

        try:
            with transaction.atomic():
                enrollment_ids = [item.get('id') for item in data if item.get('id')]
                enrollments = Enrollment.objects.select_related('teacher_class').in_bulk(enrollment_ids)
                
                for item in data:
                    enrollment_id = item.get('id')
                    if not enrollment_id:
                        errors.append({"error": "Missing 'id' in one or more items."})
                        continue

                    enrollment = enrollments.get(enrollment_id)
                    if not enrollment:
                        errors.append({"id": enrollment_id, "error": "Enrollment record not found."})
                        continue

                    if is_teacher:
                        if enrollment.teacher_class.teacher != user:
                            errors.append({"id": enrollment_id, "error": "Permission denied: Not your class."})
                            continue 

                        if enrollment.is_finalized:
                            errors.append({"id": enrollment_id, "error": "Permission denied: Grade is finalized."})
                            continue

                        quarter_locked = False
                        for field, is_open in quarter_lock_map.items():
                            if field in item and not is_open:
                                errors.append({"id": enrollment_id, "error": f"Permission denied: Quarter {field.upper()} is locked."})
                                quarter_locked = True
                                break 
                        
                        if quarter_locked:
                            continue 

                    serializer = EnrollmentSerializer(enrollment, data=item, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        updated_records.append(serializer.data)
                    else:
                        errors.append({"id": enrollment_id, "error": serializer.errors})

                if errors:
                    raise IntegrityError("Batch update failed due to validation or permission errors.")

        except IntegrityError:
            return Response(
                {"status": "Update failed. No grades were saved.", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Batch grade update failed: {e}")
            return Response(
                {"error": "An unexpected error occurred.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"status": "Batch update successful", "updated": updated_records, "errors": errors},
            status=status.HTTP_200_OK
        )

class StudentGradesView(generics.RetrieveAPIView):
    queryset = Student.objects.all().prefetch_related(
        "section_enrollments__section", 
        "enrollments__teacher_class__subject",
        "enrollments__teacher_class__teacher",
        "enrollments__teacher_class__section"
    )
    serializer_class = StudentGradesSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]
    lookup_field = 'pk'

class GradeSettingsViewSet(viewsets.ModelViewSet):
    queryset = GradeSettings.objects.all()
    serializer_class = GradeSettingsSerializer
    permission_classes = [permissions.IsAuthenticated] 

    def _check_admin_permission(self, request):
        try:
            if request.user.profile.role in ['admin', 'registrar']:
                return True
        except UserProfile.DoesNotExist:
            pass
        raise PermissionDenied("You do not have permission to perform this action.")
    def list(self, request, *args, **kwargs):
        if not GradeSettings.objects.exists():
            try:
                if request.user.profile.role == 'admin':
                    GradeSettings.objects.create()
            except Exception:
                pass
        return super().list(request, *args, **kwargs)
    def get_object(self):
        try:
            return GradeSettings.objects.first()
        except GradeSettings.DoesNotExist:
            return None
    def create(self, request, *args, **kwargs):
        self._check_admin_permission(request)
        if GradeSettings.objects.exists():
            return Response({"detail": "Settings object already. Use PATCH to update."}, status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)
    def update(self, request, *args, **kwargs):
        self._check_admin_permission(request)
        instance = self.get_object()
        if not instance:
            return Response({"detail": "Grade settings object not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
    def partial_update(self, request, *args, **kwargs):
        self._check_admin_permission(request)
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    def destroy(self, request, *args, **kwargs):
        self._check_admin_permission(request)
        return super().destroy(request, *args, **kwargs)

class StudentSf10DetailView(generics.RetrieveAPIView):
    queryset = Student.objects.all().prefetch_related(
        "section_enrollments__section",
        "enrollments__teacher_class__subject",
        "enrollments__teacher_class__section"
    )
    serializer_class = StudentSf10Serializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]
    lookup_field = 'lrn'

# ===================================================================
# ⭐️ SECTION & TEACHERCLASS VIEWS ⭐️
# ===================================================================

class SubjectListCreateView(generics.ListCreateAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]

class SubjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]

class SectionListCreateView(generics.ListCreateAPIView):
    queryset = Section.objects.all().order_by('school_year', 'grade', 'name')
    serializer_class = SectionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['grade', 'school_year']
    ordering_fields = ['name', 'grade', 'school_year', 'adviser_name']
    ordering = ['school_year', 'grade', 'name']

class SectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]

class TeacherClassListCreateView(generics.ListCreateAPIView):
    serializer_class = TeacherClassSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['teacher', 'subject', 'section', 'academic_year']
    search_fields = ['teacher__username', 'teacher__first_name', 'teacher__last_name', 'subject__name', 'section__name']
    ordering_fields = ['academic_year', 'section__grade', 'section__name', 'subject__name', 'teacher__last_name']
    ordering = ['academic_year', 'section__grade', 'section__name', 'subject__name']

    def get_queryset(self):
        return TeacherClass.objects.select_related(
            "teacher", "subject", "section"
        ).annotate(
            enrolled_students_count=Count('enrollments', distinct=True),
            total_students_in_section=Count(
                'section__section_enrollments__student', 
                filter=Q(
                    section__section_enrollments__school_year=F('academic_year'), 
                    section__section_enrollments__student__is_active=True
                ),
                distinct=True
            )
        ).order_by('academic_year', 'section__grade', 'section__name', 'subject__name')
    

class TeacherClassDetailView(generics.RetrieveAPIView):
    queryset = TeacherClass.objects.all().select_related("teacher", "subject", "section")
    serializer_class = TeacherClassSerializer
    permission_classes = [permissions.IsAuthenticated]
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        is_admin_or_registrar = False
        is_assigned_teacher = (instance.teacher == user)
        try:
            is_admin_or_registrar = user.profile.role in ['admin', 'registrar']
        except UserProfile.DoesNotExist:
            if not is_assigned_teacher:
                raise PermissionDenied("User profile not found and not assigned teacher.")
        if not (is_admin_or_registrar or is_assigned_teacher):
            raise PermissionDenied("You do not have permission to view this class assignment.")
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class TeacherDashboardView(generics.ListCreateAPIView):
    serializer_class = TeacherClassSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        return TeacherClass.objects.filter(
            teacher=self.request.user
        ).select_related("subject", "section").order_by("section__grade", "section__name", "subject__name")

class TeacherClassRosterView(generics.ListCreateAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        class_id = self.kwargs.get('class_id')
        if not class_id: return Enrollment.objects.none()
        teacher_class = get_object_or_404(TeacherClass.objects.select_related('teacher'), pk=class_id)
        is_admin_or_registrar = False
        is_assigned_teacher = (teacher_class.teacher == user)
        try:
            is_admin_or_registrar = user.profile.role in ['admin', 'registrar']
        except UserProfile.DoesNotExist:
            if not is_assigned_teacher:
                raise PermissionDenied("User profile not found and not assigned teacher.")
        if not (is_admin_or_registrar or is_assigned_teacher):
            raise PermissionDenied("You do not have permission to view this class roster.")
        return Enrollment.objects.filter(
            teacher_class=teacher_class
        ).select_related("student").order_by("student__last_name", "student__first_name")

# ===================================================================
# ⭐️ CLINIC & BEHAVIOR VIEWS ⭐️
# ===================================================================

class ClinicVisitListCreateView(generics.ListCreateAPIView):
    queryset = ClinicVisit.objects.all().prefetch_related(
        Prefetch(
            'student__section_enrollments',
            queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
            to_attr='current_enrollment_prefetch'
        )
    ).order_by("-visit_date")
    serializer_class = ClinicVisitSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'student': ['exact'],
        'illness': ['exact'],
        'student__section_enrollments__section__grade': ['exact'],
        'student__section_enrollments__section__name': ['exact'],
    }
    search_fields = ['student__first_name', 'student__last_name', 'student__lrn', 'illness', 'attended_by']
    ordering_fields = ['visit_date', 'student__last_name']

class ClinicVisitRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ClinicVisit.objects.all().prefetch_related("student__section_enrollments__section")
    serializer_class = ClinicVisitSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]

class ClinicReportSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]

    def get(self, request, *args, **kwargs):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        grade = request.query_params.get('grade')
        section = request.query_params.get('section')
        school_year = request.query_params.get('school_year') 

        queryset = ClinicVisit.objects.all()

        if date_from and date_to:
            queryset = queryset.filter(visit_date__date__range=[date_from, date_to])
        elif date_from:
            queryset = queryset.filter(visit_date__date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(visit_date__date__lte=date_to)

        if school_year:
            if grade:
                queryset = queryset.filter(
                    student__section_enrollments__school_year=school_year,
                    student__section_enrollments__section__grade=grade
                )
            if section:
                queryset = queryset.filter(
                    student__section_enrollments__school_year=school_year,
                    student__section_enrollments__section__name__iexact=section
                )
        else:
            if grade:
                queryset = queryset.filter(
                    student__section_enrollments__is_active=True,
                    student__section_enrollments__section__grade=grade
                )
            if section:
                queryset = queryset.filter(
                    student__section_enrollments__is_active=True,
                    student__section_enrollments__section__name__iexact=section
                )
        
        by_illness = queryset.values('illness').annotate(
            count=Count('id')
        ).order_by('-count')

        by_grade = queryset.filter(
            student__section_enrollments__is_active=True
        ).values(
            'student__section_enrollments__section__grade'
        ).annotate(
            count=Count('id')
        ).order_by('student__section_enrollments__section__grade')
        
        by_grade_cleaned = [
            {'grade': item['student__section_enrollments__section__grade'], 'count': item['count']}
            for item in by_grade if item['student__section_enrollments__section__grade'] is not None
        ]

        by_section = queryset.filter(
            student__section_enrollments__is_active=True
        ).values(
            grade_name=F('student__section_enrollments__section__grade'),
            section_name=F('student__section_enrollments__section__name')
        ).annotate(
            count=Count('id')
        ).order_by('grade_name', 'section_name')

        by_section_cleaned = [
            {'grade': item['grade_name'], 'section': item['section_name'], 'count': item['count']}
            for item in by_section if item['section_name'] is not None
        ]

        total_visits = queryset.count()

        return Response({
            "total_visits": total_visits,
            "summary_by_illness": list(by_illness),
            "summary_by_grade": by_grade_cleaned,
            "summary_by_section": by_section_cleaned,
        }, status=status.HTTP_200_OK)


class SectionReportSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]

    def get(self, request, *args, **kwargs):
        school_year = request.query_params.get('school_year')
        grade = request.query_params.get('grade')

        if not school_year:
            return Response(
                {"error": "A 'school_year' query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = Section.objects.filter(school_year=school_year)

        if grade:
            queryset = queryset.filter(grade=grade)

        annotated_queryset = queryset.annotate(
            student_count=Count(
                'section_enrollments__student',
                filter=Q(
                    section_enrollments__school_year=school_year,
                    section_enrollments__student__is_active=True
                ),
                distinct=True
            )
        ).order_by('grade', 'name')

        data = []
        for section in annotated_queryset:
            data.append({
                "id": section.id,
                "name": section.name,
                "grade": section.grade,
                "school_year": section.school_year,
                "adviser_name": section.adviser_name,
                "student_count": section.student_count,
            })
        
        total_students_in_filter = sum(item['student_count'] for item in data)
        total_sections_in_filter = len(data)

        return Response({
            "total_students": total_students_in_filter,
            "total_sections": total_sections_in_filter,
            "sections": data
        }, status=status.HTTP_200_OK)


class BehaviorRecordListCreateView(generics.ListCreateAPIView):
    serializer_class = BehaviorRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'student': ['exact'], 
        'category': ['exact'], 
        'date': ['exact', 'range', 'gte', 'lte'], 
        'offense_type': ['exact'],
        'student__section_enrollments__section__grade': ['exact'],
        'student__section_enrollments__section__name': ['exact'],
    }
    search_fields = ['student__first_name', 'student__last_name', 'student__lrn', 'description', 'reported_by', 'category']
    ordering_fields = ['date', 'student__last_name', 'category', 'offense_type']

    def get_queryset(self):
        queryset = BehaviorRecord.objects.all().prefetch_related(
            Prefetch(
                'student__section_enrollments',
                queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
                to_attr='current_enrollment_prefetch'
            )
        ).order_by("-date")
        student_pk = self.request.query_params.get('student_pk')
        if student_pk is not None:
            queryset = queryset.filter(student__pk=student_pk)
        return queryset

class BehaviorRecordRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BehaviorRecord.objects.all().prefetch_related("student__section_enrollments__section")
    serializer_class = BehaviorRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]

# ===================================================================
# ⭐️ HELPER VIEWS ⭐️
# ===================================================================

@api_view(['POST'])
@permission_classes([IsAdminOrRegistrar]) 
def toggle_student_status(request, pk):
    try:
        student = Student.objects.prefetch_related(
            Prefetch(
                'section_enrollments',
                queryset=SectionEnrollment.objects.filter(is_active=True).select_related('section'),
                to_attr='active_enrollment'
            )
        ).get(pk=pk)
        
        student.is_active = not student.is_active
        student.save(update_fields=['is_active'])
        
        serializer = StudentSerializer(student, context={'request': request}) 
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Student.DoesNotExist:
        return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in toggle_student_status: {e}") 
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================================================
# ⭐️ IMPORT/EXPORT/PDF VIEWS ⭐️
# ===================================================================
class StudentImportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAdminOrRegistrar]

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "No file was uploaded."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl')
            elif file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                return Response(
                    {"error": "Invalid file type. Please upload a .xlsx or .csv file."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"File read error: {e}")
            return Response(
                {"error": "Failed to read file.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Clean NaN values
        df = df.where(pd.notnull(df), None)
        
        created_count = 0
        updated_count = 0
        errors = []

        # ⭐️ ⭐️ ⭐️ UPDATED: BATCH PROMOTION LOGIC ⭐️ ⭐️ ⭐️
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    # Normalize LRN (remove non-digits)
                    lrn_raw = str(row.get('lrn', ''))
                    lrn = ''.join(filter(str.isdigit, lrn_raw))
                    
                    if not lrn or len(lrn) != 12:
                        errors.append(f"Row {index+2}: Invalid LRN '{lrn_raw}'. Must be exactly 12 digits.")
                        continue

                    # 1. Find or Create the Student (Update if exists)
                    student, created = Student.objects.update_or_create(
                        lrn=lrn,
                        defaults={
                            'first_name': row.get('first_name'),
                            'last_name': row.get('last_name'),
                            'middle_name': row.get('middle_name'),
                            'gender': row.get('gender'),
                            'email': row.get('email'),
                            'phone': row.get('phone'),
                            'address': row.get('address'),
                            'guardian_name': row.get('guardian_name'),
                            'guardian_phone': row.get('guardian_phone'),
                            'is_active': True # Reactivate if they were inactive
                        }
                    )

                    # 2. Handle Section Enrollment (Promotion/Update)
                    section_id = row.get('section_id')
                    school_year = row.get('school_year')

                    if section_id and school_year:
                        try:
                            # Ensure section exists
                            section = Section.objects.get(id=section_id)
                            
                            # Deactivate ANY previous enrollment for this student
                            SectionEnrollment.objects.filter(student=student).update(is_active=False)

                            # Create new active enrollment or update existing one for this year
                            SectionEnrollment.objects.update_or_create(
                                student=student,
                                school_year=school_year,
                                defaults={
                                    'section': section,
                                    'is_active': True
                                }
                            )
                        except Section.DoesNotExist:
                            errors.append(f"Row {index+2}: Section ID {section_id} not found.")

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    errors.append(f"Row {index+2}: {str(e)}")
        # ⭐️ ⭐️ ⭐️ END OF UPDATE ⭐️ ⭐️ ⭐️

        return Response({
            "status": "Import processing complete",
            "created": created_count,
            "updated": updated_count,
            "errors": errors
        }, status=status.HTTP_200_OK)

class StudentExportView(APIView):
    permission_classes = [IsAdminOrRegistrarOrTeacher]

    def get(self, request, *args, **kwargs):
        school_year = request.query_params.get('school_year')
        grade = request.query_params.get('grade')
        section = request.query_params.get('section')

        queryset = SectionEnrollment.objects.all().select_related(
            'student', 'section'
        ).order_by('section__grade', 'section__name', 'student__last_name')

        if school_year:
            queryset = queryset.filter(school_year=school_year)
        else:
            queryset = queryset.filter(is_active=True)
            
        if grade:
            queryset = queryset.filter(section__grade=grade)
        if section:
            queryset = queryset.filter(section__name__iexact=section)
        
        data = []
        for enrollment in queryset:
            s = enrollment.student
            data.append({
                "LRN": s.lrn,
                "Last Name": s.last_name,
                "First Name": s.first_name,
                "Middle Name": s.middle_name,
                "Extension": s.name_extension,
                "Gender": s.gender,
                "Birth Date": s.birth_date,
                "School Year": enrollment.school_year,
                "Grade": enrollment.section.grade,
                "Section": enrollment.section.name,
                "Email": s.email,
                "Phone": s.phone,
                "Address": s.address,
                "Guardian Name": s.guardian_name,
                "Guardian Phone": s.guardian_phone,
            })

        if not data:
            return Response({"error": "No students found matching criteria."}, status=status.HTTP_404_NOT_FOUND)

        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Students')
        output.seek(0)

        filename = f"student_export_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

# --- PDF HELPER ---
def _draw_student_list_pdf(buffer, students_qs, filter_criteria):
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    elements = []
    styles = getSampleStyleSheet()

    title_text = "Student List"
    if filter_criteria:
        title_text += f" ({filter_criteria})"
    elements.append(Paragraph(title_text, styles['h1']))
    
    data = [
        ["LRN", "Last Name", "First Name", "Middle Name", "Gender", "Grade", "Section"]
    ]
    
    for enrollment in students_qs:
        student = enrollment.student
        data.append([
            student.lrn,
            student.last_name,
            student.first_name,
            student.middle_name or '',
            student.gender,
            enrollment.section.grade,
            enrollment.section.name
        ])

    col_widths = [1.5*inch, 1.5*inch, 1.5*inch, 1*inch, 0.8*inch, 0.7*inch, 2*inch]
    
    table = Table(data, colWidths=col_widths)
    
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    
    elements.append(table)
    doc.build(elements)
    
    return buffer

class StudentListPDFView(APIView):
    permission_classes = [IsAdminOrRegistrarOrTeacher]

    def get(self, request, *args, **kwargs):
        school_year = request.query_params.get('school_year')
        grade = request.query_params.get('grade')
        section = request.query_params.get('section')
        
        filter_text_parts = []

        queryset = SectionEnrollment.objects.all().select_related(
            'student', 'section'
        ).order_by('section__grade', 'section__name', 'student__last_name')

        if school_year:
            queryset = queryset.filter(school_year=school_year)
            filter_text_parts.append(f"S.Y. {school_year}")
        else:
            queryset = queryset.filter(is_active=True)
            filter_text_parts.append("Active Students")
            
        if grade:
            queryset = queryset.filter(section__grade=grade)
            filter_text_parts.append(f"Grade {grade}")
        if section:
            queryset = queryset.filter(section__name__iexact=section)
            filter_text_parts.append(f"Section {section}")
        
        if not queryset.exists():
            return Response({"error": "No students found matching criteria."}, status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        filter_criteria = ", ".join(filter_text_parts)
        
        try:
            pdf_buffer = _draw_student_list_pdf(buffer, queryset, filter_criteria)
            pdf_buffer.seek(0)
        except Exception as e:
            logger.error(f"PDF Generation failed: {e}")
            return Response({"error": "Failed to generate PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = f"student_list_{timezone.now().strftime('%Y-%m-%d')}.pdf"
        response = HttpResponse(
            pdf_buffer,
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response


@api_view(['POST'])
@permission_classes([IsAdminOrRegistrar]) 
def enroll_all_students_in_class(request, class_pk):
    try:
        teacher_class = TeacherClass.objects.get(pk=class_pk)
    except TeacherClass.DoesNotExist:
        return Response({"detail": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

    section = teacher_class.section
    if not section:
        return Response({"detail": "This class has no section assigned."}, status=status.HTTP_400_BAD_REQUEST)

    students_in_section = Student.objects.filter(
        section_enrollments__section=section,
        section_enrollments__school_year=teacher_class.academic_year,
        is_active=True
    )
    
    if not students_in_section.exists():
        return Response({"detail": "No active students found in this section for this school year."}, status=status.HTTP_400_BAD_REQUEST)

    created_count = 0
    already_exists_count = 0
    
    with transaction.atomic(): 
        for student in students_in_section:
            enrollment, created = Enrollment.objects.get_or_create(
                student=student,
                teacher_class=teacher_class
            )
            if created:
                created_count += 1
            else:
                already_exists_count += 1

    return Response({
        "detail": f"Successfully enrolled {created_count} new students. {already_exists_count} students were already enrolled."
    }, status=status.HTTP_201_CREATED)

# ===================================================================
# ⭐️ DASHBOARD VIEW ⭐️
# ===================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    try:
        total_students = Student.objects.count()
        active_records = Student.objects.filter(is_active=True).count()
        today = timezone.now().date()
        clinic_visits_today = ClinicVisit.objects.filter(visit_date__date=today).count()
        behavioral_reports = BehaviorRecord.objects.count()

        data = {
            "totalStudents": total_students,
            "activeRecords": active_records,
            "clinicVisits": clinic_visits_today,
            "behavioralReports": behavioral_reports,
        }
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================================================
# ⭐️ ATTENDANCE SUMMARY VIEWS (FIXED FOR ALL QUARTERS) ⭐️
# ===================================================================

class TeacherAttendanceSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, *args, **kwargs):
        try:
            teacher = request.user
            # 1. Get threshold (default 3)
            min_absences = int(request.query_params.get('min_absences', 3))
            
            # 2. Check for optional quarter param (Do NOT default to 1)
            quarter_param = request.query_params.get('quarter')

            student_ids = Enrollment.objects.filter(
                teacher_class__teacher=teacher
                # Removed strict year filter to ensure it catches current enrollments
            ).values_list('student_id', flat=True).distinct()

            # 3. Build the query dynamically
            query_filters = {
                'status': 'Absent',
                'student_id__in': student_ids
            }

            # 4. Only filter by quarter if the user SPECIFICALLY asked for it
            if quarter_param:
                query_filters['quarter'] = int(quarter_param)

            # 5. Execute Query
            absent_records = AttendanceRecord.objects.filter(**query_filters)

            at_risk_students_query = absent_records.values(
                'student__id', 
                'student__first_name', 
                'student__last_name'
            ).annotate(
                absent_count=Count('id')
            ).filter(
                absent_count__gte=min_absences
            ).order_by('-absent_count')

            at_risk_list = []
            for student_data in at_risk_students_query:
                enrollment = SectionEnrollment.objects.filter(
                    student_id=student_data['student__id'],
                    is_active=True
                ).select_related('section').first()

                at_risk_list.append({
                    'student_id': student_data['student__id'],
                    'student_name': f"{student_data['student__last_name']}, {student_data['student__first_name']}",
                    'absent_count': student_data['absent_count'],
                    'grade': enrollment.section.grade if enrollment else 'N/A',
                    'section': enrollment.section.name if enrollment else 'N/A',
                })
            
            return Response({"at_risk_students": at_risk_list}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in TeacherAttendanceSummaryView: {e}")
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AttendanceSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]

    def get(self, request, *args, **kwargs):
        try:
            # 1. Get threshold
            min_absences = int(request.query_params.get('min_absences', 3))
            
            # 2. Check for optional quarter param
            quarter_param = request.query_params.get('quarter')

            # 3. Build Query
            query_filters = {'status': 'Absent'}
            
            if quarter_param:
                query_filters['quarter'] = int(quarter_param)

            absent_records = AttendanceRecord.objects.filter(**query_filters)

            at_risk_students_query = absent_records.values(
                'student__id', 
                'student__first_name', 
                'student__last_name'
            ).annotate(
                absent_count=Count('id')
            ).filter(
                absent_count__gte=min_absences
            ).order_by('-absent_count')

            at_risk_list = []
            for student_data in at_risk_students_query:
                enrollment = SectionEnrollment.objects.filter(
                    student_id=student_data['student__id'],
                    is_active=True
                ).select_related('section').first()

                at_risk_list.append({
                    'student_id': student_data['student__id'],
                    'student_name': f"{student_data['student__last_name']}, {student_data['student__first_name']}",
                    'absent_count': student_data['absent_count'],
                    'grade': enrollment.section.grade if enrollment else 'N/A',
                    'section': enrollment.section.name if enrollment else 'N/A',
                })
            
            return Response({"at_risk_students": at_risk_list}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in AttendanceSummaryView: {e}")
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================================================
# ⭐️ NEW: CLASS ATTENDANCE PDF VIEW ⭐️
# ===================================================================
class ClassAttendancePDFView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, class_pk):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({"error": "Date is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            teacher_class = TeacherClass.objects.get(pk=class_pk)
        except TeacherClass.DoesNotExist:
            return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

        # Fetch records
        records = AttendanceRecord.objects.filter(
            teacher_class=teacher_class,
            date=date_str
        ).select_related('student').order_by('student__last_name')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=inch, bottomMargin=inch)
        elements = []
        styles = getSampleStyleSheet()

        # Header
        header_text = f"Attendance Report: {teacher_class.subject.name}"
        sub_header = f"Section: Grade {teacher_class.section.grade} - {teacher_class.section.name} | Date: {date_str}"
        
        elements.append(Paragraph(header_text, styles['h2']))
        elements.append(Paragraph(sub_header, styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal'])) # Spacer

        # Table Data
        data = [["Student Name", "LRN", "Status"]]
        
        if not records.exists():
             elements.append(Paragraph("No attendance records found for this date.", styles['Normal']))
        else:
            for record in records:
                student_name = f"{record.student.last_name}, {record.student.first_name}"
                data.append([student_name, record.student.lrn, record.status])

            # Column widths: Name, LRN, Status
            table = Table(data, colWidths=[3*inch, 2*inch, 1.5*inch])
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ])
            table.setStyle(style)
            elements.append(table)

        try:
            doc.build(elements)
            buffer.seek(0)
            filename = f"attendance_{teacher_class.section.name}_{date_str}.pdf"
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            logger.error(f"PDF Generation Error: {e}")
            return Response({"error": "Failed to generate PDF"}, status=500)