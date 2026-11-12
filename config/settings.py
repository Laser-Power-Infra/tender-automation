import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = "django-insecure-automation-key-not-for-production"
DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "daphne",
    "corsheaders",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "rest_framework",
]

# ponytail: externally managed DB — no auth tables, disable auth migrations permanently
MIGRATION_MODULES = {"auth": None}
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    },
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3125",
    "http://127.0.0.1:3125",
]

# No database or URLs here: config.settings_v2 adds them. This module alone is enough for the self-checks.
DATABASES = {}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MQ_URL = os.getenv("MQ_URL", "")

TENDER_TIGER_EMAIL = os.getenv("TENDER_TIGER_EMAIL", "")
TENDER_TIGER_PASSWORD = os.getenv("TENDER_TIGER_PASSWORD", "")

TENDER247_EMAIL = os.getenv("TENDER247_EMAIL", "")
TENDER247_PASSWORD = os.getenv("TENDER247_PASSWORD", "")

GOOGLE_DRIVE_CREDENTIALS_PATH = BASE_DIR / os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_DRIVE_TOKEN_PATH = BASE_DIR / os.getenv("GOOGLE_DRIVE_TOKEN_PATH", "token.json")

TENDER_PARSING_TEMP_DIR = os.getenv("TENDER_PARSING_TEMP_DIR", r"D:\temp")

GDRIVE_CLIENT_EMAIL = os.getenv("GDRIVE_CLIENT_EMAIL", "")
GDRIVE_PRIVATE_KEY = os.getenv("GDRIVE_PRIVATE_KEY", "").replace("\\n", "\n")

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_PUBLIC_URL = os.getenv("PUBLIC_URL_ENV", os.getenv("S3_PUBLIC_URL", ""))

INDEXER_NETWORK_PATH = os.getenv("INDEXER_NETWORK_PATH", "")
COSTING_FILE_NETWORK_PATH = os.getenv("COSTING_FILE_NETWORK_PATH", "")
CONDUTOR_PATH = os.getenv("CONDUTOR_PATH", "")

USE_TZ = False


CHROME_PATH= os.getenv("CHROME_PATH")

HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "true").lower() not in ("false", "0", "no", "off")

REST_FRAMEWORK = {
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
