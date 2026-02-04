import os
from pathlib import Path
from datetime import timedelta

def _env_list(key: str, default: str = "") -> list:
    """Parse comma-separated env var into list; empty string means use default list."""
    val = os.environ.get(key, default).strip()
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-c=q1&)#p8i1@e_@i$tlr#^0uwt438fw&^z=x5qmju%0lc(0%wh",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")

# Comma-separated for easy profile switching (e.g. ALLOWED_HOSTS=127.0.0.1,localhost)
_ALLOWED_DEFAULT = "127.0.0.1,localhost"
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", _ALLOWED_DEFAULT) or _ALLOWED_DEFAULT.split(",")

_CORS_DEFAULT = "http://localhost:3000,http://localhost:4200,http://127.0.0.1:3000"
CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS", _CORS_DEFAULT) or _CORS_DEFAULT.split(",")

CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS", _CORS_DEFAULT) or _CORS_DEFAULT.split(",")


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

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
        profile_session_sample_rate=float(os.environ.get("SENTRY_PROFILE_SAMPLE_RATE", "1.0")),
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


# Database: set env vars per profile (e.g. DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "dallol_bingo_online"),
        "USER": os.environ.get("DB_USER", "dallol"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
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

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

OTP_PROVIDER_API_URL = os.environ.get("OTP_PROVIDER_API_URL", "https://api.afromessage.com/api")
OTP_PROVIDER_API_KEY = os.environ.get("OTP_PROVIDER_API_KEY", "")
OTP_EXPIRY_TIME = int(os.environ.get("OTP_EXPIRY_TIME", "300"))
OTP_SENDER_NAME = os.environ.get("OTP_SENDER_NAME", "Dallol Games")
OTP_MESSAGE_PREFIX = os.environ.get("OTP_MESSAGE_PREFIX", "Wellcome to Dallol Games")
OTP_MESSAGE_POSTFIX = os.environ.get("OTP_MESSAGE_POSTFIX", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

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
