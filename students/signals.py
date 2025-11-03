# students/signals.py

from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from decimal import Decimal, InvalidOperation
from django.utils import timezone # ⭐️ --- 1. ADD THIS IMPORT --- ⭐️

# --- MODIFIED IMPORTS ---
from .models import (
    Student, 
    Enrollment, 
    TeacherClass, 
    Subject,
    AttendanceRecord,
    ClinicVisit,      # <-- This model is now used
    BehaviorRecord
)
# --- END MODIFIED IMPORTS ---

REQUIRED_SUBJECTS = [
    "Filipino", "English", "Mathematics", "Science", "Araling Panlipunan (AP)",
    "Edukasyon sa Pagpapakatao (EsP)", "Technology and Livelihood Education (TLE)", "MAPEH",
]

# --- Helper functions to get serializers ---
def get_enrollment_serializer():
    from .serializers import EnrollmentSerializer
    return EnrollmentSerializer

def get_student_serializer():
    from .serializers import StudentSerializer
    return StudentSerializer

def get_behavior_record_serializer():
    from .serializers import BehaviorRecordSerializer
    return BehaviorRecordSerializer

def get_clinic_visit_serializer():
    from .serializers import ClinicVisitSerializer
    return ClinicVisitSerializer


# ======================================================
# ⭐️ 2. ADD NEW DASHBOARD HELPER FUNCTIONS ⭐️
# ======================================================

def _get_sync_dashboard_stats():
    """
    A SYNCHRONOUS helper to get the 4 dashboard counts.
    This is safe to call from signals.
    """
    today = timezone.now().date()
    
    total_students = Student.objects.count()
    active_records = Student.objects.filter(is_active=True).count()
    clinic_visits_today = ClinicVisit.objects.filter(visit_date__date=today).count()
    behavioral_reports = BehaviorRecord.objects.count()

    return {
        "totalStudents": total_students,
        "activeRecords": active_records,
        "clinicVisits": clinic_visits_today,
        "behavioralReports": behavioral_reports,
    }

def _broadcast_dashboard_stats():
    """
    Helper to fetch and send dashboard stats to the 'dashboard_updates' group.
    """
    print("Signal: Broadcasting dashboard stats update.")
    try:
        # Get the new stats synchronously
        stats = _get_sync_dashboard_stats()
        
        channel_layer = get_channel_layer()
        group_name = "dashboard_updates"
        message = {
            "type": "dashboard.update", # This maps to DashboardConsumer.dashboard_update
            "stats": stats
        }
        
        # Send the message to the channel group
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        print(f"CRITICAL Error in _broadcast_dashboard_stats: {e}")

# ======================================================
# ⭐️ END NEW DASHBOARD HELPER FUNCTIONS ⭐️
# ======================================================


def calculate_and_update_student_average(student_id, academic_year):
    # ... (This function is unchanged)
    try:
        student = Student.objects.get(pk=student_id)
        enrollments = Enrollment.objects.filter(
            student=student, 
            teacher_class__academic_year=academic_year
        ).select_related('teacher_class__subject') 

        required_grades_with_final = []
        all_required_subjects_present = True
        
        required_subjects_in_enrollments = {
            e.teacher_class.subject.name 
            for e in enrollments 
            if e.teacher_class.subject.name in REQUIRED_SUBJECTS
        }

        if len(required_subjects_in_enrollments) < len(REQUIRED_SUBJECTS):
            all_required_subjects_present = False

        if all_required_subjects_present:
            for subject_name in REQUIRED_SUBJECTS:
                subject_enrollment = next(
                    (e for e in enrollments if e.teacher_class.subject.name == subject_name), 
                    None
                )
                if subject_enrollment is None or subject_enrollment.pre_final is None:
                    required_grades_with_final = [] 
                    break
                required_grades_with_final.append(subject_enrollment.pre_final)

        new_average = None
        if len(required_grades_with_final) == len(REQUIRED_SUBJECTS):
            try:
                total = sum(required_grades_with_final)
                new_average = round(total / Decimal(len(required_grades_with_final)), 2)
            except (TypeError, InvalidOperation):
                new_average = None
        
        if student.general_average != new_average:
            student.general_average = new_average
            student.save(update_fields=['general_average'])
            return new_average
        else:
            return student.general_average 

    except Student.DoesNotExist:
        print(f"Error: Student with ID {student_id} not found during average calculation.")
        return None
    except Exception as e:
        print(f"Error calculating/updating average for student {student_id}: {e}")
        return None


