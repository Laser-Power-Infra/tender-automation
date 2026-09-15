import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# ponytail: sync HTTP only via ASGI, add ProtocolTypeRouter + channels when websocket needed
application = get_asgi_application()
