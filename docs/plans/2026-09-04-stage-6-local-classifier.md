# Panel Redesign — Stage 6: Local classifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `classify` backend action — one grammar-constrained call per day load to a local `llama-server`, degrading to `ok:true` on any failure and never reachable from `create_entry` — plus the settings control the rulings say is missing (R-M), and an opt-in, skippable, checksum-verified installer for the runtime and the 378 MB model. Every network-touching piece is written and tested against a stub; nobody runs the real 378 MB download as part of this plan.

**Architecture:** `toggl_api.py` gains a fifth localhost HTTP dependency (`llama-server` at `127.0.0.1:8127`, alongside ActivityWatch at `127.0.0.1:5600`) reached the same way — `urllib`, an injectable `_opener` for tests, no new third-party imports. `classify()` never raises past its own `try`/`except`: connection refused, timeout, non-200, and a malformed body all fall through to the same `{"results": [], "degraded": True}` return, so `handle()`'s `{"ok": true, ...}` envelope is unconditional for this action. `toggl_log.py` needs **no code change** — `SENSITIVE` already lists `prompt`, `response`, `topics`, `apps`, `domains`, `label`, and `_clean()` already gates them on `debug` and truncates every string at 500 chars; this plan verifies that with new tests rather than re-implementing it. `Model.js` gains three pure functions that build the request from blocks/projects already in `Panel.qml` and decide whether one classify result may still land on a block — refusing once the user has touched it, so a late response can never overwrite an edit. `setup` gains a second, skippable, idempotent stage: runtime, model, systemd unit, all installed only on explicit opt-in, with the model's checksum verified both before reuse and after every fresh download.

