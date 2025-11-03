# /backend/students/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
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
    GradeSettings 
)
from collections import OrderedDict
from decimal import Decimal

# ============================
# User/Subject/Section Serializers
# ============================

class UserSerializer(serializers.ModelSerializer):
    """ Serializer for basic User info (e.g., displaying teacher names). """
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]

class SubjectSerializer(serializers.ModelSerializer):
    """ Serializer for the Subject model. """
    class Meta:
        model = Subject
        fields = '__all__'

class SectionSerializer(serializers.ModelSerializer):
    """ Updated Serializer for the Section model. """
    class Meta:
        model = Section
        fields = ['id', 'name', 'school_year', 'grade', 'adviser_name']

# ============================
# TeacherClass Serializer
# ============================
class TeacherClassSerializer(serializers.ModelSerializer):
    """ Serializer for the main TeacherClass (assignment) model. """
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
            "teacher", 
            "subject", 
            "section",
            "enrolled_students_count",
            "total_students_in_section",
        ]

    def get_is_fully_enrolled(self, obj):
        total_students = getattr(obj, 'total_students_in_section', 0)
        enrolled_students = getattr(obj, 'enrolled_students_count', 0)
        
        if total_students > 0:
            return enrolled_students == total_students
        
        return False

# ============================
# GradeSettings Serializer
# ============================
class GradeSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeSettings
        fields = '__all__'


# ====================================================================
# +++ HELPER FUNCTION --- Moved up to be used by both serializers
# ====================================================================
def _calculate_enrollment_final(enrollment_obj):
    """ Helper to calculate a single enrollment's final grade """
    if not enrollment_obj:
        return None
    
    grades = []
    # Use Decimal for precision
    if enrollment_obj.q1 is not None:
        grades.append(Decimal(str(enrollment_obj.q1)))
    if enrollment_obj.q2 is not None:
        grades.append(Decimal(str(enrollment_obj.q2)))
    if enrollment_obj.q3 is not None:
        grades.append(Decimal(str(enrollment_obj.q3)))
    if enrollment_obj.q4 is not None:
        grades.append(Decimal(str(enrollment_obj.q4)))

    if not grades: # Avoid division by zero
        return None
    
    average = sum(grades) / Decimal(len(grades))
    # DepEd rules often round to the nearest integer for the final grade
    return average.to_integral_value(rounding='ROUND_HALF_UP')


# ====================================================================
# +++ NEW SimpleStudentSerializer (FOR NESTING) +++
# ====================================================================
class SimpleStudentSerializer(serializers.ModelSerializer):
    """
    Provides essential student info for nesting in other serializers
    (like ClinicVisit and BehaviorRecord).
    """
    section = SectionSerializer(read_only=True)
    
    class Meta:
        model = Student
        fields = [
            'id', 
            'student_id',  # This is the LRN
            'first_name', 
            'last_name', 
            'grade', 
            'section',
        ]

# ============================
# Enrollment Serializer 
# ============================
class EnrollmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="teacher_class.subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher_class.teacher.username", read_only=True)
    section_name = serializers.StringRelatedField(source="teacher_class.section", read_only=True)
    academic_year = serializers.CharField(source="teacher_class.academic_year", read_only=True)
    student_id_str = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.SerializerMethodField(read_only=True)
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    teacher_class = serializers.PrimaryKeyRelatedField(queryset=TeacherClass.objects.all())
    
    
    final_grade = serializers.SerializerMethodField()
    
    pre_final = serializers.FloatField(read_only=True)   
    is_finalized = serializers.BooleanField(read_only=True)
    q1 = serializers.FloatField(allow_null=True)
    q2 = serializers.FloatField(allow_null=True)
    q3 = serializers.FloatField(allow_null=True)
    q4 = serializers.FloatField(allow_null=True)
    class Meta:
        model = Enrollment
        fields = [
            "id", "student", "teacher_class", "student_id_str", "student_name", 
            "subject_name", "teacher_name", "section_name", "academic_year", 
            "q1", "q2", "q3", "q4", "pre_final", "final_grade", "is_finalized",
            "created_at", "updated_at",
        ]
    
    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.last_name}, {obj.student.first_name}"
        return None

    
    def get_final_grade(self, obj):
        """
        Calculates the average of the four quarters using the helper.
        """
        final_grade = _calculate_enrollment_final(obj)
        
        return float(final_grade) if final_grade is not None else None

# ----------------- ATTENDANCE SERIALIZERS -----------------
class AttendanceHistorySerializer(serializers.ModelSerializer):
    day_of_week = serializers.ReadOnlyField()
    class Meta:
        model = AttendanceRecord
        fields = ["id", "student", "date", "quarter", "status", "day_of_week", "created_at", "updated_at"]
        read_only_fields = ['student']

