#!/usr/bin/env python3
"""Invented data for documentation screenshots.

The panel spawns `toggl_api.py` once per request, so `main()` can route to this
module instead of `handle()` when demo mode is on. Routing happens *before* a
`TogglAPI` is built, which is the whole point: nothing here can reach Toggl, the
ActivityWatch server on 127.0.0.1:5600, the cache under `$XDG_CACHE_HOME`, or the
real `history.json`. The user's own data is unreachable by construction rather
than by care.

Window titles are the most sensitive field in the whole app and they come from
ActivityWatch, not from Toggl -- so faking the Toggl side alone would not be
enough, and every block below is invented outright.

Every response mirrors the real shape exactly: see `_normalized_entry`,
`_normalized_user`, `_normalized_project` and `day_activity`'s return in
`toggl_api.py`. If those change, these must follow, and
`tests/test_toggl_demo.py` is what notices.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

MARKER_NAME = "omarchy-toggl-track-demo"

# Anchored to the machine's own today, at a fixed time of day. It has to be
# today: the panel asks for whatever date its clock says, so a hardcoded date
# would leave the day and calendar scopes empty -- the two screens the manual
# most needs to show full. The fixed hour keeps a rerun's images stable within
# any one day.
TODAY = datetime.now().date()
NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 16, 20, 0, tzinfo=timezone.utc)

WORKSPACE_ID = 7001
USER_ID = 9100

# --- the invented account ---------------------------------------------------
# Names that read like real work and belong to nobody. Colours are Toggl's own
# palette values so the calendar's project stripes look right.
CLIENTS = [
    {"id": 501, "name": "Northwind Marine"},
    {"id": 502, "name": "Internal"},
]

PROJECTS = [
    {"id": 101, "name": "NW-104 Harbour Telemetry", "client_id": 501,
     "client_name": "Northwind Marine", "color": "#0b83d9"},
    {"id": 102, "name": "NW-118 Buoy Firmware", "client_id": 501,
     "client_name": "Northwind Marine", "color": "#9e5bd9"},
    {"id": 103, "name": "Growth: Q2 Launch Deck", "client_id": 502,
     "client_name": "Internal", "color": "#e36a00"},
    {"id": 104, "name": "Platform Upkeep", "client_id": 502,
     "client_name": "Internal", "color": "#2da608"},
    {"id": 105, "name": "PTO", "client_id": 502, "client_name": "Internal",
     "color": "#bf7000"},
]

TASKS = [
    {"id": 201, "project_id": 101, "name": "ingest pipeline"},
    {"id": 202, "project_id": 101, "name": "tide model"},
    {"id": 203, "project_id": 102, "name": "power budget"},
    {"id": 204, "project_id": 103, "name": "slides"},
]

TAGS = ["deep-work", "meeting", "review"]


def _iso(moment):
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _project(project_id):
    for project in PROJECTS:
        if project["id"] == project_id:
            return project
    return None


def _entry(entry_id, description, project_id, task_id, start, minutes, tags=None,
           created_with="omarchy-shell"):
    """One entry in `_normalized_entry`'s exact shape."""
    project = _project(project_id) or {}
    task = next((t for t in TASKS if t["id"] == task_id), {})
    stop = start + timedelta(minutes=minutes)
    return {
        "id": entry_id,
        "workspace_id": WORKSPACE_ID,
        "project_id": project_id,
        "task_id": task_id,
        "description": description,
        "project_name": project.get("name", ""),
        "task_name": task.get("name", ""),
        "client_name": project.get("client_name", ""),
        "tags": list(tags or []),
        "billable": bool(project.get("client_id") == 501),
        "project_color": project.get("color", ""),
        "start": _iso(start),
        "stop": _iso(stop),
        "duration": minutes * 60,
        "created_with": created_with,
    }


def _at(days_ago, hour, minute=0):
    day = TODAY - timedelta(days=days_ago)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


