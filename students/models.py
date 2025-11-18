# /backend/students/models.py (FINAL CORRECTED FILE - LRN FIX APPLIED)

from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

# ============================
# SUBJECT MODEL (Unchanged)
# ============================
class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name
    class Meta:
        ordering = ['name']

# ============================
# USER PROFILE MODEL (Unchanged)
# ============================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('teacher', 'Teacher'),
        ('registrar', 'Registrar'),
        ('nurse', 'Nurse'),
        ('guidance_counselor', 'Guidance Counselor'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

# ============================
# SECTION MODEL (Unchanged)
# ============================
class Section(models.Model):
    GRADE_CHOICES = [
        ("7", "Grade 7"),
        ("8", "Grade 8"),
        ("9", "Grade 9"),
        ("10", "Grade 10"),
    ]
    name = models.CharField(max_length=100) 
    school_year = models.CharField(max_length=9, help_text="e.g., 2024-2025", db_index=True)
    grade = models.CharField(
        max_length=2, 
        choices=GRADE_CHOICES, 
        help_text="Grade level", 
        db_index=True
    )
    adviser_name = models.CharField(max_length=255, blank=True, null=True) 
    
    class Meta:
        unique_together = ('name', 'school_year', 'grade') 
        ordering = ['school_year', 'grade', 'name']
        indexes = [
            models.Index(fields=['school_year']),
            models.Index(fields=['grade']),
            models.Index(fields=['name']),
        ]
    def __str__(self):
        return f"Grade {self.grade} - {self.name} ({self.school_year})"

# ============================
# STUDENT MODEL (UPDATED)
# ============================
class Student(models.Model):
    GENDER_CHOICES = [("Male", "Male"), ("Female", "Female")]
    
    first_name = models.CharField(max_length=100, db_index=True)
    last_name = models.CharField(max_length=100, db_index=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    name_extension = models.CharField(max_length=10, blank=True, null=True, help_text="e.g., Jr., Sr., III")

    # ⭐️ UPDATE: Added RegexValidator to enforce exactly 12 digits ⭐️
    lrn = models.CharField(
        max_length=12, 
        unique=True, 
        db_index=True,
        validators=[
            RegexValidator(
                regex=r'^\d{12}$', 
                message='LRN must be exactly 12 digits and contain numbers only.'
            )
        ]
    )

    email = models.EmailField(blank=True, null=True, unique=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, null=True, validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid phone number.")])
    address = models.TextField(blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    is_active = models.BooleanField(default=True, db_index=True)
    
    guardian_name = models.CharField(max_length=200)
    guardian_phone = models.CharField(max_length=20, validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid guardian phone number.")])
    guardian_email = models.EmailField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=20, blank=True, null=True, validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid phone number.")])
    medical_notes = models.TextField(blank=True, null=True)
    
    general_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    elementary_school = models.CharField(max_length=255, blank=True, null=True)
    elementary_school_id = models.CharField(max_length=100, blank=True, null=True)
    elementary_school_address = models.CharField(max_length=255, blank=True, null=True)
    elementary_gen_ave = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="e.g., 88.75")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    historical_sections = models.ManyToManyField(
        Section,
        through='SectionEnrollment',
        related_name='enrolled_students'
    )

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['lrn']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.lrn} - {self.last_name}, {self.first_name}"

# ================================================
# SECTIONENROLLMENT MODEL (Unchanged)
# ================================================
class SectionEnrollment(models.Model):
    """
    This model links a Student to a Section for a specific school year.
    This creates the "historical data."
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="section_enrollments")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="section_enrollments")
    school_year = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True, help_text="Is this their current enrollment?")
    
    class Meta:
        unique_together = ('student', 'school_year')
        ordering = ['-school_year', 'student__last_name']

    def __str__(self):
        return f"{self.student} -> {self.section} ({self.school_year})"

# ============================
# TEACHER CLASS MODEL (Unchanged)
# ============================
class TeacherClass(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classes_taught", limit_choices_to={'profile__role': 'teacher'})
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="classes")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="classes")
    academic_year = models.CharField(max_length=9, db_index=True, help_text="e.g., 2024-2025")
    
    class Meta:
        ordering = ['academic_year', 'section__grade', 'section__name', 'subject__name']
        unique_together = ('subject', 'section', 'academic_year')
        verbose_name = "Teacher Class Assignment"
        verbose_name_plural = "Teacher Class Assignments"

    def __str__(self):
        return f"{self.subject.name} (Grade {self.section.grade}-{self.section.name}) - {self.teacher.username} ({self.academic_year})"


# ============================
# ENROLLMENT MODEL (Unchanged)
# ============================
class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    teacher_class = models.ForeignKey(TeacherClass, on_delete=models.CASCADE, related_name="enrollments")

    q1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    q2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    q3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    q4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    pre_final = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Calculated final rating")
    is_finalized = models.BooleanField(default=False, help_text="If True, this grade record cannot be edited.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__last_name", "teacher_class__subject__name"]
        unique_together = ('student', 'teacher_class')
        indexes = [models.Index(fields=['is_finalized'])]

    def __str__(self):
        return f"{self.student} - {self.teacher_class.subject.name}"

    @property
    def final_grade(self):
        return self.pre_final

    def calculate_final_grade(self):
        grades = []
        if self.q1 is not None: grades.append(self.q1)
        if self.q2 is not None: grades.append(self.q2)
        if self.q3 is not None: grades.append(self.q3)
        if self.q4 is not None: grades.append(self.q4)
        if not grades:
            return None
        average = sum(grades) / len(grades)
        
        return Decimal(average).to_integral_value(rounding='ROUND_HALF_UP') 

    def save(self, *args, **kwargs):
        calculated_grade = self.calculate_final_grade()
        if calculated_grade is not None:
            self.pre_final = calculated_grade.quantize(Decimal('0.01'))
        else:
            self.pre_final = None
        super().save(*args, **kwargs)


# ============================
# ⭐️ ATTENDANCE MODEL (Unchanged) ⭐️
# ============================
class AttendanceRecord(models.Model):
    STATUS_CHOICES = [("Present", "Present"), ("Absent", "Absent"), ("Late", "Late"), ("Excused", "Excused")]
    QUARTER_CHOICES = [(1, "Quarter 1"), (2, "Quarter 2"), (3, "Quarter 3"), (4, "Quarter 4")]
    
    teacher_class = models.ForeignKey(
        TeacherClass, 
        on_delete=models.CASCADE, 
        related_name="attendance_records"
    )
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField(db_index=True)
    quarter = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Present")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("teacher_class", "student", "date") 
        ordering = ["-date", "student__last_name", "student__first_name"]
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['quarter']),
            models.Index(fields=['status']),
            models.Index(fields=['teacher_class']),
        ]
        db_table = 'students_attendancerecord'
        
    def __str__(self):
        if self.teacher_class:
            return f"{self.student.last_name} - {self.teacher_class.subject.name} ({self.date}): {self.status}"
        return f"{self.student.last_name} - (No Class) ({self.date}): {self.status}"
    
    @property
    def day_of_week(self):
        return self.date.strftime("%A")


# ============================
# CLINIC VISIT MODEL (Unchanged)
# ============================
class ClinicVisit(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="clinic_visits")
    visit_date = models.DateTimeField(auto_now_add=True)
    illness = models.CharField(max_length=255, db_index=True)
    treatment = models.TextField(blank=True, null=True)
    treatment_details = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    attended_by = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-visit_date']
        indexes = [ models.Index(fields=['illness']), models.Index(fields=['visit_date']), ]
    def __str__(self):
        return f"Clinic Visit - {self.student.last_name}, {self.student.first_name} ({self.visit_date.strftime('%Y-%m-%d %H:%M')})"


# ============================
# BEHAVIOR RECORD MODEL (Unchanged)
# ============================
class BehaviorRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="behavior_records")
    
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    category = models.CharField(max_length=255, db_index=True)
    offense_type = models.CharField(max_length=10, default="Minor")
    offense_count = models.PositiveIntegerField(default=1)
    description = models.TextField()
    action_taken = models.CharField(max_length=255, blank=True, null=True)
    action_taken_details = models.TextField(blank=True, null=True)
    reported_by = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-date', 'student__last_name', 'student__first_name']
        indexes = [ models.Index(fields=['date']), models.Index(fields=['category']), ]
    def __str__(self):
        return f"{self.student.last_name}, {self.student.first_name} - {self.category} ({self.date})"


# ============================
# GRADE SETTINGS MODEL (Unchanged)
# ============================
class GradeSettings(models.Model):
    q1_open = models.BooleanField(default=True, help_text="Is Quarter 1 grade entry open for teachers?")
    q2_open = models.BooleanField(default=False, help_text="Is Quarter 2 grade entry open for teachers?")
    q3_open = models.BooleanField(default=False, help_text="Is Quarter 4 grade entry open for teachers?")
    q4_open = models.BooleanField(default=False, help_text="Is Quarter 4 grade entry open for teachers?")
    def __str__(self):
        return "Global Grade Lock Settings"
    def save(self, *args, **kwargs):
        if not self.pk and GradeSettings.objects.exists():
            raise ValidationError("Cannot create more than one GradeSettings instance.")
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Grade Lock Setting"
        verbose_name_plural = "Grade Lock Settings"