class AttendanceListSerializer(serializers.ModelSerializer):
    student_id_str = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.SerializerMethodField()
    class Meta:
        model = AttendanceRecord
        fields = ["id", "student", "student_id_str", "student_name", "date", "quarter", "status"]
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
            "id", "student_display", 
            "student_id",
            "teacher_class_id",
            "date", "quarter", "day_of_week", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "updated_at", "created_at", "day_of_week", 
            "student_display"
        ]



class AdminAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_lrn = serializers.CharField(source="student.student_id", read_only=True)
    student_grade = serializers.CharField(source="student.grade", read_only=True)
    student_section = serializers.CharField(source="student.section.name", read_only=True)
    
    subject = serializers.CharField(source="teacher_class.subject.name", read_only=True)
    teacher = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'date',
            'status',
            'quarter',
            'student_name',
            'student_lrn',
            'student_grade',
            'student_section',
            'subject',
            'teacher',
            'updated_at',
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


# ----------------- Students -----------------

class StudentSerializer(serializers.ModelSerializer):
    attendance_records = serializers.SerializerMethodField()
    enrollments = serializers.SerializerMethodField()
    
    general_average = serializers.FloatField(read_only=True)
    
    adviser_name = serializers.CharField(source='section.adviser_name', read_only=True, allow_null=True)
    
    
    section = SectionSerializer(read_only=True) 
    
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
        write_only=True,
        allow_null=True,
        required=False
    )
    
    elementary_gen_ave = serializers.FloatField(read_only=True) 

    class Meta:
        model = Student
        fields = [
            "id", "student_id",
            "first_name", "last_name", "middle_name",
            "grade", "section", "section_id", "adviser_name",
            "gender", "school_year",
            "email", "phone", "address", "birth_date",
            "guardian_name", "guardian_phone", "guardian_email",
            "emergency_contact", "medical_notes", "is_active",
            "general_average", "attendance_records", "enrollments", 
            "name_extension", "elementary_school", "elementary_school_id",
            "elementary_school_address", "elementary_gen_ave",
            "created_at", "updated_at",
        ]
        read_only_fields = ['general_average']
    
    def get_attendance_records(self, obj):
        if hasattr(obj, 'filtered_attendance_records'):
            return AttendanceHistorySerializer(obj.filtered_attendance_records, many=True).data
        if hasattr(obj, 'attendance_records'):
            return AttendanceHistorySerializer(obj.attendance_records.all(), many=True).data
        return []

    def get_enrollments(self, obj):
        # This check is important. We use the *fixed* EnrollmentSerializer.
        if hasattr(obj, 'filtered_enrollments'):
            return EnrollmentSerializer(obj.filtered_enrollments, many=True).data
        if hasattr(obj, 'enrollments'):
            return EnrollmentSerializer(obj.enrollments.all(), many=True).data
        return []

    def validate_email(self, value):
        if value:
            normalized_email = value.lower().strip()
            qs = Student.objects.filter(email__iexact=normalized_email)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("This email is already used by another student.")
            return normalized_email
        return value

class StudentGradesSerializer(serializers.ModelSerializer):
    # This also uses the fixed EnrollmentSerializer, so it should work.
    enrollments = EnrollmentSerializer(many=True, read_only=True)
    
    general_average = serializers.FloatField(read_only=True)
    
    section = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = Student
        fields = [
            "id", "student_id", "first_name", "last_name", "middle_name",
            "grade", "section", "gender", "school_year", "is_active",
            "enrollments", "general_average", "created_at", "updated_at",
        ]
        read_only_fields = ['general_average']

# ----------------- ClinicVisit -----------------



class ClinicVisitSerializer(serializers.ModelSerializer):
    
    # This sends the nested student object to React (for GET requests)
    student = SimpleStudentSerializer(read_only=True) 
    
    # This receives a simple ID from React (for POST/PUT requests)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        source="student",
        write_only=True
    )
    
    # We get these from the 'student' object above now
    grade = serializers.CharField(source="student.grade", read_only=True)
    
    section = SectionSerializer(source="student.section", read_only=True)

    class Meta:
        model = ClinicVisit
        fields = [
            "id",
            "student",       
            "student_id",    
            "grade", 
            "section", 
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
            "grade", "section", "visit_date"
        ]

# ----------------- BehaviorRecord -----------------



