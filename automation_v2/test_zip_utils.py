"""zip_utils self-check. No S3, no network: the upload is stubbed.

Run: uv run python -m automation_v2.test_zip_utils
"""
import os
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from automation_v2.lib import zip_utils  # noqa: E402

tmp = Path(tempfile.mkdtemp())
settings.TENDER_PARSING_TEMP_DIR = str(tmp)


def outer_zip() -> Path:
    """outer.zip = NIT.pdf + a.zip + b.zip, where both inner zips hold a file named BOQ.xls."""
    for name in ("a", "b"):
        with zipfile.ZipFile(tmp / f"{name}.zip", "w") as z:
            z.writestr("BOQ.xls", name)
    with zipfile.ZipFile(tmp / "outer.zip", "w") as z:
        z.writestr("NIT.pdf", "nit")
        for name in ("a", "b"):
            z.write(tmp / f"{name}.zip", f"{name}.zip")
            (tmp / f"{name}.zip").unlink()
    return tmp / "outer.zip"


# inner zips with the same file name: both files survive, each under its own folder
zip_utils.file_storage = SimpleNamespace(
    upload=lambda path, reference_no, key: {"key": f"{reference_no}/{key}", "url": Path(path).read_text()})
got = zip_utils.extract_and_upload(outer_zip(), "REF")
assert sorted((x["key"], x["url"]) for x in got) == [
    ("REF/NIT.pdf", "nit"), ("REF/a/BOQ.xls", "a"), ("REF/b/BOQ.xls", "b")], got
assert not (tmp / "outer.zip").exists() and not (tmp / "REF_extracted").exists()


# a failed upload fails the whole call (no silent success with files missing) and still cleans up
def boom(path, reference_no, key):
    raise RuntimeError("S3 down")


zip_utils.file_storage = SimpleNamespace(upload=boom)
try:
    zip_utils.extract_and_upload(outer_zip(), "REF")
    raise AssertionError("upload failure should raise")
except RuntimeError:
    pass
assert not (tmp / "REF_extracted").exists()

print("zip_utils self-check OK")
