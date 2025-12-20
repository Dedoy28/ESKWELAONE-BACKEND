# backend/settings.py (FOR LOCALHOST)

from pathlib import Path
from datetime import timedelta
import os
import dj_database_url

# =====================================
# BASE DIRECTORY
# =====================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================
# SECURITY SETTINGS - (MODIFIED FOR LOCALHOST)
# =====================================
SECRET_KEY = 'a-simple-local-key-for-development-it-can-be-anything'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# =====================================
# INSTALLED APPS
# =====================================
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic', 
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'channels',
    'api',
    'students.apps.StudentsConfig',
]

# =====================================
# MIDDLEWARE
# =====================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =====================================
# URL / WSGI / ASGI CONFIG
# =====================================
ROOT_URLCONF = 'backend.urls'
WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

# =====================================
# TEMPLATES
# =====================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# =====================================
# DATABASE (POSTGRESQL) - (MODIFIED FOR LOCALHOST)
# =====================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'eskwelaone',      # Your local database name
        'USER': 'postgres',         # Your local postgres username
        'PASSWORD': 'admin',      # Your local postgres password
        'HOST': 'localhost',        # Or '127.0.0.1'
        'PORT': '5432',
    }
}

# =====================================
# PASSWORD VALIDATORS
# =====================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =====================================
# INTERNATIONALIZATION
# =====================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =====================================
# STATIC FILES - (MODIFIED FOR LOCALHOST)
# =====================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================
# REST FRAMEWORK + JWT
# =====================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=300),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# =============================================================
# ⭐️⭐️⭐️ THIS IS THE FIX ⭐️⭐️⭐️
# =============================================================
# CORS / CSRF CONFIGURATION - (MODIFIED FOR LOCALHOST:8080)
# =============================================================
CORS_ALLOW_CREDENTIALS = True
# This should be your local React app's URL
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8080',
    'http://127.0.0.1:8080',
]
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8080',
    'http://127.0.0.1:8080',
]
# =============================================================
# ⭐️⭐️⭐️ END OF FIX ⭐️⭐️⭐️
# =============================================================

# =====================================
# CHANNELS + REDIS CONFIGURATION - (MODIFIED FOR LOCALHOST)
# =====================================
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            # This points to your local Redis server
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}