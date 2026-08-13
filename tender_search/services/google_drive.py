import os
import time
import logging
from pathlib import Path
import gc

from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _remove_with_retry(file_path, retries=5, delay=1.0):
    for attempt in range(retries):
        try:
            os.remove(file_path)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            wait = delay * (attempt + 1)
            logger.debug("File locked, retrying remove in %.1fs...", wait)
            time.sleep(wait)


def _get_authenticated_service():
    token_path = settings.GOOGLE_DRIVE_TOKEN_PATH
    creds_path = settings.GOOGLE_DRIVE_CREDENTIALS_PATH
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.valid:
        return build("drive", "v3", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        return build("drive", "v3", credentials=creds)

    if os.path.exists(creds_path):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            logger.warning("OAuth flow failed, falling back to service account: %s", e)

    logger.info("Using service account authentication")
    sa_creds = ServiceAccountCredentials.from_service_account_info(
        {
            "client_email": settings.GDRIVE_CLIENT_EMAIL,
            "private_key": settings.GDRIVE_PRIVATE_KEY,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=sa_creds)


def upload_to_drive(file_path, folder_id=None, mime_type=None):
    service = _get_authenticated_service()
    file_name = Path(file_path).name

    parents = [folder_id] if folder_id else None
    body = {"name": file_name}
    if parents:
        body["parents"] = parents

    last_error = None
    for attempt in range(3):
        try:
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            uploaded = service.files().create(body=body, media_body=media, fields="id,name,webViewLink,mimeType,size").execute()
            break
        except (PermissionError, IOError) as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning("Upload attempt %d failed (file locked), retrying in %ds: %s", attempt + 1, wait, e)
            time.sleep(wait)
    else:
        raise last_error or RuntimeError("Upload failed after 3 retries")

    link = uploaded.get("webViewLink", "")
    logger.info("Uploaded %s — %s", file_name, link)
    print("Uploaded %s — %s", file_name, link)
    # Explicitly release the upload object
    media = None

    
    gc.collect()

    time.sleep(1)

    _remove_with_retry(file_path)
    logger.info("Deleted local file: %s", file_path)

    return {
        "id": uploaded["id"],
        "name": uploaded["name"],
        "mimeType": uploaded.get("mimeType"),
        "size": uploaded.get("size"),
        "webViewLink": link,
    }
