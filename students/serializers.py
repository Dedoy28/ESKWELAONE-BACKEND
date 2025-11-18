# /backend/students/serializers.py (FINAL CORRECTED FILE - FIX 4)

from rest_framework import serializers, validators
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import transaction
import logging

from .models import (
    Student,
    AttendanceRecord,
    ClinicVisit,
    BehaviorRecord,
    Section,
    Subject,
    TeacherClass,
    Enrollment,
    UserProfile,
    GradeSettings,
    SectionEnrollment
)
from collections import OrderedDict
from decimal import Decimal

logger = logging.getLogger(__name__)

# ============================
# User/Subject/Section Serializers (Unchanged)
# ============================

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name', 'school_year', 'grade', 'adviser_name']

# ============================
# TeacherClass Serializer (Unchanged)
# ============================
class TeacherClassSerializer(serializers.ModelSerializer):
    teacher = serializers.StringRelatedField(read_only=True)
    subject = serializers.StringRelatedField(read_only=True)
    section = serializers.StringRelatedField(read_only=True)
    teacher_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role='teacher'),
        source='teacher',
        write_only=True
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(),
        source='subject',
        write_only=True
    )
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
        write_only=True
    )
    enrolled_students_count = serializers.IntegerField(read_only=True)
    total_students_in_section = serializers.IntegerField(read_only=True)
    is_fully_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = TeacherClass
        fields = [
            "id",
            "teacher", "subject", "section", "academic_year", # Read-only
            "teacher_id", "subject_id", "section_id", # Write-only
            "enrolled_students_count",
            "total_students_in_section",
            "is_fully_enrolled",
        ]
        read_only_fields = [
            "teacher", "subject", "section",
            "enrolled_students_count", "total_students_in_section",
        ]

    def get_is_fully_enrolled(self, obj):
        total_students = getattr(obj, 'total_students_in_section', 0)
        enrolled_students = getattr(obj, 'enrolled_students_count', 0)
        if total_students > 0:
            return enrolled_students == total_students
        return False

# ============================
# GradeSettings Serializer (Unchanged)
# ============================
class GradeSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeSettings
        fields = '__all__'

# ============================
# Helper Function (Unchanged)
# ============================
def _calculate_enrollment_final(enrollment_obj):
    if not enrollment_obj:
        return None
    grades = []
    if enrollment_obj.q1 is not None: grades.append(Decimal(str(enrollment_obj.q1)))
    if enrollment_obj.q2 is not None: grades.append(Decimal(str(enrollment_obj.q2)))
    if enrollment_obj.q3 is not None: grades.append(Decimal(str(enrollment_obj.q3)))
    if enrollment_obj.q4 is not None: grades.append(Decimal(str(enrollment_obj.q4)))
    if not grades:
        return None
    average = sum(grades) / Decimal(len(grades))
    return average.to_integral_value(rounding='ROUND_HALF_UP')


