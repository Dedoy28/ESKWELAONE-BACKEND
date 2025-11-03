# /backend/students/models.py

from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.conf import settings # Import settings
# --- ADD THESE IMPORTS for the signal ---
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ValidationError # ADDED for clean error handling
from django.utils import timezone # <-- Added this import

# ============================
# SUBJECT MODEL (No Change)
# ============================
class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

# ============================
# USER PROFILE MODEL (No Change)
# ============================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('teacher', 'Teacher'),
        ('registrar', 'Registrar'),
        ('nurse', 'Nurse'),
        ('guidance_counselor', 'Guidance Counselor'),
        ('admin', 'Admin'),
    ]

    # Link to the built-in User model
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Add the role field
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


# ============================
# STUDENT MODEL (No Change)
# ============================
class Student(models.Model):
    GENDER_CHOICES = [
        ("Male", "Male"),
        ("Female", "Female"),
    ]

    GRADE_CHOICES = [
        ("7", "Grade 7"),
        ("8", "Grade 8"),
        ("9", "Grade 9"),
        ("10", "Grade 10"),
    ]

    first_name = models.CharField(max_length=100, db_index=True)
    last_name = models.CharField(max_length=100, db_index=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    name_extension = models.CharField(max_length=10, blank=True, null=True, help_text="e.g., Jr., Sr., III")

    student_id = models.CharField(max_length=20, unique=True, db_index=True) # Example: LRN or unique ID

    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, db_index=True)
    
    # This field will be linked below, after Section is defined
    section = models.ForeignKey(
        'Section', # Use string reference to avoid order issues
        on_delete=models.SET_NULL, # If a section is deleted, don't delete the student
        null=True, 
        blank=True, 
        related_name="students"
    )
    
    school_year = models.CharField(max_length=10, blank=True, null=True)

    email = models.EmailField(blank=True, null=True, unique=True, db_index=True)
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid phone number.")]
    )
    address = models.TextField(blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True) # Allow blank/null if not always required

    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)

    guardian_name = models.CharField(max_length=200) # Increased length
    guardian_phone = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid guardian phone number.")]
    )
    guardian_email = models.EmailField(blank=True, null=True)

    emergency_contact = models.CharField(
        max_length=20, blank=True, null=True,
        validators=[RegexValidator(r'^\+?\d{7,15}$', "Enter a valid phone number.")]
    )
    medical_notes = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True, db_index=True)

    general_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    elementary_school = models.CharField(max_length=255, blank=True, null=True)
    elementary_school_id = models.CharField(max_length=100, blank=True, null=True)
    elementary_school_address = models.CharField(max_length=255, blank=True, null=True)
    elementary_gen_ave = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="e.g., 88.75")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['student_id']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['grade']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.student_id} - {self.last_name}, {self.first_name}"


