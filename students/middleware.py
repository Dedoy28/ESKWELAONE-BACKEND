# students/middleware.py

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken, UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from urllib.parse import parse_qs
import logging # Import logging

logger = logging.getLogger(__name__) # Use logging instead of print for clarity

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    """
    Asynchronously retrieves the user from the database.
    """
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware:
    """
    Custom WebSocket middleware to authenticate users via a JWT token
    in the query string.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        
        # 📍 ADD LOGGING: Log the connection path and query string
        path = scope.get('path', 'N/A')
        query_string_bytes = scope.get('query_string', b'')
        query_string = query_string_bytes.decode('utf-8')
        logger.warning(f"TokenAuthMiddleware: Path='{path}', QueryString='{query_string}'") # Use warning to make it stand out

        query_params = parse_qs(query_string)
        token_key = query_params.get('token', [None])[0]

        # 📍 ADD LOGGING: Log whether a token was found
        logger.warning(f"TokenAuthMiddleware: Token found in query params? {'Yes' if token_key else 'No'}")

        if token_key:
            try:
                UntypedToken(token_key)
                token = AccessToken(token_key)
                user_id = token['user_id']
                user = await get_user(user_id)
                scope['user'] = user
                
                # 📍 ADD LOGGING: Log successful authentication
                if not isinstance(user, AnonymousUser):
                     logger.warning(f"TokenAuthMiddleware: Authenticated User ID: {user.id}")
                else:
                     logger.warning(f"TokenAuthMiddleware: User ID {user_id} not found in DB.")

            except (InvalidToken, TokenError) as e:
                # 📍 ADD LOGGING: Log token validation error
                logger.error(f"TokenAuthMiddleware: Invalid Token Error: {e}") # Use error level
                scope['user'] = AnonymousUser()
        else:
            # 📍 ADD LOGGING: Log setting AnonymousUser due to no token
            logger.warning(f"TokenAuthMiddleware: No token provided, setting AnonymousUser.")
            scope['user'] = AnonymousUser()

        # Check final user status before passing to consumer
        final_user = scope.get('user', AnonymousUser())
        is_authenticated = not isinstance(final_user, AnonymousUser)
        logger.warning(f"TokenAuthMiddleware: Passing user to consumer. Authenticated: {is_authenticated}")


        return await self.inner(scope, receive, send)