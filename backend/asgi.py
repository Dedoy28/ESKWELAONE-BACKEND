# backend/asgi.py

import os
from django.core.asgi import get_asgi_application

# --- Step 1: Load Django Settings and Apps ---
# This MUST come before any other Django-related imports.
# This line initializes the Django app registry.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings") 
django_asgi_app = get_asgi_application()

# --- Step 2: Now it's safe to import Channels and your app's code ---
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
import students.routing  # <-- Now it's safe to import this
from students.middleware import TokenAuthMiddleware # <-- And this

# --- Step 3: Define the Application ---
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter(
                # This part was already correct
                students.routing.websocket_urlpatterns
            )
        )
    ),
})