# ==========================================================
# ⭐️ NEW SERIALIZER FOR SECTION ENROLLMENT ⭐️
# ==========================================================
class SectionEnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for the new SectionEnrollment model (Student's history)
    """
    section = SectionSerializer(read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
        write_only=True
    )
    
    class Meta:
        model = SectionEnrollment
        fields = ['id', 'student', 'section', 'section_id', 'school_year', 'is_active']
        read_only_fields = ['student']


# ==========================================================
# ⭐️ UPDATED SimpleStudentSerializer (FOR NESTING) ⭐️
# ==========================================================
class SimpleStudentSerializer(serializers.ModelSerializer):
    """
    Provides essential student info for nesting.
    Now gets grade/section from the *current* active enrollment.
    """
    current_grade = serializers.SerializerMethodField()
    current_section_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            'id', 
            'lrn',
            'first_name', 
            'last_name', 
            'current_grade',
            'current_section_name',
        ]

    def get_current_enrollment(self, obj):
        # Re-usable helper to find the active enrollment
        # Use prefetch_related in the view for optimization
        if hasattr(obj, 'current_enrollment_prefetch'):
             # Use the prefetched data if available
            if obj.current_enrollment_prefetch:
                return obj.current_enrollment_prefetch[0]
            return None
            
        return obj.section_enrollments.filter(is_active=True).select_related('section').first()

    def get_current_grade(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.grade if enrollment else None

    def get_current_section_name(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.name if enrollment else None


# ==========================================================
# ⭐️ UPDATED Enrollment Serializer (FOR GRADES) ⭐️
# ==========================================================
class EnrollmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="teacher_class.subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher_class.teacher.username", read_only=True)
    section_name = serializers.StringRelatedField(source="teacher_class.section", read_only=True)
    academic_year = serializers.CharField(source="teacher_class.academic_year", read_only=True)
    
    student_lrn = serializers.CharField(source="student.lrn", read_only=True) 
    
    student_name = serializers.SerializerMethodField(read_only=True)
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    teacher_class = serializers.PrimaryKeyRelatedField(queryset=TeacherClass.objects.all())
    final_grade = serializers.SerializerMethodField()
    
    pre_final = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    
    q1 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False, validators=[MinValueValidator(0), MaxValueValidator(100)])
    q2 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False, validators=[MinValueValidator(0), MaxValueValidator(100)])
    q3 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # ⭐️⭐️⭐️ THIS IS THE FIX ⭐️⭐️⭐️
    # It now says 100 instead of 1G00
    q4 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    class Meta:
        model = Enrollment
        fields = [
            "id", "student", "teacher_class", 
            "student_lrn",
            "student_name", 
            "subject_name", "teacher_name", "section_name", "academic_year", 
            "q1", "q2", "q3", "q4", "pre_final", "final_grade", "is_finalized",
            "created_at", "updated_at",
        ]
    
    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.last_name}, {obj.student.first_name}"
        return None
    
    def get_final_grade(self, obj):
        return obj.pre_final


# ==========================================================
# ⭐️ UPDATED Attendance Serializers ⭐️
# ==========================================================
class AttendanceHistorySerializer(serializers.ModelSerializer):
    day_of_week = serializers.ReadOnlyField()
    class Meta:
        model = AttendanceRecord
        fields = ["id", "student", "date", "quarter", "status", "day_of_week", "created_at", "updated_at"]
        read_only_fields = ['student']

class AttendanceListSerializer(serializers.ModelSerializer):
    student_lrn = serializers.CharField(source="student.lrn", read_only=True)
    student_name = serializers.SerializerMethodField()
    class Meta:
        model = AttendanceRecord
        fields = ["id", "student", "student_lrn", "student_name", "date", "quarter", "status"]
        read_only_fields = ['student']
    def get_student_name(self, obj):
        return f"{obj.student.last_name}, {obj.student.first_name}"

class AttendanceSerializer(serializers.ModelSerializer):
    student_display = serializers.StringRelatedField(source="student", read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        write_only=True,
        source="student"
    )
    teacher_class_id = serializers.PrimaryKeyRelatedField(
        queryset=TeacherClass.objects.all(),
        write_only=True,
        source="teacher_class"
    )
    day_of_week = serializers.ReadOnlyField()
    class Meta:
        model = AttendanceRecord
        fields = [
            "id", "student_display", "student_id", "teacher_class_id",
            "date", "quarter", "day_of_week", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "updated_at", "created_at", "day_of_week", "student_display"
        ]

class AdminAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_lrn = serializers.CharField(source="student.lrn", read_only=True)
    student_grade = serializers.SerializerMethodField()
    student_section = serializers.SerializerMethodField()
    subject = serializers.CharField(source="teacher_class.subject.name", read_only=True)
    teacher = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'date', 'status', 'quarter',
            'student_name', 
            'student_lrn',
            'student_grade', 
            'student_section',
            'subject', 'teacher', 'updated_at',
        ]
    
    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.last_name}, {obj.student.first_name}"
        return None
    
    def get_teacher(self, obj):
        if obj.teacher_class and obj.teacher_class.teacher:
            if obj.teacher_class.teacher.first_name and obj.teacher_class.teacher.last_name:
                return f"{obj.teacher_class.teacher.last_name}, {obj.teacher_class.teacher.first_name}"
            return obj.teacher_class.teacher.username
        return None

    def get_current_enrollment(self, obj):
        if hasattr(obj.student, 'current_enrollment_prefetch'):
            if obj.student.current_enrollment_prefetch:
                return obj.student.current_enrollment_prefetch[0]
            return None
        return obj.student.section_enrollments.filter(is_active=True).select_related('section').first()

    def get_student_grade(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.grade if enrollment else None

    def get_student_section(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.name if enrollment else None

# ==========================================================
# ⭐️ UPDATED StudentSerializer (The Main One) ⭐️
# ==========================================================
class StudentSerializer(serializers.ModelSerializer):
    
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        write_only=True,
        required=True,
        help_text="The ID of the Section to enroll the student in."
    )
    school_year = serializers.CharField(
        write_only=True,
        required=True,
        help_text="The school year for this enrollment (e.g., 2025-2026)."
    )
    current_enrollment = serializers.SerializerMethodField()
    section_history = SectionEnrollmentSerializer(
        source='section_enrollments',
        many=True,
        read_only=True
    )
    grade = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()
    adviser_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            "id", 
            "lrn",
            "first_name", "last_name", "middle_name", "name_extension",
            "section_id", "school_year",
            "current_enrollment",
            "section_history",
            "grade",
            "section",
            "adviser_name",
            "gender", "email", "phone", "address", "birth_date",
            "guardian_name", "guardian_phone", "guardian_email",
            "emergency_contact", "medical_notes", "is_active",
            "general_average", 
            "elementary_school", "elementary_school_id",
            "elementary_school_address", "elementary_gen_ave",
            "created_at", "updated_at",
        ]
        read_only_fields = ['general_average', 'created_at', 'updated_at']
    
    def get_current_enrollment_obj(self, obj):
        if hasattr(obj, 'active_enrollment'):
            if obj.active_enrollment:
                return obj.active_enrollment[0]
            return None
        return obj.section_enrollments.filter(is_active=True).select_related('section').first()

    def get_current_enrollment(self, obj):
        enrollment = self.get_current_enrollment_obj(obj)
        if enrollment:
            return SectionEnrollmentSerializer(enrollment).data
        return None

    def get_grade(self, obj):
        enrollment = self.get_current_enrollment_obj(obj)
        return enrollment.section.grade if enrollment else None

    def get_section(self, obj):
        enrollment = self.get_current_enrollment_obj(obj)
        return SectionSerializer(enrollment.section).data if enrollment else None

    def get_adviser_name(self, obj):
        enrollment = self.get_current_enrollment_obj(obj)
        return enrollment.section.adviser_name if enrollment and enrollment.section else None

    @transaction.atomic
    def create(self, validated_data):
        section = validated_data.pop('section_id')
        school_year = validated_data.pop('school_year')
        
        student = Student.objects.create(**validated_data)
        
        SectionEnrollment.objects.create(
            student=student,
            section=section,
            school_year=school_year,
            is_active=True 
        )
        return student

    @transaction.atomic
    def update(self, instance, validated_data):
        section = validated_data.pop('section_id', None)
        school_year = validated_data.pop('school_year', None)

        instance = super().update(instance, validated_data)

        if section and school_year:
            instance.section_enrollments.update(is_active=False)
            
            enrollment, created = SectionEnrollment.objects.update_or_create(
                student=instance,
                school_year=school_year,
                defaults={'section': section, 'is_active': True}
            )
        
        return instance


# ==========================================================
# ⭐️ UPDATED StudentGradesSerializer ⭐️
# ==========================================================
class StudentGradesSerializer(serializers.ModelSerializer):
    enrollments = EnrollmentSerializer(many=True, read_only=True)
    general_average = serializers.FloatField(read_only=True)
    
    grade = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()
    school_year = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id", 
            "lrn",
            "first_name", "last_name", "middle_name",
            "grade", "section", "gender", "school_year", "is_active",
            "enrollments", "general_average", "created_at", "updated_at",
        ]
        read_only_fields = ['general_average']

    def get_current_enrollment(self, obj):
        if hasattr(obj, 'active_enrollment'):
            if obj.active_enrollment:
                return obj.active_enrollment[0]
            return None
        return obj.section_enrollments.filter(is_active=True).select_related('section').first()

    def get_grade(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.grade if enrollment else None

    def get_section(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.name if enrollment else None
    
    def get_school_year(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.school_year if enrollment else None

# ==========================================================
# ⭐️ UPDATED ClinicVisitSerializer ⭐️
# ==========================================================
class ClinicVisitSerializer(serializers.ModelSerializer):
    student = SimpleStudentSerializer(read_only=True) 
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        source="student",
        write_only=True
    )
    grade = serializers.CharField(source="student.current_grade", read_only=True)
    section_name = serializers.CharField(source="student.current_section_name", read_only=True)

    class Meta:
        model = ClinicVisit
        fields = [
            "id",
            "student",      
            "student_id",    
            "grade",        
            "section_name",  
            "visit_date",
            "illness",
            "treatment",
            "treatment_details", 
            "notes",
            "attended_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at",
            "student", 
            "grade", "section_name", "visit_date"
        ]

# ==========================================================
# ⭐️ UPDATED BehaviorRecordSerializer ⭐️
# ==========================================================
class BehaviorRecordSerializer(serializers.ModelSerializer):
    student = SimpleStudentSerializer(read_only=True) 
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        source="student",
        write_only=True
    )
    grade = serializers.CharField(source="student.current_grade", read_only=True)
    section_name = serializers.CharField(source="student.current_section_name", read_only=True)
    
    class Meta:
        model = BehaviorRecord
        fields = [
            "id", 
            "student",      
            "student_id",    
            "grade",        
            "section_name",  
            "date", 
            "category", 
            "offense_type", 
            "offense_count", 
            "description",
            "action_taken", 
            "action_taken_details",
            "reported_by", 
            "created_at", 
            "updated_at",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at",
            "student",
            "grade", "section_name", "date"
        ]

# ====================================================================
# ⭐️ UPDATED StudentSf10Serializer (FIXED REDUNDANCY ERROR) ⭐️
# ====================================================================
class Sf10GradeSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='teacher_class.subject.name')
    final = serializers.SerializerMethodField()
    
    q1 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False)
    q2 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False)
    q3 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False)
    q4 = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False)
    class Meta:
        model = Enrollment
        fields = ['subject_name', 'q1', 'q2', 'q3', 'q4', 'final']
        read_only_fields = fields

    def get_final(self, obj):
        return obj.pre_final


class StudentSf10Serializer(serializers.ModelSerializer):
    lastName = serializers.CharField(source='last_name')
    firstName = serializers.CharField(source='first_name')
    nameExtension = serializers.CharField(source='name_extension', allow_null=True)
    middleName = serializers.CharField(source='middle_name', allow_null=True)
    
    # ⭐️ FIX: Removed "source='lrn'" because it caused the AssertionError
    lrn = serializers.CharField() 
    
    sex = serializers.CharField(source='gender')
    
    grade = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()
    adviser = serializers.SerializerMethodField()
    
    elementarySchool = serializers.CharField(source='elementary_school', allow_null=True)
    elementarySchoolId = serializers.CharField(source='elementary_school_id', allow_null=True)
    elementarySchoolAddress = serializers.CharField(source='elementary_school_address', allow_null=True)
    elementaryGenAve = serializers.DecimalField(source='elementary_gen_ave', max_digits=5, decimal_places=2, allow_null=True)
    
    general_average = serializers.SerializerMethodField() 
    gradesByYear = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            'lastName', 'firstName', 'nameExtension', 'middleName',
            'lrn', 'birth_date', 'sex',
            'grade', 'section', 'adviser', 'general_average',
            'elementarySchool', 'elementarySchoolId', 'elementarySchoolAddress', 'elementaryGenAve',
            'gradesByYear',
        ]
        read_only_fields = fields
    
    def get_current_enrollment(self, obj):
        # We use getattr to avoid AttributeErrors if the serializer is re-used strangely
        if not hasattr(self, '_current_enrollment'):
             self._current_enrollment = obj.section_enrollments.filter(
                 is_active=True
             ).select_related('section').first()
        return self._current_enrollment
    
    def get_grade(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.grade if enrollment else None

    def get_section(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.name if enrollment else None
    
    def get_adviser(self, obj):
        enrollment = self.get_current_enrollment(obj)
        return enrollment.section.adviser_name if enrollment else None

    def get_general_average(self, obj):
        enrollment = self.get_current_enrollment(obj)
        if not enrollment:
            return None
            
        current_school_year = enrollment.school_year
        
        coreLearningAreas = [
            "Filipino", "English", "Mathematics", "Science", "Araling Panlipunan (AP)",
            "Edukasyon sa Pagpapakatao (EsP)", "Technology and Livelihood Education (TLE)",
        ]
        mapehComponents = ["Music", "Arts", "Physical Education", "Health"]
        
        current_enrollments = obj.enrollments.filter(
            teacher_class__academic_year=current_school_year
        ).select_related('teacher_class__subject')

        core_finals = []
        mapeh_finals = []

        for enrollment_item in current_enrollments:
            # Renamed variable to enrollment_item to avoid confusion with outer scope
            final_grade = enrollment_item.pre_final
            if final_grade is None:
                continue

            subject_name = enrollment_item.teacher_class.subject.name
            if subject_name in coreLearningAreas:
                core_finals.append(final_grade)
            elif subject_name in mapehComponents:
                mapeh_finals.append(final_grade)

        all_final_ratings = list(core_finals) 

        if mapeh_finals:
            mapeh_average = sum(mapeh_finals) / Decimal(len(mapeh_finals))
            all_final_ratings.append(mapeh_average.to_integral_value(rounding='ROUND_HALF_UP'))

        # ⭐️ Crash Prevention Logic
        if not all_final_ratings:
            return None

        general_avg = sum(all_final_ratings) / Decimal(len(all_final_ratings))
        return general_avg.quantize(Decimal('0.01'))
    
    def get_gradesByYear(self, obj):
        grouped_grades = OrderedDict()
        
        enrollments_qs = obj.enrollments.select_related(
            'teacher_class__subject', 
            'teacher_class__section'
        ).order_by('teacher_class__academic_year')

        for enrollment_item in enrollments_qs:
            year = enrollment_item.teacher_class.academic_year
            if year not in grouped_grades:
                grouped_grades[year] = []
            
            grade_data = Sf10GradeSerializer(enrollment_item).data
            grouped_grades[year].append(grade_data)
        return grouped_grades


# ==========================================================
# ⭐️⭐️⭐️ THIS IS THE FIX ⭐️⭐️⭐️
# The missing StudentImportSerializer class
# ==========================================================
class StudentImportSerializer(serializers.ModelSerializer):
    """
    Serializer for handling the batch import of students from a CSV/Excel file.
    This matches the 'StudentImportView'.
    """
    section_id = serializers.IntegerField(write_only=True, required=True)
    school_year = serializers.CharField(write_only=True, required=True, max_length=10)

    class Meta:
        model = Student
        fields = [
            'first_name',
            'last_name',
            'middle_name',
            'name_extension',
            'lrn',
            'email',
            'phone',
            'address',
            'birth_date',
            'gender',
            'guardian_name',
            'guardian_phone',
            'guardian_email',
            'emergency_contact',
            'medical_notes',
            'section_id',
            'school_year',
        ]
        
        extra_kwargs = {
            'lrn': {
                'validators': [
                    validators.UniqueValidator(
                        queryset=Student.objects.all(),
                        message="A student with this LRN already exists."
                    )
                ]
            },
            'email': {
                'validators': [
                    validators.UniqueValidator(
                        queryset=Student.objects.all(),
                        message="A student with this email already exists."
                    )
                ],
                'required': False,
                'allow_blank': True,
                'allow_null': True,
            },
            'middle_name': {'required': False, 'allow_blank': True, 'allow_null': True},
            'name_extension': {'required': False, 'allow_blank': True, 'allow_null': True},
            'phone': {'required': False, 'allow_blank': True, 'allow_null': True},
            'guardian_email': {'required': False, 'allow_blank': True, 'allow_null': True},
            'emergency_contact': {'required': False, 'allow_blank': True, 'allow_null': True},
            'medical_notes': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate_section_id(self, value):
        if not Section.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Section with ID {value} does not exist.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        section_id = validated_data.pop('section_id')
        school_year = validated_data.pop('school_year')
        
        section = Section.objects.get(id=section_id)

        student = Student.objects.create(**validated_data)
        
        SectionEnrollment.objects.create(
            student=student,
            section=section,
            school_year=school_year,
            is_active=True
        )
        
        return student