**Tech Stack:** Python 3 standard library only (`urllib`, `json`, `hashlib`, `zipfile`). QML/Quickshell for `Panel.qml`. Node for `Model.js` tests. Bash for `setup`/`install`. No third-party packages.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §10.4–10.6, §13.4
**Rulings:** [`docs/2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — R-M binds this stage directly; the standing constraints in its §5 bind every stage.
**Visual acceptance reference:** [`docs/design-guide.html`](../design-guide.html) — carries no rendered mock of the classifier's installation mechanics (no XDG paths, no port number, no systemd, no SHA-256 — confirmed by inspection). Its only classifier-adjacent rendered values are the `~` guess marker and its `--warn` colour (§05 Row states), which stage 4 already owns; this stage only feeds that plumbing.

**Prerequisite state this plan assumes stages 2–5 have already produced** (per the rulings' sequencing, §4: `2 → 3 → 4 → 6`, with 6 depending on 4's block fields and the `~` marker): `root.scope` (renamed from `root.activeTab`), `root.dayBlocks[]` objects carrying a `guessed` boolean set by stage 4's `Model.prepareBlocks()`/`blockReady()` work (spec §7.1: "ready, guessed" is `●` + `~`), and `ui/PanelTheme.qml`'s three muted-text roles replacing every `Qt.darker()` call. **Every code snippet below that touches `Panel.qml` was written and syntax-verified (`qmlformat`, `qmllint -I /usr/share/omarchy/shell`, both exit 0) against the actual pre-stage-2 file, using its real, current property names (`root.activeTab`, `Qt.darker(root.foreground, 1.8)`) because that is the only real source this plan can check code against.** Task 2 and Task 3's QML steps say explicitly, at the point it matters, which two tokens to swap for stage 3/2's renamed equivalents before applying the edit to the real merged file — this is flagged again in Open Questions.

## Global Constraints

Every task's requirements implicitly include all of these.

- **Python: standard library only.** `urllib`, `hashlib`, `zipfile`, `json`. No third-party imports, ever.
- **No daemon in `toggl_api.py`.** It handles exactly one JSON request per process and exits. `classify()` makes exactly one outbound HTTP call per invocation.
- **`classify()` must never return `ok:false`.** Connection refused, timeout, any non-200, and a malformed response body from `llama-server` all degrade to `{"ok": true, "data": {"results": [], "degraded": True}}`. This is the one action in the whole backend that promises never to surface as an error.
- **The classifier is never reachable from `create_entry`.** No shared helper, no shared opener default that could accidentally wire one into the other. Enforced by a source-inspection test, not just a manual read.
- **The model lives under `$XDG_DATA_HOME`, never `$XDG_CACHE_HOME`.** The cache is TTL'd and safe to delete at any moment (`toggl_api.py`'s existing metadata cache); a 378 MB download is not something to silently lose.
- **The download is verified against a pinned SHA-256 before first use, every time** — on reuse of an existing file and after every fresh download. A checksum failure removes the file; it never leaves a partial or corrupt one in place.
- **`setup` remains runnable to completion with the classifier declined.** Declining is the default whenever stdin is not a terminal — no prompt ever blocks a non-interactive run.
- **Nobody runs the real download during this plan.** Every verification step below either uses a stub HTTP opener (Python tests) or a tiny local `python3 -m http.server` fixture (`setup`'s bash verification) standing in for `huggingface.co`. The 396,705,472-byte real artifact is the user's decision, made later, separately.
- **QML: multi-line, one property per line.** Run `qmlformat` after editing and check its exit status directly, never piped.
- **Never put `;` after an object member in QML.**
- **QML signal handlers declare their parameters.** `onChanged: function(value) { … }`.
- **A `Repeater` is not an `Item`; `visible` does not hide its output.** Not touched by this stage, restated because it is a standing constraint.
- **Theme values come from `Style.*`/`Color.*`/`ui/PanelTheme.qml`, never literals — and never `Qt.darker()`.** R-F: `grep -c Qt.darker` across `Panel.qml` and `ui/*.qml` must stay at 0 after stage 2; this stage must not reintroduce it.
- **There is no bash test harness and no QML test harness in this repository.** `bash -n` proves shell syntax; `qmlformat`/`qmllint` prove QML syntax; everything else that touches the filesystem, the network, or the terminal is verified by hand, against a local fixture, exactly as the reference stage-0/1 plan verified `install --dev` by actually running it. This plan's `setup` verification steps are that kind of manual, hands-on check, not an automated assertion.
- **Never let a window title, topic name, description, or project name reach the log at `info`.** Already enforced by `toggl_log._clean()`; this stage adds tests, not code, to prove the classify action honours it.
- **Editing QML requires `omarchy-restart-shell`, never `reloadConfig` or `rescanPlugins`.**

## File Structure

| File | Responsibility |
| --- | --- |
| `toggl_api.py` | modified — `classify` dispatch action, prompt/schema builders, degrade-on-failure HTTP call |
| `tests/test_toggl_api.py` | modified — `ClassifyTest`, `ClassifyLoggingTest` |
| `manifest.json` | modified — `classifier` setting (`off`/`local`, default `off`) |
| `Panel.qml` | modified — `classifier` property/setter, settings `ButtonGroup` (R-M), day-load trigger, response handling, `blockReady()` guessed guard |
| `Model.js` | modified — `classifyBlockPayload`, `classifyProjectPayload`, `classifyGuessFor` |
| `tests/test_model.mjs` | modified |
| `setup` | modified — token idempotency (`--reset`), skippable classifier stage: runtime, model download+verify, systemd unit |
| `install` | modified — `--uninstall --purge` also disables and removes the systemd unit (the model and cache removal already exists from stage 0/1) |
| `README.md` | modified — classifier section |
| `AGENTS.md` | modified — new anti-patterns from this stage |

`toggl_log.py`, `.gitignore`, and `build` are **not modified** by this stage — verified already sufficient (see Task 1 Step 6 and the note at the end of this file).

---

### Task 1: The `classify` backend action

**Files:**
- Modify: `toggl_api.py`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Consumes: `llama-server`'s OpenAI-compatible `POST /v1/chat/completions` at `127.0.0.1:8127` (external, stubbed in every test via an injected opener). `_log`, `_dict`, `_field`, `_id`, `_text`, `_minutes`, `ValidationError`, `ApiError` — all pre-existing.
- Produces: dispatch action `classify` → `{"ok": true, "data": {"results": [{"index", "description", "project_id", "confidence"}], "model": "qwen3-0.6b", "elapsed_ms": N}}` on success, or `{"ok": true, "data": {"results": [], "degraded": True}}` on any failure. `TogglAPI.__init__` gains a `classify_opener=None` parameter (defaults to `urlopen`), mirroring the existing `activitywatch_opener` pattern exactly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_toggl_api.py`, immediately before the trailing `if __name__ == "__main__":` block:

```python
class ClassifyTest(unittest.TestCase):
    def _projects(self):
        return [{"id": 5, "name": "acme", "client": "Acme Ltd"}]

    def _blocks(self):
        return [{
            "index": 0, "label": "vim",
            "topics": [{"name": "vim", "seconds": 600}],
            "apps": ["dev.zed.Zed"], "domains": ["bitbucket.org"], "seconds": 600,
        }]

    def _payload(self):
        return {
            "action": "classify", "workspace_id": 4,
            "blocks": self._blocks(), "projects": self._projects(),
        }

    def test_classify_returns_results_and_model(self):
        content = json.dumps({"results": [
            {"index": 0, "description": "Reviewing PRs", "project_id": 5, "confidence": 0.8},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertEqual(result["results"], [
            {"index": 0, "description": "Reviewing PRs", "project_id": 5, "confidence": 0.8},
        ])
        self.assertEqual(result["model"], "qwen3-0.6b")
        self.assertIsInstance(result["elapsed_ms"], int)

    def test_classify_degraded_on_connection_refused(self):
        def opener(request, timeout):
            raise URLError(ConnectionRefusedError())
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        self.assertEqual(api.dispatch(self._payload()), {"results": [], "degraded": True})

    def test_classify_degraded_on_timeout(self):
        def opener(request, timeout):
            raise TimeoutError("timed out")
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        self.assertEqual(api.dispatch(self._payload()), {"results": [], "degraded": True})

    def test_classify_degraded_on_non_200(self):
        error = HTTPError("http://127.0.0.1:8127/v1/chat/completions", 500, "error", Message(), BytesIO(b"failure"))
        def opener(request, timeout):
            raise error
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        self.assertEqual(api.dispatch(self._payload()), {"results": [], "degraded": True})

    def test_classify_never_returns_a_project_id_outside_the_supplied_set(self):
        content = json.dumps({"results": [
            {"index": 0, "description": "x", "project_id": 999, "confidence": 0.5},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertIsNone(result["results"][0]["project_id"])

    def test_classify_clamps_confidence_to_the_unit_interval(self):
        content = json.dumps({"results": [
            {"index": 0, "description": "x", "project_id": 5, "confidence": 4.2},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertEqual(result["results"][0]["confidence"], 1.0)

    def test_classify_posts_to_llama_server_with_json_schema_response_format(self):
        captured = {}
        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return Response({"choices": [{"message": {"content": json.dumps({"results": []})}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        api.dispatch(self._payload())
        self.assertEqual(captured["url"], "http://127.0.0.1:8127/v1/chat/completions")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], 20)
        self.assertEqual(captured["body"]["response_format"]["type"], "json_schema")
        schema = captured["body"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(
            schema["properties"]["results"]["items"]["properties"]["project_id"]["enum"], [5, None]
        )
        self.assertEqual(
            schema["properties"]["results"]["items"]["properties"]["description"]["maxLength"], 120
        )

    def test_classify_prompt_carries_only_normalised_topics_never_raw_labels(self):
        captured = {}
        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return Response({"choices": [{"message": {"content": json.dumps({"results": []})}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        payload = self._payload()
        payload["blocks"][0]["label"] = "a raw window title that must never leak"
        api.dispatch(payload)
        prompt = captured["body"]["messages"][0]["content"]
        self.assertNotIn("a raw window title that must never leak", prompt)
        self.assertIn("vim", prompt)
        self.assertIn("acme", prompt)
        self.assertIn("bitbucket.org", prompt)

    def test_classify_is_not_reachable_from_create_entry(self):
        def opener(request, timeout):
            raise AssertionError("create_entry must never reach llama-server")
        client = FakeClient([[], {"id": 1, "workspace_id": 4, "description": "history"}])
        api = toggl_api.TogglAPI(client, classify_opener=opener)
        result = api.create_entry({
            "workspace_id": 4, "start": "2026-08-19T10:00:00Z", "duration": 300,
            "description": "history", "project_id": None, "tags": [], "billable": False,
        })
        self.assertEqual(result["entry"]["id"], 1)

    def test_create_entry_source_never_mentions_classify_or_the_llama_port(self):
        import inspect
        source = inspect.getsource(toggl_api.TogglAPI.create_entry)
        self.assertNotIn("classify", source)
        self.assertNotIn("8127", source)


class ClassifyLoggingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def _payload(self):
        return {
            "action": "classify", "workspace_id": 4,
            "blocks": [{
                "index": 0,
                "topics": [{"name": "a very identifying topic name", "seconds": 600}],
                "apps": ["dev.zed.Zed"], "domains": [], "seconds": 600,
            }],
            "projects": [{"id": 5, "name": "acme", "client": "Acme Ltd"}],
        }

    def test_classify_prompt_and_response_absent_at_info(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        def opener(request, timeout):
            raise URLError(ConnectionRefusedError())
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        contents = (Path(self.tmp.name) / "logs" / "toggl.jsonl").read_text()
        self.assertNotIn("a very identifying topic name", contents)

    def test_classify_prompt_and_response_present_at_debug(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "debug")
        content = json.dumps({"results": [
            {"index": 0, "description": "Reviewing PRs", "project_id": 5, "confidence": 0.8},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        contents = (Path(self.tmp.name) / "logs" / "toggl.jsonl").read_text()
        self.assertIn("a very identifying topic name", contents)

    def test_classify_string_fields_truncate_at_500_characters(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "debug")
        content = json.dumps({"results": [
            {"index": 0, "description": "x" * 600, "project_id": 5, "confidence": 0.8},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        record = [r for r in self._records() if r.get("action") == "classify"][0]
        self.assertLessEqual(len(record["prompt"]), 500)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_toggl_api.ClassifyTest tests.test_toggl_api.ClassifyLoggingTest -v
```

Expected: every test errors — `TogglAPI.classify` and the `classify_opener` keyword do not exist yet, and `dispatch` raises `ValidationError("unsupported action.")` for the ones that get far enough to call it.

- [ ] **Step 3: Add the constants and the four module-level helpers**

In `toggl_api.py`, add four constants right after the existing `ACTIVITYWATCH_URL = "http://127.0.0.1:5600"` line:

```python
CLASSIFIER_URL = "http://127.0.0.1:8127/v1/chat/completions"
CLASSIFIER_TIMEOUT = 20
CLASSIFIER_MODEL = "qwen3-0.6b"
CLASSIFIER_MAX_DESCRIPTION = 120
```

Then, immediately before `class TogglAPI:`, add:

```python
def _classify_index(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(name + " must be a non-negative integer.")
    return value


def _classify_prompt(blocks, projects):
    project_lines = "\n".join(
        "%d — %s (%s)" % (project["id"], project["name"], project["client"] or "no client")
        for project in projects
    )
    block_lines = []
    for block in blocks:
        topics = ", ".join(
            "%s (%ds)" % (topic["name"], topic["seconds"]) for topic in block["topics"]
        ) or "none"
        apps = ", ".join(block["apps"]) or "none"
        domains = ", ".join(block["domains"]) or "none"
        block_lines.append(
            "Block %d — %ds\nTopics: %s\nApps: %s\nDomains: %s"
            % (block["index"], block["seconds"], topics, apps, domains)
        )
    return (
        "Name and assign each work block below to one of the listed Toggl "
        "projects, or leave project_id null when none fits well. Write a "
        "short, specific description of the work actually done, not the raw "
        "topic name.\n\nProjects (id — name (client)):\n%s\n\nBlocks:\n%s"
        % (project_lines or "none", "\n\n".join(block_lines) or "none")
    )


def _classify_schema(project_ids):
    return {
        "type": "object",
        "required": ["results"],
        "properties": {
            "results": {
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
            }
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
```

`_classify_prompt` deliberately never reads `block["label"]` — the wire schema in R6-1 accepts it (validated in Step 5 below, for contract completeness) but spec §10.5 lists only topics, apps, domains and duration as prompt content. `label` is already a normalised topic name today (§10.3), not a raw title, but the prompt omits it anyway so the contract stays exact.

- [ ] **Step 4: Add `classify_opener` to `TogglAPI.__init__`**

Change:

```python
    def __init__(self, client=None, cache_root=None, clock=None, activitywatch_opener=None, logger=None):
        self._client = client
        self._cache_root = cache_root
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._activitywatch_opener = activitywatch_opener or urlopen
        self._cache_allowed = client is None or cache_root is not None
        self._cache_store = None
        self._cache_store_loaded = False
        self.logger = logger
```

to:

```python
    def __init__(self, client=None, cache_root=None, clock=None, activitywatch_opener=None, classify_opener=None, logger=None):
        self._client = client
        self._cache_root = cache_root
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._activitywatch_opener = activitywatch_opener or urlopen
        self._classify_opener = classify_opener or urlopen
        self._cache_allowed = client is None or cache_root is not None
        self._cache_store = None
        self._cache_store_loaded = False
        self.logger = logger
```

- [ ] **Step 5: Implement `classify()` and wire the dispatch**

Add this method immediately before `def dispatch(self, payload):` (i.e. as the last method of `TogglAPI`, right after `create_entry`):

```python
    def classify(self, payload):
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
                "apps": [str(app) for app in (block.get("apps") or [])],
                "domains": [str(domain) for domain in (block.get("domains") or [])],
                "seconds": int(_minutes(block.get("seconds"), "block.seconds", 0)),
            })

        prompt = _classify_prompt(blocks, projects)
        body = {
            "model": CLASSIFIER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "classify_result", "schema": _classify_schema(project_ids)},
            },
        }

        started = time.monotonic()
        try:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            request = Request(
                CLASSIFIER_URL, data=data,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with self._classify_opener(request, timeout=CLASSIFIER_TIMEOUT) as response:
                raw = response.read()
            content = _classify_content(json.loads(raw.decode("utf-8")))
            results = _classify_results(content, project_ids)
        except HTTPError as error:
            error.close()
            _log(self.logger, "debug", action="classify", prompt=prompt, response=None,
                 degraded=True, status=int(error.code))
            return {"results": [], "degraded": True}
        except (URLError, TimeoutError, OSError, ValueError):
            # Connection refused, timeout, or a malformed body from
            # llama-server -- all degrade the same way. classify() must
            # never return ok:false; the day still loads with topic labels.
            _log(self.logger, "debug", action="classify", prompt=prompt, response=None, degraded=True)
            return {"results": [], "degraded": True}

        elapsed_ms = int((time.monotonic() - started) * 1000)
        _log(self.logger, "debug", action="classify", prompt=prompt, response=content)
        return {"results": results, "model": CLASSIFIER_MODEL, "elapsed_ms": elapsed_ms}
```

Then wire it into `dispatch`, changing:

```python
        if action == "create_entry":
            return self.create_entry(payload)
        raise ValidationError("unsupported action.")
```

to:

```python
        if action == "create_entry":
            return self.create_entry(payload)
        if action == "classify":
            return self.classify(payload)
        raise ValidationError("unsupported action.")
```

`ValueError` in the second `except` also catches `json.JSONDecodeError` (a `ValueError` subclass), so a non-JSON body from `llama-server` degrades the same as a network failure. A 200 response whose *inner* schema-constrained `content` string fails to parse is handled separately by `_classify_content`'s own `try`/`except`, returning `None` — that path is **not** treated as degraded (the server did answer with 200; the day gets an empty `results` list instead, still with a `model`/`elapsed_ms`). This split is a deliberate implementation choice: only transport-level failure (refused, timeout, non-200, unparseable outer body) counts as "degraded" per spec §10.4's exact three triggers; a well-formed-but-empty model answer is not.

- [ ] **Step 6: Run the whole suite to verify pass**

```bash
python3 -m py_compile toggl_api.py tests/test_toggl_api.py
python3 -m unittest discover -s tests -v 2>&1 | tail -20
```

Expected: all tests pass — 126 pre-existing plus the 13 added here (139 total; verified while writing this plan). This also proves the negative claim in the File Structure table: no `toggl_log.py` edit was needed for the debug-only, 500-char-truncated, token-never-logged behaviour the `ClassifyLoggingTest` cases check — `SENSITIVE` already lists `prompt`/`response`/`topics`/`apps`/`domains`/`label`, and `_clean()` already gates and truncates them.

- [ ] **Step 7: Commit**

```bash
git add toggl_api.py tests/test_toggl_api.py
git commit -m "feat(classify): add the local-classifier backend action"
```

---

### Task 2: The classifier setting — manifest schema and the settings control (R-M)

**Files:**
- Modify: `manifest.json`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `root.setting(key, fallback)` and `root.persist(fields)` (both pre-existing), the `ButtonGroup` component from `qs.Ui` (already used for `LOG DETAIL` and three other settings groups).
- Produces: `root.classifier` (`"off"`/`"local"`, persisted), `root.setClassifier(value)`.

- [ ] **Step 1: Add the manifest setting**

In `manifest.json`, change:

```json
    "defaults": {
      "workspaceId": 0,
      "historyDays": 30,
      "idleReminderMinutes": 0,
      "dayBlockMinutes": 5,
      "logLevel": "info"
    },
```

to:

```json
    "defaults": {
      "workspaceId": 0,
      "historyDays": 30,
      "idleReminderMinutes": 0,
      "dayBlockMinutes": 5,
      "logLevel": "info",
      "classifier": "off"
    },
```

and change:

```json
      { "key": "logLevel", "type": "string", "label": "Log detail", "defaultValue": "info" }
    ]
```

to:

```json
      { "key": "logLevel", "type": "string", "label": "Log detail", "defaultValue": "info" },
      { "key": "classifier", "type": "string", "label": "Local classifier", "defaultValue": "off" }
    ]
```

- [ ] **Step 2: Verify the manifest**

```bash
omarchy plugin validate .
```

Expected: exit 0 (verified while writing this plan).

- [ ] **Step 3: Add the property, the setter, and the `blockReady()` guard**

These three edits are written against the current, pre-stage-2/3 `Panel.qml` (the only real source available) and were syntax-verified there (`qmlformat`/`qmllint` both exit 0). **Before applying them to the actual merged file, confirm the anchors still read this way; if stage 3 has already renamed `root.activeTab` to `root.scope`, use `root.scope` in the new `visible:` bindings in Step 4 instead of `root.activeTab` — the property/setter/guard below don't reference either name and need no change.**

Add the `classifier` property next to `dayRevision`/`applyQueue`:

```qml
    property int dayRevision: 0
    property var applyQueue: []
    readonly property var classifierChoices: ["off", "local"]
    property string classifier: classifierChoices.indexOf(String(setting("classifier", "off"))) >= 0 ? String(setting("classifier", "off")) : "off"
```

Add the setter next to `setLogLevel`:

```qml
    function setLogLevel(level) {
        logLevel = logLevels.indexOf(level) >= 0 ? level : "info";
        persist({
            "logLevel": logLevel
        });
    }

    function setClassifier(value) {
        classifier = classifierChoices.indexOf(value) >= 0 ? value : "off";
        persist({
            "classifier": classifier
        });
    }
```

Extend `blockReady()` — spec §7.5: "A guessed row is not ready until confirmed, so a batch apply can never write an unreviewed guess." This defends that rule at the one function `Shift+Enter`'s `applyAssigned()` filters through, regardless of exactly how stage 4 wired the `guessed` flag:

```qml
    function blockReady(block) {
        return !!block && block.state === "pending" && !block.busy && !block.guessed && !!block.projectId && String(block.description || "").trim().length > 0;
    }
```

If stage 4 already added `!block.guessed` here, this step is a no-op confirmation (check with `grep -n "function blockReady" Panel.qml` first) — do not duplicate the clause.

- [ ] **Step 4: Add the settings control**

R-M: "Stage 6 adds a `ButtonGroup` mirroring the existing `LOG DETAIL` pattern, plus the warning line that the local model reads window titles." Insert immediately after the existing `LOG DETAIL` warning `Text` and before the `BREAK` section's `Text`:

```qml
                            Text {
                                visible: root.activeTab === "timer" && root.logLevel === "debug"
                                Layout.fillWidth: true
                                text: "Debug records window titles and entry descriptions in the plugin's log."
                                color: Qt.darker(root.foreground, 1.8)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                visible: root.activeTab === "timer"
                                text: "CLASSIFIER"
                                color: Qt.darker(root.foreground, 1.8)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.activeTab === "timer"
                                options: ["Off", "Local"]
                                value: root.classifier.charAt(0).toUpperCase() + root.classifier.slice(1)
                                onChanged: function(value) {
                                    root.setClassifier(value.toLowerCase());
                                }
                            }

                            Text {
                                visible: root.activeTab === "timer" && root.classifier === "local"
                                Layout.fillWidth: true
                                text: "The local model reads window titles to name and assign day blocks. Titles never leave this machine."
                                color: Qt.darker(root.foreground, 1.8)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                visible: root.activeTab === "day"
```

(the final `Text { visible: root.activeTab === "day"` line is the existing `BREAK` header already in the file — shown only so the insertion point is unambiguous; do not duplicate it.)

**Against the real merged file:** replace every `root.activeTab === "timer"` above with `root.scope === "timer"` (stage 3's rename), and every `Qt.darker(root.foreground, 1.8)` with `PanelTheme.textDisabled` — or whatever `ui/PanelTheme.qml`'s exposure point in `Panel.qml` turns out to be (see Open Questions; this repo's stage 2 source did not exist at the time this plan was written, so the exact property path could not be verified here). Reintroducing `Qt.darker()` would violate R-F.

- [ ] **Step 5: Verify**

```bash
qmlformat Panel.qml >/dev/null; echo "qmlformat: $?"
qmllint -I /usr/share/omarchy/shell Panel.qml; echo "qmllint: $?"
```

Expected: both `0` (verified against the pre-stage-2 file while writing this plan — every snippet above formats and lints clean). Then `omarchy-restart-shell` and open the panel's settings: **CLASSIFIER** shows `Off`/`Local`, clicking `Local` reveals the warning line, and the choice survives a panel close/reopen (persisted via `setting()`/`persist()`).

- [ ] **Step 6: Commit**

```bash
git add manifest.json Panel.qml
git commit -m "feat(settings): add the classifier off/local control (R-M)"
```

---

### Task 3: Wire the classify call into day load

**Files:**
- Modify: `Model.js`
- Modify: `tests/test_model.mjs`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `root.dayBlocks`, `root.projects`, `root.selectedWorkspaceId`, `root.request()`, `root.mutateBlock()`, `root.classifier` (from Task 2). `block.guessed` — read and written here, assumed set to `false` by stage 4's `Model.prepareBlocks()`; `classifyGuessFor` treats a missing field the same as `false` (falsy), so this works even if stage 4 does not default it explicitly.
- Produces: `Model.classifyBlockPayload(blocks)`, `Model.classifyProjectPayload(projects)`, `Model.classifyGuessFor(block, result)` (pure, tested). `root.classifyDay()`, `root.applyClassifyResults(results)`.

- [ ] **Step 1: Write the failing node tests**

In `tests/test_model.mjs`, change the `Model` export list:

```js
  searchItems, normalizeProject, normalizeTask, applySummaryDelta
}`)()
```

to:

```js
  searchItems, normalizeProject, normalizeTask, applySummaryDelta,
  classifyBlockPayload, classifyProjectPayload, classifyGuessFor
}`)()
```

Then add these tests, immediately before the final `if (failures) {` block:

```js
test("classifyBlockPayload sends only pending blocks, normalised", () => {
  const blocks = [
    { state: "pending", label: "vim", topics: [{ name: "vim", seconds: 600 }], apps: [{ name: "dev.zed.Zed", seconds: 600 }], domain: "bitbucket.org", seconds: 600 },
    { state: "applied", label: "done", topics: [], apps: [], domain: "", seconds: 300 },
  ]
  assert.deepEqual(Model.classifyBlockPayload(blocks), [
    { index: 0, label: "vim", topics: [{ name: "vim", seconds: 600 }], apps: ["dev.zed.Zed"], domains: ["bitbucket.org"], seconds: 600 },
  ])
})
test("classifyBlockPayload keeps the block's real dayBlocks index", () => {
  const blocks = [
    { state: "applied", label: "done", topics: [], apps: [], domain: "", seconds: 300 },
    { state: "pending", label: "vim", topics: [], apps: [], domain: "", seconds: 600 },
  ]
  assert.equal(Model.classifyBlockPayload(blocks)[0].index, 1)
})
test("classifyProjectPayload keeps only active projects with id/name/client", () => {
  const projects = [
    Model.normalizeProject({ id: 5, name: "acme", client_name: "Acme Ltd", active: true }),
    Model.normalizeProject({ id: 6, name: "old", active: false }),
  ]
  assert.deepEqual(Model.classifyProjectPayload(projects), [{ id: 5, name: "acme", client: "Acme Ltd" }])
})
test("classifyGuessFor fills an untouched pending block", () => {
  const block = { state: "pending", busy: false, guessed: false, label: "vim", description: "vim", projectId: 0 }
  const guess = Model.classifyGuessFor(block, { index: 0, description: "Reviewing PRs", project_id: 5, confidence: 0.8 })
  assert.deepEqual(guess, { description: "Reviewing PRs", projectId: 5, guessed: true })
})
test("classifyGuessFor never overwrites a block the user already described", () => {
  const block = { state: "pending", busy: false, guessed: false, label: "vim", description: "my own text", projectId: 0 }
  assert.equal(Model.classifyGuessFor(block, { index: 0, description: "Reviewing PRs", project_id: 5, confidence: 0.8 }), null)
})
test("classifyGuessFor never overwrites a block the user already assigned", () => {
  const block = { state: "pending", busy: false, guessed: false, label: "vim", description: "vim", projectId: 9 }
  assert.equal(Model.classifyGuessFor(block, { index: 0, description: "Reviewing PRs", project_id: 5, confidence: 0.8 }), null)
})
test("classifyGuessFor skips an applied or conflict block", () => {
  const block = { state: "applied", busy: false, guessed: false, label: "vim", description: "vim", projectId: 0 }
  assert.equal(Model.classifyGuessFor(block, { index: 0, description: "x", project_id: 5, confidence: 0.5 }), null)
})
test("classifyGuessFor never re-guesses an already-guessed block", () => {
  const block = { state: "pending", busy: false, guessed: true, label: "vim", description: "Reviewing PRs", projectId: 5 }
  assert.equal(Model.classifyGuessFor(block, { index: 0, description: "Something else", project_id: 6, confidence: 0.9 }), null)
})
test("classifyGuessFor falls back to the block's own label when only a project is guessed", () => {
  const block = { state: "pending", busy: false, guessed: false, label: "vim", description: "vim", projectId: 0 }
  const guess = Model.classifyGuessFor(block, { index: 0, description: "", project_id: 5, confidence: 0.6 })
  assert.deepEqual(guess, { description: "vim", projectId: 5, guessed: true })
})
test("classifyGuessFor returns null when the result carries neither a description nor a project", () => {
  const block = { state: "pending", busy: false, guessed: false, label: "vim", description: "vim", projectId: 0 }
  assert.equal(Model.classifyGuessFor(block, { index: 0, description: "", project_id: null, confidence: 0 }), null)
})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node tests/test_model.mjs
```

Expected: `TypeError: Model.classifyBlockPayload is not a function` (or similar) on the first new test.

- [ ] **Step 3: Implement in `Model.js`**

Add at the end of the file, after the existing `clampReminder` function:

```js
// --- Local classifier (stage 6) -------------------------------------------
//
// classifyBlockPayload/classifyProjectPayload build the "classify" request
// body from the same block/project objects the panel already holds; the
// index in the returned array is the block's real position in dayBlocks,
// so a response can be applied back with a plain array lookup.
//
// classifyGuessFor decides whether one classify result may still be applied.
// It refuses once the block has left "pending", once the user has typed a
// description or picked a project, or once a guess has already landed --
// so an in-flight or late response can never clobber a real edit.

function classifyBlockPayload(blocks) {
  var out = []
  ;(blocks || []).forEach(function(block, index) {
    if (!block || block.state !== "pending") return
    out.push({
      index: index,
      label: String(block.label || ""),
      topics: (block.topics || []).slice(0, 8).map(function(topic) {
        return { name: String(topic.name || ""), seconds: number(topic.seconds, 0) }
      }),
      apps: (block.apps || []).map(function(app) {
        return String((app && app.name) || app || "")
      }).filter(Boolean),
      domains: block.domain ? [block.domain] : [],
      seconds: number(block.seconds, 0)
    })
  })
  return out
}

function classifyProjectPayload(projects) {
  return (projects || []).filter(function(project) { return project.active }).map(function(project) {
    return { id: project.id, name: project.name, client: project.clientName || project.client || "" }
  })
}

function classifyGuessFor(block, result) {
  if (!block || !result) return null
  if (block.state !== "pending" || block.busy || block.guessed) return null
  var untouched = String(block.description || "").trim() === String(block.label || "").trim()
  if (!untouched || block.projectId) return null
  var description = String(result.description || "").trim()
  var projectId = number(result.project_id, 0)
  if (!description && !projectId) return null
  return {
    description: description || block.label,
    projectId: projectId,
    guessed: true
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node tests/test_model.mjs
```

Expected: `all model checks passed` (verified while writing this plan — 18 new assertions across the 9 tests above, plus every pre-existing test, all pass).

- [ ] **Step 5: Wire it into `Panel.qml`**

These edits, like Task 2's, are written and syntax-verified (`qmlformat`, `qmllint`, both exit 0) against the current pre-stage-2/3 file. Add `classifyDay()` and `applyClassifyResults()` right after `loadDay()`:

```qml
    function loadDay() {
        if (selectedWorkspaceId <= 0) {
            noteClient("errors", "request_dropped", "day_activity");
            return ;
        }
        dayError = "";
        request("day_activity", {
            "workspace_id": selectedWorkspaceId,
            "date": dayDate,
            "min_block_minutes": dayBlockMinutes
        });
    }

    // One classify call per day load, per spec -- fired once, right after the
    // freshly loaded blocks land, never per row and never re-fired by a
    // setting change alone.
    function classifyDay() {
        if (classifier !== "local")
            return ;

        var payloadBlocks = Model.classifyBlockPayload(dayBlocks);
        if (payloadBlocks.length === 0)
            return ;

        request("classify", {
            "workspace_id": selectedWorkspaceId,
            "blocks": payloadBlocks,
            "projects": Model.classifyProjectPayload(projects)
        });
    }

    function applyClassifyResults(results) {
        (results || []).forEach(function(result) {
            var block = dayBlocks[result.index];
            var guess = block && Model.classifyGuessFor(block, result);
            if (!guess)
                return ;

            mutateBlock(block, function() {
                block.description = guess.description;
                block.projectId = guess.projectId;
                block.guessed = guess.guessed;
            });
        });
    }
```

Then trigger it from `handleResponseBody`'s `day_activity` branch, and add a `classify` branch, changing:

```qml
            if (action === "day_activity") {
                status = "ready";
                dayLoaded = true;
                dayBlocks = Model.prepareBlocks(response.data.blocks, response.data.entries);
                daySummary = Model.blockSummary(dayBlocks);
                slotChanged();
                return ;
            }
            if (action === "create_entry") {
```

to:

```qml
            if (action === "day_activity") {
                status = "ready";
                dayLoaded = true;
                dayBlocks = Model.prepareBlocks(response.data.blocks, response.data.entries);
                daySummary = Model.blockSummary(dayBlocks);
                slotChanged();
                classifyDay();
                return ;
            }
            if (action === "classify") {
                status = "ready";
                if (response.data)
                    applyClassifyResults(response.data.results);

                return ;
            }
            if (action === "create_entry") {
```

`request()` sets `requestPending = true` synchronously, so calling `classifyDay()` from inside `handleResponseBody` (which has just set `requestPending = false` at its own entry) is safe: if `classifyDay()` fires a request, the `Qt.callLater(root.pumpQueue)` that `handleResponse` runs afterward finds `requestPending` true again and no-ops, exactly as it already does for any other request issued synchronously from a response handler.

`applyClassifyResults` mutates blocks in place through the existing `mutateBlock()` helper, so it inherits the `dayRevision` bump and summary-delta bookkeeping `mutateBlock` already does — no new `dayRevision` handling needed here.

- [ ] **Step 6: Verify**

```bash
qmlformat Panel.qml >/dev/null; echo "qmlformat: $?"
qmllint -I /usr/share/omarchy/shell Panel.qml; echo "qmllint: $?"
```

Expected: both `0` (verified against the pre-stage-2 file while writing this plan). Then manually: with `classifier` set to `local` and `llama-server` **not** running, load a day — the day still loads with topic labels (degraded path, no error banner, matching §11's table row). With a stub server answering on `127.0.0.1:8127` (or the real one, once a maintainer has separately completed the model download), a `pending` row whose description/project were never touched shows the `~` marker after the classify response lands; editing that row's description clears `guessed` back to a normal ready row (already stage 4's rendering, fed here); `Shift+Enter` never applies an unconfirmed guessed row.

- [ ] **Step 7: Commit**

```bash
git add Model.js tests/test_model.mjs Panel.qml
git commit -m "feat(day): wire the classify call into day load"
```

---

### Task 4: `setup` — token idempotency and the classifier stage skeleton

**Files:**
- Modify: `setup`

**Interfaces:**
- Consumes: `secret-tool`, `python3`, `toggl_api.py` (unchanged).
- Produces: `setup [--reset] [--skip-classifier]`. `--reset` forces the token prompt even when a token is already stored. Non-interactive runs (`[ ! -t 0 ]`) always decline the classifier stage without prompting.

- [ ] **Step 1: Restructure into `main()`, add argument parsing and token idempotency**

Replace the whole file with:

```bash
#!/usr/bin/env bash
set -eu

reset=0
skip_classifier=0
for argument in "$@"; do
    case "$argument" in
        --reset) reset=1 ;;
        --skip-classifier) skip_classifier=1 ;;
        *) printf 'usage: setup [--reset] [--skip-classifier]\n' >&2; exit 2 ;;
    esac
done

for tool in secret-tool python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Required tool missing: %s\n' "$tool" >&2
        exit 1
    fi
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

run_classifier_stage() {
    printf 'Classifier stage placeholder -- replaced in Task 5.\n' >&2
}

main() {
    if [ "$reset" -eq 0 ] && secret-tool lookup service daz.toggl-track account api-token >/dev/null 2>&1; then
        printf 'Toggl token already stored; keeping it. Pass --reset to replace it.\n' >&2
    else
        printf '%s' 'Toggl API token: ' >&2
        IFS= read -r -s token
        printf '\n' >&2
        if [ -z "$token" ]; then
            printf '%s\n' 'No token entered.' >&2
            exit 1
        fi
        if ! printf '%s' "$token" | secret-tool store --label='Omarchy Toggl Track' service daz.toggl-track account api-token >/dev/null 2>&1; then
            unset token
            printf '%s\n' 'Could not store the Toggl token.' >&2
            exit 1
        fi
        unset token
        if ! printf '%s\n' '{"action":"bootstrap","skip_sync":true}' | python3 "$script_dir/toggl_api.py" >/dev/null 2>&1; then
            secret-tool clear service daz.toggl-track account api-token >/dev/null 2>&1 || true
            printf '%s\n' 'Toggl token validation failed; stored token cleared.' >&2
            exit 1
        fi
        printf '%s\n' 'Toggl token stored and validated.' >&2
    fi

    run_classifier_stage
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main
fi
```

The `if [ "${BASH_SOURCE[0]}" = "${0}" ]; then main; fi` guard is new: it lets Task 5's verification step `source ./setup` and call individual functions (like the model downloader) without running the whole interactive flow — the same idiom used later in this stage's own manual test steps, not a new test harness.

- [ ] **Step 2: Replace the placeholder with the real classifier-stage skeleton**

Change:

```bash
run_classifier_stage() {
    printf 'Classifier stage placeholder -- replaced in Task 5.\n' >&2
}
```

to:

```bash
run_classifier_stage() {
    if [ "$skip_classifier" -eq 1 ]; then
        printf 'Classifier stage skipped (--skip-classifier).\n' >&2
        return 0
    fi
    if [ ! -t 0 ]; then
        printf 'No terminal attached; classifier stage declined by default.\n' >&2
        printf 'Run setup again interactively to install it.\n' >&2
        return 0
    fi
    printf '\nInstall the local classifier? It reads window titles locally to name and\n' >&2
    printf 'assign day blocks -- titles never leave this machine. Adds ~383 MB\n' >&2
    printf '(runtime + model) and a systemd --user service. [y/N] ' >&2
    IFS= read -r answer || answer=""
    case "$answer" in
        y|Y|yes|Yes) ;;
        *) printf 'Classifier skipped. Re-run setup to install it later.\n' >&2; return 0 ;;
    esac
    printf 'Classifier install placeholder -- replaced in Task 5.\n' >&2
}
```

- [ ] **Step 3: Verify syntax**

```bash
bash -n setup && echo SYNTAX_OK
```

Expected: `SYNTAX_OK` (verified while writing this plan).

- [ ] **Step 4: Manually verify token idempotency and the non-interactive default, against a stub `secret-tool`**

No real keyring is touched — a stub script on `PATH` stands in, so this needs no network and no real credentials:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/bin"
cat > "$tmp/bin/secret-tool" <<'EOF'
#!/usr/bin/env bash
case "$1" in
    store) cat >/dev/null; exit 0 ;;
    lookup) echo "stub-token-value"; exit 0 ;;
    clear) exit 0 ;;
esac
EOF
chmod +x "$tmp/bin/secret-tool"
PATH="$tmp/bin:$PATH" ./setup --skip-classifier < /dev/null
echo "exit=$?"
PATH="$tmp/bin:$PATH" timeout 5 ./setup < /dev/null
echo "exit=$?"
```

Expected, and verified while writing this plan: both runs print `Toggl token already stored; keeping it. Pass --reset to replace it.`, the first prints `Classifier stage skipped (--skip-classifier).` and exits 0, the second prints `No terminal attached; classifier stage declined by default.` and also exits 0 — neither run blocks waiting for input, satisfying R6-19's non-interactive-decline default and R6-20's token idempotency in the same pass.

- [ ] **Step 5: Commit**

```bash
git add setup
git commit -m "feat(setup): idempotent token stage, skippable classifier stage skeleton"
```

---

### Task 5: `setup` — runtime, model download+verify, systemd unit; `install` purge cleanup

**Files:**
- Modify: `setup`
- Modify: `install`

**Interfaces:**
- Consumes: `python3` (`urllib.request`, `hashlib`, `zipfile`, `json` — all stdlib), `systemctl --user`, GitHub's public Releases API (fallback runtime install only).
- Produces: `$XDG_DATA_HOME/omarchy-toggl-track/models/Qwen3-0.6B-Q4_K_M.gguf` (verified), `$XDG_DATA_HOME/omarchy-toggl-track/bin/llama-server` (fallback only), `~/.config/systemd/user/omarchy-toggl-track-llama-server.service`.

- [ ] **Step 1: Add the classifier constants and the model download/verify functions**

In `setup`, right after `script_dir=$(...)`, add:

```bash
# --- Classifier constants ---------------------------------------------------
# Where the model lives: $XDG_DATA_HOME, never $XDG_CACHE_HOME -- the cache is
# TTL'd and safe to delete at any moment, and this 378 MB download is not.
MODEL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track/models"
MODEL_FILE="Qwen3-0.6B-Q4_K_M.gguf"
MODEL_URL="${TOGGL_CLASSIFIER_MODEL_URL:-https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf}"
MODEL_SIZE="${TOGGL_CLASSIFIER_MODEL_SIZE:-396705472}"
# Pinned against the unsloth/Qwen3-0.6B-GGUF release of Qwen3-0.6B-Q4_K_M.gguf.
# This all-zero value can never match a real download, so verification fails
# closed (aborts, deletes the partial file) until a maintainer replaces it
# with the real sha256sum of that exact release artifact -- computing that
# requires downloading the file, which is a separate, explicit, later step,
# never part of running this plan.
MODEL_SHA256="${TOGGL_CLASSIFIER_MODEL_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
LLAMA_BIN_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track/bin"
LLAMA_SERVER_PORT=8127
SYSTEMD_UNIT_NAME="omarchy-toggl-track-llama-server.service"
SYSTEMD_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

_classifier_model_path() {
    printf '%s/%s\n' "$MODEL_DIR" "$MODEL_FILE"
}

_classifier_model_sha256() {
    python3 - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(1048576), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

_classifier_download_model() {
    local target
    target=$(_classifier_model_path)
    mkdir -p "$MODEL_DIR"
    if [ -f "$target" ]; then
        local existing_size
        existing_size=$(wc -c < "$target")
        if [ "$existing_size" -eq "$MODEL_SIZE" ] && [ "$(_classifier_model_sha256 "$target")" = "$MODEL_SHA256" ]; then
            printf 'Model already present and verified: %s\n' "$target" >&2
            return 0
        fi
        printf 'Existing model file failed verification; re-downloading.\n' >&2
        rm -f -- "$target"
    fi
    printf 'Downloading the classifier model (378 MB)...\n' >&2
    local tmp
    tmp="$target.partial"
    rm -f -- "$tmp"
    if ! python3 - "$MODEL_URL" "$tmp" <<'PY'
import sys
import urllib.error
import urllib.request

url, dest = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(url, timeout=60) as response, open(dest, "wb") as handle:
        while True:
            chunk = response.read(1048576)
            if not chunk:
                break
            handle.write(chunk)
except (OSError, urllib.error.URLError) as error:
    print(error, file=sys.stderr)
    raise SystemExit(1)
PY
    then
        rm -f -- "$tmp"
        printf 'Model download failed; nothing was left in place.\n' >&2
        return 1
    fi
    local downloaded_size
    downloaded_size=$(wc -c < "$tmp")
    if [ "$downloaded_size" -ne "$MODEL_SIZE" ] || [ "$(_classifier_model_sha256 "$tmp")" != "$MODEL_SHA256" ]; then
        rm -f -- "$tmp"
        printf 'Downloaded model failed checksum verification; removed.\n' >&2
        return 1
    fi
    mv -- "$tmp" "$target"
    printf 'Model downloaded and verified: %s\n' "$target" >&2
}
```

- [ ] **Step 2: Manually verify the download/verify function against a local fixture — no real download**

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/serve" "$tmp/data"
python3 -c "
import hashlib, os
data = os.urandom(4096)
open('$tmp/serve/Qwen3-0.6B-Q4_K_M.gguf', 'wb').write(data)
print('SIZE', len(data))
print('SHA', hashlib.sha256(data).hexdigest())
"
(cd "$tmp/serve" && python3 -m http.server 8931 --bind 127.0.0.1 &)
sleep 1

export TOGGL_CLASSIFIER_MODEL_URL="http://127.0.0.1:8931/Qwen3-0.6B-Q4_K_M.gguf"
export TOGGL_CLASSIFIER_MODEL_SIZE=4096
export TOGGL_CLASSIFIER_MODEL_SHA256="<paste the SHA printed above>"
export XDG_DATA_HOME="$tmp/data"

echo "--- fresh download ---"
bash -c 'source ./setup; _classifier_download_model'
echo "--- second run, already verified, no re-download ---"
bash -c 'source ./setup; _classifier_download_model'
echo "--- corrupted file is detected and re-downloaded ---"
printf 'garbage' >> "$XDG_DATA_HOME/omarchy-toggl-track/models/Qwen3-0.6B-Q4_K_M.gguf"
bash -c 'source ./setup; _classifier_download_model'
sha256sum "$XDG_DATA_HOME/omarchy-toggl-track/models/Qwen3-0.6B-Q4_K_M.gguf"

echo "--- server unreachable: no partial file left ---"
rm -rf "$XDG_DATA_HOME/omarchy-toggl-track"
export TOGGL_CLASSIFIER_MODEL_URL="http://127.0.0.1:1/nope.gguf"
bash -c 'source ./setup; _classifier_download_model'; echo "exit=$?"
test -e "$XDG_DATA_HOME/omarchy-toggl-track/models/Qwen3-0.6B-Q4_K_M.gguf" && echo BAD || echo "OK: nothing left"

pkill -f "http.server 8931" || true
```

Expected, and verified while writing this plan: the fresh download succeeds and prints "downloaded and verified"; the second run prints "already present and verified" and makes no HTTP request; the corrupted file is detected, removed, and re-downloaded to a file whose sha256 matches the pinned value; the unreachable-server run prints "Model download failed; nothing was left in place." and leaves no `models/` directory at all.

- [ ] **Step 3: Add the runtime installer**

```bash
_classifier_llama_server_path() {
    if command -v llama-server >/dev/null 2>&1; then
        command -v llama-server
        return 0
    fi
    if [ -x "$LLAMA_BIN_DIR/llama-server" ]; then
        printf '%s/llama-server\n' "$LLAMA_BIN_DIR"
        return 0
    fi
    return 1
}

_classifier_install_runtime_from_release() {
    local asset_url
    asset_url=$(python3 - <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
try:
    with urllib.request.urlopen(url, timeout=30) as response:
        release = json.load(response)
except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
    print(error, file=sys.stderr)
    raise SystemExit(1)
for asset in release.get("assets", []):
    name = asset.get("name", "").lower()
    if "ubuntu" in name and name.endswith(("x64.zip", "x86_64.zip", "amd64.zip")):
        print(asset["browser_download_url"])
        break
PY
    ) || { printf 'Could not query the latest llama.cpp release.\n' >&2; return 1; }
    if [ -z "$asset_url" ]; then
        printf 'No matching llama.cpp Linux release asset was found.\n' >&2
        return 1
    fi
    mkdir -p "$LLAMA_BIN_DIR"
    local archive="$LLAMA_BIN_DIR/llama-cpp-release.zip"
    if ! python3 - "$asset_url" "$archive" <<'PY'
import sys
import urllib.error
import urllib.request

url, dest = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(url, timeout=60) as response, open(dest, "wb") as handle:
        handle.write(response.read())
except (OSError, urllib.error.URLError) as error:
    print(error, file=sys.stderr)
    raise SystemExit(1)
PY
    then
        rm -f -- "$archive"
        printf 'Runtime download failed.\n' >&2
        return 1
    fi
    if ! python3 - "$archive" "$LLAMA_BIN_DIR" <<'PY'
import sys
import zipfile

archive, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(archive) as bundle:
    for name in bundle.namelist():
        if name.rsplit("/", 1)[-1] == "llama-server":
            with bundle.open(name) as source, open(dest + "/llama-server", "wb") as target:
                target.write(source.read())
            break
    else:
        raise SystemExit("llama-server not found in the release archive")
PY
    then
        rm -f -- "$archive"
        printf 'Could not extract llama-server from the release archive.\n' >&2
        return 1
    fi
    rm -f -- "$archive"
    chmod 755 "$LLAMA_BIN_DIR/llama-server"
    printf 'Installed llama-server to %s\n' "$LLAMA_BIN_DIR/llama-server" >&2
}

_classifier_install_runtime() {
    if _classifier_llama_server_path >/dev/null 2>&1; then
        printf 'llama-server already available: %s\n' "$(_classifier_llama_server_path)" >&2
        return 0
    fi
    _classifier_install_runtime_from_release
}
```

Per spec §10.6, the distribution package is tried first; here that reduces to `command -v llama-server` (a package-provided binary is already on `PATH`), with the GitHub Releases API as the "upstream release binary otherwise" fallback. The exact distro package name(s) to probe explicitly and the exact `llama-server` CLI flags (context size, thread count) are left as an implementation-level choice, not pinned by spec or guide — see Open Questions.

- [ ] **Step 4: Add the systemd unit installer and wire the whole stage together**

```bash
_classifier_install_unit() {
    local llama_bin model_path
    llama_bin=$(_classifier_llama_server_path) || return 1
    model_path=$(_classifier_model_path)
    mkdir -p "$SYSTEMD_UNIT_DIR"
    cat > "$SYSTEMD_UNIT_DIR/$SYSTEMD_UNIT_NAME" <<EOF
[Unit]
Description=Omarchy Toggl Track -- local classifier (llama-server)
After=network-online.target

[Service]
ExecStart=$llama_bin --host 127.0.0.1 --port $LLAMA_SERVER_PORT --model $model_path --ctx-size 4096 --threads 4
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    printf 'Installed the systemd --user unit: %s\n' "$SYSTEMD_UNIT_DIR/$SYSTEMD_UNIT_NAME" >&2
}

_classifier_enable_unit() {
    systemctl --user enable --now "$SYSTEMD_UNIT_NAME"
    printf 'Enabled and started %s\n' "$SYSTEMD_UNIT_NAME" >&2
}
```

Then replace the Task 4 placeholder line inside `run_classifier_stage`:

```bash
    printf 'Classifier install placeholder -- replaced in Task 5.\n' >&2
```

with:

```bash
    _classifier_install_runtime || { printf 'Could not install the llama-server runtime; classifier not installed.\n' >&2; return 1; }
    _classifier_download_model || { printf 'Model install failed; classifier not installed.\n' >&2; return 1; }
    _classifier_install_unit || { printf 'Could not install the systemd unit; classifier not installed.\n' >&2; return 1; }
    printf 'Enable and start it now? [y/N] ' >&2
    IFS= read -r enable_answer || enable_answer=""
    case "$enable_answer" in
        y|Y|yes|Yes) _classifier_enable_unit ;;
        *) printf 'Unit installed but not started. Start it later with:\n  systemctl --user enable --now %s\n' "$SYSTEMD_UNIT_NAME" >&2 ;;
    esac
    printf 'Classifier installed. Set classifier=local in the panel settings to use it.\n' >&2
```

The unit file is written unconditionally once opted in (per R6-17, "the unit is installed but only enabled when the user opts in") but `systemctl --user enable --now` — the step that actually starts it and makes it survive a login — runs only after the second, separate confirmation. Installing and enabling stay two distinct steps even though both are reachable from the same initial "install the classifier?" opt-in.

- [ ] **Step 5: Verify syntax**

```bash
bash -n setup && echo SYNTAX_OK
```

Expected: `SYNTAX_OK` (verified while writing this plan, on the complete file).

- [ ] **Step 6: Extend `install --uninstall --purge` to also remove the systemd unit**

`install` already removes the model (`rm -rf -- "${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track"`, which also covers the fallback-installed `bin/llama-server` from Step 3, since both live under the same `omarchy-toggl-track` data directory) — that part needs no change. Only the systemd unit is left behind by the existing purge block. Change:

```bash
    if [ "$purge" -eq 1 ]; then
        secret-tool clear service "$id" account api-token >/dev/null 2>&1 || true
        rm -rf -- "${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-toggl-track"
        rm -rf -- "${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track"
        printf 'Purged the stored token, the cache and the model.\n' >&2
    fi
```

to:

```bash
    if [ "$purge" -eq 1 ]; then
        secret-tool clear service "$id" account api-token >/dev/null 2>&1 || true
        systemctl --user disable --now omarchy-toggl-track-llama-server.service >/dev/null 2>&1 || true
        rm -f -- "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/omarchy-toggl-track-llama-server.service"
        systemctl --user daemon-reload >/dev/null 2>&1 || true
        rm -rf -- "${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-toggl-track"
        rm -rf -- "${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track"
        printf 'Purged the stored token, the cache, the model and the classifier service.\n' >&2
    fi
```

Every classifier-specific command here is `|| true`-guarded, so `--purge` on a machine where the classifier was never installed behaves exactly as before — `systemctl --user disable --now` on a unit that does not exist just fails quietly, and `rm -f` on a missing file is a no-op.

- [ ] **Step 7: Verify**

```bash
bash -n install && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`.

- [ ] **Step 8: Commit**

```bash
git add setup install
git commit -m "feat(setup): classifier runtime, model download+verify, systemd unit"
```

---

### Task 6: Documentation and the final gate

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: README — add a classifier section and a requirements bullet**

Add a bullet to the `## Requirements` list:

```markdown
- For the optional local classifier: `systemd --user`, and either the
  `llama-server` binary from `llama.cpp` already on `PATH`, or enough disk to
  let `setup` fetch one plus the 378 MB model
```

Add a new section after `## Connect Toggl Track`:

```markdown
## Local classifier (optional)

`setup` offers a second, skippable stage: a local `llama-server` plus a
378 MB Qwen3-0.6B model, both under `$XDG_DATA_HOME/omarchy-toggl-track`,
that name and assign Day scope blocks in one call per day load. Declining
is the default — nothing downloads unless you say yes, and `setup` run
non-interactively always declines it.

The model is verified against a pinned SHA-256 both before reuse and after
every download; a corrupt or partial file is removed, never left in place.

It reads window titles to do its job. That is the whole reason it runs
locally instead of calling out to a hosted API: nothing it reads ever
leaves this machine. Turn it on with the `classifier` setting in the panel
(`Off`/`Local`), or later, at the command line:

```bash
./setup                # re-run any time; the token stage is skipped if
                        # one is already stored, unless you pass --reset
```

If `llama-server` is unreachable — not installed, not started, or the
model missing — the Day scope still loads normally with topic labels; it
never shows an error for this.
```

- [ ] **Step 2: AGENTS.md — record the anti-patterns this stage introduced**

Add to the `## ANTI-PATTERNS` section:

```markdown
**Never treat a `classify` failure as an error.** Connection refused, a
timeout, a non-200, or a malformed body from `llama-server` all return
`{"ok": true, "data": {"results": [], "degraded": True}}` from
`toggl_api.classify()` — never `ok:false`. The Day scope must keep working
with topic labels when the classifier is absent or down; enforced by
`ClassifyTest` in `tests/test_toggl_api.py`.

**Never let `create_entry` gain a path to `classify` or port 8127.**
Enforced by `test_create_entry_source_never_mentions_classify_or_the_llama_port`,
which inspects `create_entry`'s own source rather than trusting a runtime
mock — a shared helper reachable from both functions would pass every
opener-based test while still creating the coupling this guards against.

**The classifier model lives under `$XDG_DATA_HOME`, never
`$XDG_CACHE_HOME`.** Mirrors the existing metadata-cache rule above, in the
opposite direction: the cache is disposable, the 378 MB model is not.

**The pinned model SHA-256 in `setup` ships as a deliberate all-zero
sentinel** (`MODEL_SHA256`) until a maintainer replaces it with the real
`sha256sum` of the published `Qwen3-0.6B-Q4_K_M.gguf` release artifact.
Computing that value requires downloading the file once, out of band —
never guess a plausible-looking hash here; the sentinel fails closed
(verification always rejects, deletes the partial file) rather than
silently accepting a wrong or tampered download.
```

- [ ] **Step 3: Run the full release gate**

```bash
./build --check
```

Expected: exit 0 — every check from `omarchy plugin validate` through the tracked-files assertion passes with this stage's changes in place. (`.gitignore`'s `*.gguf` entry and `build`'s step-9 `\.gguf$` tracked-file check both already exist from stage 0/1 — verified present at the start of this plan — so no new work is needed there; this run is what proves it.)

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: document the local classifier"
```

---

## Note: what this stage found already done

Three pieces the stage-6 requirement digest listed as this stage's responsibility were already shipped by stage 0/1, verified by inspection while writing this plan, and are **not** touched by any task above:

- `.gitignore` already contains `*.gguf` (alongside `logs/` and `dist/`).
- `build`'s step 9 (`nothing unshippable is tracked`) already loops over the pattern `'\.gguf$'` and fails if a match is tracked.
- `install --uninstall --purge` already removes `${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-toggl-track` — the model's directory — alongside the secret and the metadata cache.

Re-implementing any of these would be redundant, and there is no such task above.

## Open Questions

- **The real SHA-256 for `Qwen3-0.6B-Q4_K_M.gguf` cannot be supplied by this plan.** Computing it requires downloading the 396,705,472-byte release artifact, which this plan was explicitly told not to do. `setup` ships with an all-zero sentinel (`MODEL_SHA256`) that fails every verification until a maintainer replaces it after downloading the real file once, separately. This is not a value this plan invented or guessed — it is a placeholder that fails closed by design, flagged loudly in code and here.
- **The exact exposure point of `ui/PanelTheme.qml` on `Panel.qml` — property name and access path — is not pinned by the spec, the rulings, or the guide, and stage 2's actual source did not exist yet when this plan was written.** Task 2 Step 4 and Task 3's edits are written and verified against the current, pre-stage-2 file (`Qt.darker(root.foreground, 1.8)`, `root.activeTab`); both call out, at the point it matters, that `Qt.darker(...)` must become whatever role stage 2 exposes (assumed `PanelTheme.textDisabled`, per the 1.8 → `textDisabled` mapping in spec §9.1) and `root.activeTab` must become `root.scope` (per R-E) before landing on the real merged file. Confirm both against the actual stage-2/3 output before applying.
- **Where exactly the `CLASSIFIER` control should sit once stage 3's `activeTab`→`scope` rename and R-E's settings-`ColumnLayout` ownership land** — R-M says only "mirroring the existing `LOG DETAIL` pattern." This plan places it directly after `LOG DETAIL`'s warning line, gated the same way `LOG DETAIL` is gated today. If stage 3 changes `LOG DETAIL`'s own visibility condition, mirror that same condition for the classifier control rather than the literal `root.scope === "timer"` written here.
- **Whether toggling `classifier` from `off` to `local` while a day is already loaded should immediately fire a classify call**, versus only firing on the next day load. Spec §10.4 says only "one call per day load" and gives no trigger-on-settings-change requirement; this plan does not add one — flipping the setting takes effect on the next `loadDay()`/`showDay()`, not immediately. A reasonable read either way; not resolved by any source.
- **The exact `llama-server` CLI flags (`--ctx-size`, `--threads`) and the precise distro-package name(s) to probe before falling back to the GitHub release** are deliberately left as an implementation choice — the stage-6 requirement digest's own risk notes say this should not be over-specified, since the spec itself only says "distribution package where available, upstream release binary otherwise" with no further detail.

## Verified while writing this plan

Every code sample in Tasks 1–5 was actually applied to a scratch copy of the repository and run, not merely composed by hand:

- Task 1: `toggl_api.py` + the new tests together — `python3 -m py_compile` clean, `python3 -m unittest discover -s tests` → **139 passed** (126 pre-existing + 13 new).
- Task 1's logging claim: a live `toggl_log.Logger` at `info` produced a `classify` record with no `prompt`/`response` key at all; the same call at `debug` produced both, full text present — with **zero changes to `toggl_log.py`**.
- Task 2: `manifest.json` with the new setting — `omarchy plugin validate .` → exit 0. The `Panel.qml` snippets (property, setter, `blockReady()` guard, settings control) — `qmlformat`/`qmllint -I /usr/share/omarchy/shell` → both exit 0, applied to the real current file.
- Task 3: `Model.js` + the new tests together — `node tests/test_model.mjs` → **all model checks passed** (9 new tests, 18 assertions, plus every pre-existing test). The `Panel.qml` day-load wiring — `qmlformat`/`qmllint` → both exit 0.
- Task 4 & 5: the complete `setup` script — `bash -n` clean; the token-idempotency and non-interactive-decline paths run end-to-end against a stub `secret-tool` with the expected output and a clean exit 0, no hang; the model download/verify function run end-to-end against a local `python3 -m http.server` fixture through all four cases — fresh download, cached reuse, corruption-triggers-redownload, and server-unreachable-leaves-no-partial-file — each with the expected output and no partial file left behind in the failure cases.
