# /backend/students/views.py

from rest_framework import generics, permissions, filters, status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.timezone import now
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404

# --- ADD THESE IMPORTS ---
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone # <-- Make sure this is imported
# --- END IMPORTS ---


# --- MODIFIED IMPORTS ---
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
    GradeSettings 
)
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
    GradeSettingsSerializer 
)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


# ===================================================================
# ⭐️ CUSTOM PERMISSIONS (These are defined locally) ⭐️
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


# -----------------------------
# STUDENT VIEWS
# -----------------------------

class StudentListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["grade", "section__name", "gender", "is_active", "school_year"]
    search_fields = ['student_id', 'first_name', 'last_name', 'email']
    ordering_fields = ["last_name", "first_name", "student_id", "grade", "section__name"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        user = self.request.user
        queryset = Student.objects.all().select_related('section')

        try:
            profile = user.profile
            if profile.role in ['admin', 'registrar']:
                queryset = queryset.prefetch_related(
                    "attendance_records",
                    "enrollments__teacher_class__subject",
                    "enrollments__teacher_class__teacher",
                    "enrollments__teacher_class__section"
                )
            elif profile.role == 'teacher':
                queryset = queryset.prefetch_related(
                    Prefetch(
                        "attendance_records",
                        queryset=AttendanceRecord.objects.filter(teacher_class__teacher=user),
                        to_attr="filtered_attendance_records" 
                    ),
                    Prefetch(
                        "enrollments",
                        queryset=Enrollment.objects.filter(teacher_class__teacher=user).select_related(
                            "teacher_class__subject",
                            "teacher_class__teacher",
                            "teacher_class__section"
                        ),
                        to_attr="filtered_enrollments" 
                    )
                )
            else:
                queryset = queryset
                
        except UserProfile.DoesNotExist:
            return Student.objects.none()

        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrRegistrar()]
        return super().get_permissions()

class StudentRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Student.objects.all().select_related('section').prefetch_related(
            "attendance_records", 
            "enrollments__teacher_class__subject",
            "enrollments__teacher_class__teacher",
            "enrollments__teacher_class__section" 
    )
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_permissions(self):
         if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminOrRegistrar()]
         return super().get_permissions()


# -----------------------------
# ATTENDANCE VIEWS
# -----------------------------

class AttendanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        "student__grade": ["exact"],
        "student__section__name": ["exact", "icontains"],
        "student__gender": ["exact"], "student__is_active": ["exact"],
        "status": ["exact"], "quarter": ["exact"],
        "date": ["exact", "gte", "lte", "range"],
    }
    ordering_fields = ["date", "student__last_name"]
    ordering = ["-date"]

    def get_serializer_class(self):
        return AttendanceListSerializer if self.request.method == "GET" else AttendanceSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = AttendanceRecord.objects.all().select_related(
            "student", 
            "student__section",
            "teacher_class__subject"
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


class ClassAttendanceView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAssignedTeacher]

    def get(self, request, class_pk):
        date_str = request.query_params.get('date', now().strftime('%Y-%m-%d'))
        
        students_in_class = Student.objects.filter(
            enrollments__teacher_class_id=class_pk, 
            is_active=True
        ).order_by('last_name', 'first_name')
        
        existing_records = AttendanceRecord.objects.filter(
            teacher_class_id=class_pk,
            date=date_str
        )
        
        attendance_map = {}
        for record in existing_records:
            attendance_map[record.student_id] = {
                "id": record.id,
                "status": record.status,
                "updated_at": record.updated_at.isoformat()
            }
        
        roster_with_attendance = []
        for student in students_in_class:
            record_data = attendance_map.get(student.pk)
            roster_with_attendance.append({
                "student_id": student.pk,
                "name": f"{student.last_name}, {student.first_name}",
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

        # Get the TeacherClass object once to be more efficient
        try:
            teacher_class = TeacherClass.objects.get(pk=class_pk)
        except TeacherClass.DoesNotExist:
            return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

        saved_records_data = []
        
        for item in attendance_data:
            student_id = item.get('student_id')
            new_status = item.get('status')

            if not student_id or not new_status:
                continue # Skip any incomplete data rows

            try:
                # This is the fix: It finds a record matching the unique keys...
                record, created = AttendanceRecord.objects.update_or_create(
                    teacher_class=teacher_class,
                    student_id=student_id,
                    date=date_str,
                    # ...and if it finds one, it UPDATES it with these defaults.
                    # If it doesn't find one, it CREATES it.
                    defaults={
                        'status': new_status,
                        'quarter': quarter
                    }
                )
                
                # We still serialize the resulting record to send it
                # back to the frontend, just like your old code.
                serializer = AttendanceSerializer(record)
                saved_records_data.append(serializer.data)

            except Exception as e:
                # Handle any other unexpected error for a single student
                print(f"Error saving attendance for student {student_id}: {e}")
                # You can choose to either stop or collect errors
                return Response({"error": f"Failed to save for student {student_id}: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        return Response({"status": "Attendance saved", "records": saved_records_data}, status=status.HTTP_201_CREATED)


# -----------------------------
# (Rest of the file is unchanged)
# -----------------------------

class AdminAttendanceReportView(generics.ListAPIView):
    serializer_class = AdminAttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrar]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'date': ['exact', 'range', 'gte', 'lte'],
        'quarter': ['exact'],
        'status': ['exact'],
        'student__grade': ['exact'],
        'student__section__name': ['exact'],
        'teacher_class__subject__name': ['exact'],
    }
    search_fields = [
        'student__last_name', 
        'student__first_name', 
        'student__student_id',
        'teacher_class__subject__name',
        'teacher_class__section__name',
        'teacher_class__teacher__username'
    ]
    ordering_fields = ['date', 'student__last_name', 'teacher_class__subject__name']
    ordering = ['-date']

    def get_queryset(self):
        return AttendanceRecord.objects.all().select_related(
            'student',
            'student__section',
            'teacher_class',
            'teacher_class__subject',
            'teacher_class__teacher'
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


        students_qs = Student.objects.filter(school_year=school_year, is_active=True).select_related('section').order_by("gender", "last_name", "first_name")
        if grade and grade != 'all':
            students_qs = students_qs.filter(grade=grade)
        if section_name and section_name != 'all':
            students_qs = students_qs.filter(section__name__iexact=section_name)

        student_ids = list(students_qs.values_list('id', flat=True))

        records = AttendanceRecord.objects.filter(
            student_id__in=student_ids,
            quarter=quarter_int,
        ).select_related("student")

        att_map = {}
        for r in records:
            sid = r.student_id
            date_str = str(r.date)
            att_map.setdefault(sid, {})[date_str] = r.status

        data = []
        for s in students_qs:
            student_att = att_map.get(s.id, {})
            present_count = sum(1 for v in student_att.values() if v == "Present")
            absent_count = sum(1 for v in student_att.values() if v == "Absent")
            late_count = sum(1 for v in student_att.values() if v == "Late")
            excused_count = sum(1 for v in student_att.values() if v == "Excused")
            total_days = len(student_att)

            row = {
                "student_pk": s.pk, "student_id": s.student_id,
                "name": f"{s.last_name}, {s.first_name}", "gender": s.gender,
                "grade": s.grade,
                "section": s.section.name if s.section else None,
                "attendance": student_att,
                "present_count": present_count,
                "absent_count": absent_count,
                "late_count": late_count,
                "excused_count": excused_count,
                "total_days": total_days,
            }
            data.append(row)

        return Response({"school_year": school_year, "quarter": quarter, "students": data})

class EnrollmentListCreateView(generics.ListCreateAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "student", "teacher_class", "teacher_class__academic_year",
        "teacher_class__subject", "teacher_class__section",
        "student__grade", "student__section"
    ]
    search_fields = ["student__student_id", "student__first_name", "student__last_name", "teacher_class__subject__name"]
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


# ⭐️ --- THIS IS THE VIEW WITH THE "FINAL" GRADE BUG --- ⭐️
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
                    'q4': global_locks.q4_open, # <-- FIX 1: Was global_bots
                }
                for field, is_open in quarter_lock_map.items():
                    if field in request_data and not is_open:
                        raise PermissionDenied(f"Quarter {field.upper()} is currently locked by the administrator.")
            except Exception as e:
                raise PermissionDenied(str(e))

    # ❗️❗️❗️ THIS 'update' METHOD IS THE FIX ❗️❗️❗️
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        self._check_finalized_and_lock_status(instance, request.data) 
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # This calls serializer.update(), which saves the instance AND student
        updated_instance = serializer.save() 
        
        if getattr(updated_instance, '_prefetched_objects_cache', None):
            # clear cache if it exists
            updated_instance._prefetched_objects_cache = {}

        # Re-serialize the UPDATED instance to get the new 'pre_final' grade
        return_serializer = self.get_serializer(updated_instance)
        
        # Send the NEW data back to the frontend
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

class StudentGradesView(generics.RetrieveAPIView):
    queryset = Student.objects.all().select_related('section').prefetch_related(
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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance:
             return Response({"detail": "Settings not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def get_object(self):
        try:
            return GradeSettings.objects.first()
        except GradeSettings.DoesNotExist:
            return None

    def create(self, request, *args, **kwargs):
        self._check_admin_permission(request)
        if GradeSettings.objects.exists():
            return Response({"detail": "Settings object already exists. Use PATCH to update."}, status=status.HTTP_400_BAD_REQUEST)
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
    queryset = Student.objects.all().select_related('section').prefetch_related(
        "enrollments__teacher_class__subject",
        "enrollments__teacher_class__section"
    )
    serializer_class = StudentSf10Serializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacher]
    lookup_field = 'student_id'

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
    # ⭐️ --- THIS IS THE FIXED LINE --- ⭐️
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
                'section__students', 
                filter=Q(section__students__is_active=True),
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
            pass
            
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

class ClinicVisitListCreateView(generics.ListCreateAPIView):
    queryset = ClinicVisit.objects.all().select_related("student", "student__section").order_by("-visit_date")
    serializer_class = ClinicVisitSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['student', 'student__grade', 'student__section__name', 'illness']
    
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id', 'illness', 'attended_by']
    ordering_fields = ['visit_date', 'student__last_name']

class ClinicVisitRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ClinicVisit.objects.all().select_related("student", "student__section")
    serializer_class = ClinicVisitSerializer
    # ⭐️ --- THIS IS THE FIXED LINE --- ⭐️
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]

class BehaviorRecordListCreateView(generics.ListCreateAPIView):
    serializer_class = BehaviorRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'student__grade', 'student__section__name', 'category', 'date', 'offense_type']
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id', 'description', 'reported_by', 'category']
    ordering_fields = ['date', 'student__last_name', 'category', 'offense_type']

    def get_queryset(self):
        queryset = BehaviorRecord.objects.all().select_related("student", "student__section").order_by("-date")
        student_pk = self.request.query_params.get('student_pk')
        if student_pk is not None:
            queryset = queryset.filter(student__pk=student_pk)
        return queryset

class BehaviorRecordRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BehaviorRecord.objects.all().select_related("student", "student__section")
    serializer_class = BehaviorRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarOrTeacherOrGuidance] # ❗️This was also a typo, corrected.

@api_view(['POST'])
@permission_classes([IsAdminOrRegistrar]) 
def toggle_student_status(request, pk):
    try:
        student = Student.objects.select_related(
            'section'
        ).prefetch_related(
            "attendance_records",
            "enrollments__teacher_class__subject",
            "enrollments__teacher_class__teacher",
            "enrollments__teacher_class__section"
        ).get(pk=pk)
        
        student.is_active = not student.is_active
        student.save(update_fields=['is_active'])
        
        serializer = StudentSerializer(student, context={'request': request}) 
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Student.DoesNotExist:
        return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in toggle_student_status: {e}") 
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

    students_in_section = Student.objects.filter(section=section, is_active=True)
    
    if not students_in_section.exists():
        return Response({"detail": "No active students found in this section."}, status=status.HTTP_400_BAD_REQUEST)

    created_count = 0
    already_exists_count = 0
    
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
# ⭐️ NEW DASHBOARD VIEW ⭐️
# ===================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated]) # Any authenticated user can see the dashboard
def dashboard_stats(request):
    """
    Provides a summary of key statistics for the main dashboard.
    """
    try:
        # 1. Total number of students
        total_students = Student.objects.count()
        
        # 2. Total active student records
        active_records = Student.objects.filter(is_active=True).count()
        
        # 3. Clinic visits for *today*
        today = timezone.now().date()
        clinic_visits_today = ClinicVisit.objects.filter(visit_date__date=today).count()
        
        # 4. Total number of behavioral reports
        behavioral_reports = BehaviorRecord.objects.count()

        # Compile the data into a single response
        data = {
            "totalStudents": total_students,
            "activeRecords": active_records,
            "clinicVisits": clinic_visits_today,
            "behavioralReports": behavioral_reports,
        }
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Handle potential errors, e.g., database issues
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)