@receiver(post_save, sender=Enrollment)
def enrollment_post_save(sender, instance: Enrollment, created, **kwargs):
    # ... (This function is unchanged)
    print(f"Signal: post_save received for Enrollment ID {instance.id}")
    student_id = instance.student_id
    academic_year = instance.teacher_class.academic_year 

    quarters = [instance.q1, instance.q2, instance.q3, instance.q4]
    valid_quarters = [q for q in quarters if q is not None]
    calculated_pre_final = None

    if len(valid_quarters) == 4:
        try:
            total = sum(valid_quarters)
            calculated_pre_final = round(total / Decimal(4), 2)
        except (TypeError, InvalidOperation):
            calculated_pre_final = None 

    pre_final_changed = False
    if instance.pre_final != calculated_pre_final:
        instance.pre_final = calculated_pre_final
        pre_final_changed = True
        print(f"Signal: Updating pre_final for Enrollment ID {instance.id} to {calculated_pre_final}")
        instance.save(update_fields=['pre_final'])

    updated_general_average = calculate_and_update_student_average(student_id, academic_year)

    channel_layer = get_channel_layer()
    group_name = f"student_{student_id}" 

    if pre_final_changed:
        try:
            instance.refresh_from_db(fields=['pre_final'])
        except Enrollment.DoesNotExist:
            print(f"Error: Enrollment {instance.id} not found after pre_final update, cannot send WS message.")
            return 

    EnrollmentSerializer = get_enrollment_serializer()
    enrollment_data = EnrollmentSerializer(instance).data

    message = {
        "type": "broadcast_message",
        "payload": {
            "type": "enrollment_update", 
            "student_id": student_id,
            "enrollment": enrollment_data,
            "general_average": updated_general_average,
            "action": "created" if created else "updated",
            "updated_enrollment_id": instance.id
        }
    }
    print(f"Signal: Sending WS message to group {group_name}: {message['payload']['type']}")
    async_to_sync(channel_layer.group_send)(group_name, message)


@receiver(post_delete, sender=Enrollment)
def enrollment_post_delete(sender, instance: Enrollment, **kwargs):
    # ... (This function is unchanged)
    print(f"Signal: post_delete received for Enrollment ID {instance.id}")
    student_id = instance.student_id
    academic_year = instance.teacher_class.academic_year

    updated_general_average = calculate_and_update_student_average(student_id, academic_year)

    channel_layer = get_channel_layer()
    group_name = f"student_{student_id}"

    message = {
        "type": "broadcast_message",
        "payload": {
            "type": "enrollment_deleted",
            "student_id": student_id,
            "enrollment_id": instance.id,
            "general_average": updated_general_average,
            "action": "deleted"
        }
    }

    print(f"Signal: Sending WS message to group {group_name}: {message['payload']['type']}")
    async_to_sync(channel_layer.group_send)(group_name, message)


@receiver(post_save, sender=Student)
def student_changed(sender, instance: Student, created, **kwargs):
    """
    Broadcasts changes on the Student model itself (e.g., name, section, is_active).
    """
    
    # ... (This part is unchanged)
    update_fields = kwargs.get('update_fields')
    if update_fields and 'general_average' in update_fields and len(update_fields) == 1:
        print(f"Signal: Skipping student_changed for {instance.id} (general_average update).")
        return

    channel_layer = get_channel_layer()
    action = "created" if created else "updated"
    
    StudentSerializer = get_student_serializer()
    
    try:
        full_instance = Student.objects.select_related(
            'section'
        ).prefetch_related(
            "attendance_records",
            "enrollments__teacher_class__subject",
            "enrollments__teacher_class__teacher",
            "enrollments__teacher_class__section"
        ).get(pk=instance.pk)
        
        student_data = StudentSerializer(full_instance, context={'request': None}).data
    except Student.DoesNotExist:
        print(f"Error in student_changed signal: Student {instance.pk} not found. Cannot serialize.")
        return
    except Exception as e:
        print(f"CRITICAL Error in student_changed signal while serializing: {e}")
        return

    # --- 1. Send to student-specific group (for detail pages) ---
    specific_group_name = f"student_{instance.id}"
    specific_payload = {
        "type": "broadcast_message", 
        "payload": {
            "type": "student_update", 
            "action": action,
            "student": student_data 
        }
    }
    print(f"Signal: Sending WS message to group {specific_group_name}: student_update")
    async_to_sync(channel_layer.group_send)(specific_group_name, specific_payload)


    # --- 2. Send to general list group (for main StudentManagement page) ---
    list_group_name = "student_list_updates"
    list_payload = {
        "type": "student.update", 
        "action": action,
        "student": student_data
    }
    
    print(f"Signal: Sending WS message to group {list_group_name}: student.update")
    async_to_sync(channel_layer.group_send)(list_group_name, list_payload)

    # ⭐️ --- 3. BROADCAST DASHBOARD UPDATE --- ⭐️
    # This change affects 'totalStudents' and 'activeRecords'
    _broadcast_dashboard_stats()


