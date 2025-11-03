# backend/backend/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

# 1. 👈 Import your app's routing (students ALREADY includes reports)
import students.routing 

# 2. 👈 Import the custom middleware
from students.middleware import TokenAuthMiddleware

# --- Ensure Django settings are loaded ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings") 

# --- Get standard Django HTTP application ---
django_asgi_app = get_asgi_application()

# --- Application setup ---
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    
    "websocket": AllowedHostsOriginValidator(
        # 3. 👈 Use your TokenAuthMiddleware
        TokenAuthMiddleware(
            URLRouter(
                # 4. 👈 This is all you need!
                # students.routing.websocket_urlpatterns already contains
                # all your routes (students, attendance, reports)
                students.routing.websocket_urlpatterns
            )
        )
    ),
})