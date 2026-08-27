import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque

from django.conf import settings

logger = logging.getLogger(__name__)

WORKER_COMMANDS = {
    "tasks": "consume_tender_tasks",
    "parsing": "consume_tender_parsing",
}

_state = {
    name: {"proc": None, "pid": None, "status": "STOPPED", "started_at": None, "logfile": None}
    for name in WORKER_COMMANDS
}

_LEVEL_RE = re.compile(r"^(ERROR|WARNING|INFO|DEBUG)\b", re.IGNORECASE)
_REF_RE = re.compile(r"(?:referenceNo|reference_no|Reference)\s*[=:\s]\s*([A-Za-z0-9/_.\-\[\] ]+)", re.IGNORECASE)

_lock = threading.Lock()
_logs = deque(maxlen=int(getattr(settings, "DASHBOARD_LOG_LIMIT", 2000)))
_seq = 0
_offsets = {name: 0 for name in WORKER_COMMANDS}


def _log_dir():
    d = getattr(settings, "DASHBOARD_LOG_DIR", "") or os.path.join(tempfile.gettempdir(), "tender_worker_logs")
    os.makedirs(d, exist_ok=True)
    return d


def _log_path(name):
    return os.path.join(_log_dir(), f"{name}.log")


def _base_dir():
    return getattr(settings, "BASE_DIR", os.getcwd())


def _python():
    return sys.executable


def _classify_level(line):
    m = _LEVEL_RE.match(line.strip())
    return m.group(1).upper() if m else "INFO"


def _extract_reference(line):
    m = _REF_RE.search(line)
    return m.group(1).strip() if m else None


def _append_log(worker, level, message):
    global _seq
    _seq += 1
    _logs.append({
        "seq": _seq,
        "ts": round(time.time(), 3),
        "worker": worker,
        "level": level,
        "message": message,
        "reference": _extract_reference(message),
    })


def tail_worker(name):
    """Read new bytes from the worker log file and append parsed lines to the in-memory buffer."""
    if name not in WORKER_COMMANDS:
        return
    path = _log_path(name)
    if not os.path.exists(path):
        return
    with _lock:
        offset = _offsets.get(name, 0)
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size < offset:
            offset = 0
        if size == offset:
            return
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
            _offsets[name] = size
        except OSError:
            return
    text = data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if not line.strip():
            continue
        _append_log(name, _classify_level(line), line)


def tail_all():
    for name in WORKER_COMMANDS:
        try:
            tail_worker(name)
        except Exception as e:
            logger.warning("tail_worker(%s) failed: %s", name, e)


def get_logs(worker=None, level=None, reference=None, limit=200, after=0):
    tail_all()
    with _lock:
        items = list(_logs)
    if after:
        items = [x for x in items if x["seq"] > after]
    if worker and worker in WORKER_COMMANDS:
        items = [x for x in items if x["worker"] == worker]
    if level:
        items = [x for x in items if x["level"] == level.upper()]
    if reference:
        ref = reference.lower()
        items = [x for x in items if x["reference"] and ref in x["reference"].lower()]
    items = items[-limit:]
    return items, (_seq if after else 0)


def clear_logs():
    with _lock:
        _logs.clear()
        for name in WORKER_COMMANDS:
            _offsets[name] = 0
            try:
                if os.path.exists(_log_path(name)):
                    open(_log_path(name), "wb").close()
            except OSError:
                pass


def start(name):
    if name not in WORKER_COMMANDS:
        return {"error": f"Unknown worker: {name}"}
    st = _state[name]
    proc = st["proc"]
    if proc and proc.poll() is None:
        return status(name)
    cmd = [_python(), "manage.py", WORKER_COMMANDS[name]]
    logger.info("Starting worker %s: %s", name, cmd)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    log_path = _log_path(name)
    try:
        logfile = open(log_path, "ab")
        logfile.seek(0)
        logfile.truncate()
        proc = subprocess.Popen(
            cmd,
            cwd=str(_base_dir()),
            env=env,
            stdout=logfile,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        st["status"] = "ERROR"
        st["pid"] = None
        st["started_at"] = None
        st["logfile"] = None
        return {"error": f"Failed to start {name}: {e}"}
    st["proc"] = proc
    st["pid"] = proc.pid
    st["status"] = "RUNNING"
    st["started_at"] = time.time()
    st["logfile"] = logfile
    with _lock:
        _offsets[name] = 0
    return status(name)


def stop(name):
    if name not in WORKER_COMMANDS:
        return {"error": f"Unknown worker: {name}"}
    st = _state[name]
    proc = st["proc"]
    if not proc or proc.poll() is not None:
        st["status"] = "STOPPED"
        st["pid"] = None
        st["started_at"] = None
        if st["logfile"]:
            try:
                st["logfile"].close()
            except Exception:
                pass
            st["logfile"] = None
        return status(name)
    logger.info("Stopping worker %s (pid %s)", name, proc.pid)
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    except Exception as e:
        st["status"] = "ERROR"
        return {"error": f"Failed to stop {name}: {e}"}
    if st["logfile"]:
        try:
            st["logfile"].close()
        except Exception:
            pass
    st["proc"] = None
    st["pid"] = None
    st["status"] = "STOPPED"
    st["started_at"] = None
    st["logfile"] = None
    return status(name)


def _refresh(name):
    st = _state[name]
    proc = st["proc"]
    if proc is None:
        st["status"] = "STOPPED"
        st["pid"] = None
        st["started_at"] = None
        return
    if proc.poll() is not None:
        st["status"] = "STOPPED"
        st["pid"] = None
        st["started_at"] = None
        st["proc"] = None
        if st["logfile"]:
            try:
                st["logfile"].close()
            except Exception:
                pass
            st["logfile"] = None


def status(name):
    if name not in WORKER_COMMANDS:
        return {"error": f"Unknown worker: {name}"}
    _refresh(name)
    st = _state[name]
    uptime = None
    if st["started_at"]:
        uptime = round(time.time() - st["started_at"], 1)
    return {
        "name": name,
        "command": WORKER_COMMANDS[name],
        "status": st["status"],
        "pid": st["pid"],
        "uptime_sec": uptime,
    }


def status_all():
    return {name: status(name) for name in WORKER_COMMANDS}