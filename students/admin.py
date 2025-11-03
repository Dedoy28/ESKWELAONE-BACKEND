# /backend/students/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

# 👇 Import all the NEW and CURRENT models
from .models import (
    Student, 
    Section, 
    Subject, 
    TeacherClass, 
    Enrollment,
    AttendanceRecord,
    ClinicVisit,
    BehaviorRecord,
    UserProfile,
    # --- ⭐️ NEW IMPORT ⭐️ ---
    GradeSettings 
)

# --- Updated UserProfile Admin ---
# This inline only shows the 'role', since 'allowed_subjects' was removed.
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    fields = ('role',) # Only show 'role'

# Define a new User admin
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')
    list_select_related = ('profile',)

    @admin.display(description='Role')
    def get_role(self, instance):
        try:
            return instance.profile.get_role_display()
        except UserProfile.DoesNotExist:
            return 'No Profile'

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
# --- End UserProfile Admin ---


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    # 'subject' field removed from list_display and search_fields
    list_display = ('name', 'grade', 'school_year', 'adviser_name')
    list_filter = ('grade', 'school_year')
    search_fields = ('name', 'adviser_name')


# --- NEW: Admin for TeacherClass (Teacher's Load) ---
@admin.register(TeacherClass)
class TeacherClassAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'teacher', 'subject', 'section', 'academic_year')
    list_filter = ('academic_year', 'teacher', 'subject', 'section__grade')
    search_fields = ('teacher__username', 'subject__name', 'section__name')
    # Autocomplete fields make it easy to link ForeignKeys
    autocomplete_fields = ('teacher', 'subject', 'section')


# --- Updated Student Admin ---
class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0 # Don't show extra blank forms
    autocomplete_fields = ('teacher_class',)
    readonly_fields = ('pre_final',)
    fields = ('teacher_class', 'q1', 'q2', 'q3', 'q4', 'pre_final', 'is_finalized')

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'last_name', 'first_name', 'grade', 'section', 'is_active')
    list_filter = ('grade', 'section', 'is_active', 'gender', 'school_year')
    search_fields = ('student_id', 'first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'general_average')
    autocomplete_fields = ('section',) # Section is now a ForeignKey
    inlines = [EnrollmentInline] # Show enrollments directly on the student page
    
    # --- UPDATED THE FIELDSETS ---
    fieldsets = (
        (None, {'fields': ('student_id', 'first_name', 'middle_name', 'last_name', 'name_extension', 'is_active')}),
        ('Academic Info', {'fields': ('grade', 'section', 'school_year')}),
        
        # --- NEW SECTION FOR SF10 ---
        ('SF10 Eligibility Info', {
            'fields': (
                'elementary_school', 
                'elementary_school_id', 
                'elementary_school_address', 
                'elementary_gen_ave'
            )
        }),
        # --- END NEW SECTION ---
        
        ('Personal Info', {'fields': ('birth_date', 'gender', 'email', 'phone', 'address')}),
        ('Guardian Info', {'fields': ('guardian_name', 'guardian_phone', 'guardian_email')}),
        ('Emergency & Medical', {'fields': ('emergency_contact', 'medical_notes')}),
        ('System Info', {'fields': ('general_average', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    # --- END UPDATED FIELDSETS ---

# --- NEW: Admin for Enrollment (Replaces Grade) ---
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher_class', 'q1', 'q2', 'q3', 'q4', 'pre_final', 'is_finalized')
    list_filter = ('is_finalized', 'teacher_class__subject', 'teacher_class__section__grade')
    search_fields = ('student__last_name', 'student__first_name', 'teacher_class__subject__name')
    autocomplete_fields = ('student', 'teacher_class')
    readonly_fields = ('pre_final', 'created_at', 'updated_at')


# --- Other Models (Updated with autocomplete) ---

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'quarter', 'status')
    list_filter = ('date', 'quarter', 'status', 'student__grade', 'student__section')
    search_fields = ('student__student_id', 'student__last_name', 'student__first_name')
    date_hierarchy = 'date'
    autocomplete_fields = ('student',)


@admin.register(ClinicVisit)
class ClinicVisitAdmin(admin.ModelAdmin):
    # ⭐️ --- THIS IS THE FIX (Part 1) --- ⭐️
    list_display = ('student', 'visit_date', 'illness', 'attended_by')
    # ⭐️ --- THIS IS THE FIX (Part 2) --- ⭐️
    list_filter = ('visit_date', 'illness', 'student__grade', 'student__section')
    
    search_fields = ('student__student_id', 'student__last_name', 'student__first_name', 'illness', 'attended_by')
    date_hierarchy = 'visit_date'
    autocomplete_fields = ('student',)


# --- BehaviorRecordAdmin ---
@admin.register(BehaviorRecord)
class BehaviorRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'offense_type', 'offense_count', 'category', 'reported_by')
    list_filter = ('date', 'offense_type', 'category', 'student__grade', 'student__section')
    search_fields = ('student__student_id', 'student__last_name', 'student__first_name', 'description', 'reported_by')
    date_hierarchy = 'date'
    autocomplete_fields = ('student',)


# -----------------------------------------------------
# ⭐️ NEW: ADMIN FOR GLOBAL GRADE LOCKS ⭐️
# -----------------------------------------------------

@admin.register(GradeSettings)
class GradeSettingsAdmin(admin.ModelAdmin):
    # Display all the open/lock fields
    list_display = ('id', 'q1_open', 'q2_open', 'q3_open', 'q4_open')
    # Allow quick editing directly from the list view (easier for Admin)
    list_editable = ('q1_open', 'q2_open', 'q3_open', 'q4_open')
    
    # Hide the save button and only show the fields (optional, but cleaner)
    fields = ('q1_open', 'q2_open', 'q3_open', 'q4_open')

    def has_add_permission(self, request):
        # Prevent adding new instances if one already exists
        return not GradeSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deleting the single existing instance
        return False
# -----------------------------------------------------
# END NEW ADMIN REGISTRATION
# -----------------------------------------------------