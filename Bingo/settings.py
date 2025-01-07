import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-c=q1&)#p8i1@e_@i$tlr#^0uwt438fw&^z=x5qmju%0lc(0%wh'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    '5.75.175.113',
    'dallolbingo.com',
    'www.dallolbingo.com',
    'https://www.dallolbingo.com',
    '127.0.0.1',
    'localhost',
    '172.20.10.2',
]

CORS_ALLOWED_ORIGINS = [
    'http://5.75.175.113',
    'https://dallolbingo.com',
    'http://www.dallolbingo.com',
    'https://www.dallolbingo.com',
    'http://localhost:3000',
    '*'
    # Add other origins as needed
]

CSRF_TRUSTED_ORIGINS = [
    'http://5.75.175.113',
    'https://dallolbingo.com',
    'http://www.dallolbingo.com',
    'https://www.dallolbingo.com',
    'http://localhost:3000',
    '*'
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'custom_auth',
    'corsheaders',
    'channels',
    'game',
    'group'
]

ASGI_APPLICATION = 'Bingo.asgi.application'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # Removed session middleware
    'custom_auth.middleware.session_expiry.SessionExpiryMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',  # Optional if you don't need CSRF protection
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

ROOT_URLCONF = 'Bingo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Bingo.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

CORS_ALLOW_ALL_ORIGINS = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'api/static/'  # URL prefix for serving static files

STATIC_ROOT = BASE_DIR / 'staticfiles'  # Directory where collectstatic will store files

STATICFILES_DIRS = [
    BASE_DIR / 'static'  # Directory where you store your development static files
]

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'custom_auth.AbstractUser'

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

OTP_PROVIDER_API_URL = "https://api.afromessage.com/api"  # Replace with your provider's API URL
OTP_PROVIDER_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJpZGVudGlmaWVyIjoiTUg4aGRvSnczUnhYSHd4OVFYUkJBWERqaFNrOVR1ZjAiLCJleHAiOjE4OTI4MTMyNDcsImlhdCI6MTczNTA0Njg0NywianRpIjoiZTgxMmM0ZDEtMjc1MS00NzkwLWFiOWQtM2I2MzlmZTI2YmI3In0.UA1JI7A7n9WJuDkBMANOryMIjbzppW_W1Bg9Pf12Uzc"  # Replace with your API key
OTP_EXPIRY_TIME = 300  # OTP expiry time in seconds (e.g., 5 minutes)
OTP_SENDER_NAME = "Dallol Games"
OTP_MESSAGE_PREFIX = "Wellcome to Dallol Games"
OTP_MESSAGE_POSTFIX = "" 

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
