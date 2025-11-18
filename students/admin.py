# /backend/students/admin.py (UPDATED FOR ALL REVISIONS)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

# Import all your models
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
    GradeSettings,
    SectionEnrollment  # <-- Import the new model
)

# --- UserProfile Admin (Unchanged) ---
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    fields = ('role',)

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

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
# --- End UserProfile Admin ---


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade', 'school_year', 'adviser_name')
    list_filter = ('grade', 'school_year')
    search_fields = ('name', 'adviser_name')
    

# --- ⭐️ FIX: This must be registered BEFORE it's used in inlines ---
@admin.register(TeacherClass)
class TeacherClassAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'teacher', 'subject', 'section', 'academic_year')
    list_filter = ('academic_year', 'teacher', 'subject', 'section__grade')
    search_fields = ('teacher__username', 'subject__name', 'section__name')
    autocomplete_fields = ('teacher', 'subject', 'section')


# --- ⭐️ NEW: Inline for Section History ⭐️ ---
class SectionEnrollmentInline(admin.TabularInline):
    model = SectionEnrollment
    extra = 1 # Show one extra blank row for adding history
    autocomplete_fields = ['section']
    verbose_name = "Section Enrollment"
    verbose_name_plural = "Section Enrollment History"
    fk_name = "student"

# --- ⭐️ UPDATED: Student Admin ⭐️ ---
class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    autocomplete_fields = ('teacher_class',)
    readonly_fields = ('pre_final',)
    fields = ('teacher_class', 'q1', 'q2', 'q3', 'q4', 'pre_final', 'is_finalized')

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    # ⭐️ FIX: Changed 'student_id' to 'lrn' and removed old fields
    list_display = ('lrn', 'last_name', 'first_name', 'is_active', 'get_current_grade', 'get_current_section')
    
    # ⭐️ FIX: Changed filter paths to use the new relationship
    list_filter = (
        'is_active', 
        'gender', 
        'section_enrollments__section__grade',  # New path
        'section_enrollments__section__name',  # New path
        'section_enrollments__school_year'  # New path
    )
    
    # ⭐️ FIX: Changed 'student_id' to 'lrn'
    search_fields = ('lrn', 'first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'general_average')
    
    # ⭐️ FIX: Removed 'section' from autocomplete_fields
    autocomplete_fields = () 
    
    # ⭐️ FIX: Added SectionEnrollmentInline to manage history
    inlines = [SectionEnrollmentInline, EnrollmentInline] 
    
    fieldsets = (
        # ⭐️ FIX: Changed 'student_id' to 'lrn'
        (None, {'fields': ('lrn', 'first_name', 'middle_name', 'last_name', 'name_extension', 'is_active')}),
        
        # ⭐️ FIX: Removed 'Academic Info' fieldset
        
        ('SF10 Eligibility Info', {
            'fields': (
                'elementary_school', 
                'elementary_school_id', 
                'elementary_school_address', 
                'elementary_gen_ave'
            )
        }),
        ('Personal Info', {'fields': ('birth_date', 'gender', 'email', 'phone', 'address')}),
        ('Guardian Info', {'fields': ('guardian_name', 'guardian_phone', 'guardian_email')}),
        ('Emergency & Medical', {'fields': ('emergency_contact', 'medical_notes')}),
        ('System Info', {'fields': ('general_average', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    # ⭐️ NEW: Custom functions to display current grade/section
    @admin.display(description='Current Grade', ordering='section_enrollments__section__grade')
    def get_current_grade(self, obj):
        enrollment = obj.section_enrollments.filter(is_active=True).first()
        if enrollment:
            return enrollment.section.grade
        return "N/A"

    @admin.display(description='Current Section', ordering='section_enrollments__section__name')
    def get_current_section(self, obj):
        enrollment = obj.section_enrollments.filter(is_active=True).first()
        if enrollment:
            return enrollment.section.name
        return "N/A"

# --- ⭐️ NEW: Admin for SectionEnrollment ⭐️ ---
@admin.register(SectionEnrollment)
class SectionEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'section', 'school_year', 'is_active')
    list_filter = ('school_year', 'section__grade', 'section__name', 'is_active')
    # ⭐️ FIX: Changed 'student__student_id' to 'student__lrn'
    search_fields = ('student__last_name', 'student__lrn', 'section__name')
    autocomplete_fields = ['student', 'section']


# --- UPDATED: Enrollment Admin ---
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher_class', 'q1', 'q2', 'q3', 'q4', 'pre_final', 'is_finalized')
    list_filter = ('is_finalized', 'teacher_class__subject', 'teacher_class__section__grade')
    # ⭐️ FIX: Changed 'student__student_id' to 'student__lrn'
    search_fields = ('student__last_name', 'student__first_name', 'student__lrn', 'teacher_class__subject__name')
    autocomplete_fields = ('student', 'teacher_class')
    readonly_fields = ('pre_final', 'created_at', 'updated_at')


# --- ⭐️ UPDATED: AttendanceRecord Admin ⭐️ ---
@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'quarter', 'status', 'teacher_class')
    # ⭐️ FIX: Changed filter paths to use TeacherClass's section
    list_filter = ('date', 'status', 'quarter', 'teacher_class__section__grade', 'teacher_class__section__name')
    # ⭐️ FIX: Changed 'student__student_id' to 'student__lrn'
    search_fields = ('student__lrn', 'student__last_name', 'student__first_name')
    date_hierarchy = 'date'
    autocomplete_fields = ('student', 'teacher_class')


# --- ⭐️ UPDATED: ClinicVisit Admin ⭐️ ---
@admin.register(ClinicVisit)
class ClinicVisitAdmin(admin.ModelAdmin):
    list_display = ('student', 'visit_date', 'illness', 'attended_by')
    # ⭐️ FIX: Changed filter paths to use SectionEnrollment
    list_filter = ('visit_date', 'illness', 'student__section_enrollments__section__grade')
    
    # ⭐️ FIX: Changed 'student__student_id' to 'student__lrn'
    search_fields = ('student__lrn', 'student__last_name', 'student__first_name', 'illness', 'attended_by')
    date_hierarchy = 'visit_date'
    autocomplete_fields = ('student',)
    
# --- ⭐️ UPDATED: BehaviorRecord Admin ⭐️ ---
@admin.register(BehaviorRecord)
class BehaviorRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'offense_type', 'offense_count', 'category', 'reported_by')
    # ⭐️ FIX: Changed filter paths to use SectionEnrollment
    list_filter = ('date', 'offense_type', 'category', 'student__section_enrollments__section__grade')
    # ⭐️ FIX: Changed 'student__student_id' to 'student__lrn'
    search_fields = ('student__lrn', 'student__last_name', 'student__first_name', 'description', 'reported_by')
    date_hierarchy = 'date'
    autocomplete_fields = ('student',)


# --- UPDATED: GradeSettings Admin ---
@admin.register(GradeSettings)
class GradeSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'q1_open', 'q2_open', 'q3_open', 'q4_open')
    list_editable = ('q1_open', 'q2_open', 'q3_open', 'q4_open')
    fields = ('q1_open', 'q2_open', 'q3_open', 'q4_open')

    def has_add_permission(self, request):
        return not GradeSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False