class BehaviorRecordSerializer(serializers.ModelSerializer):
    
    
    student = SimpleStudentSerializer(read_only=True) 
    
    
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        source="student",
        write_only=True
    )
    
    # We get these from the 'student' object above now
    grade = serializers.CharField(source="student.grade", read_only=True)

    section = SectionSerializer(source="student.section", read_only=True)
    
    class Meta:
        model = BehaviorRecord
        fields = [
            "id", 
            "student",       # <-- This is the new field for read-only
            "student_id",    # <-- This is the old field for write-only
            "grade", 
            "section", 
            "date", 
            "category", 
            "offense_type", 
            "offense_count", 
            "description",
            "action_taken", 
            "action_taken_details", # <-- This field is already correct
            "reported_by", 
            "created_at", 
            "updated_at",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at",
            "student", # <-- Mark the nested object as read-only
            "grade", "section", "date"
        ]

# ====================================================================
# +++ SERIALIZERS FOR SF10 (FORM 137) REPORT +++
# (This section is already correct from our previous fix)
# ====================================================================

class Sf10GradeSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='teacher_class.subject.name')
    
    final = serializers.SerializerMethodField()
    
    q1 = serializers.FloatField(allow_null=True)
    q2 = serializers.FloatField(allow_null=True)
    q3 = serializers.FloatField(allow_null=True)
    q4 = serializers.FloatField(allow_null=True)
    class Meta:
        model = Enrollment
        fields = ['subject_name', 'q1', 'q2', 'q3', 'q4', 'final']
        read_only_fields = fields

    def get_final(self, obj):
        """
        Calculates the average of the four quarters using the helper.
        """
        final_grade = _calculate_enrollment_final(obj)
        return float(final_grade) if final_grade is not None else None


class StudentSf10Serializer(serializers.ModelSerializer):
    lastName = serializers.CharField(source='last_name')
    firstName = serializers.CharField(source='first_name')
    nameExtension = serializers.CharField(source='name_extension')
    middleName = serializers.CharField(source='middle_name')
    lrn = serializers.CharField(source='student_id')
    sex = serializers.CharField(source='gender')
    section = serializers.StringRelatedField() 
    adviser = serializers.CharField(source='section.adviser_name')
    elementarySchool = serializers.CharField(source='elementary_school')
    elementarySchoolId = serializers.CharField(source='elementary_school_id')
    elementarySchoolAddress = serializers.CharField(source='elementary_school_address')
    
    elementaryGenAve = serializers.FloatField(source='elementary_gen_ave')
    
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
    
    def get_general_average(self, obj):
        """
        Calculates the general average for the student's *current* school year.
        """
        coreLearningAreas = [
            "Filipino", "English", "Mathematics", "Science", "Araling Panlipunan (AP)",
            "Edukasyon sa Pagpapakatao (EsP)", "Technology and Livelihood Education (TLE)",
        ]
        mapehComponents = ["Music", "Arts", "Physical Education", "Health"]
        
        current_enrollments = obj.enrollments.filter(
            teacher_class__academic_year=obj.school_year
        ).select_related('teacher_class__subject')

        core_finals = []
        mapeh_finals = []

        for enrollment in current_enrollments:
            subject_name = enrollment.teacher_class.subject.name
            
            final_grade = _calculate_enrollment_final(enrollment)
            if final_grade is None:
                continue

            if subject_name in coreLearningAreas:
                core_finals.append(final_grade)
            elif subject_name in mapehComponents:
                mapeh_finals.append(final_grade)

        all_final_ratings = list(core_finals) 

        if mapeh_finals:
            mapeh_average = sum(mapeh_finals) / Decimal(len(mapeh_finals))
            all_final_ratings.append(mapeh_average.to_integral_value(rounding='ROUND_HALF_UP'))

        if not all_final_ratings:
            return None

        general_avg = sum(all_final_ratings) / Decimal(len(all_final_ratings))
        return round(general_avg, 2)

    
    def get_gradesByYear(self, obj):
        grouped_grades = OrderedDict()
        
        enrollments_qs = getattr(obj, 'filtered_enrollments', obj.enrollments.all())
        
        if isinstance(enrollments_qs, list):
            enrollments_list = sorted(enrollments_qs, key=lambda e: e.teacher_class.academic_year)
        else:
            enrollments_list = enrollments_qs.select_related(
                'teacher_class__subject', 
                'teacher_class__section'
            ).order_by('teacher_class__academic_year')

        for enrollment in enrollments_list:
            year = enrollment.teacher_class.academic_year
            if year not in grouped_grades:
                grouped_grades[year] = []
            
            grade_data = Sf10GradeSerializer(enrollment).data
            grouped_grades[year].append(grade_data)
        return grouped_grades