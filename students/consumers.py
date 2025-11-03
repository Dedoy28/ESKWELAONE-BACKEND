import json
import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.db.models import Q
from django.utils import timezone # ⭐️ --- 1. ADD THIS IMPORT --- ⭐️

# ⭐️ --- 2. ADD ClinicVisit and BehaviorRecord TO THIS IMPORT --- ⭐️
from students.models import UserProfile, Student, ClinicVisit, BehaviorRecord


# ⭐️ --- 3. ADD THIS HELPER FUNCTION --- ⭐️
@sync_to_async
def get_user_role(user):
    """
    Fetches the user's profile role from the database.
    """
    if user.is_anonymous:
        return None
    try:
        # We must access the related 'profile' object to get the role
        return user.profile.role
    except UserProfile.DoesNotExist:
        print(f"WS Auth Error: UserProfile does not exist for user {user.username}")
        return None
    except Exception as e:
        print(f"Error getting user role: {e}")
        return None


# ⭐️ --- 4. ADD THIS NEW HELPER FUNCTION --- ⭐️
@sync_to_async
def get_dashboard_stats():
    """
    Fetches the four key dashboard statistics from the database.
    This is called by signals to get the new counts.
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

# ======================================================
# STUDENT LIST CONSUMER (For the main management page)
# ======================================================
class StudentListConsumer(AsyncWebsocketConsumer):
    """
    Handles connections for the main student management page (ws/students/).
    Broadcasts general student list updates.
    """
    async def connect(self):
        self.user = self.scope['user']
        
        # 1. Check if user is authenticated
        if self.user.is_anonymous:
            print("StudentList WS rejected: User is not authenticated.")
            await self.close()
            return

        # 2. Get user role from the database
        user_role = await get_user_role(self.user)

        # 3. Check if role is allowed
        if user_role not in ['admin', 'registrar']:
            print(f"StudentList WS rejected: User role '{user_role}' is not authorized.")
            await self.close()
            return

        self.group_name = 'student_list_updates'
        print(f"StudentList WS attempting connection, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] User {self.user.id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] User {self.scope['user'].id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received message on student_list WS: {text_data}") # Log messages from client if any

    async def student_update(self, event):
        """ Handles 'student.update' type messages from signals. """
        print(f"Broadcasting student_update to group {self.group_name}")
        await self.send(text_data=json.dumps({
            'action': event.get('action'),
            'student': event.get('student'),
        }))
        print(f"Sent student_update payload to client {self.channel_name}")


# ======================================================
# STUDENT CONSUMER (For a specific student's detail page)
# ======================================================
class StudentConsumer(AsyncWebsocketConsumer):
    """ Handles connections related to a single student (ws/students/<id>/). """
    async def connect(self):
        self.student_id = self.scope['url_route']['kwargs'].get('student_id')
        if not self.student_id:
            print("Student WS rejected: No student ID provided in URL.")
            await self.close()
            return

        self.group_name = f'student_{self.student_id}'
        print(f"Student WS attempting connection for student {self.student_id}, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] Student {self.student_id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] Student {self.student_id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received message on student {self.student_id} WS: {text_data}")

    async def broadcast_message(self, event):
        """ Handles various message types sent to the student-specific group. """
        payload = event.get('payload', {})
        message_type = payload.get('type', 'unknown_message')
        print(f"Broadcasting {message_type} to student {self.student_id} group")
        await self.send(text_data=json.dumps(payload))
        print(f"Sent {message_type} payload to client {self.channel_name}")


# ======================================================
# 📍 ATTENDANCE CONSUMER (Handles ws/attendance/)
# ======================================================
class AttendanceConsumer(AsyncWebsocketConsumer):
    """ Handles connections for general attendance updates (ws/attendance/). """
    async def connect(self):
        if self.scope['user'].is_anonymous:
            print("Attendance WS rejected: User is not authenticated.")
            await self.close()
            return

        # Use a consistent group name for all general attendance updates
        self.group_name = 'attendance_updates'
        print(f"Attendance WS attempting connection, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] User {self.scope['user'].id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] User {self.scope['user'].id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received message on attendance WS: {text_data}")

    async def attendance_update(self, event):
        """ Handles 'attendance.update' type messages from signals. """
        print(f"Broadcasting attendance_update to group {self.group_name}")
        await self.send(text_data=json.dumps({
            'action': event.get('action'),
            'attendance': event.get('attendance'), 
        }))
        print(f"Sent attendance_update payload to client {self.channel_name}")


# ======================================================
# REPORT CONSUMER (Live Search)
# ======================================================
class ReportConsumer(AsyncWebsocketConsumer):
    """ Handles live search requests for reports (ws/reports/). """
    async def connect(self):
        await self.accept()
        print(f"✅ [WS Connected] Reports: {self.channel_name}")

    async def disconnect(self, close_code):
        print(f"❌ [WS Disconnected] Reports: {self.channel_name}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get("action")
            search = data.get("search", "").strip()
            
            # Get the filters from the WebSocket message
            grade = data.get("grade") 
            section = data.get("section")
            print(f"ReportConsumer received action: {action}, search: '{search}', grade: {grade}, section: {section}")

            if action == "search_student":
                # Pass all filters to the search function
                results = await self.search_students(search, grade, section)
                await self.send(text_data=json.dumps({"status": "ok", "results": results}))
            
            else:
                await self.send(text_data=json.dumps({"status": "error", "message": f"Unknown or invalid action: {action}"}))

        except json.JSONDecodeError:
            print(f"Invalid JSON received on reports WS: {text_data}")
            await self.send(text_data=json.dumps({"status": "error", "message": "Invalid request format."}))
        except Exception as e:
            print(f"Error in ReportConsumer receive: {e}")
            await self.send(text_data=json.dumps({"status": "error", "message": f"An server error occurred."}))


    @sync_to_async
    def search_students(self, search, grade, section):
        # Start with an empty Q object to build the query
        query = Q()

        # Add text search if provided
        if search:
            query.add(
                Q(student_id__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search),
                Q.AND
            )

        # Add grade filter if provided and not "all"
        if grade and grade != "all":
            query.add(Q(grade=grade), Q.AND)
        
        # Add section filter if provided and not "all"
        if section and section != "all":
            # Filter by the related Section model's 'name' field
            query.add(Q(section__name__iexact=section), Q.AND)
        
        # Ensure we don't return an empty query (which would fetch all students)
        if not search and (not grade or grade == "all") and (not section or section == "all"):
            return [] # Return empty list if no filters are active

        # Run the query
        qs = Student.objects.filter(query).select_related('section').order_by('last_name', 'first_name')[:10]

        # Manually build the results to match the frontend's SearchResultStudent interface
        results = []
        for s in qs:
            results.append({
                "id": s.id,
                "student_id": s.student_id,
                "name": f"{s.last_name}, {s.first_name} {s.middle_name or ''}".strip(),
                "grade": s.grade,
                "section": s.section.name if s.section else "N/A"
            })
        return results


# ======================================================
# 📍 CLINIC CONSUMER (Handles ws/clinic/)
# ======================================================
class ClinicConsumer(AsyncWebsocketConsumer):
    """ Handles connections for general clinic visit updates (ws/clinic/). """
    async def connect(self):
        if self.scope['user'].is_anonymous:
            print("Clinic WS rejected: User is not authenticated.")
            await self.close()
            return

        self.group_name = 'clinic_updates'
        print(f"Clinic WS attempting connection, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] User {self.scope['user'].id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] User {self.scope['user'].id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received message on clinic WS: {text_data}")
        
    async def clinic_update(self, event):
        """ Handles 'clinic.update' type messages from signals. """
        print(f"Broadcasting clinic_update to group {self.group_name}")
        
        # ⭐️ --- Fix: use 'clinic_visit' to match signals.py --- ⭐️
        clinic_data = event.get('clinic_visit')
        if not clinic_data:
            print("Warning: Received clinic_update event without 'clinic_visit' data.")
            return

        await self.send(text_data=json.dumps({
            'action': event.get('action'),
            'clinic_visit': clinic_data, # ⭐️ --- Fix --- ⭐️
        }))
        print(f"Sent clinic_update payload to client {self.channel_name}")


# ======================================================
# 📍 BEHAVIOR CONSUMER (Handles ws/behavior/)
# ======================================================
class BehaviorConsumer(AsyncWebsocketConsumer):
    """ Handles connections for general behavior record updates (ws/behavior/). """
    async def connect(self):
        if self.scope['user'].is_anonymous:
            print("Behavior WS rejected: User is not authenticated.")
            await self.close()
            return

        self.group_name = 'behavior_updates'
        print(f"Behavior WS attempting connection, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] User {self.scope['user'].id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] User {self.scope['user'].id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received message on behavior WS: {text_data}")

    async def behavior_update(self, event):
        """ Handles 'behavior.update' type messages from signals. """
        print(f"Broadcasting behavior_update to group {self.group_name}")
        
        behavior_data = event.get('behavior_record') 
        if not behavior_data:
             print("Warning: Received behavior_update event without 'behavior_record' data.")
             return 

        await self.send(text_data=json.dumps({
            'action': event.get('action'),
            'behavior_record': behavior_data 
        }))
        print(f"Sent behavior_update payload to client {self.channel_name}")


# ======================================================
# ⭐️ 5. ADD THIS NEW DASHBOARD CONSUMER ⭐️
# (Handles ws/dashboard-updates/)
# ======================================================
class DashboardConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time updates for the main dashboard.
    Broadcasts new aggregate stats when data changes.
    """
    async def connect(self):
        self.user = self.scope['user']
        
        # 1. Check if user is authenticated
        if self.user.is_anonymous:
            print("Dashboard WS rejected: User is not authenticated.")
            await self.close()
            return
        
        # 2. Add any authenticated user to the dashboard group
        self.group_name = 'dashboard_updates'
        print(f"Dashboard WS attempting connection, joining group {self.group_name}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ [WS Connected] User {self.user.id} ({self.channel_name}), Group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            print(f"❌ [WS Disconnected] User {self.scope['user'].id} ({self.channel_name}), Leaving group {self.group_name}")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        # This consumer doesn't need to receive data from the client,
        # but we can add a "fetch" action if the client wants a manual refresh.
        try:
            data = json.loads(text_data)
            if data.get('action') == 'fetch_stats':
                print("Dashboard WS: Client requested manual stats refresh.")
                # We use the helper function to get fresh stats
                stats = await get_dashboard_stats() 
                await self.send(text_data=json.dumps({
                    'type': 'stats_update',
                    'payload': stats
                }))
        except Exception as e:
            print(f"Error in DashboardConsumer receive: {e}")

    async def dashboard_update(self, event):
        """
        Handles 'dashboard.update' messages sent from signals.
        The event is expected to contain the full, pre-calculated stats payload.
        """
        print(f"Broadcasting dashboard_update to group {self.group_name}")
        stats_payload = event.get('stats')
        
        if stats_payload:
            # Send the payload to the connected client
            await self.send(text_data=json.dumps({
                'type': 'stats_update', # This 'type' is for the frontend client
                'payload': stats_payload
            }))
            print(f"Sent dashboard_update payload to client {self.channel_name}")
        else:
            print("Warning: Received dashboard_update event without 'stats' data.")