#!/usr/bin/env python3
"""Small, quiet JSON-in/JSON-out bridge for the Toggl Track API."""

import base64
import fcntl
from contextlib import contextmanager
from functools import wraps
import hashlib
import collections
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python 3.8 compatibility
    ZoneInfo = None
    ZoneInfoNotFoundError = LookupError

import toggl_log
from toggl_perf import InferenceCache, model_fingerprint


_REAL_DATETIME = datetime


BASE_URL = "https://api.track.toggl.com/api/v9"
ACTIVITYWATCH_URL = "http://127.0.0.1:5600"
CLASSIFIER_URL = "http://127.0.0.1:8127/v1/chat/completions"
# The embedder is a second llama-server: one process per model is the documented
# answer, and a 35 MB encoder has no business sharing a slot with the chat model.
EMBEDDER_URL = "http://127.0.0.1:8128/v1/embeddings"
EMBEDDER_MODEL = "toggl-embedder"
EMBEDDER_TIMEOUT = 15
# Ruling R-AO. Measured over 26 labelled blocks: the usage prior alone scores
# 81%, embedding centroids 77%, the best language model 65%. So the project is
# decided by counting and geometry, and the model never votes on it. The blend
# weight is the share given to centroid similarity over the prior.
PROJECT_CENTROID_WEIGHT = 0.5
PROJECT_SHORTLIST = 5
CLASSIFIER_TIMEOUT = 20
# The unit serves whichever model the profile installed under one alias, so
# the client never has to know which (ruling R-AM).
CLASSIFIER_MODEL = "toggl-classifier"
CLASSIFIER_MAX_DESCRIPTION = 120
# Roughly 40 tokens per block; 12 blocks fit. At 72 tok/s on the GPU profile
# even the cap stays well inside the 20 s budget (ruling R-AM).
CLASSIFIER_MAX_TOKENS = 800
CLASSIFIER_SYSTEM_PROMPT = (
    # Ruling R-AO. The model's only job is prose. Shown a shortlist of projects
    # it copied the winning project's name into the description on every block
    # of a live day; shown the user's past descriptions it copied those instead.
    # So it is shown neither: the project is decided by prior and centroid, and
    # this prompt asks for one sentence about the work and nothing else.
    "You are a personal assistant who writes Toggl time-entry descriptions for "
    "an engineer. You see one block of their computer activity: window titles, "
    "apps and websites with minutes spent, and the time of day. Write one "
    "specific description of 4 to 10 words naming the concrete work -- the "
    "repository, document, system or task, and what was being done to it. Do "
    "not copy a window title verbatim, do not list apps, never mention Toggl."
)
SECRET_COMMAND = ["secret-tool", "lookup", "service", "daz.toggl-track", "account", "api-token"]
MAX_RETRIES = 2
MAX_RETRY_DELAY = 30.0
PROJECT_PAGE_SIZE = 200
TASK_PAGE_SIZE = 200
MAX_TEXT = 500
MAX_TIMELINE = 200
MAX_TAGS = 50
MAX_TAG = 100
ACCOUNT_TTL = timedelta(hours=24)
WORKSPACE_TTL = timedelta(minutes=60)
AW_BUCKETS_TTL = timedelta(hours=24)
AW_DAY_TTL = timedelta(minutes=10)
ENTRIES_TTL = timedelta(minutes=60)
CACHE_SCHEMA = "omarchy-toggl-track"
CACHE_VERSION = 1
# Measured against the live API on 2026-09-03: a start_date earlier than
# today-91 is rejected with HTTP 400 "start_date must not be earlier than
# <date>". 92 days inclusive is the largest window that succeeds; 90 is the
# largest value offered, leaving margin.
HISTORY_FLOOR_DAYS = 91
HISTORY_MAX_DAYS = HISTORY_FLOOR_DAYS + 1
HISTORY_SAFE_DAYS = 90
MAX_CLIENT_LOG = 32
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


