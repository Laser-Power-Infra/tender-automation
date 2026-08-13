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
    "corsheaders",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "rest_framework",
    "tender_search",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3125",
    "http://127.0.0.1:3125",
]

ROOT_URLCONF = "config.urls"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(default=DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")

TENDER_TIGER_EMAIL = os.getenv("TENDER_TIGER_EMAIL", "")
TENDER_TIGER_PASSWORD = os.getenv("TENDER_TIGER_PASSWORD", "")

TENDER247_EMAIL = os.getenv("TENDER247_EMAIL", "")
TENDER247_PASSWORD = os.getenv("TENDER247_PASSWORD", "")

GOOGLE_DRIVE_CREDENTIALS_PATH = BASE_DIR / os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_DRIVE_TOKEN_PATH = BASE_DIR / os.getenv("GOOGLE_DRIVE_TOKEN_PATH", "token.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

TENDER_PARSING_TEMP_DIR = os.getenv("TENDER_PARSING_TEMP_DIR", r"D:\temp")

GDRIVE_CLIENT_EMAIL = os.getenv("GDRIVE_CLIENT_EMAIL", "")
GDRIVE_PRIVATE_KEY = os.getenv("GDRIVE_PRIVATE_KEY", "").replace("\\n", "\n")

INDEXER_NETWORK_PATH = os.getenv("INDEXER_NETWORK_PATH", "")
COSTING_FILE_NETWORK_PATH = os.getenv("COSTING_FILE_NETWORK_PATH", "")
CONDUTOR_PATH = os.getenv("CONDUTOR_PATH", "")

USE_TZ = False