# Ten distinct descriptions, because the timer scope's empty command line offers
# ten recent entries to continue and the manual photographs that list full.
ENTRIES = [
    _entry(3001, "Tide model calibration", 101, 202, _at(0, 9, 5), 95, ["deep-work"]),
    _entry(3002, "Harbour telemetry ingest retries", 101, 201, _at(0, 11, 10), 65),
    _entry(3003, "Buoy power budget review", 102, 203, _at(1, 9, 30), 80, ["review"]),
    _entry(3004, "Q2 launch deck narrative", 103, 204, _at(1, 13, 0), 110),
    _entry(3005, "Standup and planning", 104, None, _at(1, 8, 45), 25, ["meeting"]),
    _entry(3006, "Firmware flash rig setup", 102, None, _at(2, 10, 0), 140, ["deep-work"]),
    _entry(3007, "Runner image upkeep", 104, None, _at(2, 15, 30), 55),
    _entry(3008, "Customer call: berth sensors", 101, None, _at(3, 11, 0), 45, ["meeting"]),
    _entry(3009, "Launch deck rehearsal", 103, 204, _at(3, 14, 0), 70),
    _entry(3010, "Annual leave", 105, None, _at(6, 9, 0), 480),
    _entry(3011, "Tide model calibration", 101, 202, _at(4, 9, 0), 120),
]

# The entry the running-timer screenshots show. duration -1 and no stop is what
# the real API returns for a timer in flight.
RUNNING = dict(
    _entry(3100, "Harbour telemetry ingest retries", 101, 201, NOW - timedelta(minutes=83), 0),
    stop="", duration=-1,
)


# --- the invented day -------------------------------------------------------
# Blocks in `segment_blocks`' exact shape. Between them these cover every row
# state the day scope can render, which is what the manual needs to photograph:
# applied, ready, guessed, conflict, unassigned.

def _named(pairs):
    return [{"name": name, "seconds": seconds} for name, seconds in pairs]


def _block(day_offset, hour, minute, minutes, label, topics, apps, domains,
           applied=False, conflict=None, idle=0, fragments=3):
    start = _at(day_offset, hour, minute)
    seconds = minutes * 60
    block = {
        "start": _iso(start),
        "end": _iso(start + timedelta(minutes=minutes)),
        "seconds": seconds,
        "span_seconds": seconds + idle,
        "idle_seconds": idle,
        "fragments": fragments,
        "longest_fragment_seconds": int(seconds * 0.6),
        "label": label,
        "topics": _named(topics),
        "apps": _named(apps),
        "domains": _named(domains),
        "domain": domains[0][0] if domains else "",
        "timeline": [
            {"offset": int(seconds * i / 6), "seconds": int(seconds / 6),
             "topic": topics[i % len(topics)][0], "idle": False}
            for i in range(6)
        ],
        "applied": applied,
    }
    if conflict:
        block["conflict"] = conflict
    return block


def _today_blocks():
    """The curated day the manual photographs: between them these five cover
    every row state the day scope can draw -- applied, ready, guessed,
    conflict and unassigned."""
    return [
        _block(0, 9, 5, 95, "harbour-telemetry: ingest.py",
               [("harbour-telemetry: ingest.py", 3300), ("tide model notes", 1800), ("PR #212 retries", 600)],
               [("dev.zed.Zed", 4200), ("zen", 1500)], [("github.com", 1500)],
               applied=True,
               conflict={"id": 3001, "description": "Tide model calibration",
                         "start": _iso(_at(0, 9, 5)), "stop": _iso(_at(0, 10, 40))}),
        _block(0, 11, 10, 65, "harbour-telemetry: retries",
               [("harbour-telemetry: retries", 2400), ("Grafana: ingest lag", 900), ("PR #212", 600)],
               [("dev.zed.Zed", 2600), ("zen", 1300)], [("github.com", 900), ("grafana.net", 400)]),
        _block(0, 13, 30, 50, "buoy-firmware: power.c",
               [("buoy-firmware: power.c", 1900), ("datasheet: LTC4015", 700)],
               [("dev.zed.Zed", 2100), ("org.gnome.Evince", 500)], [("analog.com", 400)]),
        _block(0, 15, 0, 40, "Q2 launch deck",
               [("Q2 launch deck", 1600), ("Slides: narrative", 500)],
               [("libreoffice", 1800)], [("docs.google.com", 500)],
               applied=True,
               conflict={"id": 4400, "description": "Deck review (mobile)",
                         "start": _iso(_at(0, 15, 5)), "stop": _iso(_at(0, 15, 35))}),
        _block(0, 16, 5, 15, "Inbox",
               [("Inbox", 600), ("Calendar", 300)],
               [("eu.betterbird.Betterbird", 700)], []),
    ]


