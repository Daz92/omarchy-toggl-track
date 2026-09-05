# Panel Redesign — Stage 0 & 1: Tooling, Logging and Backend Truth

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the release gate, the 24-hour ring-buffered log, and every backend correctness and performance fix — with no user-visible UI change beyond the settings that are currently broken.

**Architecture:** `toggl_api.py` keeps handling exactly one JSON request per process and exiting. A new sibling module `toggl_log.py` owns the log and is imported by the helper; it never raises into the request path. Caching gains three kinds (entries, ActivityWatch bucket ids, raw ActivityWatch events), all derivable and disposable. `build` and `install` are bash scripts alongside the existing `setup`.

**Tech Stack:** Python 3 standard library only (`urllib`, `fcntl`, `json`). QML/Quickshell for `Panel.qml`. Node for `Model.js` tests. Bash for scripts. No third-party packages, no `requirements.txt`, no `pyproject.toml`.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md)
**Visual acceptance reference:** [`docs/design-guide.html`](../design-guide.html)

## Global Constraints

Every task's requirements implicitly include all of these.

- **Python: standard library only.** Network I/O is `urllib`. No third-party imports, ever.
- **No daemon.** `toggl_api.py` handles exactly one JSON request per process and exits. Anything that seems to need persistence goes to Toggl, to the on-disk cache, or to QML properties.
- **Never write durable state into the metadata cache.** `$XDG_CACHE_HOME/omarchy-toggl-track` is TTL'd and safe to delete at any moment. Everything cached must be re-derivable.
- **Never let the token reach a URL, argv, or a log.** Enforced by `test_auth_creation_does_not_put_token_in_request_url` and, from Task 3, by a log test.
- **Never retry a mutation.** `TogglClient.request(..., mutation=True)` must not retry on 5xx or timeout. A resent POST creates a duplicate entry.
- **Never reuse `start` or `continue` to write historical entries.** Both call `_stop_current`. Historical writes use `create_entry`.
- **QML: multi-line, one property per line.** Run `qmlformat -n -i` after editing.
- **Never put `;` after an object member in QML.** `Item { Text {} ; Text {} }` is a parse error and both tools report it with zero output.
- **Never pipe `qmllint` and read `$?`.** It writes nothing on failure, so `qmllint x.qml | tail` returns *tail's* exit status. Check its status directly, or use `qmlformat`.
- **`BarWidget.qml` cannot be gated by either QML tool.** Both reject `function open(): void`, which `IpcHandler` requires. Review it by hand.
- **QML signal handlers must declare their parameters.** `onChanged: function(value) { … }`, never the injected form.
- **Theme values come from `Style.*` and `Color.*`, never literals.** `Style.cornerRadius` resolves to 0.
- **`docs/design-guide.html` is the acceptance reference.** Where this plan and that page disagree about a rendered value, the page wins and the disagreement is a bug in this plan — stop and report it rather than guessing.
- **Editing QML requires `omarchy-restart-shell`,** not `reloadConfig` and never `rescanPlugins`, which is not in this shell's IPC surface and exits 0 regardless.

## File Structure

| File | Responsibility |
| --- | --- |
| `toggl_log.py` | **new** — level filtering, redaction, atomic append, age-first ring prune. Knows nothing about Toggl. |
| `tests/test_toggl_log.py` | **new** — logger unit tests |
| `toggl_api.py` | modified — logger wiring, cache kinds, `since` delta, block schema, `_history_days` |
| `tests/test_toggl_api.py` | modified |
| `Model.js` | modified — `clampHistory`, `searchItems` normalisation |
| `tests/test_model.mjs` | modified |
| `Panel.qml` | modified — request queue, incremental day summary, `client_log`, settings options |
| `manifest.json` | modified — settings schema and defaults |
| `build` | **new** — release gate |
| `install` | **new** — local install / dev symlink / uninstall |
| `.gitignore` | modified — `logs/`, `dist/`, `*.gguf` |
| `README.md` | modified — install section |
| `AGENTS.md` | modified — new anti-patterns and the verified API floor |

---

### Task 1: The log writer

**Files:**
- Create: `toggl_log.py`
- Create: `tests/test_toggl_log.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `toggl_log.Logger(directory, level="info", clock=None)` with methods
  `enabled(level) -> bool` and `write(level, **fields) -> bool`. Module constants
  `LOG_MAX_BYTES`, `LOG_MAX_AGE`, `MAX_FIELD`, `SENSITIVE`, `LEVELS`.

- [ ] **Step 1: Add the ignore entries**

`.gitignore` — append. The install directory is a symlink into this working tree, so
without this every log write dirties the repo.

```
logs/
dist/
*.gguf
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_toggl_log.py`:

```python
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import toggl_log


