#!/usr/bin/env python3
"""Ring-buffered JSONL log for the Toggl helper.

Never raises into the caller. A read-only install, a permissions failure or a
full disk disables logging for that process and the request proceeds.
"""

import fcntl
import json
import os
from datetime import datetime, timedelta, timezone

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "toggl.jsonl"
LOG_MAX_BYTES = 1024 * 1024
LOG_MAX_AGE = timedelta(hours=24)
MAX_FIELD = 500
MAX_ITEMS = 50
LEVELS = ("off", "errors", "info", "debug")
_ORDER = {"off": 0, "errors": 1, "info": 2, "debug": 3}
_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# Keys whose values name real work: window titles, entry descriptions, project
# names. Written only at debug. The whole reason classification is local is that
# titles do not leave the machine; a verbose log in the install directory would
# quietly undo that.
SENSITIVE = frozenset({
    "app", "apps", "client_name", "description", "domain", "domains", "label",
    "project_name", "prompt", "query", "response", "task_name", "title",
    "topic", "topics",
})


def _utc_now(clock=None):
    moment = clock() if clock else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (moment.microsecond // 1000)


def _clean(value, debug):
    """Drop sensitive keys unless debug, and truncate every string."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not debug and key in SENSITIVE:
                continue
            out[key] = _clean(item, debug)
        return out
    if isinstance(value, list):
        return [_clean(item, debug) for item in value[:MAX_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_FIELD]
    return value


class Logger:
    def __init__(self, directory, level="info", clock=None):
        self.level = level if level in _ORDER else "info"
        self.clock = clock
        self.path = None
        self._pruned = False
        if self.level == "off":
            return
        try:
            root = os.path.join(directory, LOG_DIR_NAME)
            os.makedirs(root, exist_ok=True)
            os.chmod(root, 0o700)
            probe = os.path.join(root, LOG_FILE_NAME)
            handle = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(handle)
            self.path = probe
        except OSError:
            self.path = None

    def enabled(self, level):
        return self.path is not None and _ORDER.get(level, 99) <= _ORDER[self.level]

    def write(self, level, **fields):
        if not self.enabled(level):
            return False
        record = _clean(dict(fields), self.level == "debug")
        record["ts"] = _stamp(_utc_now(self.clock))
        record["lvl"] = level
        try:
            line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
            handle = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(handle, line.encode("utf-8"))
            finally:
                os.close(handle)
        except (OSError, TypeError, ValueError):
            return False
        self.prune()
        return True

    def prune(self):
        """Bound the log by age first, size second. At most once per process,
        and always after the record is appended, so it never delays a response."""
        if self.path is None or self._pruned:
            return
        self._pruned = True
        try:
            if os.path.getsize(self.path) <= LOG_MAX_BYTES:
                return
        except OSError:
            return
        cutoff = _utc_now(self.clock) - LOG_MAX_AGE
        try:
            handle = os.open(self.path, os.O_RDWR)
        except OSError:
            return
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            chunks = []
            while True:
                chunk = os.read(handle, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            kept = []
            for line in b"".join(chunks).decode("utf-8", "replace").splitlines():
                if not line:
                    continue
                try:
                    moment = datetime.strptime(json.loads(line)["ts"], _TS_FORMAT)
                except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue  # malformed line dropped; the prune continues
                if moment.replace(tzinfo=timezone.utc) >= cutoff:
                    kept.append(line)
            # Walk newest-first once; no repeated joins or O(n) pop(0).
            tail, used = [], 0
            for line in reversed(kept):
                encoded = (line + "\n").encode("utf-8")
                if used + len(encoded) > LOG_MAX_BYTES:
                    break
                tail.append(encoded)
                used += len(encoded)
            payload = b"".join(reversed(tail))
            os.ftruncate(handle, 0)
            os.lseek(handle, 0, os.SEEK_SET)
            os.write(handle, payload)
        except OSError:
            return
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(handle)