# Earlier weekdays, so the calendar week and month have something to draw. Each
# day gets a deterministic slice of this rota rather than random noise, so the
# same date always renders the same way.
_ROTA = [
    (9, 30, 80, "buoy-firmware: power.c",
     [("buoy-firmware: power.c", 2900), ("power budget.xlsx", 1000)],
     [("dev.zed.Zed", 3400)], [("analog.com", 500)]),
    (11, 15, 55, "Q2 launch deck",
     [("Q2 launch deck", 2100), ("Slides: metrics", 800)],
     [("libreoffice", 2500)], [("docs.google.com", 700)]),
    (13, 45, 70, "harbour-telemetry: ingest.py",
     [("harbour-telemetry: ingest.py", 2600), ("Grafana: ingest lag", 900)],
     [("dev.zed.Zed", 3000), ("zen", 1100)], [("github.com", 1200)]),
    (15, 20, 45, "runner image",
     [("runner image", 1700), ("CI: build 4471", 600)],
     [("com.mitchellh.ghostty", 2000)], [("github.com", 500)]),
]


def _blocks_for(day_offset):
    weekday = (TODAY - timedelta(days=day_offset)).weekday()
    if weekday >= 5:
        return []  # weekends stay empty, which is honest and looks right
    picks = _ROTA[: 2 + (day_offset + weekday) % 3]
    blocks = []
    for index, (hour, minute, minutes, label, topics, apps, domains) in enumerate(picks):
        # The first block of a past day is already written up, so the calendar
        # shows a mix of applied and still-unapplied work.
        applied = index == 0
        conflict = None
        if applied:
            match = next((e for e in ENTRIES if e["start"][:10] ==
                          (TODAY - timedelta(days=day_offset)).isoformat()), None)
            if match:
                conflict = {"id": match["id"], "description": match["description"],
                            "start": match["start"], "stop": match["stop"]}
            else:
                applied = False
        blocks.append(_block(day_offset, hour, minute, minutes, label, topics, apps,
                             domains, applied=applied, conflict=conflict))
    return blocks


# What the local model proposes for the blocks that still need a description.
GUESSES = {
    1: ("Harbour ingest retry debugging", 101, 0.82),
    2: ("Buoy power budget from the LTC4015 datasheet", 102, 0.74),
    4: ("Inbox and calendar triage", None, 0.31),
}


# --- responder --------------------------------------------------------------

def marker_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(runtime, MARKER_NAME)


def enabled():
    return os.environ.get("TOGGL_DEMO") == "1" or os.path.exists(marker_path())


def _cache():
    return {"workspace": "fresh", "forced": False, "stale": False, "expires_at": None}


def _sync_data(skip_current=False):
    projects = [dict(p, workspace_id=WORKSPACE_ID, active=True, archived=False,
                     status="active", client=p["client_name"], billable=True,
                     is_private=False, external_reference="", at=_iso(NOW))
                for p in PROJECTS]
    tasks = [dict(t, workspace_id=WORKSPACE_ID, active=True, status="active",
                  at=_iso(NOW), estimated_seconds=None,
                  project_name=(_project(t["project_id"]) or {}).get("name", ""),
                  client_name=(_project(t["project_id"]) or {}).get("client_name", ""))
             for t in TASKS]
    data = {
        "projects": projects,
        "tasks": tasks,
        "tasks_available": True,
        "tags": [{"id": 700 + i, "workspace_id": WORKSPACE_ID, "name": name}
                 for i, name in enumerate(TAGS)],
        "clients": [dict(c, workspace_id=WORKSPACE_ID) for c in CLIENTS],
        "entries": list(ENTRIES),
        "cache": _cache(),
    }
    if not skip_current:
        data["current"] = dict(RUNNING) if _running_enabled() else None
    return data


def _running_enabled():
    """The manual needs both an idle panel and a running one. A second marker
    file switches the running timer on, so the capture script can photograph
    each without restarting anything."""
    return os.path.exists(marker_path() + "-running")


def _day_data(date_value):
    """Any date the panel asks for. The day scope shows today; the calendar's
    week view asks for each of its seven days, and every one of them needs an
    answer or the grid renders bare."""
    try:
        asked = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        asked = TODAY
    offset = (TODAY - asked).days
    if offset == 0:
        blocks = _today_blocks()
    elif 0 < offset <= 21:
        blocks = _blocks_for(offset)
    else:
        blocks = []
    entries = [e for e in ENTRIES if e["start"][:10] == date_value]
    return {"date": date_value, "blocks": blocks, "entries": entries}