def read_lines(directory):
    path = os.path.join(directory, "logs", "toggl.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream.read().splitlines() if line]


class LoggerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_writes_a_record_with_ts_and_lvl(self):
        logger = toggl_log.Logger(self.dir, "info")
        self.assertTrue(logger.write("info", action="sync", ms=412, ok=True))
        records = read_lines(self.dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "sync")
        self.assertEqual(records[0]["lvl"], "info")
        self.assertTrue(records[0]["ts"].endswith("Z"))

    def test_off_creates_no_file(self):
        logger = toggl_log.Logger(self.dir, "off")
        self.assertFalse(logger.write("errors", action="sync"))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "logs")))

    def test_errors_level_drops_info_records(self):
        logger = toggl_log.Logger(self.dir, "errors")
        logger.write("info", action="sync")
        logger.write("errors", action="sync", error="boom")
        records = read_lines(self.dir)
        self.assertEqual([r["lvl"] for r in records], ["errors"])

    def test_info_omits_sensitive_keys(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.write("info", action="day_activity", label="Refactor day segmentation",
                     description="secret work", counts={"blocks": 6})
        record = read_lines(self.dir)[0]
        self.assertNotIn("label", record)
        self.assertNotIn("description", record)
        self.assertEqual(record["counts"], {"blocks": 6})

    def test_info_omits_sensitive_keys_nested(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.write("info", action="classify", batch={"label": "x", "n": 3})
        record = read_lines(self.dir)[0]
        self.assertNotIn("label", record["batch"])
        self.assertEqual(record["batch"]["n"], 3)

    def test_debug_keeps_sensitive_keys(self):
        logger = toggl_log.Logger(self.dir, "debug")
        logger.write("debug", action="day_activity", label="Refactor day segmentation")
        self.assertEqual(read_lines(self.dir)[0]["label"], "Refactor day segmentation")

    def test_strings_truncate_at_500(self):
        logger = toggl_log.Logger(self.dir, "debug")
        logger.write("debug", action="x", label="a" * 900)
        self.assertEqual(len(read_lines(self.dir)[0]["label"]), 500)

    def test_unwritable_directory_disables_logging_without_raising(self):
        blocked = os.path.join(self.dir, "blocked")
        os.makedirs(blocked)
        os.chmod(blocked, 0o500)
        self.addCleanup(os.chmod, blocked, 0o700)
        logger = toggl_log.Logger(blocked, "info")
        self.assertFalse(logger.write("info", action="sync"))

    def test_log_directory_is_private(self):
        toggl_log.Logger(self.dir, "info").write("info", action="sync")
        mode = os.stat(os.path.join(self.dir, "logs")).st_mode & 0o777
        self.assertEqual(mode, 0o700)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_toggl_log -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'toggl_log'`

- [ ] **Step 4: Write the module**

Create `toggl_log.py`:

```python
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


def _truncate(value):
    if isinstance(value, str):
        return value[:MAX_FIELD]
    if isinstance(value, list):
        return [_truncate(item) for item in value[:MAX_ITEMS]]
    if isinstance(value, dict):
        return {key: _truncate(item) for key, item in value.items()}
    return value


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
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        try:
            handle = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(handle, line.encode("utf-8"))
            finally:
                os.close(handle)
        except OSError:
            return False
        return True
```

Note the constructor opens the file once as a probe: an unwritable directory that
`makedirs` accepted still has to fail closed before the first `write`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_toggl_log -v`
Expected: PASS, 9 tests

- [ ] **Step 6: Commit**

```bash
git add toggl_log.py tests/test_toggl_log.py .gitignore
git commit -m "feat(log): JSONL log writer with levels and redaction"
```

---

### Task 2: The ring buffer

**Files:**
- Modify: `toggl_log.py`
- Modify: `tests/test_toggl_log.py`

**Interfaces:**
- Consumes: `Logger` from Task 1.
- Produces: `Logger.prune() -> None`, called automatically at the end of `write()`.
  Runs at most once per `Logger` instance.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_log.py`, inside `LoggerTest`:

```python
    def _seed(self, records):
        root = os.path.join(self.dir, "logs")
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, "toggl.jsonl")
        with open(path, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
        return path

    def test_prune_drops_records_older_than_24h(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=25))
        new = toggl_log._stamp(now - timedelta(hours=1))
        pad = "x" * 2000
        path = self._seed(
            [{"ts": old, "lvl": "info", "pad": pad}] * 400
            + [{"ts": new, "lvl": "info", "pad": pad}] * 400
        )
        self.assertGreater(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        stamps = {record["ts"] for record in read_lines(self.dir)}
        self.assertEqual(stamps, {new})

    def test_prune_is_skipped_below_the_size_bound(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=48))
        self._seed([{"ts": old, "lvl": "info"}])
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        self.assertEqual(len(read_lines(self.dir)), 1)

    def test_prune_drops_oldest_survivors_when_still_over_size(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        pad = "x" * 4000
        records = [
            {"ts": toggl_log._stamp(now - timedelta(minutes=index)), "lvl": "info", "pad": pad}
            for index in range(600, 0, -1)
        ]
        self._seed(records)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        path = os.path.join(self.dir, "logs", "toggl.jsonl")
        self.assertLessEqual(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        kept = read_lines(self.dir)
        self.assertGreater(len(kept), 0)
        self.assertEqual(kept[-1]["ts"], records[-1]["ts"])

    def test_prune_drops_malformed_lines_without_aborting(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        good = toggl_log._stamp(now - timedelta(hours=1))
        root = os.path.join(self.dir, "logs")
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, "toggl.jsonl")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("{not json\n")
            for _ in range(500):
                stream.write(json.dumps({"ts": good, "lvl": "info", "pad": "x" * 2500}) + "\n")
        self.assertGreater(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        toggl_log.Logger(self.dir, "info", clock=lambda: now).prune()
        records = read_lines(self.dir)
        self.assertTrue(records)
        self.assertTrue(all(record["ts"] == good for record in records))

    def test_prune_runs_once_per_instance(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.prune()
        self.assertTrue(logger._pruned)
        logger.prune()

    def test_write_prunes_after_appending(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=30))
        self._seed([{"ts": old, "lvl": "info", "pad": "x" * 3000}] * 400)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.write("info", action="sync")
        records = read_lines(self.dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "sync")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_toggl_log -v`
Expected: FAIL with `AttributeError: 'Logger' object has no attribute 'prune'`

- [ ] **Step 3: Implement the prune**

Add to `toggl_log.py`, as a method on `Logger`:

```python
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
            payload = ("\n".join(kept) + "\n").encode("utf-8") if kept else b""
            while len(payload) > LOG_MAX_BYTES and kept:
                kept.pop(0)
                payload = ("\n".join(kept) + "\n").encode("utf-8") if kept else b""
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
```

- [ ] **Step 4: Call it from `write()`**

In `toggl_log.py`, replace the final `return True` of `write()` with:

```python
        self.prune()
        return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_toggl_log -v`
Expected: PASS, 15 tests

- [ ] **Step 6: Commit**

```bash
git add toggl_log.py tests/test_toggl_log.py
git commit -m "feat(log): age-first ring buffer bounded at 24h and 1 MiB"
```

---

### Task 3: Wire the logger into the helper

**Files:**
- Modify: `toggl_api.py` — `handle()`, `main()`, `TogglAPI.__init__`, `TogglClient.request`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Consumes: `toggl_log.Logger` from Tasks 1–2.
- Produces: `handle(payload, client=None, cache_root=None, clock=None, logger=None)`.
  `TogglAPI(..., logger=None)` exposes `self.logger`. Every response carries the same
  shape as before — logging changes nothing a caller sees.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_api.py`:

```python
class LoggingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def test_action_is_logged_with_timing_and_ok(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}]])
        toggl_api.handle({"action": "bootstrap"}, client=client, logger=logger)
        record = [r for r in self._records() if r.get("action") == "bootstrap"][0]
        self.assertTrue(record["ok"])
        self.assertIsInstance(record["ms"], int)

    def test_failure_is_logged_with_status(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([toggl_api.ApiError("nope", 400, False)])
        result = toggl_api.handle({"action": "bootstrap"}, client=client, logger=logger)
        self.assertFalse(result["ok"])
        record = [r for r in self._records() if r.get("action") == "bootstrap"][0]
        self.assertFalse(record["ok"])
        self.assertEqual(record["status"], 400)

    def test_token_never_reaches_the_log(self):
        import toggl_log
        secret = "s3cr3t-token-value"
        logger = toggl_log.Logger(self.tmp.name, "debug")
        client = toggl_api.TogglClient(token=secret)
        logger.write("debug", action="probe", note="x")
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        self.assertNotIn(secret, path.read_text())
        self.assertNotIn(client.account_key, secret)

    def test_client_log_entries_are_flushed_with_src_qml(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}]])
        toggl_api.handle(
            {"action": "bootstrap", "client_log": [{"lvl": "errors", "event": "request_dropped"}]},
            client=client, logger=logger,
        )
        qml = [r for r in self._records() if r.get("src") == "qml"]
        self.assertEqual(len(qml), 1)
        self.assertEqual(qml[0]["event"], "request_dropped")

    def test_client_log_is_capped_at_32_entries(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}]])
        toggl_api.handle(
            {"action": "bootstrap", "client_log": [{"lvl": "errors", "event": "e%d" % i} for i in range(80)]},
            client=client, logger=logger,
        )
        self.assertEqual(len([r for r in self._records() if r.get("src") == "qml"]), 32)

    def test_logging_failure_does_not_break_the_request(self):
        class Exploding:
            def enabled(self, level):
                return True

            def write(self, level, **fields):
                raise OSError("disk full")

        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}]])
        result = toggl_api.handle({"action": "bootstrap"}, client=client, logger=Exploding())
        self.assertTrue(result["ok"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_toggl_api.LoggingTest -v`
Expected: FAIL — `handle()` takes no `logger` keyword

- [ ] **Step 3: Add the constants and the import**

In `toggl_api.py`, after the existing imports add:

```python
import toggl_log
```

and after `CACHE_VERSION = 1` add:

```python
MAX_CLIENT_LOG = 32
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
```

- [ ] **Step 4: Add the safe-log wrapper and thread the logger through**

In `toggl_api.py`, above `def handle(...)`:

```python
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
```

Replace `handle()` entirely:

```python
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
```

In `TogglAPI.__init__`, add `logger=None` as the last keyword parameter and
`self.logger = logger` as the last assignment.

Replace `main()`:

```python
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
        result = handle(payload, logger=logger)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if result.get("ok") else 1
```

- [ ] **Step 5: Log the HTTP calls**

In `TogglClient.__init__`, add `logger=None` as the last keyword parameter and
`self._logger = logger` as the last assignment. In `request()`, immediately after
`with self._opener(request, timeout=15) as response:` block completes — that is, right
before `if not raw:` — insert:

```python
                if self._logger is not None:
                    _log(self._logger, "info", http=[{
                        "path": path,
                        "status": int(getattr(response, "status", 0) or 0),
                        "ms": int((time.monotonic() - attempt_started) * 1000),
                        "bytes": len(raw),
                    }])
```

and add `attempt_started = time.monotonic()` as the first statement inside the
`while True:` loop.

`path` is logged, never `url` — the URL would carry query parameters and the rule is that
nothing resembling a credential reaches the log.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS, including the 6 new `LoggingTest` cases

- [ ] **Step 7: Commit**

```bash
git add toggl_api.py tests/test_toggl_api.py
git commit -m "feat(log): record every action, HTTP call and panel-side event"
```

---

### Task 4: Fix the broken `historyDays: 365` setting

**Files:**
- Modify: `toggl_api.py:856` — `_history_days`
- Modify: `Model.js:278` — `clampHistory`
- Modify: `tests/test_toggl_api.py`, `tests/test_model.mjs`

**Interfaces:**
- Produces: `toggl_api.HISTORY_MAX_DAYS = 92`, `toggl_api.HISTORY_SAFE_DAYS = 90`,
  `Model.historyFloor(todayIso) -> String`.

This is the live bug. Toggl rejects any `start_date` earlier than 91 days with HTTP 400
and the message `start_date must not be earlier than <date>`. `365` is offered in the UI,
accepted by `_history_days`, and makes every `sync` fail.

- [ ] **Step 1: Write the failing Python tests**

Append to `tests/test_toggl_api.py`:

```python
class HistoryDaysTest(unittest.TestCase):
    def test_none_defaults_to_30(self):
        self.assertEqual(toggl_api._history_days(None), 30)

    def test_365_clamps_to_the_safe_window(self):
        self.assertEqual(toggl_api._history_days(365), toggl_api.HISTORY_SAFE_DAYS)

    def test_93_clamps_because_the_api_floor_is_91_days(self):
        self.assertEqual(toggl_api._history_days(93), toggl_api.HISTORY_SAFE_DAYS)

    def test_92_is_the_largest_accepted_window(self):
        self.assertEqual(toggl_api._history_days(92), 92)

    def test_arbitrary_small_values_pass_through(self):
        self.assertEqual(toggl_api._history_days(45), 45)

    def test_zero_and_negative_default_to_30(self):
        self.assertEqual(toggl_api._history_days(0), 30)
        self.assertEqual(toggl_api._history_days(-5), 30)

    def test_non_integer_is_rejected(self):
        with self.assertRaises(toggl_api.ValidationError):
            toggl_api._history_days("30")
        with self.assertRaises(toggl_api.ValidationError):
            toggl_api._history_days(True)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.HistoryDaysTest -v`
Expected: FAIL — `AttributeError: module 'toggl_api' has no attribute 'HISTORY_SAFE_DAYS'`

- [ ] **Step 3: Implement**

In `toggl_api.py`, after `CACHE_VERSION = 1`:

```python
# Measured against the live API on 2026-09-03: a start_date earlier than
# today-91 is rejected with HTTP 400 "start_date must not be earlier than
# <date>". 92 days inclusive is the largest window that succeeds; 90 is the
# largest value offered, leaving margin.
HISTORY_MAX_DAYS = 92
HISTORY_SAFE_DAYS = 90
HISTORY_FLOOR_DAYS = 91
```

Replace `_history_days`:

```python
def _history_days(value):
    if value is None:
        return 30
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("days must be an integer.")
    if value < 1:
        return 30
    return value if value <= HISTORY_MAX_DAYS else HISTORY_SAFE_DAYS
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest tests.test_toggl_api.HistoryDaysTest -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Write the failing node tests**

In `tests/test_model.mjs`, add `historyFloor` to the exported names in the `new Function`
block, then append before the summary:

```js
test("clampHistory maps 365 to 90", () => {
  assert.equal(Model.clampHistory(365), 90)
})
test("clampHistory keeps 30 and 90", () => {
  assert.equal(Model.clampHistory(30), 30)
  assert.equal(Model.clampHistory(90), 90)
})
test("clampHistory accepts the new 60 option", () => {
  assert.equal(Model.clampHistory(60), 60)
})
test("clampHistory falls back to 30 for junk", () => {
  assert.equal(Model.clampHistory("nope"), 30)
  assert.equal(Model.clampHistory(0), 30)
})
test("historyFloor is 91 days before the given day", () => {
  assert.equal(Model.historyFloor("2026-09-03"), "2026-06-04")
})
test("historyFloor crosses a month boundary", () => {
  assert.equal(Model.historyFloor("2026-03-01"), "2025-11-30")
})
```

- [ ] **Step 6: Run to verify failure**

Run: `node tests/test_model.mjs`
Expected: FAIL — `clampHistory(365)` returns 365, `historyFloor` is not a function

- [ ] **Step 7: Implement in `Model.js`**

Replace `clampHistory` and add `historyFloor`:

```js
// Toggl rejects any start_date earlier than today-91 with HTTP 400. 90 is the
// largest option offered, leaving margin against the 92-day hard bound.
function clampHistory(days) {
  days = Number(days)
  if (!isFinite(days) || days < 1) return 30
  return days > 92 ? 90 : Math.round(days)
}
function historyFloor(dateValue) { return shiftDate(dateValue, -91) }
```

- [ ] **Step 8: Run to verify pass**

Run: `node tests/test_model.mjs`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add toggl_api.py Model.js tests/test_toggl_api.py tests/test_model.mjs
git commit -m "fix(history): clamp to the verified 91-day Toggl start_date floor"
```

---

### Task 5: Return the block detail already being computed

**Files:**
- Modify: `toggl_api.py:440-532` — `segment_blocks`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Produces: each block dict additionally carries `idle_seconds` (int),
  `fragments` (int), `longest_fragment_seconds` (int),
  `domains` (`[{"name": str, "seconds": int}]`) and
  `timeline` (`[{"offset": int, "seconds": int, "topic": str, "idle": bool}]`).
  `apps` **changes** from `[str]` to `[{"name": str, "seconds": int}]`.
  `domain` (str) is retained unchanged for compatibility.

`segment_blocks` already builds a full `domains` weight map and then keeps only
`max()`. Per-fragment seconds are in hand one loop earlier. Everything here is computed
inside the existing loop — no extra pass over the events.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_api.py`. Reuse the module's existing event helpers if present;
otherwise this builds them locally:

```python
class BlockDetailTest(unittest.TestCase):
    @staticmethod
    def _window(start, seconds, app, title):
        return {"timestamp": start, "duration": seconds, "data": {"app": app, "title": title}}

    def _blocks(self):
        base = "2026-09-03T08:00:00+00:00"

        def at(minutes, seconds, app, title):
            moment = datetime.fromisoformat(base) + timedelta(minutes=minutes)
            return self._window(moment.isoformat(), seconds, app, title)

        windows = [
            at(0, 600, "dev.zed.Zed", "toggl_api.py — plugin"),
            at(10, 300, "zen", "Toggl API reference — Zen"),
            at(15, 600, "dev.zed.Zed", "toggl_api.py — plugin"),
            at(40, 900, "dev.zed.Zed", "Model.js — plugin"),
        ]
        afk = [{"timestamp": base, "duration": 4200, "data": {"status": "not-afk"}}]
        web = [{
            "timestamp": (datetime.fromisoformat(base) + timedelta(minutes=10)).isoformat(),
            "duration": 300,
            "data": {"url": "https://engineering.toggl.com/docs", "title": "Toggl"},
        }]
        return toggl_api.segment_blocks(windows, afk, web, {"min_block_minutes": 5})

    def test_apps_carry_seconds(self):
        block = self._blocks()[0]
        self.assertTrue(all(set(item) == {"name", "seconds"} for item in block["apps"]))
        zed = [item for item in block["apps"] if item["name"] == "dev.zed.Zed"][0]
        self.assertEqual(zed["seconds"], 2100)

    def test_apps_are_ranked_by_seconds(self):
        seconds = [item["seconds"] for item in self._blocks()[0]["apps"]]
        self.assertEqual(seconds, sorted(seconds, reverse=True))

    def test_domains_are_a_ranked_list_not_only_the_max(self):
        block = self._blocks()[0]
        self.assertEqual(block["domains"], [{"name": "engineering.toggl.com", "seconds": 300}])
        self.assertEqual(block["domain"], "engineering.toggl.com")

    def test_fragment_count_and_longest_run(self):
        block = self._blocks()[0]
        self.assertEqual(block["fragments"], 4)
        self.assertEqual(block["longest_fragment_seconds"], 900)

    def test_idle_seconds_is_span_minus_active(self):
        block = self._blocks()[0]
        self.assertEqual(block["idle_seconds"], block["span_seconds"] - block["seconds"])
        self.assertGreaterEqual(block["idle_seconds"], 0)

    def test_timeline_offsets_are_relative_and_ascending(self):
        timeline = self._blocks()[0]["timeline"]
        offsets = [item["offset"] for item in timeline]
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(all(set(item) == {"offset", "seconds", "topic", "idle"} for item in timeline))

    def test_timeline_marks_the_gap_between_fragments(self):
        self.assertTrue(any(item["idle"] for item in self._blocks()[0]["timeline"]))

    def test_timeline_is_capped_at_200_entries(self):
        base = datetime.fromisoformat("2026-09-03T08:00:00+00:00")
        windows = [
            self._window((base + timedelta(seconds=index * 20)).isoformat(), 20,
                         "dev.zed.Zed", "file-%d.py — plugin" % index)
            for index in range(400)
        ]
        afk = [{"timestamp": base.isoformat(), "duration": 8000, "data": {"status": "not-afk"}}]
        blocks = toggl_api.segment_blocks(windows, afk, [], {"min_block_minutes": 5})
        self.assertTrue(all(len(block["timeline"]) <= 200 for block in blocks))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.BlockDetailTest -v`
Expected: FAIL — `apps` entries are strings, `KeyError: 'domains'`

- [ ] **Step 3: Add the timeline cap constant**

In `toggl_api.py`, beside the other constants:

```python
MAX_TIMELINE = 200
```

- [ ] **Step 4: Rewrite the block-building loop**

In `segment_blocks`, replace the body of the `for group in groups:` loop — everything from
`weights = {}` to the `blocks.append({...})` call — with:

```python
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
```

- [ ] **Step 5: Add the timeline builder**

In `toggl_api.py`, immediately above `def segment_blocks(`:

```python
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
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS. If an existing test asserts `apps` is a list of strings, update it to the
new shape — that is the one intentional non-additive change in this task.

- [ ] **Step 7: Commit**

```bash
git add toggl_api.py tests/test_toggl_api.py
git commit -m "feat(day): return app, domain, fragment and timeline detail per block"
```

---

### Task 6: Cache the ActivityWatch round trips

**Files:**
- Modify: `toggl_api.py` — `_CacheStore`, `_activitywatch_day`, `day_activity`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Produces: two new cache kinds, `"awbuckets"` (TTL 24 h) and `"awday"` (TTL 10 min,
  keyed by date). `_activitywatch_day(start, end, date_value)` gains a third parameter.
  `day_activity` accepts an optional `entries` list in its payload and skips
  `_history_entries` when given one.

`day_activity` currently re-lists every ActivityWatch bucket on each call to resolve three
ids that never change, refetches the events when only the break setting changed, and
refetches the day's entries that `sync` already returned.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_api.py`:

```python
AW_BUCKETS = {
    "aw-watcher-window_host": {"id": "aw-watcher-window_host", "type": "currentwindow"},
    "aw-watcher-afk_host": {"id": "aw-watcher-afk_host", "type": "afkstatus"},
    "aw-watcher-web_host": {"id": "aw-watcher-web_host", "type": "web.tab.current"},
}


class RecordingOpener:
    """Serves ActivityWatch responses indefinitely and records every path."""

    def __init__(self, events):
        self.events = events
        self.paths = []

    def __call__(self, request, timeout):
        path = request.full_url.split("?")[0].replace(toggl_api.ACTIVITYWATCH_URL, "")
        self.paths.append(path)
        if path == "/api/0/buckets/":
            return Response(AW_BUCKETS)
        for kind, bucket_id in (("window", "aw-watcher-window_host"),
                                ("afk", "aw-watcher-afk_host"),
                                ("web", "aw-watcher-web_host")):
            if bucket_id in path:
                return Response(self.events.get(kind, []))
        return Response([])

    def event_paths(self):
        return [path for path in self.paths if path.endswith("/events")]


class ActivityCacheTest(unittest.TestCase):
    DATE = "2026-08-19"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        self.opener = RecordingOpener({
            "window": [
                aw_event(base.isoformat(), 600, {"app": "dev.zed.Zed", "title": "a — plugin"}),
                # Fragment 1 runs 08:00–08:10; this one 08:17–08:27. The 7-minute
                # gap splits under a 5-minute break and merges under a 15-minute one.
                aw_event((base + timedelta(minutes=17)).isoformat(), 600,
                         {"app": "dev.zed.Zed", "title": "b — plugin"}),
            ],
            "afk": [aw_event(base.isoformat(), 4200, {"status": "not-afk"})],
            "web": [],
        })

    def _api(self):
        client = cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=TestClock(),
            activitywatch_opener=self.opener,
        ), client

    def _call(self, api, minutes=5, entries=None):
        payload = {"workspace_id": 4, "date": self.DATE, "min_block_minutes": minutes}
        if entries is not None:
            payload["entries"] = entries
        return api.day_activity(payload)

    def test_bucket_ids_are_cached_across_calls(self):
        api, _ = self._api()
        self._call(api)
        second, _ = self._api()
        self._call(second)
        self.assertEqual(self.opener.paths.count("/api/0/buckets/"), 1)

    def test_raw_events_are_cached_across_calls(self):
        api, _ = self._api()
        self._call(api)
        first = len(self.opener.event_paths())
        second, _ = self._api()
        self._call(second)
        self.assertEqual(len(self.opener.event_paths()), first)

    def test_changing_the_break_reuses_cached_events(self):
        api, _ = self._api()
        five = self._call(api, minutes=5)
        before = len(self.opener.event_paths())
        other, _ = self._api()
        fifteen = self._call(other, minutes=15)
        self.assertEqual(len(self.opener.event_paths()), before)
        self.assertEqual(len(five["blocks"]), 2)
        self.assertEqual(len(fifteen["blocks"]), 1)

    def test_day_activity_uses_supplied_entries(self):
        api, client = self._api()
        result = self._call(api, entries=[{"id": 9, "start": "", "stop": ""}])
        self.assertEqual(result["entries"], [{"id": 9, "start": "", "stop": ""}])
        self.assertNotIn("/me/time_entries", [call[1] for call in client.calls])

    def test_day_activity_still_fetches_entries_when_none_supplied(self):
        api, client = self._api()
        self._call(api)
        self.assertIn("/me/time_entries", [call[1] for call in client.calls])
```

Each test builds a **second** `TogglAPI` for the repeat call, because the caches are
on disk and a fresh process is what actually happens in production — the helper handles
one request and exits.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.ActivityCacheTest -v`
Expected: FAIL on all four

- [ ] **Step 3: Add the TTLs and cache paths**

In `toggl_api.py`, beside the other TTLs:

```python
AW_BUCKETS_TTL = timedelta(hours=24)
AW_DAY_TTL = timedelta(minutes=10)
```

In `_CacheStore._path`, replace the body:

```python
    def _path(self, kind, workspace_id=None):
        if kind == "account":
            name = "account-%s.json" % self.account_key
        elif kind == "awbuckets":
            name = "awbuckets-%s.json" % self.account_key
        elif kind == "awday":
            name = "awday-%s-%s.json" % (self.account_key, workspace_id)
        else:
            name = "workspace-%s-%d.json" % (self.account_key, workspace_id)
        return self.root / name
```

For `"awday"`, `workspace_id` carries the ISO date string. Guard it:

```python
        if kind == "awday" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(workspace_id or "")):
            raise ValueError("awday cache key must be an ISO date")
```

placed as the first statement of `_path`.

In `_valid_common`, the `kind == "workspace"` identity check must not fire for the new
kinds. Change:

```python
        if kind == "workspace" and value.get("workspace_id") != workspace_id:
            return None
```

to:

```python
        if kind in ("workspace", "awday") and value.get("workspace_id") != workspace_id:
            return None
```

In `load()`, the validation branch:

```python
            if kind == "account":
                if not self._valid_account(value):
                    return None
            elif kind in ("awbuckets", "awday"):
                if not isinstance(value.get("payload"), (dict, list)):
                    return None
            elif not self._valid_workspace(value, workspace_id):
                return None
```

- [ ] **Step 4: Use the caches in `_activitywatch_day`**

Replace `_activitywatch_day`:

```python
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
```

The cached events are raw ActivityWatch records — derivable and disposable, so this
respects the rule against durable state in the cache. `segment_blocks` stays the single
implementation of segmentation; re-segmenting a cached day costs no HTTP.

- [ ] **Step 5: Accept caller-supplied entries in `day_activity`**

In `day_activity`, replace these two lines:

```python
        activity = self._activitywatch_day(start, end)
        entries = self._history_entries(workspace_id, payload["date"], payload["date"])
```

with:

```python
        activity = self._activitywatch_day(start, end, payload["date"])
        supplied = payload.get("entries")
        if isinstance(supplied, list):
            entries = [item for item in supplied if isinstance(item, dict)]
        else:
            entries = self._history_entries(workspace_id, payload["date"], payload["date"])
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add toggl_api.py tests/test_toggl_api.py
git commit -m "perf(day): cache bucket ids and raw activity, accept supplied entries"
```

---

### Task 7: Cache entries, use `since`, and ask for `meta`

**Files:**
- Modify: `toggl_api.py` — `_CacheStore`, `sync`, `_history_entries`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Produces: cache kind `"entries"` (TTL 60 min, keyed by workspace). `sync` sends
  `meta=true` on `/me/time_entries` and, when a cached window exists, refreshes with
  `since` instead of refetching. `_normalized_entry` gains `project_color`.

`/me/time_entries` is refetched on every `sync` over the whole window even when the
metadata cache is fresh, and entries are never cached at all. `since` is documented,
delta by modification time, and confirmed working — but it is subject to the same 91-day
floor, so it must be clamped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_api.py`:

```python
class EntryCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _api(self, client=None, clock=None):
        client = client or cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=clock or TestClock()), client

    @staticmethod
    def _entry_params(client):
        return [call[2] for call in client.calls if call[1] == "/me/time_entries"]

    def test_sync_requests_meta_true(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 30})
        self.assertEqual(self._entry_params(client)[0].get("meta"), "true")

    def test_first_sync_sends_a_window(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[0]
        self.assertIn("start_date", params)
        self.assertNotIn("since", params)

    def test_second_sync_uses_since_not_the_full_window(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[1]
        self.assertIn("since", params)
        self.assertNotIn("start_date", params)

    def test_since_is_never_earlier_than_the_history_floor(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        late = TestClock()
        late.value = late.value + timedelta(days=200)
        second, _ = self._api(client=client, clock=late)
        second.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[1]
        # The cache has long expired, so this must be a fresh window, never a
        # `since` older than the floor -- which the API rejects with 400.
        self.assertIn("start_date", params)
        self.assertNotIn("since", params)

    def test_start_date_is_never_earlier_than_the_history_floor(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 92})
        params = self._entry_params(client)[0]
        floor = (TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)).isoformat()
        self.assertGreaterEqual(params["start_date"], floor)

    def test_force_refresh_ignores_the_entry_cache(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 30, "force_refresh": True})
        params = self._entry_params(client)[1]
        self.assertIn("start_date", params)

    def test_since_delta_removes_a_deleted_entry(self):
        client = cache_client()
        client.queue(
            "/me/time_entries",
            [{"id": 1, "workspace_id": 4, "start": "2026-08-18T08:00:00Z", "duration": 60}],
            [{"id": 1, "workspace_id": 4, "start": "2026-08-18T08:00:00Z", "duration": 60,
              "server_deleted_at": "2026-08-19T09:00:00Z"}],
        )
        first, _ = self._api(client=client)
        self.assertEqual(len(first.sync({"workspace_id": 4, "days": 30})["entries"]), 1)
        second, _ = self._api(client=client)
        self.assertEqual(second.sync({"workspace_id": 4, "days": 30})["entries"], [])

    def test_project_color_survives_normalisation(self):
        entry = toggl_api._normalized_entry({
            "id": 1, "workspace_id": 7, "project_id": 3, "project_color": "#0b83d9",
            "start": "2026-09-03T08:00:00Z", "duration": 60,
        })
        self.assertEqual(entry["project_color"], "#0b83d9")
```

`cache_client()` responds to `/me/time_entries` with `[]` by default; `client.queue()`
supplies a different response per call, which is what the delta test needs.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.EntryCacheTest -v`
Expected: FAIL on all five

- [ ] **Step 3: Add the TTL and cache kind**

In `toggl_api.py`:

```python
ENTRIES_TTL = timedelta(minutes=60)
```

In `_CacheStore._path`, add before the final `else`:

```python
        elif kind == "entries":
            name = "entries-%s-%d.json" % (self.account_key, workspace_id)
```

In `_valid_common`, extend the identity check to include `"entries"`:

```python
        if kind in ("workspace", "awday", "entries") and value.get("workspace_id") != workspace_id:
            return None
```

In `load()`, add `"entries"` to the `elif kind in ("awbuckets", "awday"):` tuple.

- [ ] **Step 4: Add `project_color` to entry normalisation**

In `_normalized_entry`, add to the returned dict, after `"billable"`:

```python
        "project_color": str(entry.get("project_color") or ""),
```

- [ ] **Step 5: Fetch entries through one helper**

In `toggl_api.py`, add a method to `TogglAPI`:

```python
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
        warm = cached is not None and not force_refresh and now < cached[1]

        if warm:
            previous = cached[0]
            since_moment = _cache_time(_cache_expiry(previous["expires_at"]) - ENTRIES_TTL)
            if since_moment.date() >= floor_date:
                params = {"since": int(since_moment.timestamp()), "meta": "true"}
                delta = _list_response(
                    self.client.request("GET", "/me/time_entries", params), "time_entries")
                merged = {str(item.get("id")): item for item in previous["entries"]}
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
                self._write_entry_cache(store, workspace_id, raw, now)
                return raw

        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "meta": "true",
        }
        raw = _list_response(self.client.request("GET", "/me/time_entries", params), "time_entries")
        raw = [item for item in raw if isinstance(item, dict)]
        self._write_entry_cache(store, workspace_id, raw, now)
        return raw

    def _write_entry_cache(self, store, workspace_id, raw, now):
        if not store:
            return
        store.write("entries", {
            "schema": CACHE_SCHEMA, "version": CACHE_VERSION, "kind": "entries",
            "account_key": self.client.account_key, "workspace_id": workspace_id,
            "expires_at": _cache_iso(now + ENTRIES_TTL),
            "entries": raw,
        }, workspace_id)
```

- [ ] **Step 6: Call it from `sync`**

In `sync`, delete **both** blocks that build `params` and call
`self.client.request("GET", "/me/time_entries", params)` — the one inside the
`else:` branch and the one inside the later `if fresh:` branch — and replace the
`entries = []` initialisation with nothing. Immediately before the
`project_names, task_names, … = self._metadata_maps(...)` line, insert:

```python
        entries = self._fetch_entries(workspace_id, days, force_refresh)
```

Then change the history loop to iterate the list directly:

```python
        history = []
        for item in entries:
            normalized = _normalized_entry(item, project_names, task_names, client_names, project_clients, task_clients)
            if normalized and normalized["workspace_id"] == workspace_id:
                history.append(normalized)
```

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add toggl_api.py tests/test_toggl_api.py
git commit -m "perf(sync): cache entries, refresh with since, request meta=true"
```

---

### Task 8: One process on panel open

**Files:**
- Modify: `toggl_api.py` — `bootstrap`
- Modify: `Panel.qml` — `handleResponse`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Produces: `bootstrap` returns its existing keys plus, when a workspace can be chosen,
  every key `sync` returns. A payload flag `"skip_sync": true` preserves the old
  behaviour for tests and for `setup`, which only needs to validate the token.

Opening the panel currently fires `bootstrap`, then `sync` from its response — two cold
Python starts, each spawning `secret-tool`, before any HTTP.

- [ ] **Step 1: Write the failing tests**

```python
class BootstrapFoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _api(self, client=None):
        client = client or cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=TestClock()), client

    def test_bootstrap_returns_sync_data_in_one_call(self):
        api, _ = self._api()
        data = api.bootstrap({})
        for key in ("user", "workspaces", "projects", "tasks_available", "entries"):
            self.assertIn(key, data)
        self.assertEqual(data["workspace_id"], 4)

    def test_bootstrap_makes_the_project_request_itself(self):
        api, client = self._api()
        api.bootstrap({})
        self.assertIn("/workspaces/4/projects", [call[1] for call in client.calls])

    def test_bootstrap_with_skip_sync_returns_only_account_data(self):
        api, client = self._api()
        data = api.bootstrap({"skip_sync": True})
        self.assertIn("workspaces", data)
        self.assertNotIn("projects", data)
        self.assertNotIn("/workspaces/4/projects", [call[1] for call in client.calls])

    def test_bootstrap_without_a_choosable_workspace_skips_sync(self):
        client = cache_client()
        client.respond("/me/workspaces", [])
        api, _ = self._api(client=client)
        data = api.bootstrap({})
        self.assertNotIn("projects", data)

    def test_a_failing_sync_still_returns_account_data(self):
        client = cache_client()
        client.respond("/workspaces/4/projects", toggl_api.ApiError("down", 500, True))
        api, _ = self._api(client=client)
        data = api.bootstrap({})
        self.assertIn("workspaces", data)
        self.assertNotIn("projects", data)

    def test_default_workspace_prefers_the_user_default(self):
        data = {
            "workspaces": [{"id": 4}, {"id": 9}],
            "user": {"default_workspace_id": 9},
            "current": None,
        }
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data), 9)

    def test_default_workspace_falls_back_to_the_first(self):
        data = {"workspaces": [{"id": 4}], "user": {"default_workspace_id": 77}, "current": None}
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data), 4)

    def test_default_workspace_returns_zero_with_no_workspaces(self):
        self.assertEqual(toggl_api.TogglAPI._default_workspace({"workspaces": []}), 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.BootstrapFoldTest -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Replace `TogglAPI.bootstrap`:

```python
    def bootstrap(self, payload=None):
        payload = payload or {}
        data = self._account_data(_bool(payload.get("force_refresh", False), "force_refresh"))
        if _bool(payload.get("skip_sync", False), "skip_sync"):
            return data
        workspace_id = self._default_workspace(data)
        if not workspace_id:
            return data
        try:
            data.update(self.sync({
                "workspace_id": workspace_id,
                "days": payload.get("days"),
                "force_refresh": payload.get("force_refresh", False),
                "skip_current": False,
            }))
        except ApiError as error:
            _log(self.logger, "errors", action="bootstrap_sync", ok=False, status=error.status)
        data["workspace_id"] = workspace_id
        return data
```

Add the workspace chooser beside it — the panel's `chooseWorkspace()` logic, moved so a
single call can resolve it:

```python
    @staticmethod
    def _default_workspace(data):
        workspaces = data.get("workspaces") or []
        user = data.get("user") or {}
        current = data.get("current") or {}
        candidates = [
            current.get("workspace_id"),
            user.get("default_workspace_id"),
            workspaces[0].get("id") if workspaces else None,
        ]
        available = {item.get("id") for item in workspaces if isinstance(item, dict)}
        for candidate in candidates:
            if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate in available:
                return candidate
        return 0
```

A `sync` failure inside `bootstrap` is logged and swallowed: the panel still gets its
account data and can retry, exactly as it does today.

- [ ] **Step 4: Stop the panel firing the second request**

In `Panel.qml`, in `handleResponse`, replace:

```qml
            if (action === "bootstrap") {
                if (chooseWorkspace())
                    sync(false, true);

            } else if (action === "sync") {
```

with:

```qml
            if (action === "bootstrap") {
                if (response.data && response.data.workspace_id)
                    root.selectedWorkspaceId = Number(response.data.workspace_id) || 0;

                root.persist({
                    "workspaceId": root.selectedWorkspaceId
                });
                if (!root.selectedWorkspaceId)
                    root.chooseWorkspace();

                if (root.activeTab === "day" && !root.dayLoaded)
                    root.loadDay();

            } else if (action === "sync") {
```

- [ ] **Step 5: Keep `setup` cheap**

In `setup`, change the validation line to send `skip_sync`:

```bash
if ! printf '%s\n' '{"action":"bootstrap","skip_sync":true}' | python3 "$script_dir/toggl_api.py" >/dev/null 2>&1; then
```

- [ ] **Step 6: Verify**

Run: `python3 -m unittest discover -s tests -v`
Run: `qmlformat Panel.qml >/dev/null; echo $?`
Expected: unittest PASS, `qmlformat` exit 0

- [ ] **Step 7: Commit**

```bash
git add toggl_api.py Panel.qml setup tests/test_toggl_api.py
git commit -m "perf(bootstrap): fold the first sync into one process"
```

---

### Task 9: Stop re-normalising on every keystroke

**Files:**
- Modify: `Model.js` — `searchItems`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Produces: `searchItems` unchanged in signature and return shape. It no longer calls
  `normalizeProject` or `normalizeTask`.

`applyData` already normalises both on arrival. `searchItems` normalises them again on
every keystroke, building a 25-field object per project each time.

- [ ] **Step 1: Write the failing test**

Add `searchItems` and `normalizeProject` to the exports in `tests/test_model.mjs`, then:

```js
test("searchItems does not renormalise its inputs", () => {
  const project = Model.normalizeProject({ id: 1, name: "acme", active: true })
  const result = Model.searchItems([], [project], [], "acme", "all", 0)
  assert.equal(result.projects[0], project, "the same object must come back, not a copy")
})
test("searchItems still filters inactive projects", () => {
  const active = Model.normalizeProject({ id: 1, name: "acme", active: true })
  const archived = Model.normalizeProject({ id: 2, name: "acme old", active: false })
  const result = Model.searchItems([], [active, archived], [], "acme", "all", 0)
  assert.deepEqual(result.projects.map((p) => p.id), [1])
})
test("searchItems still scopes tasks to a project in tasks mode", () => {
  const a = Model.normalizeTask({ id: 1, name: "build", project_id: 1, active: true })
  const b = Model.normalizeTask({ id: 2, name: "build", project_id: 2, active: true })
  const result = Model.searchItems([], [], [a, b], "build", "tasks", 1)
  assert.deepEqual(result.tasks.map((t) => t.id), [1])
})
```

- [ ] **Step 2: Run to verify failure**

Run: `node tests/test_model.mjs`
Expected: FAIL on the identity assertion — a copy comes back

- [ ] **Step 3: Implement**

In `Model.js`, inside `searchItems`, change:

```js
  var sortedProjects = (projects || []).map(normalizeProject).filter(function(project) {
```

to:

```js
  var sortedProjects = (projects || []).filter(function(project) {
```

and:

```js
  var scopedTasks = (tasks || []).map(normalizeTask).filter(function(task) {
```

to:

```js
  var scopedTasks = (tasks || []).filter(function(task) {
```

Add a comment above the function:

```js
// Inputs arrive already normalised from Panel.qml's applyData(). Renormalising
// here rebuilt a 25-field object per project on every keystroke.
```

- [ ] **Step 4: Run to verify pass**

Run: `node tests/test_model.mjs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Model.js tests/test_model.mjs
git commit -m "perf(search): stop renormalising projects and tasks per keystroke"
```

---

### Task 10: Queue requests instead of dropping them

**Files:**
- Modify: `Panel.qml` — `request()`, `handleResponse()`, new `requestQueue` property

**Interfaces:**
- Produces: `root.requestQueue` (array, max 8), `root.enqueue(action, data)`.
  `request()` keeps its signature. A dropped enqueue appends to `root.clientLog`.

`request()` returns early and silently when `requestPending` is set. The click does not
queue and nothing tells the user.

- [ ] **Step 1: Add the properties**

In `Panel.qml`, beside the other properties:

```qml
    property var requestQueue: []
    property var clientLog: []
```

- [ ] **Step 2: Add the queue helpers**

Replace `request()`:

```qml
    function noteClient(level, event, detail) {
        if (clientLog.length >= 32)
            return ;

        var entry = clientLog.slice();
        entry.push({
            "lvl": level,
            "event": event,
            "detail": detail || ""
        });
        clientLog = entry;
    }

    function request(action, data) {
        if (requestPending) {
            enqueue(action, data);
            return ;
        }
        requestPending = true;
        pendingAction = action;
        errorMessage = "";
        status = "loading";
        var payload = data || {
        };
        payload.action = action;
        payload.log_level = root.logLevel;
        if (clientLog.length > 0) {
            payload.client_log = clientLog;
            clientLog = [];
        }
        apiProc.request = JSON.stringify(payload);
        apiProc.running = true;
    }

    // Coalesces by action: a second refresh queued behind a first is the same
    // refresh, and running it twice only costs a process.
    function enqueue(action, data) {
        var queue = requestQueue.slice();
        for (var i = 0; i < queue.length; i++) {
            if (queue[i].action === action) {
                queue[i] = {
                    "action": action,
                    "data": data
                };
                requestQueue = queue;
                return ;
            }
        }
        if (queue.length >= 8) {
            noteClient("errors", "queue_overflow", action);
            return ;
        }
        queue.push({
            "action": action,
            "data": data
        });
        requestQueue = queue;
    }

    function pumpQueue() {
        if (requestPending || requestQueue.length === 0)
            return ;

        var queue = requestQueue.slice();
        var next = queue.shift();
        requestQueue = queue;
        request(next.action, next.data);
    }
```

- [ ] **Step 3: Pump the queue after every response**

In `Panel.qml`, `handleResponse` currently has several early `return` statements. Wrap the
body so the queue is always pumped. Rename the existing function to
`handleResponseBody(raw)` — changing only its name, not a line of its body — and add:

```qml
    function handleResponse(raw) {
        handleResponseBody(raw);
        Qt.callLater(root.pumpQueue);
    }
```

`Qt.callLater` is required: pumping synchronously would re-enter `request()` while
`handleResponseBody` is still unwinding.

Also pump on process failure. In `apiProc.onExited`, after the existing
`root.errorMessage = "The Toggl helper is unavailable.";` line, add:

```qml
                Qt.callLater(root.pumpQueue);
```

- [ ] **Step 4: Verify the file still parses**

Run: `qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo $?`
Expected: exit 0. A parse error here reports with **zero output** — if that happens, look
first for a `;` between sibling objects.

- [ ] **Step 5: Commit**

```bash
git add Panel.qml
git commit -m "fix(panel): queue requests instead of dropping them silently"
```

---

### Task 11: Incremental day summary

**Files:**
- Modify: `Model.js` — `blockSummary`
- Modify: `Panel.qml` — `daySummary`, `slotChanged()`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Produces: `Model.applySummaryDelta(summary, before, after)` returning a new summary
  object. `blockSummary` keeps its existing signature and is still used for the initial
  full pass.

`daySummary` recomputes across all blocks on every `dayRevision` bump, which happens on
every keystroke in a block editor.

- [ ] **Step 1: Write the failing test**

```js
test("applySummaryDelta moves a block from pending to applied", () => {
  const blocks = [
    { state: "pending", seconds: 100, projectId: 1, description: "a" },
    { state: "applied", seconds: 200, projectId: 1, description: "b" },
  ]
  const before = Model.blockSummary(blocks)
  const changed = Object.assign({}, blocks[0], { state: "applied" })
  const next = Model.applySummaryDelta(before, blocks[0], changed)
  const expected = Model.blockSummary([changed, blocks[1]])
  assert.deepEqual(next, expected)
})
test("applySummaryDelta is a no-op when nothing summary-relevant changed", () => {
  const block = { state: "pending", seconds: 100, projectId: 1, description: "a" }
  const before = Model.blockSummary([block])
  const changed = Object.assign({}, block, { expanded: true })
  assert.deepEqual(Model.applySummaryDelta(before, block, changed), before)
})
```

- [ ] **Step 2: Run to verify failure**

Run: `node tests/test_model.mjs`
Expected: FAIL — `applySummaryDelta` is not a function

- [ ] **Step 3: Implement in `Model.js`**

Add `applySummaryDelta` to the exports in the test file and to `Model.js`:

```js
// blockSummary is O(blocks); dayRevision bumps on every keystroke in an editor.
// This applies one block's transition instead of re-walking the list.
function applySummaryDelta(summary, before, after) {
  var counts = function(block) {
    if (!block) return { total: 0, applied: 0, ready: 0, conflict: 0 }
    var ready = block.state === "pending" && !block.busy && !!block.projectId &&
      String(block.description || "").trim().length > 0
    return {
      total: number(block.seconds, 0),
      applied: block.state === "applied" ? 1 : 0,
      ready: ready ? 1 : 0,
      conflict: block.state === "conflict" ? 1 : 0
    }
  }
  var a = counts(before)
  var b = counts(after)
  if (a.total === b.total && a.applied === b.applied && a.ready === b.ready && a.conflict === b.conflict)
    return summary
  return {
    totalSeconds: summary.totalSeconds - a.total + b.total,
    applied: summary.applied - a.applied + b.applied,
    ready: summary.ready - a.ready + b.ready,
    conflict: summary.conflict - a.conflict + b.conflict
  }
}
```

If `blockSummary` does not currently return a `conflict` key, add it there too, counting
`state === "conflict"`, and update any test that asserts its exact shape.

- [ ] **Step 4: Use it in `Panel.qml`**

Replace the `daySummary` declaration:

```qml
    property var daySummary: Model.blockSummary([])
```

and add a helper, called by every site that currently mutates a block:

```qml
    function mutateBlock(block, apply) {
        var before = {
            "state": block.state,
            "seconds": block.seconds,
            "projectId": block.projectId,
            "description": block.description,
            "busy": block.busy
        };
        apply();
        root.daySummary = Model.applySummaryDelta(root.daySummary, before, block);
        root.dayRevision += 1;
    }
```

Set the full summary once, where `dayBlocks` is assigned in `handleResponseBody`:

```qml
                dayBlocks = Model.prepareBlocks(response.data.blocks, response.data.entries);
                daySummary = Model.blockSummary(dayBlocks);
                slotChanged();
```

- [ ] **Step 5: Verify**

Run: `node tests/test_model.mjs`
Run: `qmlformat Panel.qml >/dev/null; echo $?`
Expected: node PASS, `qmlformat` exit 0

- [ ] **Step 6: Commit**

```bash
git add Model.js Panel.qml tests/test_model.mjs
git commit -m "perf(day): apply summary deltas instead of rewalking every block"
```

---

### Task 12: Settings — remove the broken option, add the log level

**Files:**
- Modify: `manifest.json`
- Modify: `Panel.qml` — settings section, `persist()`, `onSettingsChanged`

**Interfaces:**
- Produces: `root.logLevel` (string), read by `request()` from Task 10.

- [ ] **Step 1: Update the manifest**

In `manifest.json`, replace `defaults` and add the two schema rows:

```json
    "defaults": {
      "workspaceId": 0,
      "historyDays": 30,
      "idleReminderMinutes": 0,
      "dayBlockMinutes": 5,
      "logLevel": "info"
    },
    "schema": [
      { "key": "workspaceId", "type": "number", "label": "Workspace", "defaultValue": 0 },
      { "key": "historyDays", "type": "number", "label": "History range (days)", "defaultValue": 30 },
      { "key": "idleReminderMinutes", "type": "number", "label": "Idle reminder (minutes)", "defaultValue": 0 },
      { "key": "dayBlockMinutes", "type": "number", "label": "Day: break between blocks (minutes)", "defaultValue": 5 },
      { "key": "logLevel", "type": "string", "label": "Log detail", "defaultValue": "info" }
    ]
```

- [ ] **Step 2: Add the property and persist it**

In `Panel.qml`:

```qml
    property string logLevel: String(setting("logLevel", "info"))
```

In `persist()`, add `"logLevel": logLevel` to the object literal. In
`onSettingsChanged`, add:

```qml
        logLevel = String(setting("logLevel", "info"));
```

- [ ] **Step 3: Replace the history options and add the log control**

In the settings `ColumnLayout`, change the history `ButtonGroup`:

```qml
                            ButtonGroup {
                                visible: root.activeTab === "timer"
                                options: ["30", "60", "90"]
                                value: String(root.historyDays)
                                onChanged: function(value) {
                                    root.setHistory(value);
                                }
                            }
```

and append, after the idle reminder group:

```qml
                            Text {
                                visible: root.activeTab === "timer"
                                text: "LOG DETAIL"
                                color: Qt.darker(root.foreground, 1.8)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.activeTab === "timer"
                                options: ["Off", "Errors", "Info", "Debug"]
                                value: root.logLevel.charAt(0).toUpperCase() + root.logLevel.slice(1)
                                onChanged: function(value) {
                                    root.setLogLevel(value.toLowerCase());
                                }
                            }

                            Text {
                                visible: root.activeTab === "timer" && root.logLevel === "debug"
                                Layout.fillWidth: true
                                text: "Debug records window titles and entry descriptions in the plugin's log."
                                color: Qt.darker(root.foreground, 1.8)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }
```

The `Qt.darker` calls here match the file's current style and are replaced wholesale in
stage 2, which removes all 21 of them at once. Do not fix them piecemeal.

- [ ] **Step 4: Add the setter**

```qml
    function setLogLevel(level) {
        logLevel = ["off", "errors", "info", "debug"].indexOf(level) >= 0 ? level : "info";
        persist({
            "logLevel": logLevel
        });
    }
```

- [ ] **Step 5: Verify**

Run: `qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo $?`
Run: `omarchy plugin validate .; echo $?`
Expected: both exit 0

- [ ] **Step 6: Commit**

```bash
git add manifest.json Panel.qml
git commit -m "feat(settings): drop the broken 365-day option, add log detail"
```

---

### Task 13: The `build` release gate

**Files:**
- Create: `build`

**Interfaces:**
- Produces: `./build` (full run, writes `dist/`) and `./build --check` (checks only).
  Exit 0 on success, non-zero on the first failure.

- [ ] **Step 1: Write the script**

Create `build`:

```bash
#!/usr/bin/env bash
# Release gate. Nothing compiles — QML and Python ship as source. This refuses
# to tag a version that would not work once cloned.
set -eu

check_only=0
case "${1:-}" in
    --check) check_only=1 ;;
    "") ;;
    *) printf 'usage: build [--check]\n' >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
step=0
say() { step=$((step + 1)); printf '[%2d] %s\n' "$step" "$1" >&2; }
die() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

say 'manifest schema'
omarchy plugin validate . >/dev/null || die 'omarchy plugin validate rejected the manifest'

say 'python syntax'
python3 -m py_compile toggl_api.py toggl_log.py tests/test_toggl_api.py tests/test_toggl_log.py \
    || die 'py_compile failed'

say 'python tests'
python3 -m unittest discover -s tests >/dev/null || die 'python tests failed'

say 'node tests'
node tests/test_model.mjs >/dev/null || die 'node tests failed'

say 'shell syntax'
bash -n setup build install || die 'bash -n failed'

say 'qml formatting'
# Never pipe qmlformat or qmllint and read $? — they write nothing on failure,
# so `qmllint x.qml | tail` returns tail's status and a broken file reads green.
for file in Panel.qml ui/*.qml; do
    [ -e "$file" ] || continue
    if ! qmlformat "$file" >/dev/null 2>&1; then
        die "qmlformat rejected $file"
    fi
done

say 'BarWidget.qml needs hand review'
printf '     both QML tools reject `function open(): void`, which IpcHandler requires\n' >&2

say 'nothing unshippable is tracked'
for pattern in 'logs/' '\.gguf$' '__pycache__/' 'dist/'; do
    if git ls-files | grep -qE "$pattern"; then
        die "tracked files match $pattern"
    fi
done
if git grep -nIE '[0-9a-f]{32}' -- . ':!docs' ':!tests' >/dev/null 2>&1; then
    die 'a 32-hex string is tracked outside docs and tests; check for a leaked token'
fi

say 'working tree and version'
[ -z "$(git status --porcelain)" ] || die 'working tree is dirty'
version=$(python3 -c 'import json;print(json.load(open("manifest.json"))["version"])')
if git rev-parse -q --verify "refs/tags/v$version" >/dev/null; then
    die "v$version is already tagged; bump manifest.json"
fi

if [ "$check_only" -eq 1 ]; then
    printf 'OK: v%s passes every check\n' "$version" >&2
    exit 0
fi

say 'artifact'
rm -rf dist
mkdir -p dist
name="omarchy-toggl-track-$version"
git archive --format=tar.gz --prefix="$name/" -o "dist/$name.tar.gz" HEAD
( cd dist && sha256sum "$name.tar.gz" > SHA256SUMS )
printf 'OK: dist/%s.tar.gz\n' "$name" >&2
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod 700 build
./build --check
```

Expected: every step prints, and it exits 0 — or names exactly what is wrong. A dirty
tree at this point is expected; commit first, then re-run.

- [ ] **Step 3: Commit**

```bash
git add build
git commit -m "build: add the release gate"
```

- [ ] **Step 4: Re-run against the clean tree**

```bash
./build --check
```

Expected: exit 0

---

### Task 14: The `install` script

**Files:**
- Create: `install`

**Interfaces:**
- Produces: `./install`, `./install --dev`, `./install --enable`,
  `./install --uninstall`, `./install --uninstall --purge`, `./install --force`.

- [ ] **Step 1: Write the script**

Create `install`:

```bash
#!/usr/bin/env bash
# Local install. The supported path for other people is:
#   omarchy plugin add <git-url> --enable
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
plugins="$HOME/.config/omarchy/plugins"
id=$(python3 -c 'import json;print(json.load(open("manifest.json"))["id"])' 2>/dev/null) \
    || { printf 'Cannot read id from manifest.json\n' >&2; exit 1; }
target="$plugins/$id"

dev=0; enable=0; uninstall=0; purge=0; force=0
for argument in "$@"; do
    case "$argument" in
        --dev) dev=1 ;;
        --enable) enable=1 ;;
        --uninstall) uninstall=1 ;;
        --purge) purge=1 ;;
        --force) force=1 ;;
        *) printf 'usage: install [--dev] [--enable] [--uninstall [--purge]] [--force]\n' >&2; exit 2 ;;
    esac
done

if [ "$uninstall" -eq 1 ]; then
    if [ -e "$target" ] || [ -L "$target" ]; then
        rm -rf -- "$target"
        printf 'Removed %s\n' "$target" >&2
    else
        printf 'Nothing installed at %s\n' "$target" >&2
    fi
    if [ "$purge" -eq 1 ]; then
        secret-tool clear service "$id" account api-token >/dev/null 2>&1 || true
        rm -rf -- "${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-toggl-track"
        rm -rf -- "${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track"
        printf 'Purged the stored token, the cache and the model.\n' >&2
    fi
    printf 'Run: omarchy-restart-shell\n' >&2
    exit 0
fi

mkdir -p "$plugins"
if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$force" -eq 0 ]; then
        if [ -L "$target" ]; then
            printf 'A symlink is already installed at %s -> %s\n' "$target" "$(readlink -- "$target")" >&2
        else
            printf 'A directory is already installed at %s\n' "$target" >&2
        fi
        printf 'Pass --force to replace it.\n' >&2
        exit 1
    fi
    rm -rf -- "$target"
fi

if [ "$dev" -eq 1 ]; then
    ln -s -- "$root" "$target"
    printf 'Linked %s -> %s\n' "$target" "$root" >&2
else
    mkdir -p "$target"
    git -C "$root" ls-files -z | while IFS= read -r -d '' file; do
        mkdir -p "$target/$(dirname -- "$file")"
        cp -p -- "$root/$file" "$target/$file"
    done
    printf 'Copied %s files to %s\n' "$(git -C "$root" ls-files | wc -l)" "$target" >&2
fi

omarchy plugin validate "$target" >/dev/null || {
    printf 'The installed folder failed manifest validation.\n' >&2
    exit 1
}

if [ "$enable" -eq 1 ]; then
    omarchy plugin enable "$id" center
fi

printf '\nNext:\n' >&2
printf '  ./setup                 store your Toggl API token\n' >&2
printf '  omarchy-restart-shell   the panel will not appear until you do\n' >&2
printf '\nNote: reloadConfig keeps the plugin Loader alive, so a panel edit does not\n' >&2
printf 'appear; rescanPlugins is not in this shell IPC surface and exits 0 regardless.\n' >&2
```

Copying via `git ls-files` is deliberate: it is the only listing that cannot pick up
`logs/`, `dist/`, `__pycache__/` or a downloaded model.

- [ ] **Step 2: Make it executable and test the dev path**

```bash
chmod 700 install
bash -n install
./install --dev --force
ls -l ~/.config/omarchy/plugins/daz.toggl-track
```

Expected: `bash -n` silent, the symlink points at this working tree — restoring exactly
the arrangement that was there before.

- [ ] **Step 3: Test the refusal path**

```bash
./install --dev
```

Expected: exit 1, naming the existing symlink and its target.

- [ ] **Step 4: Commit**

```bash
git add install
git commit -m "build: add the local install script"
```

---

### Task 15: Document it

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the install section to `README.md`**

Immediately after the opening description:

```markdown
## Install

```bash
omarchy plugin add https://github.com/<owner>/omarchy-toggl-track.git --enable
```

Then store your API token and restart the shell:

```bash
~/.config/omarchy/plugins/daz.toggl-track/setup
omarchy-restart-shell
```

To work on the plugin instead, clone it anywhere and link it in place:

```bash
./install --dev --enable
```
```

- [ ] **Step 2: Correct the history range in `README.md`**

Change `Configure 30, 90, or 365 days of searchable history` to:

```markdown
- Configure 30, 60, or 90 days of searchable history — Toggl rejects any
  `start_date` earlier than 91 days, so a longer range is not available
```

- [ ] **Step 3: Add the verified facts to `AGENTS.md`**

Under **ANTI-PATTERNS**:

```markdown
**Never offer a history range beyond 92 days.** Measured against the live API on
2026-09-03: `GET /me/time_entries` rejects any `start_date` earlier than `today-91`
with HTTP 400 and the body `start_date must not be earlier than <date>`. A 92-day
window is the largest that succeeds. The same floor applies to `since`. The shipped
`historyDays: 365` option made every `sync` fail; `_history_days` now clamps it.

**Never let the log carry a window title at `info`.** `toggl_log.SENSITIVE` drops
those keys unless the level is `debug`. The whole reason classification runs locally
is that titles do not leave the machine, and the log lives in the install directory.

**Never call `logger.write()` directly from the request path.** Use `_log()`, which
swallows every exception. Logging must never turn a working request into a failure.
```

Under **COMMANDS**, add:

```bash
./build --check                                # full release gate, no artifact
./install --dev --force                        # relink a development install
python3 -m unittest discover -s tests -v
```

Update the **WHERE TO LOOK** table with a `toggl_log.py` row: *Log levels, redaction,
the 24-hour ring buffer.*

- [ ] **Step 4: Run the gate**

```bash
./build --check
```

Expected: exit 0

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: install path, corrected history range, verified API floor"
```

---

## Self-Review

**Spec coverage.** Stage 0 (§13.2 `build`, §13.3 `install`, §10.8 logging) is Tasks 1–3
and 13–15. Stage 1 (§10.7 P1–P9, §10.3 block schema, §10.9 `historyDays`, §4.2
`meta=true`) is Tasks 4–12: P1 Task 8, P2/P3 Task 7, P4/P5/P6 Task 6, P7 Task 9,
P8 Task 10, P9 Task 11, D1/D2/D3/D7 Task 5, D5 Task 4, D6 Task 7.

**Deliberately out of scope for this plan**, each with its own plan to follow:
§9 theme coordination and the `ui/` split (stage 2), §6 the command line (stage 3),
§7 the drawers (stage 4), §8 the calendar and `range_entries` (stage 5), §10.4–10.6 the
classifier (stage 6).

**Not yet covered by any plan and not forgotten:** §13.4, making `setup` idempotent,
belongs with stage 6, where the model download it must be idempotent about is introduced.

**Type consistency.** `_history_days` and `Model.clampHistory` agree on 92/90.
`Logger.write` is reached only through `_log`. `applySummaryDelta` and `blockSummary`
return the same four keys. `_activitywatch_day` gains its third parameter in Task 6 and
has exactly one caller. `apps` changes shape in Task 5 and has no consumer in `Panel.qml`
today.

**Open risk to watch during Task 7.** The `since` merge assumes `server_deleted_at`
marks deletions, which is present in the confirmed `meta=true` field list but has not been
observed carrying a value. If the second-sync test cannot be made to pass against a real
response, fall back to the windowed fetch and note it — a correct full fetch beats a fast
wrong one.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-04-stage-0-1-tooling-and-backend.md`.
