import os
from pathlib import Path
from datetime import timedelta

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
    '91.98.86.196',
    'ntbingo.com',
    'https://ntbingo.com',
    'dallolbingo.com',
    'online.vamosbingo.com',
    'https://online.vamosbingo.com',
    'vamosbingo.com',
    '49.13.50.120',
    'www.dallolbingo.com',
    'https://www.dallolbingo.com',
    '127.0.0.1',
    'localhost',
    '172.20.10.2',

]

CORS_ALLOWED_ORIGINS = [
    'http://5.75.175.113',
    'https://91.98.86.196',
    'https://dallolbingo.com',
    'http://www.dallolbingo.com',
    'https://www.dallolbingo.com',
    'http://localhost:3000',
    'http://localhost:4200',
    'https://ntbingo.com',
    'http://127.0.0.1:3000',
    'https://vamosbingo.com',
    'https://online.vamosbingo.com',
    'http://49.13.50.120',
    # Add other origins as needed
]

CSRF_TRUSTED_ORIGINS = [
    'http://5.75.175.113',
    'https://91.98.86.196',
    'https://dallolbingo.com',
    'http://www.dallolbingo.com',
    'https://www.dallolbingo.com',
    'http://localhost:3000',
    'http://localhost:4200',
    'https://ntbingo.com',
    'http://127.0.0.1:3000',
    'https://vamosbingo.com',
    'https://online.vamosbingo.com',
    'http://49.13.50.120',
]


CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
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
    'group',
    'affiliate'
]

ASGI_APPLICATION = 'Bingo.asgi.application'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # Removed session middleware
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',  # Optional if you don't need CSRF protection
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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

import sentry_sdk

sentry_sdk.init(
    dsn="https://3b9d9cc849194c0c490a99a63e77bb5d@o4510549827780608.ingest.de.sentry.io/4510549830074448",
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # Set profile_session_sample_rate to 1.0 to profile 100%
    # of profile sessions.
    profile_session_sample_rate=1.0,
    # Set profile_lifecycle to "trace" to automatically
    # run the profiler on when there is an active transaction
    profile_lifecycle="trace",
)

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


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'agents_local',
        'USER': 'postgres',
        'PASSWORD': 'localdev123',
        'HOST': 'localhost',  # Typically localhost for shared hosting
        'PORT': '5433',  # Leave empty if default port 5432 is used           # Leave empty if default port 5432 is used
    }
}
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'dallol_bingo_online',
#         'USER': 'dallol',
#         'PASSWORD': 'Byihun@123',
#         'HOST': '49.13.50.120',
#         'PORT': '5432',
#         'CONN_MAX_AGE': 60,  # keep connection open for 60 seconds max
#     }
# }
# DATABASES={
#     'default':{
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'agents_local',
#         'USER': 'postgres',
#         'PASSWORD': 'localdev123',
#         'HOST': 'localhost',  # Typically localhost for shared hosting
#         'PORT': '5433',
#     }
# }


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

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

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

TELEGRAM_BOT_TOKEN = "8518728704:AAGsNx8aRK7DSg-YTdErDchyPATjDmLmFXI"

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,  # Keep True if you want full control
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',  # Only show ERROR and above
            'propagate': True,
        },
        'channels': {
            'handlers': ['console'],
            'level': 'ERROR',  # Only errors from Django Channels
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',  # Errors from HTTP handling
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',  # Hide SQL queries unless they error
        },
    },
}