# ⭐️ --- 4. ADD NEW RECEIVER FOR STUDENT DELETION --- ⭐️
@receiver(post_delete, sender=Student)
def student_post_delete(sender, instance: Student, **kwargs):
    """
    Handles when a student is deleted.
    """
    print(f"Signal: post_delete received for Student ID {instance.id}")
    
    # --- 1. Send update to general student list ---
    channel_layer = get_channel_layer()
    group_name = "student_list_updates"
    message = {
        "type": "student.update",
        "action": "deleted",
        "student": {"id": instance.id} # Send just the ID for deletion
    }
    print(f"Signal: Sending WS message to group {group_name}: student.update (delete)")
    async_to_sync(channel_layer.group_send)(group_name, message)

    # --- 2. BROADCAST DASHBOARD UPDATE ---
    # This change affects 'totalStudents' and 'activeRecords'
    _broadcast_dashboard_stats()


# ======================================================
# 📍 Behavior Record Signals
# ======================================================

@receiver(post_save, sender=BehaviorRecord)
def behavior_record_post_save(sender, instance: BehaviorRecord, created, **kwargs):
    # ... (This part is unchanged)
    print(f"Signal: post_save received for BehaviorRecord ID {instance.id}")
    channel_layer = get_channel_layer()
    group_name = "behavior_updates" 
    action = "create" if created else "update"

    BehaviorRecordSerializer = get_behavior_record_serializer()
    try:
        instance_with_student = BehaviorRecord.objects.select_related('student', 'student__section').get(pk=instance.pk)
        record_data = BehaviorRecordSerializer(instance_with_student).data
    except BehaviorRecord.DoesNotExist:
        print(f"Error: BehaviorRecord {instance.id} not found after save, cannot serialize for WS.")
        return
    except Exception as e:
        print(f"Error serializing BehaviorRecord {instance.id}: {e}")
        return

    message = {
        "type": "behavior.update",
        "action": action,
        "behavior_record": record_data
    }

    print(f"Signal: Sending WS message to group {group_name}: behavior.update ({action})")
    async_to_sync(channel_layer.group_send)(group_name, message)

    # ⭐️ --- 5. BROADCAST DASHBOARD UPDATE --- ⭐️
    # This change affects 'behavioralReports'
    _broadcast_dashboard_stats()


@receiver(post_delete, sender=BehaviorRecord)
def behavior_record_post_delete(sender, instance: BehaviorRecord, **kwargs):
    # ... (This part is unchanged)
    print(f"Signal: post_delete received for BehaviorRecord ID {instance.id}")
    channel_layer = get_channel_layer()
    group_name = "behavior_updates" 

    message = {
        "type": "behavior.update", 
        "action": "delete",
        "behavior_record": { 
             "id": instance.id,
             "student_id": instance.student_id 
        }
    }

    print(f"Signal: Sending WS message to group {group_name}: behavior.update (delete)")
    async_to_sync(channel_layer.group_send)(group_name, message)

    # ⭐️ --- 6. BROADCAST DASHBOARD UPDATE --- ⭐️
    # This change affects 'behavioralReports'
    _broadcast_dashboard_stats()


@receiver(post_save, sender=ClinicVisit)
def clinic_visit_post_save(sender, instance: ClinicVisit, created, **kwargs):
    """
    Broadcasts creates and updates for ClinicVisit records.
    """
    # ... (This part is unchanged)
    print(f"Signal: post_save received for ClinicVisit ID {instance.id}")
    channel_layer = get_channel_layer()
    group_name = "clinic_updates" 
    action = "create" if created else "update"

    ClinicVisitSerializer = get_clinic_visit_serializer()
    try:
        instance_with_student = ClinicVisit.objects.select_related('student', 'student__section').get(pk=instance.pk)
        record_data = ClinicVisitSerializer(instance_with_student).data
    except ClinicVisit.DoesNotExist:
        print(f"Error: ClinicVisit {instance.id} not found after save, cannot serialize for WS.")
        return
    except Exception as e:
        print(f"Error serializing ClinicVisit {instance.id}: {e}")
        return

    message = {
        "type": "clinic.update", 
        "action": action,
        "clinic_visit": record_data
    }

    print(f"Signal: Sending WS message to group {group_name}: clinic.update ({action})")
    async_to_sync(channel_layer.group_send)(group_name, message)

    # ⭐️ --- 7. BROADCAST DASHBOARD UPDATE --- ⭐️
    # This change affects 'clinicVisits'
    _broadcast_dashboard_stats()


@receiver(post_delete, sender=ClinicVisit)
def clinic_visit_post_delete(sender, instance: ClinicVisit, **kwargs):
    """
    Broadcasts deletes for ClinicVisit records.
    """
    # ... (This part is unchanged)
    print(f"Signal: post_delete received for ClinicVisit ID {instance.id}")
    channel_layer = get_channel_layer()
    group_name = "clinic_updates" 

    message = {
        "type": "clinic.update", 
        "action": "delete",
        "clinic_visit": { 
             "id": instance.id,
             "student": { "id": instance.student_id } 
        }
    }

    print(f"Signal: Sending WS message to group {group_name}: clinic.update (delete)")
    async_to_sync(channel_layer.group_send)(group_name, message)

    # ⭐️ --- 8. BROADCAST DASHBOARD UPDATE --- ⭐️
    # This change affects 'clinicVisits'
    _broadcast_dashboard_stats()