# ============================
# SECTION MODEL (No Change)
# ============================
class Section(models.Model):
    name = models.CharField(max_length=100) # e.g., "A", "Einstein"
    school_year = models.CharField(max_length=9, help_text="e.g., 2024-2025", db_index=True)
    
    grade = models.CharField(
        max_length=2, 
        choices=Student.GRADE_CHOICES, 
        help_text="Grade level", 
        db_index=True
    )
    
    adviser_name = models.CharField(max_length=255, blank=True, null=True) # Adviser might change or not be assigned initially
    
    class Meta:
        unique_together = ('name', 'school_year', 'grade') # Ensure unique section per grade per year
        ordering = ['school_year', 'grade', 'name']
        indexes = [
            models.Index(fields=['school_year']),
            models.Index(fields=['grade']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"Grade {self.grade} - {self.name} ({self.school_year})"


# ============================
# TEACHER CLASS MODEL (No Change)
# ============================
class TeacherClass(models.Model):
    """
    This is the central "assignment" model.
    It links a Teacher to a Subject for a specific Section and School Year.
    Example: G. Pineda (Teacher) -> English (Subject) -> Grade 7-A (Section)
    """
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, # Links to the main User model
        on_delete=models.CASCADE,
        related_name="classes_taught",
        limit_choices_to={'profile__role': 'teacher'}, # Ensures only teachers can be selected in admin
        help_text="The teacher assigned to this class."
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="classes"
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="classes"
    )
    academic_year = models.CharField(
        max_length=9, 
        db_index=True,
        help_text="e.g., 2024-2025"
    )
    
    class Meta:
        ordering = ['academic_year', 'section__grade', 'section__name', 'subject__name']
        # A subject should only be assigned once per section in a given year
        unique_together = ('subject', 'section', 'academic_year')
        verbose_name = "Teacher Class Assignment"
        verbose_name_plural = "Teacher Class Assignments"

    def __str__(self):
        return f"{self.subject.name} (Grade {self.section.grade}-{self.section.name}) - {self.teacher.username} ({self.academic_year})"


# ============================
# ENROLLMENT MODEL (No Change)
# ============================
class Enrollment(models.Model):
    """
    This model links a Student to a TeacherClass and stores their grades.
    This replaces the old 'Grade' model.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments"
    )
    
    teacher_class = models.ForeignKey(
        TeacherClass,
        on_delete=models.CASCADE,
        related_name="enrollments"
    )

    q1 = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    q2 = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    q3 = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    q4 = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    pre_final = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Calculated final rating for this subject based on quarters"
    )

    is_finalized = models.BooleanField(
        default=False,
        help_text="If True, this grade record cannot be edited or deleted."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__last_name", "teacher_class__subject__name"]
        # A student can only be enrolled in a specific class once
        unique_together = ('student', 'teacher_class')
        indexes = [
            models.Index(fields=['is_finalized']),
        ]

    def __str__(self):
        return f"{self.student} - {self.teacher_class.subject.name}"

    @property
    def final_grade(self):
        """ Alias for pre_final, for consistency """
        return self.pre_final

# ============================
# ⭐️ ATTENDANCE MODEL (No Change) ⭐️
# ============================
class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
        ("Late", "Late"),
        ("Excused", "Excused"),
    ]

    QUARTER_CHOICES = [
        (1, "Quarter 1"),
        (2, "Quarter 2"),
        (3, "Quarter 3"),
        (4, "Quarter 4"),
    ]
    
    teacher_class = models.ForeignKey(
        TeacherClass, 
        on_delete=models.CASCADE, 
        related_name="attendance_records",
        null=True 
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )

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
# CLINIC VISIT MODEL (No Change)
# ============================
class ClinicVisit(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="clinic_visits"
    )
    visit_date = models.DateTimeField(auto_now_add=True) # This is the DateTimeField
    illness = models.CharField(max_length=255, db_index=True)
    treatment = models.TextField(blank=True, null=True)
    
    treatment_details = models.TextField(blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)

    attended_by = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-visit_date']
        indexes = [
            models.Index(fields=['illness']),
            models.Index(fields=['visit_date']),
        ]

    def __str__(self):
        return f"Clinic Visit - {self.student.last_name}, {self.student.first_name} ({self.visit_date.strftime('%Y-%m-%d %H:%M')})"


# ============================
# ⭐️ BEHAVIOR RECORD MODEL (CHANGED) ⭐️
# ============================
class BehaviorRecord(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="behavior_records"
    )

    # ⭐️ --- THIS IS THE CHANGE --- ⭐️
    # Changed from DateField to DateTimeField to include time
    date = models.DateTimeField(auto_now_add=True, db_index=True)
    # ⭐️ --- END OF CHANGE --- ⭐️

    category = models.CharField(max_length=255, db_index=True)

    offense_type = models.CharField(max_length=10, default="Minor") # "Minor" or "Major"
    offense_count = models.PositiveIntegerField(default=1)

    description = models.TextField()
    
    action_taken = models.CharField(max_length=255, blank=True, null=True)
    
    action_taken_details = models.TextField(blank=True, null=True)

    reported_by = models.CharField(max_length=100, blank=True, null=True) # e.g., Teacher Name

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'student__last_name', 'student__first_name']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"{self.student.last_name}, {self.student.first_name} - {self.category} ({self.date})"


# ==========================================================
# --- ⭐️ NEW MODEL: GLOBAL GRADE SETTINGS ⭐️ ---
# ==========================================================
class GradeSettings(models.Model):
    """
    Stores the global lock status for grade entry. 
    Only one instance of this model should ever exist.
    """
    
    # Defaults: Q1 open, others locked (closed/False)
    q1_open = models.BooleanField(default=True, help_text="Is Quarter 1 grade entry open for teachers?")
    q2_open = models.BooleanField(default=False, help_text="Is Quarter 2 grade entry open for teachers?")
    q3_open = models.BooleanField(default=False, help_text="Is Quarter 4 grade entry open for teachers?")
    q4_open = models.BooleanField(default=False, help_text="Is Quarter 4 grade entry open for teachers?")

    def __str__(self):
        return "Global Grade Lock Settings"

    def save(self, *args, **kwargs):
        # Enforce single instance constraint (prevents creating more than one)
        # Allows saving the current instance (self.pk is set)
        if not self.pk and GradeSettings.objects.exists():
            raise ValidationError("Cannot create more than one GradeSettings instance.")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Grade Lock Setting"
        verbose_name_plural = "Grade Lock Settings"
# ==========================================================
# --- ⭐️ END NEW MODEL ⭐️ ---


# ==========================================================
# AUTO-ENROLLMENT SIGNAL (No Change)
# ==========================================================

@receiver(post_save, sender=Student)
def auto_enroll_student_in_classes(sender, instance, created, **kwargs):
    """
    Signal to automatically enroll a student in all classes
    associated with their assigned section.
    
    This runs when a Student is created OR when their section is updated.
    """
    
    # Use transaction.atomic to ensure this all happens or none of it does
    try:
        with transaction.atomic():
            if instance.section:
                # Find all TeacherClasses linked to this student's section
                classes_to_enroll = TeacherClass.objects.filter(section=instance.section)
                
                # Get a list of classes the student is *already* enrolled in
                current_enrollments = Enrollment.objects.filter(student=instance)
                current_class_ids = current_enrollments.values_list('teacher_class__id', flat=True)

                # 1. Enroll in new classes
                new_enrollments = []
                for tc in classes_to_enroll:
                    if tc.id not in current_class_ids:
                        # Use get_or_create to be extra safe
                        Enrollment.objects.get_or_create(student=instance, teacher_class=tc)

                # 2. (Optional but recommended) Un-enroll from old classes
                new_section_class_ids = classes_to_enroll.values_list('id', flat=True)
                
                # Find enrollments in classes that are NOT part of the new section
                # and are not yet finalized.
                enrollments_to_remove = current_enrollments.exclude(
                    teacher_class__id__in=new_section_class_ids
                ).filter(
                    is_finalized=False # Safety check: don't remove finalized grades
                )
                
                if enrollments_to_remove.exists():
                    enrollments_to_remove.delete()
                    
            else:
                # If the student is un-assigned from a section (section=None)
                # Remove all their non-finalized enrollments
                Enrollment.objects.filter(student=instance, is_finalized=False).delete()
                
    except Exception as e:
        # Log this error if you have logging configured
        print(f"Error in auto-enroll signal for student {instance.id}: {e}")