def _enrich_data(payload):
    date_value = str(payload.get("date") or TODAY.isoformat())
    blocks_in = payload.get("blocks") or []
    ranked = [{"project_id": 101, "score": 0.71, "prior": 0.44, "similarity": 0.86},
              {"project_id": 104, "score": 0.29, "prior": 0.22, "similarity": 0.35},
              {"project_id": 102, "score": 0.24, "prior": 0.18, "similarity": 0.31}]
    blocks_out, results = [], []
    for block in blocks_in:
        index = block.get("index", 0)
        blocks_out.append({"index": index, "signature": "demo", "projects": ranked})
        guess = GUESSES.get(index)
        if guess:
            description, project_id, confidence = guess
            results.append({"index": index, "description": description,
                            "project_id": project_id, "confidence": confidence,
                            "source": "history" if project_id else "model"})
    return {"workspace_id": WORKSPACE_ID, "date": date_value,
            "generation": payload.get("generation", 0),
            "blocks": blocks_out, "results": results,
            "model": "toggl-classifier", "elapsed_ms": 640}


def respond(payload):
    """One request in, one `{"ok": ...}` envelope out -- the same contract
    `handle()` honours."""
    if not isinstance(payload, dict):
        return {"ok": False, "error": {"message": "Input must be one valid JSON object.",
                                       "status": 400, "retryable": False}}
    action = payload.get("action")
    if "data" in payload and isinstance(payload["data"], dict):
        merged = dict(payload["data"])
        merged.update((k, v) for k, v in payload.items() if k != "data")
        payload = merged

    if action == "bootstrap":
        data = {
            "user": {"id": USER_ID, "name": "Sam Rivers", "timezone": "UTC",
                     "default_workspace_id": WORKSPACE_ID, "beginning_of_week": 1},
            "workspaces": [{"id": WORKSPACE_ID, "name": "Northwind Studio",
                            "organization_id": 800, "default_currency": "EUR",
                            "default_hourly_rate": None}],
            "cache": _cache(),
            "workspace_id": WORKSPACE_ID,
        }
        if not payload.get("skip_sync"):
            data.update(_sync_data())
        else:
            data["current"] = dict(RUNNING) if _running_enabled() else None
        return {"ok": True, "data": data}

    if action == "sync":
        return {"ok": True, "data": _sync_data(bool(payload.get("skip_current")))}

    if action == "day_activity":
        return {"ok": True, "data": _day_data(str(payload.get("date") or TODAY.isoformat()))}

    if action == "range_entries":
        start = str(payload.get("start_date") or "")
        end = str(payload.get("end_date") or "")
        entries = [e for e in ENTRIES if start <= e["start"][:10] <= end] if start and end else list(ENTRIES)
        return {"ok": True, "data": {"entries": entries, "start_date": start,
                                     "end_date": end, "clamped": False}}

    if action == "enrich_day":
        return {"ok": True, "data": _enrich_data(payload)}

    if action in ("start", "continue"):
        source = payload.get("entry") if action == "continue" else payload
        description = str((source or {}).get("description") or "Untitled")
        project_id = (source or {}).get("project_id") or 101
        entry = dict(_entry(3200, description, project_id, None, NOW, 0),
                     stop="", duration=-1)
        return {"ok": True, "data": {"entry": entry}}

    if action == "stop":
        return {"ok": True, "data": {"entry": _entry(3100, RUNNING["description"], 101, 201,
                                                     NOW - timedelta(minutes=83), 83)}}

    if action in ("update", "create_entry"):
        entry = _entry(payload.get("entry_id") or 3300,
                       str(payload.get("description") or "Demo entry"),
                       payload.get("project_id") or 101, payload.get("task_id"),
                       NOW, max(1, int(payload.get("duration") or 1800) // 60),
                       created_with="omarchy-toggl-track/day")
        return {"ok": True, "data": {"entry": entry}}

    if action in ("learn_history", "evaluate", "classify"):
        # CLI-only in the real backend; the panel never sends these.
        return {"ok": True, "data": {"demo": True}}

    return {"ok": False, "error": {"message": "unsupported action.", "status": 400,
                                   "retryable": False}}


def main():
    try:
        payload = json.loads(sys.stdin.readline())
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = {"ok": False, "error": {"message": "Input must be one valid JSON object.",
                                         "status": 400, "retryable": False}}
    else:
        result = respond(payload)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