class ApiError(Exception):
    def __init__(self, message, status=None, retryable=False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable


class ValidationError(ApiError):
    def __init__(self, message):
        super().__init__(message, 400, False)


def _error(message, status=None, retryable=False):
    return {"ok": False, "error": {"message": message, "status": status, "retryable": retryable}}


def _token_diagnosis(has_secret_tool=True):
    """Why the lookup came back empty, in words that name the fix.

    `secret-tool lookup` exits 1 with no output whether the item is absent, the
    keyring daemon is dead, or there is no session bus -- so the bare message
    sent someone with a broken keyring round a loop through setup. The D-Bus
    round trip this costs is paid only on the failure branch. If the diagnosis
    itself cannot run, the old message stands: a worse error beats no answer."""
    try:
        import toggl_secret

        return toggl_secret.describe_failure(has_secret_tool)
    except Exception:
        return "Toggl API token not found; run setup first."


def _secure_keyring_block():
    """In secure mode, refuse before `secret-tool` can summon a dialog.

    A lookup against a locked collection blocks on a `gcr-prompter` window
    until someone types the password. The panel runs this with stdin closed on
    a ten-second leash, so the wait ends in a timeout with a password dialog
    stranded on screen and nothing to explain it. Returns a sentence to fail
    with, or None to go ahead."""
    try:
        import toggl_secret

        if toggl_secret.mode() != toggl_secret.MODE_SECURE:
            return None
        _, problem = toggl_secret.secure_ready()
        return problem
    except Exception:
        return None


def _load_token():
    blocked = _secure_keyring_block()
    if blocked:
        raise ApiError(blocked)
    try:
        result = subprocess.run(
            SECRET_COMMAND,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError:
        raise ApiError(_token_diagnosis(has_secret_tool=False))
    except (OSError, subprocess.TimeoutExpired):
        raise ApiError("Unable to read the Toggl API token securely.")
    token = (result.stdout or "").strip()
    if result.returncode != 0 or not token:
        raise ApiError(_token_diagnosis())
    if len(token) > 1000 or any(ord(char) < 0x20 for char in token):
        raise ApiError("Stored Toggl API token is invalid; run setup again.")
    return token


def _safe_retry_after(value):
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, min(MAX_RETRY_DELAY, seconds))


class TogglClient:
    def __init__(self, token=None, opener=None, sleep=time.sleep, logger=None):
        token = token if token is not None else _load_token()
        if not isinstance(token, str) or not token:
            raise ApiError("Toggl API token not found; run setup first.")
        self.account_key = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
        self._auth = "Basic " + base64.b64encode((token + ":api_token").encode("utf-8")).decode("ascii")
        self._opener = opener or urlopen
        self._sleep = sleep
        self._logger = logger

    def request(self, method, path, params=None, body=None, mutation=False):
        url = BASE_URL + path
        if params:
            url += "?" + urlencode(params)
        headers = {"Authorization": self._auth, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        attempts = 0
        while True:
            attempt_started = time.monotonic()
            try:
                with self._opener(request, timeout=15) as response:
                    raw = response.read()
                if self._logger is not None:
                    _log(self._logger, "info", http=[{
                        "path": path,
                        "status": int(getattr(response, "status", 0) or 0),
                        "ms": int((time.monotonic() - attempt_started) * 1000),
                        "bytes": len(raw),
                    }])
                if not raw:
                    return {}
                try:
                    return json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise ApiError("Toggl returned an invalid response.", 502, True)
            except HTTPError as error:
                status = int(error.code)
                retryable = status == 429 or status >= 500
                if not mutation and retryable and attempts < MAX_RETRIES:
                    delay = _safe_retry_after(error.headers.get("Retry-After") if error.headers else None)
                    error.close()
                    self._sleep(delay if delay is not None else min(2 ** attempts, 4))
                    attempts += 1
                    continue
                body_text = None
                if status == 400:
                    try:
                        body_text = error.read().decode("utf-8", "replace").strip()
                    except Exception:
                        body_text = None
                error.close()
                raise ApiError(_http_message(status, body_text), status, retryable)
            except (URLError, TimeoutError, OSError):
                if not mutation and attempts < MAX_RETRIES:
                    self._sleep(min(2 ** attempts, 4))
                    attempts += 1
                    continue
                raise ApiError("Unable to reach Toggl; check your network connection.", None, True)


def _http_message(status, body=None):
    if status == 400:
        text = (body or "").strip()
        if text:
            return text[:MAX_TEXT]
        return "Toggl rejected the request."
    if status == 401:
        return "Toggl authentication failed; run setup to refresh your token."
    if status == 403:
        return "Toggl denied access to the requested workspace. Check your workspace permissions."
    if status == 404:
        return "Toggl resource was not found."
    if status == 409:
        return "Toggl rejected the change because it conflicted with another change."
    if status == 422:
        return "Toggl rejected the supplied data."
    if status == 429:
        return "Toggl rate limit reached; try again later."
    if status >= 500:
        return "Toggl is temporarily unavailable; try again later."
    return "Toggl request failed."


def _dict(value, name):
    if not isinstance(value, dict):
        raise ValidationError(name + " must be an object.")
    return value


def _field(value, name, *aliases):
    if name in value:
        return value[name]
    for alias in aliases:
        if alias in value:
            return value[alias]
    return None


def _id(value, name, required=True):
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(name + " must be a positive integer.")
    return value


def _text(value, name, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValidationError(name + " must be a string.")
    if any(ord(char) < 0x20 and char not in "\t\n\r" for char in value):
        raise ValidationError(name + " contains unsupported control characters.")
    return value[:MAX_TEXT]


def _tags(value, name="tags"):
    if not isinstance(value, list) or len(value) > MAX_TAGS:
        raise ValidationError(name + " must be an array of at most 50 names.")
    result = []
    for tag in value:
        if isinstance(tag, dict):
            tag = tag.get("name")
        if not isinstance(tag, str) or not tag.strip():
            raise ValidationError(name + " must contain non-empty strings.")
        result.append(tag[:MAX_TAG])
    return result


def _bool(value, name):
    if not isinstance(value, bool):
        raise ValidationError(name + " must be a boolean.")
    return value


def _rfc3339(value, name):
    if not isinstance(value, str):
        raise ValidationError(name + " must be an RFC3339 date.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(name + " must be an RFC3339 date.")
    if parsed.tzinfo is None:
        raise ValidationError(name + " must include a timezone.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_datetime(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _activitywatch_request(path, params=None, opener=None):
    url = ACTIVITYWATCH_URL + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with (opener or urlopen)(request, timeout=5) as response:
            raw = response.read()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("ActivityWatch returned an invalid response.", 502, True)
    except HTTPError as error:
        status = int(error.code)
        error.close()
        raise ApiError("ActivityWatch request failed.", status, status >= 500)
    except (URLError, TimeoutError, OSError):
        raise ApiError("Unable to reach ActivityWatch; check that aw-server is running.", None, True)


def _activitywatch_events(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("events", "data", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    raise ApiError("ActivityWatch returned an invalid events response.", 502, True)


def _clip_activity_events(events, start, end):
    if events is None:
        return None
    clipped = []
    for event in events:
        span = _activity_span(event)
        if span is None:
            continue
        overlap_start = max(start, span["start"])
        overlap_end = min(end, span["end"])
        if overlap_start >= overlap_end:
            continue
        item = dict(event)
        item["timestamp"] = _iso_datetime(overlap_start)
        item["duration"] = (overlap_end - overlap_start).total_seconds()
        clipped.append(item)
    return clipped


def _activitywatch_buckets(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        raise ApiError("ActivityWatch returned an invalid buckets response.", 502, True)
    if isinstance(value.get("data"), list):
        return value["data"]
    if isinstance(value.get("buckets"), list):
        return value["buckets"]
    result = []
    for bucket_id, bucket in value.items():
        if isinstance(bucket, dict):
            item = dict(bucket)
            item.setdefault("id", bucket_id)
            result.append(item)
    return result


def _event_datetime(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(Z|[+-]\d{2}:\d{2})$", lambda match: "%s.%s%s" % (match.group(1), match.group(2)[:6], match.group(3)), value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _activity_span(event):
    if not isinstance(event, dict):
        return None
    start = _event_datetime(event.get("timestamp"))
    duration = event.get("duration")
    if start is None or isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        return None
    data = event.get("data")
    return {
        "start": start,
        "end": start + timedelta(seconds=float(duration)),
        "data": data if isinstance(data, dict) else {},
    }


def _merge_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _local_timezone():
    if ZoneInfo is not None:
        name = os.environ.get("TZ", "").lstrip(":")
        if name:
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                pass
        try:
            return ZoneInfo("localtime")
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def _day_bounds(date_value):
    if not isinstance(date_value, str):
        raise ValidationError("date must be YYYY-MM-DD.")
    try:
        day = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("date must be YYYY-MM-DD.")
    local = _local_timezone()
    start = datetime.combine(day, datetime.min.time(), tzinfo=local)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=local)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _minutes(value, name, default):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValidationError(name + " must be a non-negative number.")
    return float(value)


def _hostname(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        return parsed.hostname.lower() if parsed.hostname else None
    except ValueError:
        return None


# Distinctive enough to match anywhere in the app id.
_BROWSER_SUBSTRINGS = (
    "chrome", "chromium", "firefox", "brave", "edge", "opera", "browser",
    "vivaldi", "librewolf", "waterfox", "floorp",
)
# Short names that would collide as substrings (zen vs zenity), so they are
# matched against the trailing segment of a reverse-DNS app id instead.
_BROWSER_NAMES = ("zen", "safari", "epiphany", "midori", "konqueror")


def _browser_app(value):
    value = str(value or "").lower()
    if any(name in value for name in _BROWSER_SUBSTRINGS):
        return True
    return value.rsplit(".", 1)[-1] in _BROWSER_NAMES


# Browser and document suffixes add nothing to a topic name.
_TITLE_SUFFIX = re.compile(
    r"\s*[\u2014\u2013-]\s*("
    r"zen browser|google chrome|chromium|mozilla firefox|firefox|brave|"
    r"microsoft edge|opera|vivaldi|librewolf|floorp"
    r")\s*$",
    re.IGNORECASE,
)
_TITLE_COUNTER = re.compile(r"^\(\d+\)\s*")
_TITLE_DOCUMENT = re.compile(r"\s*-\s*Google (?:Docs|Sheets|Slides)\s*$", re.IGNORECASE)

# Shell surfaces that are on screen but are not work.
_IGNORED_APPS = ("omarchy-screensaver", "org.omarchy.screensaver", "org.omarchy.lock")

def _ignored_app(value):
    value = str(value or "").lower()
    return any(name in value for name in _IGNORED_APPS)


def _topic(app, title):
    """Human-recognisable name for whatever a window was showing."""
    text = _TITLE_COUNTER.sub("", str(title or "").strip())
    text = _TITLE_SUFFIX.sub("", text)
    text = _TITLE_DOCUMENT.sub("", text).strip()
    return (text or str(app or ""))[:MAX_TEXT]


def _timeline(origin, fragments):
    """Ticks across the block's wall span, with the gaps between fragments
    marked idle. Capped at MAX_TIMELINE by merging the shortest neighbours."""
    items = []
    cursor = origin
    for fragment in fragments:
        gap = (fragment["start"] - cursor).total_seconds()
        if gap > 0:
            items.append({
                "offset": int(round((cursor - origin).total_seconds())),
                "seconds": int(round(gap)),
                "topic": "",
                "idle": True,
            })
        items.append({
            "offset": int(round((fragment["start"] - origin).total_seconds())),
            "seconds": int(round((fragment["end"] - fragment["start"]).total_seconds())),
            "topic": fragment["topic"],
            "idle": False,
        })
        cursor = max(cursor, fragment["end"])
    while len(items) > MAX_TIMELINE:
        merged = []
        index = 0
        while index < len(items):
            current = items[index]
            following = items[index + 1] if index + 1 < len(items) else None
            if following is not None and following["idle"] == current["idle"] \
                    and following["topic"] == current["topic"]:
                current = dict(current)
                current["seconds"] += following["seconds"]
                index += 2
            else:
                index += 1
            merged.append(current)
        if len(merged) == len(items):
            return items[:MAX_TIMELINE]
        items = merged
    return items


def segment_blocks(window_events, afk_events, web_events=None, config=None):
    """Group a day's activity into work blocks separated by real breaks.

    Grouping by application, or by runs of one dominant window title, produces
    confetti: a measured day holds ~4,500 focus fragments in ~340 title runs
    whose longest is 12 minutes, because the work itself means switching
    between an editor, a browser and a chat client every couple of minutes.
    So a block is instead a stretch of activity bounded by an actual pause,
    and the topics seen inside it are reported alongside it. Nothing is
    discarded, so the blocks account for all active time.
    """
    config = config or {}
    break_seconds = _minutes(config.get("min_block_minutes"), "min_block_minutes", 5) * 60

    window_spans = [_activity_span(event) for event in (window_events or [])]
    window_spans = [
        span
        for span in window_spans
        if span is not None
        and span["data"].get("app") is not None
        and not _ignored_app(span["data"].get("app"))
    ]
    afk_spans = [_activity_span(event) for event in (afk_events or [])]
    active_intervals = _merge_intervals(
        (span["start"], span["end"])
        for span in afk_spans
        if span is not None and span["data"].get("status") == "not-afk"
    )
    # A missing AFK bucket means there is no idle information to remove.
    if afk_events is None:
        active_intervals = [(datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc))]

    fragments = []
    active_index = 0
    for window_order, window in sorted(enumerate(window_spans), key=lambda pair: pair[1]["start"]):
        while active_index < len(active_intervals) and active_intervals[active_index][1] <= window["start"]:
            active_index += 1
        for interval_index in range(active_index, len(active_intervals)):
            active_start, active_end = active_intervals[interval_index]
            if active_start >= window["end"]:
                break
            start = max(window["start"], active_start)
            end = min(window["end"], active_end)
            if start >= end:
                continue
            fragments.append({
                "_order": window_order,
                "start": start,
                "end": end,
                "app": str(window["data"].get("app") or "")[:MAX_TEXT],
                "topic": _topic(window["data"].get("app"), window["data"].get("title")),
            })
    fragments.sort(key=lambda item: (item["start"], item["end"], item["_order"]))
    for fragment in fragments:
        del fragment["_order"]

    groups = []
    for fragment in fragments:
        if groups and (fragment["start"] - groups[-1]["end"]).total_seconds() <= break_seconds:
            groups[-1]["end"] = max(groups[-1]["end"], fragment["end"])
            groups[-1]["members"].append(fragment)
        else:
            groups.append({"start": fragment["start"], "end": fragment["end"], "members": [fragment]})

    web_spans = [_activity_span(event) for event in (web_events or [])]
    blocks = []
    for group in groups:
        weights = {}
        app_weights = {}
        fragments = sorted(group["members"], key=lambda item: item["start"])
        longest = 0.0
        for fragment in fragments:
            seconds = (fragment["end"] - fragment["start"]).total_seconds()
            weights[fragment["topic"]] = weights.get(fragment["topic"], 0.0) + seconds
            app_weights[fragment["app"]] = app_weights.get(fragment["app"], 0.0) + seconds
            longest = max(longest, seconds)
        topics = [
            {"name": name, "seconds": int(round(weights[name]))}
            for name in sorted(weights, key=lambda name: (-weights[name], name))
        ]
        apps = [
            {"name": name, "seconds": int(round(app_weights[name]))}
            for name in sorted(app_weights, key=lambda name: (-app_weights[name], name))
        ]
        domain_weights = {}
        if any(_browser_app(item["name"]) for item in apps):
            for web in web_spans:
                if web is None or web["data"].get("incognito") is True:
                    continue
                overlap = (min(group["end"], web["end"]) - max(group["start"], web["start"])).total_seconds()
                if overlap <= 0:
                    continue
                domain = _hostname(web["data"].get("url"))
                if domain:
                    domain_weights[domain] = domain_weights.get(domain, 0.0) + overlap
        domains = [
            {"name": name, "seconds": int(round(domain_weights[name]))}
            for name in sorted(domain_weights, key=lambda name: (-domain_weights[name], name))
        ]
        active = sum(weights.values())
        span = (group["end"] - group["start"]).total_seconds()
        blocks.append({
            "start": _iso_datetime(group["start"]),
            "end": _iso_datetime(group["end"]),
            "seconds": int(round(active)),
            "span_seconds": int(round(span)),
            "idle_seconds": max(0, int(round(span)) - int(round(active))),
            "fragments": len(fragments),
            "longest_fragment_seconds": int(round(longest)),
            "label": topics[0]["name"],
            "topics": topics,
            "apps": apps,
            "domains": domains,
            "domain": domains[0]["name"] if domains else "",
            "timeline": _timeline(group["start"], fragments),
        })
    return blocks


def _normalized_entry(entry, project_names=None, task_names=None, client_names=None, project_clients=None, task_clients=None):
    if not entry:
        return None
    entry = _dict(entry, "entry")
    project_id = _field(entry, "project_id", "projectId", "pid")
    project_name = entry.get("project_name", entry.get("projectName"))
    if project_name is None and project_names and project_id in project_names:
        project_name = project_names[project_id]
    task_id = _field(entry, "task_id", "taskId", "tid")
    task_name = entry.get("task_name", entry.get("taskName"))
    if task_name is None and task_names and task_id in task_names:
        task_name = task_names[task_id]
    client_id = _field(entry, "client_id", "clientId", "cid")
    client_name = entry.get("client_name", entry.get("clientName"))
    if client_name is None and client_names and client_id in client_names:
        client_name = client_names[client_id]
    if not client_name and task_clients and task_id in task_clients:
        client_name = task_clients[task_id]
    if not client_name and project_clients and project_id in project_clients:
        client_name = project_clients[project_id]
    tags = entry.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {
        "id": entry.get("id"),
        "workspace_id": _field(entry, "workspace_id", "workspaceId", "wid"),
        "project_id": project_id,
        "task_id": task_id,
        "description": str(entry.get("description") or "")[:MAX_TEXT],
        "project_name": str(project_name or ""),
        "task_name": str(task_name or ""),
        "client_name": str(client_name or ""),
        "tags": [str(tag.get("name") if isinstance(tag, dict) else tag)[:MAX_TAG] for tag in tags[:MAX_TAGS]],
        "billable": bool(entry.get("billable")),
        "project_color": str(entry.get("project_color") or ""),
        "start": entry.get("start", entry.get("started_at", "")),
        "stop": entry.get("stop", entry.get("stopped_at", "")) or "",
        "duration": entry.get("duration"),
        "created_with": entry.get("created_with", ""),
    }


def _normalized_user(user):
    user = _dict(user, "user")
    return {
        "id": user.get("id"),
        "name": str(user.get("fullname") or user.get("name") or ""),
        "timezone": user.get("timezone"),
        "default_workspace_id": user.get("default_workspace_id"),
        "beginning_of_week": user.get("beginning_of_week"),
    }


def _normalized_workspace(workspace):
    workspace = _dict(workspace, "workspace")
    return {
        "id": workspace.get("id"),
        "name": str(workspace.get("name") or ""),
        "organization_id": workspace.get("organization_id"),
        "default_currency": workspace.get("default_currency"),
        "default_hourly_rate": workspace.get("default_hourly_rate"),
    }


def _normalized_project(project):
    project = _dict(project, "project")
    archived = bool(project.get("archived")) or project.get("active") is False
    status = project.get("status") or ("archived" if archived else "active")
    color = _color(project.get("color"))
    return {
        "id": project.get("id"),
        "workspace_id": _field(project, "workspace_id", "workspaceId", "wid"),
        "name": str(project.get("name") or "")[:MAX_TEXT],
        "client_id": project.get("client_id"),
        "client_name": str(project.get("client_name") or "")[:MAX_TEXT],
        "client": str(project.get("client_name") or "")[:MAX_TEXT],
        "archived": archived,
        "active": not archived,
        "status": status,
        "is_private": project.get("is_private"),
        "external_reference": project.get("external_reference"),
        "created_at": project.get("created_at"),
        "at": project.get("at"),
        "start_date": project.get("start_date"),
        "end_date": project.get("end_date"),
        "estimated_hours": project.get("estimated_hours"),
        "estimated_seconds": project.get("estimated_seconds"),
        "fixed_fee": project.get("fixed_fee"),
        "billable": project.get("billable"),
        "color": color,
    }


def _color(value):
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        return ""
    return value.lower()


def _normalized_task(task):
    task = _dict(task, "task")
    status = task.get("status")
    active = task.get("active")
    if active is None:
        active = str(status or "active").lower() not in ("archived", "inactive")
    return {
        "id": task.get("id"),
        "workspace_id": _field(task, "workspace_id", "workspaceId", "wid"),
        "project_id": _field(task, "project_id", "projectId", "pid"),
        "name": str(task.get("name") or "")[:MAX_TEXT],
        "active": bool(active),
        "status": str(status or ("active" if active else "inactive")),
        "at": task.get("at"),
        "estimated_seconds": task.get("estimated_seconds"),
        "tracked_seconds": task.get("tracked_seconds"),
        "client_id": task.get("client_id"),
        "client_name": str(task.get("client_name") or "")[:MAX_TEXT],
        "project_name": str(task.get("project_name") or "")[:MAX_TEXT],
        "project_color": _color(_field(task, "project_color", "color")),
        "project_billable": task.get("project_billable"),
        "project_is_private": task.get("project_is_private"),
        "external_reference": task.get("external_reference"),
    }


def _normalized_tag(tag, workspace_id):
    if isinstance(tag, str):
        return {"id": None, "workspace_id": workspace_id, "name": tag[:MAX_TAG]}
    tag = _dict(tag, "tag")
    return {"id": tag.get("id"), "workspace_id": tag.get("workspace_id", workspace_id), "name": str(tag.get("name") or "")[:MAX_TAG]}


def _normalized_client(client, workspace_id):
    client = _dict(client, "client")
    return {"id": client.get("id"), "workspace_id": client.get("workspace_id", workspace_id), "name": str(client.get("name") or "")[:MAX_TEXT]}


def _list_response(value, name):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in (name, "data", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    raise ApiError("Toggl returned an invalid " + name + " response.", 502, True)


def _task_page(value):
    if isinstance(value, list):
        return value, None
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        total_count = value.get("total_count")
        if total_count is not None and (isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < 0):
            raise ApiError("Toggl returned an invalid tasks response.", 502, True)
        return value["data"], total_count
    raise ApiError("Toggl returned an invalid tasks response.", 502, True)


def _cache_time(value):
    if isinstance(value, _REAL_DATETIME):
        result = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result = _REAL_DATETIME.fromtimestamp(value, timezone.utc)
    else:
        raise ValueError("invalid cache clock")
    if result.tzinfo is None:
        raise ValueError("cache clock must include a timezone")
    return result.astimezone(timezone.utc)


def _cache_iso(value):
    return _cache_time(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cache_expiry(value):
    if not isinstance(value, str):
        raise ValueError("invalid cache expiry")
    return _cache_time(_REAL_DATETIME.fromisoformat(value.replace("Z", "+00:00")))


def _cache_fields(value, fields):
    return isinstance(value, dict) and set(value) == set(fields)


def _cache_workspace_items(value, workspace_id, fields):
    if not isinstance(value, list):
        return False
    for item in value:
        if not _cache_fields(item, fields):
            return False
        item_workspace = item.get("workspace_id")
        if item_workspace not in (None, workspace_id):
            return False
    return True


class _CacheStore:
    """Small private cache store; only normalized values are passed to it."""

    _USER_FIELDS = {"id", "name", "timezone", "default_workspace_id", "beginning_of_week"}
    _WORKSPACE_FIELDS = {"id", "name", "organization_id", "default_currency", "default_hourly_rate"}
    _PROJECT_FIELDS = {
        "id", "workspace_id", "name", "client_id", "client_name", "client", "archived", "active", "status",
        "is_private", "external_reference", "created_at", "at", "start_date", "end_date", "estimated_hours",
        "estimated_seconds", "fixed_fee", "billable", "color",
    }
    _TASK_FIELDS = {
        "id", "workspace_id", "project_id", "name", "active", "status", "at", "estimated_seconds",
        "tracked_seconds", "client_id", "client_name", "project_name", "project_color", "project_billable",
        "project_is_private", "external_reference",
    }
    _TAG_FIELDS = {"id", "workspace_id", "name"}
    _CLIENT_FIELDS = {"id", "workspace_id", "name"}

    def __init__(self, root, account_key, clock):
        self.root = Path(root)
        self.account_key = account_key
        self.clock = clock
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, kind, workspace_id=None):
        # For "awday", workspace_id carries an ISO date string, not a workspace id.
        if kind == "awday" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(workspace_id or "")):
            raise ValueError("awday cache key must be an ISO date")
        if kind == "account":
            name = "account-%s.json" % self.account_key
        elif kind == "awbuckets":
            name = "awbuckets-%s.json" % self.account_key
        elif kind == "awday":
            name = "awday-%s-%s.json" % (self.account_key, workspace_id)
        elif kind == "entries":
            name = "entries-%s-%d.json" % (self.account_key, workspace_id)
        else:
            name = "workspace-%s-%d.json" % (self.account_key, workspace_id)
        return self.root / name

    def _valid_common(self, value, kind, workspace_id=None):
        if not isinstance(value, dict):
            return None
        if value.get("schema") != CACHE_SCHEMA or value.get("version") != CACHE_VERSION:
            return None
        if value.get("kind") != kind or value.get("account_key") != self.account_key:
            return None
        if kind in ("workspace", "awday", "entries") and value.get("workspace_id") != workspace_id:
            return None
        try:
            expiry = _cache_expiry(value.get("expires_at"))
        except (TypeError, ValueError, OverflowError):
            return None
        return expiry

    def _valid_account(self, value):
        if set(value) != {"schema", "version", "kind", "account_key", "expires_at", "user", "workspaces"}:
            return None
        if not _cache_fields(value["user"], self._USER_FIELDS):
            return None
        workspaces = value["workspaces"]
        if not isinstance(workspaces, list):
            return None
        for workspace in workspaces:
            if not _cache_fields(workspace, self._WORKSPACE_FIELDS):
                return None
            if isinstance(workspace.get("id"), bool) or not isinstance(workspace.get("id"), int) or workspace["id"] <= 0:
                return None
        return True

    def _valid_workspace(self, value, workspace_id):
        expected = {
            "schema", "version", "kind", "account_key", "workspace_id", "expires_at", "projects", "tasks",
            "tasks_available", "tags", "clients",
        }
        if set(value) != expected or not isinstance(value.get("tasks_available"), bool):
            return False
        return (
            _cache_workspace_items(value["projects"], workspace_id, self._PROJECT_FIELDS)
            and _cache_workspace_items(value["tasks"], workspace_id, self._TASK_FIELDS)
            and _cache_workspace_items(value["tags"], workspace_id, self._TAG_FIELDS)
            and _cache_workspace_items(value["clients"], workspace_id, self._CLIENT_FIELDS)
        )

    def load(self, kind, workspace_id=None):
        try:
            with self._path(kind, workspace_id).open("r", encoding="utf-8") as stream:
                value = json.load(stream)
            expiry = self._valid_common(value, kind, workspace_id)
            if expiry is None:
                return None
            if kind == "account":
                if not self._valid_account(value):
                    return None
            elif kind in ("awbuckets", "awday"):
                if not isinstance(value.get("payload"), dict):
                    return None
            elif kind == "entries":
                if not isinstance(value.get("entries"), list):
                    return None
            elif not self._valid_workspace(value, workspace_id):
                return None
            return value, expiry
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def write(self, kind, value, workspace_id=None):
        path = self._path(kind, workspace_id)
        fd = None
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".omarchy-toggl-", suffix=".tmp", dir=str(self.root))
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                fd = None
                json.dump(value, stream, separators=(",", ":"), sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            temporary = None
            try:
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        except (OSError, TypeError, ValueError):
            return False
        finally:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        return True


def _history_days(value):
    if value is None:
        return 30
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("days must be an integer.")
    if value < 1:
        return 30
    return value if value <= HISTORY_MAX_DAYS else HISTORY_SAFE_DAYS


def _next_day(date_value):
    """Toggl's /me/time_entries treats end_date as exclusive: start_date=D&
    end_date=D answers nothing. Measured live (0 vs 6 entries for the same
    day). Every single-day fetch must ask for D..D+1."""
    return (datetime.strptime(date_value, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def _range_date(payload, name):
    try:
        return datetime.strptime(str(payload.get(name)), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(name + " must be an ISO date (YYYY-MM-DD).")


def _classify_index(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(name + " must be a non-negative integer.")
    return value


def _classify_block_prompt(block):
    """One block, no projects, no past descriptions -- everything the model was
    ever shown as context, it copied (ruling R-AO)."""
    when = str(block.get("start") or "")[11:16]
    return "\n".join([
        "Activity block:",
        "%s%s" % (when + ", " if when else "", _classify_minutes(block["seconds"])),
        "Window titles: %s" % _classify_list(block["topics"], 12),
        "Apps: %s" % _classify_list(block["apps"], 6),
        "Sites: %s" % _classify_list(block["domains"], 6),
    ])


def _classify_block_schema():
    return {"type": "object", "required": ["description"], "properties": {
        "description": {"type": "string", "maxLength": CLASSIFIER_MAX_DESCRIPTION}}}


def _classify_prompt(blocks, projects, past=None):
    project_lines = "\n".join(
        "%d — %s (%s)" % (project["id"], project["name"], project["client"] or "no client")
        for project in projects
    )
    names = dict((project["id"], project["name"]) for project in projects)
    block_lines = []
    for block in blocks:
        # Rich input (ruling R-AN): titles, apps and sites with minutes, and the
        # time of day -- the model synthesises from what it is shown.
        start = str(block.get("start") or "")
        when = start[11:16] if len(start) >= 16 else ""
        line = (
            "Block %d — %s%s\nWindow titles: %s\nApps: %s\nSites: %s"
            % (block["index"], when + ", " if when else "", _classify_minutes(block["seconds"]),
               _classify_list(block["topics"], 12), _classify_list(block["apps"], 6), _classify_list(block["domains"], 6))
        )
        # The user's own past labels for similar activity (ruling R-AK), as a
        # hint: strong matches never reach the model (Model.js guesses them
        # directly), so what arrives here is weak, and a 1.7B model given a
        # bare quote copied it onto every block. Say what it is for.
        hits = (past or {}).get(block["index"]) or []
        if hits:
            line += "\nPast entries for similar activity: " + "; ".join(
                '"%s" (project %s)' % (hit["description"], hit["project_id"] if hit.get("project_id") in names else "none")
                for hit in hits
            ) + " -- a hint for the project; still describe this block's own work."
        block_lines.append(line)
    # No worked example: on every live variant the 0.6B model leaked it into
    # its answers -- verbatim, blended ("<repo> PR #42"), or by copying the
    # example's units. Without one it copies a topic title, which
    # Model.classifyGuessFor discards when it equals the label (R-AH, R-AJ).
    # The instruction stays short so the debug log (500 chars per string)
    # still shows the first block.
    # No "answer every block" line: the grammar pins the count, and the
    # measured wording (ruling R-AN) is exactly this.
    return (
        "Projects (id — name (client)):\n%s\n\nBlocks:\n%s"
        % (project_lines or "none", "\n\n".join(block_lines) or "none")
    )


def _classify_name(value):
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _classify_named(items):
    """[{name, seconds}] from either bare names or {name, seconds} pairs;
    Model.js sends the pairs (ruling R-AN), older callers sent names."""
    out = []
    for item in items or []:
        name = _classify_name(item)
        if not name:
            continue
        seconds = 0
        if isinstance(item, dict):
            try:
                seconds = max(0, int(item.get("seconds") or 0))
            except (TypeError, ValueError):
                seconds = 0
        out.append({"name": name, "seconds": seconds})
    return out


def _classify_minutes(seconds):
    return "%dm" % max(1, int(seconds or 0) // 60)


def _classify_list(items, limit):
    items = sorted(items or [], key=lambda item: -int(item.get("seconds") or 0))[:limit]
    return ", ".join(
        "%s (%s)" % (item["name"], _classify_minutes(item["seconds"])) if item.get("seconds") else item["name"]
        for item in items
    ) or "none"


def _classify_schema(project_ids, block_count=None):
    # block_count pins the results array: with it the grammar itself forces one
    # result per block, where the 0.6B model alone stopped after four of six.
    items = {} if block_count is None else {"minItems": block_count, "maxItems": block_count}
    return {
        "type": "object",
        "required": ["results"],
        "properties": {
            "results": dict(items, **{
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["index", "description", "project_id", "confidence"],
                    "properties": {
                        "index": {"type": "integer"},
                        "description": {"type": "string", "maxLength": CLASSIFIER_MAX_DESCRIPTION},
                        "project_id": {"enum": list(project_ids) + [None]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            })
        },
    }


def _classify_content(raw):
    """Pulls the JSON-schema-constrained message content out of an
    OpenAI-compatible chat completion response. Any shape surprise here is
    treated as an empty result, never as a reason to raise -- classify()
    already promises never to return ok:false."""
    try:
        content = raw["choices"][0]["message"]["content"]
        return json.loads(content) if isinstance(content, str) else content
    except (TypeError, KeyError, IndexError, ValueError):
        return None


def _classify_results(content, project_ids):
    if not isinstance(content, dict) or not isinstance(content.get("results"), list):
        return []
    valid_ids = set(project_ids)
    results = []
    for item in content["results"]:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item["index"])
        except (KeyError, TypeError, ValueError):
            continue
        description = str(item.get("description", ""))[:CLASSIFIER_MAX_DESCRIPTION]
        project_id = item.get("project_id")
        # Safety net: the schema already constrains this to the supplied
        # enum, but a hand-rolled or misbehaving server can ignore it.
        if project_id not in valid_ids:
            project_id = None
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        results.append({
            "index": index, "description": description,
            "project_id": project_id, "confidence": confidence,
        })
    return results


# ---------------------------------------------------------------------------
# Local history store (stage 7, ruling R-AK). Learns which description and
# project the user attached to which activity -- from blocks already covered by
# a Toggl entry (ours or a manual one) and from every apply -- and suggests the
# closest past records for a pending block. Lives in XDG_DATA_HOME, never the
# cache dir: it is the user's data, not something to be regenerated.
HISTORY_VERSION = 2
HISTORY_CORRECTION_CAP = 2000
HISTORY_RECORD_CAP = 2000
HISTORY_ENTRY_CAP = 5000
HISTORY_GUESS_SCORE = 0.5     # Model.historyGuessFor takes a guess at this score
HISTORY_PROMPT_SCORE = 0.2    # classify quotes records at this score...
HISTORY_PROMPT_LIMIT = 2      # ...at most this many per block


def _embed(texts, opener=None, timeout=EMBEDDER_TIMEOUT):
    """Vectors for `texts`, or None when the embedder is absent. Like classify(),
    this never raises: the day renders without geometry rather than not at all."""
    texts = [str(t or "").strip() or "unknown activity" for t in texts]
    if not texts:
        return None
    body = json.dumps({"input": texts, "model": EMBEDDER_MODEL}, separators=(",", ":")).encode("utf-8")
    request = Request(EMBEDDER_URL, data=body,
                      headers={"Content-Type": "application/json", "Accept": "application/json"},
                      method="POST")
    try:
        with (opener or urlopen)(request, timeout=timeout) as response:
            payload = json.load(response)
        items = payload["data"]
        if len(items) != len(texts):
            return None
        indices = [item.get("index", offset) for offset, item in enumerate(items)]
        if sorted(indices) != list(range(len(texts))):
            return None
        vectors = [item["embedding"] for _, item in sorted(zip(indices, items), key=lambda pair: pair[0])]
        return vectors if all(_valid_vector(v) for v in vectors) else None
    except Exception:
        return None


def _valid_vector(value):
    return (isinstance(value, list) and bool(value) and
            all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value))


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def block_signature(block):
    """The text an embedder sees: the titles, apps and sites, biggest first and
    without minutes -- durations are noise to a sentence encoder."""
    parts = []
    for field, cap in (("topics", 12), ("apps", 6), ("domains", 6)):
        names = [item["name"] for item in _named_list(block.get(field))][:cap]
        if names:
            parts.append(", ".join(names))
    label = str(block.get("label") or "")
    if label:
        parts.insert(0, label)
    return " | ".join(parts)


def _named_list(items):
    out = []
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            seconds = item.get("seconds") or 0
        else:
            name, seconds = str(item or ""), 0
        if name:
            try:
                seconds = max(0, int(seconds))
            except (TypeError, ValueError):
                seconds = 0
            out.append({"name": name, "seconds": seconds})
    out.sort(key=lambda i: -i["seconds"])
    return out


def _text_f1(predicted, truth):
    """Token overlap between a proposal and what the user actually wrote. Blunt,
    but it is the same number for every layer, which is what a harness needs."""
    a = set(t for t in re.findall(r"[a-z0-9]+", (predicted or "").lower()) if len(t) > 2)
    b = set(t for t in re.findall(r"[a-z0-9]+", (truth or "").lower()) if len(t) > 2)
    if not a or not b:
        return 0.0
    hit = len(a & b)
    if not hit:
        return 0.0
    precision, recall = hit / len(a), hit / len(b)
    return 2 * precision * recall / (precision + recall)


def _history_root():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "omarchy-toggl-track")


def _history_key(name):
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()


def _named_seconds(items, fallback_seconds=0):
    out = {}
    for item in items or []:
        if isinstance(item, dict):
            key = _history_key(item.get("name"))
            seconds = item.get("seconds", fallback_seconds)
        else:
            key = _history_key(item)
            seconds = fallback_seconds
        if not key:
            continue
        try:
            out[key] = out.get(key, 0) + max(0, int(seconds or 0))
        except (TypeError, ValueError):
            out[key] = out.get(key, 0)
    return out


def history_mutation(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.transaction():
            self._indexes = None
            return method(self, *args, **kwargs)
    return wrapped


class HistoryStore:
    """JSON-backed learning state. Actions catch store failures and degrade.

    Mutating actions use transaction(); no network call runs under its lock.
    """

    def __init__(self, root, clock=None):
        self.root = root
        self.path = os.path.join(root, "history.json")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._data = None
        self._transaction_depth = 0
        self._indexes = None

    @contextmanager
    def transaction(self):
        """Short read/modify/write lock. Never hold this across network I/O."""
        if self._transaction_depth:
            yield self
            return
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        with os.fdopen(os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600), "r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._data = None
            self._indexes = None
            before = json.dumps(self.load(), sort_keys=True)
            self._transaction_depth = 1
            try:
                yield self
            finally:
                self._transaction_depth = 0
                if json.dumps(self._data, sort_keys=True) != before:
                    self.save()

    def indexes(self):
        if self._indexes is None:
            data = self.load()
            counts = collections.Counter()
            records = {}
            bags = []
            for record in data["records"]:
                records[record["key"]] = record
                bags.append((record, set(record.get("apps") or {}), set(record.get("domains") or {})))
                pid = record.get("project_id")
                if pid is not None:
                    counts[int(pid)] += max(1, int(record.get("seen") or 1))
            self._indexes = {"counts": counts, "records": records, "bags": bags,
                             "seen": set(data["entry_ids"])}
        return self._indexes

    def queue_vector(self, block, entry, workspace_id):
        if entry.get("id") is None or entry.get("project_id") is None:
            return
        key = "%s:%s" % (workspace_id, entry["id"])
        self.load()["pending_vectors"][key] = {"workspace_id": workspace_id,
            "project_id": entry["project_id"], "text": block_signature(block)}

    def _now(self):
        return _iso_datetime(_cache_time(self._clock()))

    def _fresh(self):
        return {"version": HISTORY_VERSION, "records": [], "entry_ids": [],
                "centroids": {}, "corrections": [], "pending_vectors": {}}

    def load(self):
        if self._data is not None:
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError("history.json is not a history store")
            data.setdefault("entry_ids", [])
            # v1 stores predate centroids and corrections; adopt them in place
            # rather than discarding a store the user has been filling for weeks.
            data.setdefault("pending_vectors", {})
            data.setdefault("centroids", {})
            data.setdefault("corrections", [])
            data["version"] = HISTORY_VERSION
            data["records"] = [r for r in data["records"] if isinstance(r, dict) and r.get("key")]
            self._data = data
        except FileNotFoundError:
            self._data = self._fresh()
        except (OSError, ValueError):
            # Keep the user's file for inspection, start clean.
            try:
                os.replace(self.path, self.path + ".broken-" + re.sub(r"[^0-9]", "", self._now())[:14])
            except OSError:
                pass
            self._data = self._fresh()
        return self._data

    def save(self):
        if self._data is None:
            return False
        if self._transaction_depth:
            return True
        try:
            os.makedirs(self.root, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as handle:
                tmp = handle.name
                json.dump(self._data, handle, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    @property
    def records(self):
        return self.load()["records"]

    def seen(self, entry_id):
        return entry_id is not None and str(entry_id) in self.indexes()["seen"]

    @history_mutation
    def learn(self, block, entry):
        """One block, one covering entry. Returns True when something was
        recorded. The same entry id is learned once, so reloads never inflate."""
        if not isinstance(block, dict) or not isinstance(entry, dict):
            return False
        description = re.sub(r"\s+", " ", str(entry.get("description") or "")).strip()
        project_id = entry.get("project_id")
        project_id = int(project_id) if isinstance(project_id, int) and not isinstance(project_id, bool) and project_id > 0 else None
        task_id = entry.get("task_id")
        task_id = int(task_id) if isinstance(task_id, int) and not isinstance(task_id, bool) and task_id > 0 else None
        if not description and project_id is None:
            return False
        data = self.load()
        entry_id = entry.get("id")
        if entry_id is not None:
            if str(entry_id) in self.indexes()["seen"]:
                return False
            data["entry_ids"].append(str(entry_id))
            del data["entry_ids"][:-HISTORY_ENTRY_CAP]
        seconds = 0
        try:
            seconds = max(0, int(block.get("seconds") or 0))
        except (TypeError, ValueError):
            pass
        key = "%s|%s" % (description.lower(), project_id or 0)
        record = self.indexes()["records"].get(key)
        now = self._now()
        if record is None:
            record = {"key": key, "description": description, "project_id": project_id, "task_id": task_id,
                      "topics": {}, "apps": {}, "domains": {}, "seen": 0, "first": now, "last": now}
            data["records"].append(record)
        if task_id is not None:
            record["task_id"] = task_id
        for field, items in (("topics", block.get("topics")), ("apps", block.get("apps"))):
            bag = record.setdefault(field, {})
            for name, secs in _named_seconds(items).items():
                bag[name] = bag.get(name, 0) + secs
        domains = record.setdefault("domains", {})
        domain_items = list(block.get("domains") or [])
        if block.get("domain"):
            domain_items.append({"name": block["domain"], "seconds": seconds})
        for name, secs in _named_seconds(domain_items, seconds).items():
            domains[name] = domains.get(name, 0) + secs
        record["seen"] = int(record.get("seen") or 0) + 1
        record["last"] = now
        if len(data["records"]) > HISTORY_RECORD_CAP:
            data["records"].sort(key=lambda r: str(r.get("last") or ""), reverse=True)
            del data["records"][HISTORY_RECORD_CAP:]
        self._indexes = None
        self.save()
        return True

    def observe_vector(self, project_id, vector):
        """Fold one labelled block's embedding into that project's centroid, as a
        running mean -- no need to keep or re-embed the raw vectors."""
        if not vector or project_id is None:
            return False
        data = self.load()
        key = str(int(project_id))
        entry = data["centroids"].get(key)
        if not entry or len(entry.get("vector") or []) != len(vector):
            data["centroids"][key] = {"vector": [float(x) for x in vector], "count": 1}
            return True
        count = int(entry.get("count") or 1)
        entry["vector"] = [(old * count + new) / (count + 1) for old, new in zip(entry["vector"], vector)]
        entry["count"] = count + 1
        return True

    def project_scores(self, block, vector=None, active_ids=None):
        """Ranked [{project_id, score, prior, similarity}], best first. The prior
        is how often the user picks that project; similarity is cosine against
        its centroid. Measured on 26 blocks: prior alone 81%, centroids 77%,
        best language model 65% -- so this is the whole decision (ruling R-AO)."""
        data = self.load()
        counts = self.indexes()["counts"]
        total = sum(counts.values())
        candidates = set(counts)
        for key in data["centroids"]:
            try:
                candidates.add(int(key))
            except (TypeError, ValueError):
                continue
        if active_ids is not None:
            allowed = set(int(i) for i in active_ids)
            candidates &= allowed
        out = []
        for pid in candidates:
            prior = (counts.get(pid, 0) / total) if total else 0.0
            entry = data["centroids"].get(str(pid))
            similarity = 0.0
            if vector and entry:
                # Clamp at zero rather than folding -1..1 into 0..1: folding hands
                # an unrelated project half a point, which let a 4:1 prior outvote
                # a perfect centroid match.
                similarity = max(0.0, _cosine(vector, entry.get("vector")))
            score = ((1.0 - PROJECT_CENTROID_WEIGHT) * prior
                     + PROJECT_CENTROID_WEIGHT * similarity) if vector else prior
            out.append({"project_id": pid, "score": round(score, 4),
                        "prior": round(prior, 4), "similarity": round(similarity, 4)})
        out.sort(key=lambda item: (-item["score"], -item["prior"], item["project_id"]))
        return out

    @history_mutation
    def record_correction(self, block, suggested, chosen):
        """Every apply is a training signal: what we offered, what the user kept.
        `corrected` is the flag the evaluation harness counts."""
        suggested = suggested if isinstance(suggested, dict) else {}
        chosen = chosen if isinstance(chosen, dict) else {}
        if not chosen:
            return False
        data = self.load()
        row = {
            "at": self._now(),
            "signature": block_signature(block) if isinstance(block, dict) else "",
            "seconds": int((block or {}).get("seconds") or 0),
            "suggested_description": str(suggested.get("description") or ""),
            "suggested_project_id": suggested.get("project_id"),
            "suggested_source": str(suggested.get("source") or ""),
            "chosen_description": str(chosen.get("description") or ""),
            "chosen_project_id": chosen.get("project_id"),
        }
        row["corrected_description"] = (
            _history_key(row["suggested_description"]) != _history_key(row["chosen_description"]))
        row["corrected_project"] = row["suggested_project_id"] != row["chosen_project_id"]
        data["corrections"].append(row)
        del data["corrections"][:-HISTORY_CORRECTION_CAP]
        self.save()
        return True

    def correction_stats(self):
        """What the harness reports: how often each suggestion source survived
        contact with the user."""
        data = self.load()
        rows = data.get("corrections") or []
        by_source = collections.defaultdict(lambda: {"n": 0, "description_kept": 0, "project_kept": 0})
        for row in rows:
            bucket = by_source[row.get("suggested_source") or "unknown"]
            bucket["n"] += 1
            if not row.get("corrected_description"):
                bucket["description_kept"] += 1
            if not row.get("corrected_project"):
                bucket["project_kept"] += 1
        return {"total": len(rows), "by_source": dict(by_source)}

    def suggest(self, block, limit=3):
        """Closest past records for a block, scored 0..1: 75% share of the
        block's topic seconds that a record has seen before, 15% app overlap,
        10% same domain. Ties go to the record seen more often."""
        if not isinstance(block, dict):
            return []
        topics = _named_seconds(block.get("topics"))
        total = sum(topics.values()) or 1
        apps = set(_named_seconds(block.get("apps")))
        domains = set(_named_seconds(block.get("domains")))
        if block.get("domain"):
            domains.add(_history_key(block["domain"]))
        scored = []
        for record, rec_apps, rec_domains in self.indexes()["bags"]:
            rec_topics = record.get("topics") or {}
            overlap = sum(secs for name, secs in topics.items() if name in rec_topics) / float(total)
            app_share = (len(apps & rec_apps) / float(len(apps))) if apps else 0.0
            domain_hit = 1.0 if domains and (domains & rec_domains) else 0.0
            if overlap <= 0 and not (domain_hit and app_share > 0):
                continue
            score = 0.75 * overlap + 0.15 * app_share + 0.10 * domain_hit
            scored.append((round(score, 2), int(record.get("seen") or 0), record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [{"description": r.get("description", ""), "project_id": r.get("project_id"),
                 "task_id": r.get("task_id"), "score": score, "seen": seen}
                for score, seen, r in scored[:max(0, int(limit))]]


class TogglAPI:
    def __init__(self, client=None, cache_root=None, clock=None, activitywatch_opener=None, classify_opener=None, logger=None, data_root=None, embed_opener=None):
        self._client = client
        self._cache_root = cache_root
        # Like the cache: a test with a fake client and no data_root must never
        # touch the real XDG_DATA_HOME.
        self._history_allowed = client is None or data_root is not None
        self._data_root = data_root
        self._history_store = None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._activitywatch_opener = activitywatch_opener or urlopen
        self._classify_opener = classify_opener or urlopen
        # Injectable like the others: a test with a fake client must never reach
        # a real embedder, and _embed() already degrades to None without one.
        self._embed_opener = embed_opener
        self._cache_allowed = client is None or cache_root is not None
        self._cache_store = None
        self._cache_store_loaded = False
        self.logger = logger

    @property
    def client(self):
        if self._client is None:
            self._client = TogglClient(logger=self.logger)
        return self._client

    def _now_datetime(self):
        return _cache_time(self._clock())

    def _history(self):
        if not self._history_allowed:
            return None
        if self._history_store is None:
            self._history_store = HistoryStore(self._data_root or _history_root(), self._clock)
        return self._history_store

    def _store(self):
        if self._cache_store_loaded:
            return self._cache_store
        self._cache_store_loaded = True
        if not self._cache_allowed:
            return None
        account_key = getattr(self.client, "account_key", None)
        if not isinstance(account_key, str) or re.fullmatch(r"[0-9a-f]{32}", account_key) is None:
            return None
        if self._cache_root is None:
            cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
            self._cache_root = os.path.join(cache_home, "omarchy-toggl-track")
        try:
            self._cache_store = _CacheStore(self._cache_root, account_key, self._clock)
        except OSError:
            self._cache_store = None
        return self._cache_store

    def _inference_cache(self, workspace_id):
        try:
            store = self._store()
            if store is not None:
                return InferenceCache(self._cache_root, [self.client.account_key, workspace_id],
                                      lambda: self._now_datetime().timestamp())
        except Exception:
            pass
        return None

    def _vectors(self, texts, workspace_id, deadline=None):
        texts = [str(t or "").strip() or "unknown activity" for t in texts]
        if not texts:
            return []
        cache = self._inference_cache(workspace_id)
        fingerprint = model_fingerprint("embedding") if cache else None
        found, missing = {}, []
        for text in dict.fromkeys(texts):
            key = cache.key("embedding", fingerprint, text) if cache else None
            value = cache.get(key) if cache else None
            if _valid_vector(value):
                found[text] = value
            else:
                missing.append(text)
        if missing:
            remaining = min(EMBEDDER_TIMEOUT, deadline - time.monotonic()) if deadline else EMBEDDER_TIMEOUT
            # Tests with fake clients never contact the installed embedder.
            opener = self._embed_opener
            if opener is None and not self._history_allowed:
                return None
            if opener is None and self._client is not None and not isinstance(self._client, TogglClient):
                return None
            vectors = _embed(missing, opener or urlopen, timeout=remaining) if remaining > 0 else None
            if vectors:
                for text, vector in zip(missing, vectors):
                    found[text] = vector
                    if cache:
                        cache.put(cache.key("embedding", fingerprint, text), vector)
        return [found.get(text) for text in texts]

    def _drain_vectors(self, workspace_id, deadline=None):
        history = self._history()
        if history is None:
            return
        # Snapshot under lock, infer without it, then merge against fresh state.
        with history.transaction():
            pending = {k: dict(v) for k, v in history.load()["pending_vectors"].items()
                       if v.get("workspace_id") == workspace_id}
        if not pending:
            return
        keys = list(pending)[:64]
        vectors = self._vectors([pending[k]["text"] for k in keys], workspace_id, deadline)
        if vectors:
            with history.transaction():
                current = history.load()["pending_vectors"]
                for key, vector in zip(keys, vectors):
                    if vector and current.get(key) == pending[key]:
                        history.observe_vector(pending[key]["project_id"], vector)
                        del current[key]

    def enrich_day(self, payload):
        workspace_id = _id(payload.get("workspace_id"), "workspace_id")
        started = time.monotonic()
        out = {"workspace_id": workspace_id, "date": payload.get("date"),
               "generation": payload.get("generation"), "blocks": [], "results": []}
        try:
            self._drain_vectors(workspace_id, started + CLASSIFIER_TIMEOUT)
            blocks = payload.get("blocks", [])
            if not isinstance(blocks, list):
                raise ValueError("blocks must be a list")
            vectors = self._vectors([block_signature(b) for b in blocks], workspace_id, started + CLASSIFIER_TIMEOUT)
            history = self._history()
            active_ids = [p["id"] for p in payload.get("projects", [])]
            for offset, block in enumerate(blocks):
                vector = vectors[offset] if vectors else None
                ranked = history.project_scores(block, vector, active_ids) if history else []
                out["blocks"].append({"index": block["index"], "signature": block.get("signature"),
                                      "projects": ranked[:PROJECT_SHORTLIST]})
            if payload.get("classify") and blocks:
                result = self.classify(payload, deadline=started + CLASSIFIER_TIMEOUT, vectors=vectors)
                out.update({key: result[key] for key in ("results", "degraded") if key in result})
            if any(v is None for v in (vectors or [])):
                out["degraded"] = True
        except Exception:
            out["degraded"] = True
        return out

    @staticmethod
    def _cache_status(kind, state, forced, stale, expires_at):
        return {kind: state, "forced": forced, "stale": stale, "expires_at": expires_at}

    def _account_data(self, force_refresh):
        store = self._store()
        now = self._now_datetime()
        cached = store.load("account") if store else None
        if cached and not force_refresh and now < cached[1]:
            return cached[0]["user"], cached[0]["workspaces"], self._cache_status(
                "account", "fresh", False, False, cached[0]["expires_at"]
            )

        try:
            user = _normalized_user(self.client.request("GET", "/me"))
            workspaces = [_normalized_workspace(item) for item in _list_response(self.client.request("GET", "/me/workspaces"), "workspaces")]
        except ApiError as error:
            if not (cached and error.retryable):
                raise
            return cached[0]["user"], cached[0]["workspaces"], self._cache_status(
                "account", "stale", force_refresh, True, cached[0]["expires_at"]
            )

        expires_at = _cache_iso(now + ACCOUNT_TTL)
        if store:
            store.write(
                "account",
                {
                    "schema": CACHE_SCHEMA,
                    "version": CACHE_VERSION,
                    "kind": "account",
                    "account_key": self.client.account_key,
                    "expires_at": expires_at,
                    "user": user,
                    "workspaces": workspaces,
                },
            )
        state = "disabled" if not store else ("refreshed" if cached or force_refresh else "miss")
        return user, workspaces, self._cache_status("account", state, force_refresh, False, None if not store else expires_at)

    def _current(self, project_names=None, task_names=None, client_names=None, project_clients=None, task_clients=None):
        return _normalized_entry(
            self.client.request("GET", "/me/time_entries/current"),
            project_names,
            task_names,
            client_names,
            project_clients,
            task_clients,
        )

    def bootstrap(self, payload=None):
        payload = payload or {}
        force_refresh = _bool(payload.get("force_refresh", False), "force_refresh")
        user, workspaces, cache = self._account_data(force_refresh)
        data = {"user": user, "workspaces": workspaces, "current": self._current(), "cache": cache}
        if _bool(payload.get("skip_sync", False), "skip_sync"):
            return data
        # A falsy workspace_id (0, absent or null) means "no persisted
        # preference sent", not an invalid id -- a fresh install or any
        # cleared-workspace state sends 0 unconditionally, and that must not
        # fail validation. Only a genuinely supplied (truthy) id is checked;
        # _default_workspace already falls through safely when passed None.
        raw_workspace_id = _field(payload, "workspace_id", "workspaceId", "wid")
        requested = _id(raw_workspace_id, "workspace_id") if raw_workspace_id else None
        workspace_id = self._default_workspace(data, requested)
        if not workspace_id:
            return data
        try:
            # The workspace-cache status below replaces the account-cache
            # status set above under the same shared "cache" key. That is not
            # a bug -- the pre-fold flow ended in the same state -- but the
            # collision is easy to misread while tracing a cache issue.
            data.update(self.sync({
                "workspace_id": workspace_id,
                "days": payload.get("days"),
                "force_refresh": payload.get("force_refresh", False),
                "skip_current": True,
            }))
        except ApiError as error:
            _log(self.logger, "errors", action="bootstrap_sync", ok=False, status=error.status)
            data["sync_failed"] = True
        data["workspace_id"] = workspace_id
        return data

    @staticmethod
    def _default_workspace(data, requested=None):
        workspaces = data.get("workspaces") or []
        user = data.get("user") or {}
        current = data.get("current") or {}
        candidates = [
            requested,
            current.get("workspace_id"),
            user.get("default_workspace_id"),
            workspaces[0].get("id") if workspaces else None,
        ]
        available = {item.get("id") for item in workspaces if isinstance(item, dict)}
        for candidate in candidates:
            if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate in available:
                return candidate
        return 0

    def _projects(self, workspace_id):
        projects = []
        page = 1
        while True:
            batch = _list_response(
                self.client.request(
                    "GET", "/workspaces/%d/projects" % workspace_id,
                    {"active": "both", "per_page": PROJECT_PAGE_SIZE, "page": page},
                ),
                "projects",
            )
            projects.extend(_normalized_project(item) for item in batch)
            if len(batch) < PROJECT_PAGE_SIZE:
                return projects
            page += 1

    def _tasks(self, workspace_id):
        tasks = []
        page = 1
        while True:
            response = self.client.request(
                "GET", "/workspaces/%d/tasks" % workspace_id,
                {"active": "both", "page": page, "per_page": TASK_PAGE_SIZE},
            )
            batch, total_count = _task_page(response)
            tasks.extend(_normalized_task(item) for item in batch)
            if (total_count is not None and len(tasks) >= total_count) or len(batch) < TASK_PAGE_SIZE:
                return tasks
            page += 1

    def _history_entries(self, workspace_id, start_date, end_date):
        entries = self.client.request(
            "GET", "/me/time_entries", {"start_date": start_date, "end_date": end_date}
        )
        history = []
        for item in _list_response(entries, "time_entries"):
            normalized = _normalized_entry(item)
            if normalized and normalized["workspace_id"] == workspace_id:
                history.append(normalized)
        return history

    @staticmethod
    def _enrich_metadata(projects, tasks, clients):
        client_names = {item["id"]: item["name"] for item in clients if item.get("name")}
        projects_by_id = {item["id"]: item for item in projects}
        for task in tasks:
            project = projects_by_id.get(task.get("project_id"))
            if project:
                if not task.get("project_name"):
                    task["project_name"] = project["name"]
                if not task.get("project_color"):
                    task["project_color"] = project["color"]
                if task.get("client_id") is None:
                    task["client_id"] = project.get("client_id")
                if not task.get("client_name"):
                    task["client_name"] = project.get("client_name", "")
                if task.get("project_billable") is None:
                    task["project_billable"] = project.get("billable")
                if task.get("project_is_private") is None:
                    task["project_is_private"] = project.get("is_private")
            if not task.get("client_name") and task.get("client_id") in client_names:
                task["client_name"] = client_names[task["client_id"]]
        for item in projects:
            if not item.get("client_name") and item.get("client_id") in client_names:
                item["client_name"] = client_names[item["client_id"]]
            item["client"] = item.get("client_name", "")

    @staticmethod
    def _metadata_maps(projects, tasks, clients):
        client_names = {item["id"]: item["name"] for item in clients if item.get("name")}
        project_names = {item["id"]: item["name"] for item in projects}
        task_names = {item["id"]: item["name"] for item in tasks}
        project_clients = {
            item["id"]: item["client_name"]
            for item in projects
            if item.get("client_name") or item.get("client_id") in client_names
        }
        task_clients = {
            item["id"]: item["client_name"]
            for item in tasks
            if item.get("client_name") or item.get("client_id") in client_names
        }
        for item in projects:
            if not item.get("client_name") and item.get("client_id") in client_names:
                project_clients[item["id"]] = client_names[item["client_id"]]
        for item in tasks:
            if not item.get("client_name") and item.get("client_id") in client_names:
                task_clients[item["id"]] = client_names[item["client_id"]]
        return project_names, task_names, client_names, project_clients, task_clients

    def _fetch_entries(self, workspace_id, days, force_refresh):
        """Windowed fetch on a cold cache, `since` delta on a warm one.

        Both forms are subject to the 91-day start_date floor, so `since` is
        clamped exactly like start_date."""
        store = self._store()
        now = self._now_datetime()
        end_date = now.date()
        floor_date = end_date - timedelta(days=HISTORY_FLOOR_DAYS)
        start_date = max(end_date - timedelta(days=days - 1), floor_date)
        cached = store.load("entries", workspace_id) if store else None
        warm = (
            cached is not None and not force_refresh and now < cached[1]
            and cached[0].get("days") == days
        )

        if warm:
            previous = cached[0]
            since_moment = _cache_time(_cache_expiry(previous["expires_at"]) - ENTRIES_TTL)
            # Defence in depth: unreachable while ENTRIES_TTL is under the floor,
            # but a longer ENTRIES_TTL would make a since older than today-91
            # possible, and Toggl rejects that with 400.
            if since_moment.date() >= floor_date:
                params = {"since": int(since_moment.timestamp()), "meta": "true"}
                delta = _list_response(
                    self.client.request("GET", "/me/time_entries", params), "time_entries")
                merged = {str(item.get("id")): item for item in previous["entries"] if isinstance(item, dict)}
                for item in delta:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("id"))
                    if item.get("server_deleted_at"):
                        merged.pop(key, None)
                    else:
                        merged[key] = item
                raw = [item for item in merged.values()
                       if str(item.get("start", ""))[:10] >= start_date.isoformat()]
                self._write_entry_cache(store, workspace_id, raw, now, days)
                return raw

        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "meta": "true",
        }
        raw = _list_response(self.client.request("GET", "/me/time_entries", params), "time_entries")
        raw = [item for item in raw if isinstance(item, dict)]
        self._write_entry_cache(store, workspace_id, raw, now, days)
        return raw

    def _write_entry_cache(self, store, workspace_id, raw, now, days):
        if not store:
            return
        store.write("entries", {
            "schema": CACHE_SCHEMA, "version": CACHE_VERSION, "kind": "entries",
            "account_key": self.client.account_key, "workspace_id": workspace_id,
            "expires_at": _cache_iso(now + ENTRIES_TTL),
            "days": days,
            "entries": raw,
        }, workspace_id)

    def sync(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        days = _history_days(payload.get("days"))
        force_refresh = _bool(payload.get("force_refresh", False), "force_refresh")
        skip_current = _bool(payload.get("skip_current", False), "skip_current")
        store = self._store()
        now = self._now_datetime()
        cached = store.load("workspace", workspace_id) if store else None
        fresh = cached is not None and not force_refresh and now < cached[1]
        cache_state = "fresh" if fresh else "miss"
        cache_stale = False
        projects = []
        tasks = []
        tags = []
        clients = []
        tasks_available = True

        if fresh:
            assert cached is not None
            metadata = cached[0]
            projects = metadata["projects"]
            tasks = metadata["tasks"]
            tasks_available = metadata["tasks_available"]
            tags = metadata["tags"]
            clients = metadata["clients"]
        else:
            refresh_error = None
            try:
                projects = self._projects(workspace_id)
            except ApiError as error:
                if not (error.retryable and cached):
                    raise
                refresh_error = error

            if refresh_error is None:
                tasks_available = True
                try:
                    tasks = self._tasks(workspace_id)
                except ApiError as error:
                    if error.status in (403, 404):
                        tasks = []
                        tasks_available = False
                    elif error.retryable and cached:
                        refresh_error = error
                    else:
                        raise

            if refresh_error is None:
                try:
                    tags = [_normalized_tag(item, workspace_id) for item in _list_response(self.client.request("GET", "/workspaces/%d/tags" % workspace_id), "tags")]
                    clients = [_normalized_client(item, workspace_id) for item in _list_response(self.client.request("GET", "/workspaces/%d/clients" % workspace_id), "clients")]
                except ApiError as error:
                    if not (error.retryable and cached):
                        raise
                    refresh_error = error

            if refresh_error is not None:
                assert cached is not None
                metadata = cached[0]
                projects = metadata["projects"]
                tasks = metadata["tasks"]
                tasks_available = metadata["tasks_available"]
                tags = metadata["tags"]
                clients = metadata["clients"]
                cache_state = "stale"
                cache_stale = True
            else:
                self._enrich_metadata(projects, tasks, clients)
                expires_at = _cache_iso(now + WORKSPACE_TTL)
                if store:
                    store.write(
                        "workspace",
                        {
                            "schema": CACHE_SCHEMA,
                            "version": CACHE_VERSION,
                            "kind": "workspace",
                            "account_key": self.client.account_key,
                            "workspace_id": workspace_id,
                            "expires_at": expires_at,
                            "projects": projects,
                            "tasks": tasks,
                            "tasks_available": tasks_available,
                            "tags": tags,
                            "clients": clients,
                        },
                        workspace_id,
                    )
                cache_state = "refreshed" if force_refresh or cached else "miss"

        if cache_state == "stale":
            assert cached is not None
            expires_at = cached[0]["expires_at"]
        elif fresh:
            assert cached is not None
            expires_at = cached[0]["expires_at"]
        else:
            expires_at = _cache_iso(now + WORKSPACE_TTL)
        entries = self._fetch_entries(workspace_id, days, force_refresh)
        project_names, task_names, client_names, project_clients, task_clients = self._metadata_maps(projects, tasks, clients)
        history = []
        for item in entries:
            normalized = _normalized_entry(item, project_names, task_names, client_names, project_clients, task_clients)
            if normalized and normalized["workspace_id"] == workspace_id:
                history.append(normalized)
        result = {
            "projects": projects,
            "tasks": tasks,
            "tasks_available": tasks_available,
            "tags": tags,
            "clients": clients,
            "entries": history,
            "cache": self._cache_status("workspace", "disabled" if not store else cache_state, force_refresh, cache_stale, None if not store else expires_at),
        }
        if not skip_current:
            result["current"] = self._current(project_names, task_names, client_names, project_clients, task_clients)
        return result

    def _activitywatch_day(self, start, end, date_value):
        store = self._store()
        now = self._now_datetime()
        cached = store.load("awday", date_value) if store else None
        if cached is not None and now < cached[1]:
            return cached[0]["payload"]

        bucket_ids = None
        bucket_cache = store.load("awbuckets") if store else None
        if bucket_cache is not None and now < bucket_cache[1]:
            bucket_ids = bucket_cache[0]["payload"]
        if not isinstance(bucket_ids, dict) or not bucket_ids:
            buckets = _activitywatch_buckets(
                _activitywatch_request("/api/0/buckets/", opener=self._activitywatch_opener)
            )
            bucket_ids = {}
            for bucket in buckets:
                if not isinstance(bucket, dict):
                    continue
                bucket_type = bucket.get("type")
                bucket_id = bucket.get("id", bucket.get("name"))
                if bucket_type in ("currentwindow", "afkstatus", "web.tab.current") \
                        and bucket_id and bucket_type not in bucket_ids:
                    bucket_ids[bucket_type] = str(bucket_id)
            if store:
                store.write("awbuckets", {
                    "schema": CACHE_SCHEMA, "version": CACHE_VERSION, "kind": "awbuckets",
                    "account_key": self.client.account_key,
                    "expires_at": _cache_iso(now + AW_BUCKETS_TTL),
                    "payload": bucket_ids,
                })

        params = {"start": _iso_datetime(start), "end": _iso_datetime(end), "limit": -1}
        events = {}
        for bucket_type in ("currentwindow", "afkstatus", "web.tab.current"):
            bucket_id = bucket_ids.get(bucket_type)
            events[bucket_type] = None if bucket_id is None else _activitywatch_events(
                _activitywatch_request(
                    "/api/0/buckets/%s/events" % quote(bucket_id, safe=""),
                    params,
                    self._activitywatch_opener,
                )
            )
        if store:
            store.write("awday", {
                "schema": CACHE_SCHEMA, "version": CACHE_VERSION, "kind": "awday",
                "account_key": self.client.account_key, "workspace_id": date_value,
                "expires_at": _cache_iso(now + AW_DAY_TTL),
                "payload": events,
            }, date_value)
        return events

    @staticmethod
    def _entry_interval(entry):
        start = _event_datetime(entry.get("start"))
        stop = _event_datetime(entry.get("stop"))
        if start is None or stop is None or stop <= start:
            return None
        return start, stop

    def range_entries(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        start_date = _range_date(payload, "start_date")
        end_date = _range_date(payload, "end_date")
        if end_date < start_date:
            raise ValidationError("end_date must not precede start_date.")
        floor_date = self._now_datetime().date() - timedelta(days=HISTORY_FLOOR_DAYS)
        if end_date < floor_date:
            raise ValidationError(
                "end_date %s is earlier than the earliest date Toggl will answer (%s)."
                % (end_date.isoformat(), floor_date.isoformat())
            )
        clamped = False
        if start_date < floor_date:
            start_date = floor_date
            clamped = True
        # The 92-day span cap is enforced the same way the floor is: truncate and
        # flag, never reject. end_date -- what the caller actually asked to see
        # -- is never moved; start_date is pulled forward instead. See this
        # plan's "scoping decisions" note for why truncation was chosen over a
        # ValidationError; the spec states the cap but not its enforcement.
        if (end_date - start_date).days + 1 > HISTORY_MAX_DAYS:
            start_date = end_date - timedelta(days=HISTORY_MAX_DAYS - 1)
            if start_date < floor_date:
                start_date = floor_date
            clamped = True
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "meta": "true",
        }
        raw = _list_response(self.client.request("GET", "/me/time_entries", params), "time_entries")
        entries = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            normalized = _normalized_entry(item)
            if normalized and normalized["workspace_id"] == workspace_id:
                entries.append(normalized)
        return {
            "entries": entries,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "clamped": clamped,
        }

    def day_activity(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        try:
            date_value = datetime.strptime(str(payload.get("date")), "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError):
            raise ValidationError("date must be an ISO date (YYYY-MM-DD).")
        start, end = _day_bounds(date_value)
        min_block_minutes = _minutes(payload.get("min_block_minutes"), "min_block_minutes", 5)
        activity = self._activitywatch_day(start, end, date_value)
        supplied = payload.get("entries")
        if isinstance(supplied, list):
            entries = [item for item in supplied if isinstance(item, dict)]
        else:
            entries = self._history_entries(workspace_id, date_value, _next_day(date_value))
        blocks = segment_blocks(
            _clip_activity_events(activity["currentwindow"], start, end),
            _clip_activity_events(activity["afkstatus"], start, end),
            _clip_activity_events(activity["web.tab.current"], start, end),
            {"min_block_minutes": min_block_minutes},
        )
        intervals = [(entry, self._entry_interval(entry)) for entry in entries]
        for block in blocks:
            block_start = _event_datetime(block["start"])
            block_end = _event_datetime(block["end"])
            conflict = None
            for entry, interval in intervals:
                if interval and interval[0] < block_end and block_start < interval[1]:
                    conflict = {
                        "id": entry.get("id"),
                        "description": entry.get("description", ""),
                        "start": entry.get("start", ""),
                        "stop": entry.get("stop", ""),
                    }
                    break
            block["applied"] = conflict is not None
            if conflict is not None:
                block["conflict"] = conflict
        self._learn_and_suggest(blocks, entries, workspace_id,
                                enrich=not _bool(payload.get("defer_enrichment", False), "defer_enrichment"))
        return {"date": date_value, "blocks": blocks, "entries": entries}

    def evaluate(self, payload):
        """The learning harness (ruling R-AP). Replays labelled blocks from the
        last N days leave-one-out and scores every layer that can propose a
        project or a description, so a change is judged by numbers rather than
        by how a screenshot looked. Cheap layers only by default; pass
        with_model=true to include the language model, which costs one request
        per block."""
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        days = max(1, min(HISTORY_MAX_DAYS, int(_minutes(payload.get("days"), "days", 30))))
        with_model = _bool(payload.get("with_model", False), "with_model")
        today = _cache_time(self._clock()).astimezone(_local_timezone()).date()

        samples, projects = [], {}
        for project in self.sync({"workspace_id": workspace_id}).get("projects", []):
            if project.get("active", True):
                projects[project["id"]] = project
        for offset in range(days):
            date_value = (today - timedelta(days=offset)).isoformat()
            try:
                day = self.day_activity({"workspace_id": workspace_id, "date": date_value})
            except ApiError:
                continue
            by_id = {str(e.get("id")): e for e in day.get("entries", []) if e.get("id") is not None}
            for block in day.get("blocks", []):
                conflict = block.get("conflict")
                entry = by_id.get(str(conflict.get("id"))) if conflict else None
                if entry is None:
                    continue
                description = str(entry.get("description") or "").strip()
                if not description and entry.get("project_id") is None:
                    continue
                samples.append({"block": block, "description": description,
                                "project_id": entry.get("project_id")})
        if not samples:
            return {"samples": 0, "days": days, "methods": {}, "note": "no labelled blocks in range"}

        vectors = _embed([block_signature(s["block"]) for s in samples], self._embed_opener or urlopen)
        methods = {
            "prior": {"right": 0, "answered": 0},
            "prior+centroid": {"right": 0, "answered": 0},
            "window title": {"f1": 0.0, "exact": 0, "n": 0},
            "past description": {"f1": 0.0, "exact": 0, "n": 0},
        }
        if with_model:
            methods["model"] = {"right": 0, "answered": 0, "f1": 0.0, "exact": 0, "n": 0}
        active_ids = list(projects)

        for index, sample in enumerate(samples):
            # Leave-one-out: a store built from every other labelled block.
            with tempfile.TemporaryDirectory(prefix="toggl-eval-") as evaluation_root:
                store = HistoryStore(evaluation_root, self._clock)
                with store.transaction():
                    for other_index, other in enumerate(samples):
                        if other_index == index:
                            continue
                        store.learn(other["block"], {"id": "eval-%d" % other_index,
                                                     "description": other["description"],
                                                     "project_id": other["project_id"]})
                        if vectors:
                            store.observe_vector(other["project_id"], vectors[other_index])
                vector = vectors[index] if vectors else None
                truth_project, truth_description = sample["project_id"], sample["description"]

                for tag, use_vector in (("prior", None), ("prior+centroid", vector)):
                    ranked = store.project_scores(sample["block"], use_vector, active_ids)
                    if ranked:
                        methods[tag]["answered"] += 1
                        if ranked[0]["project_id"] == truth_project:
                            methods[tag]["right"] += 1

                if truth_description:
                    label = str(sample["block"].get("label") or "")
                    hits = store.suggest(sample["block"], 1)
                    past = hits[0]["description"] if hits else ""
                    for tag, candidate in (("window title", label), ("past description", past)):
                        methods[tag]["n"] += 1
                        methods[tag]["f1"] += _text_f1(candidate, truth_description)
                        if _history_key(candidate) == _history_key(truth_description):
                            methods[tag]["exact"] += 1

                if with_model:
                    shortlist = [projects[r["project_id"]] for r in
                                 store.project_scores(sample["block"], vector, active_ids)[:PROJECT_SHORTLIST]
                                 if r["project_id"] in projects]
                    out = self.classify({"workspace_id": workspace_id,
                                         "blocks": [dict(sample["block"], index=0)],
                                         "projects": [{"id": p["id"], "name": p["name"],
                                                       "client": p.get("client_name") or ""} for p in shortlist]})
                    row = (out.get("results") or [{}])[0]
                    if row.get("project_id") is not None:
                        methods["model"]["answered"] += 1
                        if row["project_id"] == truth_project:
                            methods["model"]["right"] += 1
                    if truth_description and row.get("description"):
                        methods["model"]["n"] += 1
                        methods["model"]["f1"] += _text_f1(row["description"], truth_description)
                        if _history_key(row["description"]) == _history_key(truth_description):
                            methods["model"]["exact"] += 1

        report = {}
        for tag, bucket in methods.items():
            row = {}
            if bucket.get("answered"):
                row["project_accuracy"] = round(bucket["right"] / bucket["answered"], 3)
                row["answered"] = bucket["answered"]
            if bucket.get("n"):
                row["description_f1"] = round(bucket["f1"] / bucket["n"], 3)
                row["description_exact"] = round(bucket["exact"] / bucket["n"], 3)
            report[tag] = row
        history = self._history()
        return {"samples": len(samples), "days": days, "methods": report,
                "corrections": history.correction_stats() if history else {}}

    def learn_history(self, payload):
        """Seeds the history store from the last N days: every block already
        covered by a Toggl entry teaches its description and project. Days
        ActivityWatch or Toggl cannot answer are skipped, not fatal."""
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        days = int(_minutes(payload.get("days"), "days", 30))
        days = max(1, min(HISTORY_MAX_DAYS, days))
        history = self._history()
        if _bool(payload.get("rebuild", False), "rebuild") and history is not None:
            # Centroids arrived after the first stores were filled, and learn()
            # skips an entry it has already seen -- so a rebuild is the only way
            # to backfill geometry onto a store that predates it.
            with history.transaction():
                data = history.load()
                data["entry_ids"] = []
                data["records"] = []
                data["centroids"] = {}
                data["pending_vectors"] = {}
        before = len(history.records) if history is not None else 0
        today = _cache_time(self._clock()).astimezone(_local_timezone()).date()
        learned_days, skipped = 0, 0
        for offset in range(days):
            date_value = (today - timedelta(days=offset)).isoformat()
            try:
                self.day_activity({"workspace_id": workspace_id, "date": date_value})
                learned_days += 1
            except ApiError:
                skipped += 1
        after = len(history.records) if history is not None else 0
        return {"days": learned_days, "skipped": skipped, "records": after, "new_records": after - before}

    def _learn_and_suggest(self, blocks, entries, workspace_id, enrich=True):
        history = self._history()
        if history is None:
            return
        by_id = {str(entry.get("id")): entry for entry in entries
                 if isinstance(entry, dict) and entry.get("id") is not None}
        try:
            with history.transaction():
                for block in blocks:
                    conflict = block.get("conflict")
                    entry = by_id.get(str(conflict.get("id"))) if conflict else None
                    if entry is not None and history.learn(block, entry):
                        history.queue_vector(block, entry, workspace_id)
                for block in blocks:
                    if not block.get("conflict"):
                        block["history"] = history.suggest(block)
                        # Defer project assignment until geometry is available;
                        # provisional prior guesses would prevent later enrichment.
                        if enrich:
                            block["projects"] = history.project_scores(block)[:PROJECT_SHORTLIST]
            if enrich:
                self._drain_vectors(workspace_id)
                pending = [b for b in blocks if not b.get("conflict")]
                vectors = self._vectors([block_signature(b) for b in pending], workspace_id)
                for offset, block in enumerate(pending):
                    block["projects"] = history.project_scores(block, vectors[offset] if vectors else None)[:PROJECT_SHORTLIST]
        except Exception:
            _log(self.logger, "errors", action="history", ok=False, error="history store unavailable")

    def create_entry(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        start = _rfc3339(payload.get("start"), "start")
        duration = payload.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise ValidationError("duration must be a positive integer.")
        description = _text(payload.get("description", ""), "description", required=True)
        project_id = _id(_field(payload, "project_id", "projectId", "pid"), "project_id", required=False)
        task_id = _id(_field(payload, "task_id", "taskId", "tid"), "task_id", required=False)
        if task_id is not None and project_id is None:
            raise ValidationError("project_id is required when task_id is supplied.")
        tags = _tags(payload.get("tags", []))
        billable = _bool(payload.get("billable", False), "billable")
        start_datetime = _event_datetime(start)
        stop = _iso_datetime(start_datetime + timedelta(seconds=duration))
        local_date = start_datetime.astimezone(_local_timezone()).date().isoformat()
        for entry in self._history_entries(workspace_id, local_date, _next_day(local_date)):
            interval = self._entry_interval(entry)
            if interval and interval[0] < _event_datetime(stop) and start_datetime < interval[1]:
                identifier = entry.get("id")
                suffix = " %s" % identifier if identifier is not None else ""
                raise ApiError("Historical entry overlaps existing entry%s." % suffix, 409, False)
        body = {
            "workspace_id": workspace_id,
            "start": start,
            "duration": duration,
            "stop": stop,
            "description": description,
            "project_id": project_id,
            "task_id": task_id,
            "tags": tags,
            "billable": billable,
            "created_with": "omarchy-toggl-track/day",
        }
        response = self.client.request(
            "POST", "/workspaces/%d/time_entries" % workspace_id, body=body, mutation=True
        )
        entry = _normalized_entry(response)
        block = payload.get("block")
        history = self._history()
        if history is not None and isinstance(block, dict):
            try:
                with history.transaction():
                    if history.learn(block, entry):
                        history.queue_vector(block, entry, workspace_id)
                    history.record_correction(block, payload.get("suggested"), {
                        "description": entry.get("description"),
                        "project_id": entry.get("project_id"),
                    })
            except Exception:
                _log(self.logger, "errors", action="history", ok=False, error="history store unavailable")
        return {"entry": entry}

    def _stop_current(self, current, fallback_workspace):
        if current is None:
            return None
        entry_id = _id(current.get("id"), "current.id")
        workspace_id = _id(current.get("workspace_id") or fallback_workspace, "current.workspace_id")
        return self.client.request("PATCH", "/workspaces/%d/time_entries/%d/stop" % (workspace_id, entry_id), mutation=True)

    def start(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        description = _text(payload.get("description", ""), "description", required=True)
        project_id = _id(_field(payload, "project_id", "projectId", "pid"), "project_id", required=False)
        task_id = _id(_field(payload, "task_id", "taskId", "tid"), "task_id", required=False)
        if task_id is not None and project_id is None:
            raise ValidationError("project_id is required when task_id is supplied.")
        tags = _tags(payload.get("tags", []))
        billable = _bool(payload.get("billable", False), "billable")
        current = self._current()
        self._stop_current(current, workspace_id)
        body = {"workspace_id": workspace_id, "description": description, "project_id": project_id, "task_id": task_id, "tags": tags, "billable": billable, "start": _now(), "duration": -1, "created_with": "omarchy-shell"}
        return {"entry": _normalized_entry(self.client.request("POST", "/workspaces/%d/time_entries" % workspace_id, body=body, mutation=True))}

    def stop(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        entry_id = _id(_field(payload, "entry_id", "entryId"), "entry_id")
        response = self.client.request("PATCH", "/workspaces/%d/time_entries/%d/stop" % (workspace_id, entry_id), mutation=True)
        return {"entry": _normalized_entry(response)}

    def update(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        entry_id = _id(_field(payload, "entry_id", "entryId"), "entry_id")
        allowed = {"description", "project_id", "task_id", "tags", "billable", "start", "stop", "duration"}
        supplied = set(payload) - {"action", "data", "workspace_id", "workspaceId", "wid", "entry_id", "entryId"}
        for alias in ("pid", "projectId"):
            if alias in supplied:
                supplied.remove(alias)
                supplied.add("project_id")
        for alias in ("tid", "taskId"):
            if alias in supplied:
                supplied.remove(alias)
                supplied.add("task_id")
        unknown = supplied - allowed
        if unknown:
            raise ValidationError("update contains unsupported fields.")
        if not supplied:
            raise ValidationError("update requires at least one editable field.")
        body = {}
        if "description" in payload:
            body["description"] = _text(payload["description"], "description", required=True)
        if "project_id" in supplied:
            body["project_id"] = _id(_field(payload, "project_id", "projectId", "pid"), "project_id", required=False)
        if "task_id" in supplied:
            body["task_id"] = _id(_field(payload, "task_id", "taskId", "tid"), "task_id", required=False)
        if "tags" in payload:
            body["tags"] = _tags(payload["tags"])
        if "billable" in payload:
            body["billable"] = _bool(payload["billable"], "billable")
        for field in ("start", "stop"):
            if field in payload:
                body[field] = _rfc3339(payload[field], field)
        if "duration" in payload:
            if isinstance(payload["duration"], bool) or not isinstance(payload["duration"], int):
                raise ValidationError("duration must be an integer.")
            body["duration"] = payload["duration"]
        response = self.client.request("PUT", "/workspaces/%d/time_entries/%d" % (workspace_id, entry_id), body=body, mutation=True)
        return {"entry": _normalized_entry(response)}

    def continue_entry(self, payload):
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        entry = _dict(payload.get("entry"), "entry")
        description = _text(entry.get("description", ""), "entry.description", required=True)
        project_id = _id(_field(entry, "project_id", "projectId", "pid"), "entry.project_id", required=False)
        task_id = _id(_field(entry, "task_id", "taskId", "tid"), "entry.task_id", required=False)
        if task_id is not None and project_id is None:
            raise ValidationError("entry.project_id is required when entry.task_id is supplied.")
        tags = _tags(entry.get("tags", []), "entry.tags")
        billable = _bool(entry.get("billable", False), "entry.billable")
        current = self._current()
        self._stop_current(current, workspace_id)
        body = {"workspace_id": workspace_id, "description": description, "project_id": project_id, "task_id": task_id, "tags": tags, "billable": billable, "start": _now(), "duration": -1, "created_with": "omarchy-shell"}
        return {"entry": _normalized_entry(self.client.request("POST", "/workspaces/%d/time_entries" % workspace_id, body=body, mutation=True))}

    def classify(self, payload, deadline=None, vectors=None):
        started = time.monotonic()
        deadline = deadline if deadline is not None else started + CLASSIFIER_TIMEOUT
        workspace_id = _id(_field(payload, "workspace_id", "workspaceId", "wid"), "workspace_id")
        raw_blocks = payload.get("blocks")
        if not isinstance(raw_blocks, list):
            raise ValidationError("blocks must be a list.")
        raw_projects = payload.get("projects")
        if not isinstance(raw_projects, list):
            raise ValidationError("projects must be a list.")

        projects = []
        for project in raw_projects:
            project = _dict(project, "project")
            projects.append({
                "id": _id(project.get("id"), "project.id"),
                "name": _text(project.get("name", ""), "project.name", required=False) or "",
                "client": _text(project.get("client", ""), "project.client", required=False) or "",
            })
        project_ids = [project["id"] for project in projects]

        blocks = []
        for block in raw_blocks:
            block = _dict(block, "block")
            topics = block.get("topics") or []
            blocks.append({
                "index": _classify_index(block.get("index"), "block.index"),
                "topics": [
                    {
                        "name": _text(topic.get("name", ""), "topic.name", required=False) or "",
                        "seconds": int(_minutes(topic.get("seconds"), "topic.seconds", 0)),
                    }
                    for topic in topics if isinstance(topic, dict)
                ],
                # Model.js sends bare names, but day_activity's own blocks carry
                # {name, seconds} pairs; str() on those would put a Python repr
                # in the prompt, so take the name from either shape.
                "apps": _classify_named(block.get("apps")),
                "domains": _classify_named(block.get("domains")),
                "label": str(block.get("label") or ""),
                "start": str(block.get("start") or ""),
                "seconds": int(_minutes(block.get("seconds"), "block.seconds", 0)),
            })

        history = self._history()
        # Geometry and counting decide the project (ruling R-AO); the model only
        # ever sees a shortlist, and its vote is advisory.
        if vectors is None:
            vectors = self._vectors([block_signature(b) for b in blocks], workspace_id, deadline)
        cache = self._inference_cache(workspace_id)
        fingerprint = model_fingerprint("description") if cache else None
        suggestions = {}
        if history is not None:
            for offset, block in enumerate(blocks):
                vector = vectors[offset] if vectors and offset < len(vectors) else None
                try:
                    ranked = history.project_scores(block, vector, project_ids)
                except Exception:
                    ranked = []
                suggestions[block["index"]] = ranked[:PROJECT_SHORTLIST]

        results, degraded = [], False
        prompt = ""
        for block in blocks:
            ranked = suggestions.get(block["index"]) or []
            prompt = _classify_block_prompt(block)
            body = {
                "model": CLASSIFIER_MODEL,
                "messages": [
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "classify_result", "schema": _classify_block_schema()}},
                # Reasoning before the answer spent the whole budget on the first
                # live run and buys nothing under a grammar this tight.
                "chat_template_kwargs": {"enable_thinking": False},
                "temperature": 0,
                "max_tokens": CLASSIFIER_MAX_TOKENS,
            }
            key = cache.key("description", fingerprint, body) if cache else None
            content = cache.get(key) if cache else None
            valid = lambda value: (isinstance(value, dict) and isinstance(value.get("description"), str)
                                   and 0 < len(value["description"].strip()) <= CLASSIFIER_MAX_DESCRIPTION)
            if not valid(content):
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
                    request = Request(CLASSIFIER_URL, data=data,
                                      headers={"Content-Type": "application/json", "Accept": "application/json"},
                                      method="POST")
                    with self._classify_opener(request, timeout=remaining) as response:
                        content = _classify_content(json.loads(response.read().decode("utf-8")))
                    if valid(content) and cache:
                        cache.put(key, content)
                except HTTPError as error:
                    error.close()
                    content = None
                except (URLError, TimeoutError, OSError, ValueError):
                    content = None
                if not valid(content):
                    degraded = True
            description = content["description"] if valid(content) else ""
            # The project is the store's, never the model's (ruling R-AO).
            project_id = ranked[0]["project_id"] if ranked else None
            confidence = float(ranked[0]["score"]) if ranked else 0.0
            if description or project_id is not None:
                results.append({"index": block["index"], "description": description,
                                "project_id": project_id, "confidence": round(confidence, 3),
                                "source": "history" if ranked else "model"})

        elapsed_ms = int((time.monotonic() - started) * 1000)
        _log(self.logger, "debug", action="classify", prompt=prompt,
             response={"results": results}, degraded=degraded)
        out = {"results": results, "model": CLASSIFIER_MODEL, "elapsed_ms": elapsed_ms,
               "projects": suggestions}
        if degraded:
            out["degraded"] = True
        return out

    def dispatch(self, payload):
        payload = _dict(payload, "request")
        action = payload.get("action")
        if not isinstance(action, str):
            raise ValidationError("action must be a string.")
        if "data" in payload:
            data = _dict(payload["data"], "data")
            merged = dict(data)
            merged.update((key, value) for key, value in payload.items() if key != "data")
            payload = merged
        if action == "bootstrap":
            return self.bootstrap(payload)
        if action == "sync":
            return self.sync(payload)
        if action == "start":
            return self.start(payload)
        if action == "stop":
            return self.stop(payload)
        if action == "update":
            return self.update(payload)
        if action == "continue":
            return self.continue_entry(payload)
        if action == "day_activity":
            return self.day_activity(payload)
        if action == "create_entry":
            return self.create_entry(payload)
        if action == "range_entries":
            return self.range_entries(payload)
        if action == "enrich_day":
            return self.enrich_day(payload)
        if action == "classify":
            return self.classify(payload)
        if action == "learn_history":
            return self.learn_history(payload)
        if action == "evaluate":
            return self.evaluate(payload)
        raise ValidationError("unsupported action.")


def _log(logger, level, **fields):
    """Logging never raises into the request path."""
    if logger is None:
        return
    try:
        logger.write(level, **fields)
    except Exception:
        pass


def _flush_client_log(logger, payload):
    entries = payload.get("client_log") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return
    for entry in entries[:MAX_CLIENT_LOG]:
        if not isinstance(entry, dict):
            continue
        level = entry.get("lvl")
        fields = {key: value for key, value in entry.items() if key not in ("lvl", "ts", "src")}
        _log(logger, level if level in toggl_log.LEVELS else "info", src="qml", **fields)


def handle(payload, client=None, cache_root=None, clock=None, logger=None):
    action = payload.get("action") if isinstance(payload, dict) else None
    started = time.monotonic()
    _flush_client_log(logger, payload)
    try:
        api = TogglAPI(client, cache_root=cache_root, clock=clock, logger=logger)
        data = api.dispatch(payload)
        result = {"ok": True, "data": data}
        _log(logger, "info", action=action, ok=True,
             ms=int((time.monotonic() - started) * 1000))
        return result
    except ApiError as error:
        _log(logger, "errors", action=action, ok=False, status=error.status,
             error=str(error.message), ms=int((time.monotonic() - started) * 1000))
        return _error(error.message, error.status, error.retryable)
    except Exception:
        _log(logger, "errors", action=action, ok=False, error="unexpected",
             ms=int((time.monotonic() - started) * 1000))
        return _error("Unexpected backend error.")


def main():
    try:
        payload = json.loads(sys.stdin.readline())
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = _error("Input must be one valid JSON object.", 400, False)
    else:
        level = payload.get("log_level") if isinstance(payload, dict) else None
        try:
            logger = toggl_log.Logger(PLUGIN_DIR, level if level in toggl_log.LEVELS else "info")
        except Exception:
            logger = None
        # Documentation screenshots run the real panel against invented data.
        # Routing here, before handle() builds a TogglAPI, is what guarantees a
        # demo run cannot reach Toggl, ActivityWatch, the cache or the history
        # store -- see toggl_demo.py.
        try:
            import toggl_demo
            demo = toggl_demo.enabled()
        except Exception:
            demo = False
        if demo:
            result = toggl_demo.respond(payload)
        else:
            result = handle(payload, logger=logger)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
