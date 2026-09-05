# Panel Redesign — Stage 2: Theme Coordination and the `ui/` Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every `Qt.darker(root.foreground, N)` call site in `Panel.qml` is gone, replaced by
three named roles on a new `ui/PanelTheme.qml`. The five theme defects of spec §9 (T1–T5) are
fixed. `Panel.qml` is split into `ui/TimerScope.qml`, `ui/DayScope.qml`, `ui/CalendarScope.qml`
(stub) and `ui/PanelTheme.qml`, each owning what spec §5's table assigns it, with `Panel.qml`
retaining state, `request()`, `handleResponse()`, the top toolbar and scope switching. No visual
redesign happens here — the timer and day tab bodies move unchanged in structure and behaviour,
only re-themed. Folded in from stage X: the `manifest.json` settings schema gains
`calendarRange`/`calendarDayStart`/`calendarDayEnd`/`classifier`, and `_http_message` stops
discarding Toggl's own 400 response body.

**Architecture:** No new runtime components. `Panel.qml` gains an `import "ui"` directory import
(the same mechanism already live in the shell itself — `plugins/notifications/Service.qml` does
`import "components"` with no `qmldir`, verified in `/usr/share/omarchy/shell`) and instantiates
one `PanelTheme` and two scope components (`TimerScope`, `DayScope`) as children of the existing
`ColumnLayout`. Every extracted scope file receives the enclosing panel as a plain
`required property var root` — named `root` on purpose, so every `root.xxx` reference already in
the moved QML keeps resolving without being rewritten — plus `required property var panelTheme`
for the three muted-text roles. `TimerScope.qml` additionally exposes five `property alias`
entries (`descriptionField`, `projectDropdown`, `taskDropdown`, `tagsField`, `searchDropdown`) so
the handful of `Panel.qml` functions that reach into the composer (`entryFields`, `selectProject`,
`selectTask`, `showEntry`, `loadComposer`) keep working through `timerScope.<name>`. The internal
`id:` on each of those five controls is renamed with an `Input`/`Field` suffix
(e.g. `id: descriptionInput`) so the alias name and the id name never collide — QML gives ids and
properties overlapping namespaces in one file, and declaring `property alias descriptionField:
descriptionField` where a sibling also carries `id: descriptionField` is not a risk worth taking
in a codebase where a bad parse produces zero diagnostic output.

**Tech Stack:** QML/Quickshell for `Panel.qml` and the new `ui/*.qml` files. Python 3 standard
library only for the `_http_message` fix. JSON for `manifest.json`. No Model.js changes — nothing
in this stage's scope touches pure-JS logic.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §5, §9
**Rulings (binding where they disagree with the spec):**
[`docs/2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — R-A, R-E, R-F, R-P
apply directly to this stage; R-D, R-B, R-C name work this stage must leave room for but not do.
**Visual acceptance reference:** [`docs/design-guide.html`](../design-guide.html) §06, §10

**Mechanical acceptance test (binding, per ruling R-F):**
`grep -c Qt.darker Panel.qml ui/*.qml` returns `0` after every task in this plan. Verified today:
23, not the 21 both the spec and the guide state — both documents are stale here; 23 is the
number this plan works against and the number Task 6 re-verifies against.

## Global Constraints

Every task's requirements implicitly include all of these.

- **No `;` after a QML object member.** `Item { Text {} ; Text {} }` is a parse error both
  `qmlformat` and `qmllint` report with **zero output**. If a new `ui/*.qml` file fails to parse
  silently, look for a stray `;` between sibling objects first.
- **Every QML signal handler declares its parameters.** `onChanged: function(value) { … }`, never
  the injected form. All handlers touched or added by this plan already use, or are written in,
  the formal form.
- **Check `qmlformat`'s exit status directly; never pipe it.** `qmllint x.qml | tail` returns
  *tail's* exit status and a broken file reads as green.
- **`BarWidget.qml` is exempt from both QML tools and is hand-reviewed.** It is not touched by
  this plan, but Task 6's acceptance check must still confirm `root.elapsedLabel` /
  `root.barLabel` — which it consumes — still render, since neither tool can catch a break there
  (ruling R-O).
- **A `Repeater` is not an `Item`; `visible` does not hide its output.** Unaffected by this plan's
  moves (the existing `model: blockRow.expanded ? … : []` gating in the day-block topic breakdown
  is carried over unchanged), stated here because two new component files are being written and
  the temptation to "clean up" a Repeater's visibility must be resisted.
- **`Style.cornerRadius` resolves to 0.** No radius literal is introduced anywhere in this plan.
  The one pre-existing `radius: 5` (the 9×9 project-colour dot in the recent-entries row) is a
  deliberate circular indicator, not a corner-rounding, and is carried over unchanged — it is not
  a `Style.cornerRadius` site and this plan does not touch it.
- **All sizes come from `Style.font.*` and `Style.spacing.*`; never literals.** This plan
  introduces no new literal pixel value. `Style.hoverFill`, used for T4, is a precomputed
  `Style.qml` property, not a literal.
- **Python: standard library only. No daemon.** The `_http_message` fix uses only `urllib.error`
  primitives already imported.
- **Never retry a mutation; never reuse `start`/`continue` for historical entries.** Unaffected —
  this stage touches no mutation path beyond reading one extra field off an already-raised
  `HTTPError`.
- **Editing QML requires `omarchy-restart-shell`, not a rescan.** `reloadConfig` keeps the
  plugin's `Loader` alive so an edit will not appear to have taken effect; `rescanPlugins` is not
  in this shell's IPC surface at all and exits 0 regardless. Task 6's manual check uses
  `omarchy-restart-shell` and then `qs -p /usr/share/omarchy/shell log`, watching for
  `qt.qml.context`.
- **There is no QML test harness in this repository.** `qmlformat` proves syntax and
  `omarchy plugin validate` proves the manifest; everything else — the border colour, the hover
  fill, the composer still working, `BarWidget.qml`'s bar label — is verified by restarting the
  shell and looking at it. Every task that touches QML ends with that manual check named
  explicitly, not implied.
- **`Style.hoverFill` / `Style.selectedFill` are computed from `Color.foreground`, not
  `Color.popups.text`** (verified: `/usr/share/omarchy/shell/Commons/Style.qml:189-191`, e.g.
  `hoverFillFor(Color.foreground, Color.accent, Color.urgent)`). A theme whose `[popups] text` is
  far from `[colors] foreground` will show a hover fill that does not match the panel's own text
  colour. This is ruling R-P: an external shell dependency, **not fixable in this repository**.
  Recorded as a risk in this plan's Self-Review, not chased as a defect.

## File Structure

| File | Responsibility |
| --- | --- |
| `manifest.json` | modified — adds `calendarRange`, `calendarDayStart`, `calendarDayEnd`, `classifier` to `defaults` and `schema` |
| `toggl_api.py` | modified — `_http_message` surfaces the Toggl 400 body instead of a generic string |
| `tests/test_toggl_api.py` | modified — one new test for the 400-body passthrough |
| `ui/PanelTheme.qml` | **new** — the 8 colour-role `QtObject` of spec §9.1 |
| `ui/TimerScope.qml` | **new** — composer + recent-entries body, moved out of `Panel.qml` unchanged in structure, re-themed |
| `ui/DayScope.qml` | **new** — day header + block rows, moved out of `Panel.qml` unchanged in structure, re-themed |
| `ui/CalendarScope.qml` | **new** — stub only, per ruling R-A. Stage 5 supplies its content. |
| `Panel.qml` | modified — theme wiring, T1–T5 fixes, `import "ui"`, extraction of the timer/day tab bodies into scope components, call-site updates for the composer's renamed ids |

---

### Task 1: Stage X fold-in — settings schema and the `_http_message` 400-body fix

This has no dependency on the rest of this stage (or on 3–6). Doing it first gets it out of the
way early, per the rulings' own sequencing note.

**Files:**
- Modify: `manifest.json`
- Modify: `toggl_api.py` — `TogglClient.request`, `_http_message`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Consumes: nothing from this stage.
- Produces: `manifest.json` defaults/schema entries for `calendarRange` (`fortnight`),
  `calendarDayStart` (`auto`), `calendarDayEnd` (`auto`), `classifier` (`off`), consumed by stage
  5 (calendar) and stage 6 (classifier). `_http_message(status, body=None)` — a new optional
  second parameter, backward compatible with the one existing direct call
  (`test_forbidden_does_not_request_token_replacement`) — consumed by stage 5's `range_entries`
  floor-violation UI and by every action's generic error path today.

- [ ] **Step 1: Add the four settings to `manifest.json`**

In `manifest.json`, extend `barWidget.defaults`:

```json
    "defaults": {
      "workspaceId": 0,
      "historyDays": 30,
      "idleReminderMinutes": 0,
      "dayBlockMinutes": 5,
      "logLevel": "info",
      "calendarRange": "fortnight",
      "calendarDayStart": "auto",
      "calendarDayEnd": "auto",
      "classifier": "off"
    },
```

and `barWidget.schema`:

```json
    "schema": [
      { "key": "workspaceId", "type": "number", "label": "Workspace", "defaultValue": 0 },
      { "key": "historyDays", "type": "number", "label": "History range (days)", "defaultValue": 30 },
      { "key": "idleReminderMinutes", "type": "number", "label": "Idle reminder (minutes)", "defaultValue": 0 },
      { "key": "dayBlockMinutes", "type": "number", "label": "Day: break between blocks (minutes)", "defaultValue": 5 },
      { "key": "logLevel", "type": "string", "label": "Log detail", "defaultValue": "info" },
      { "key": "calendarRange", "type": "string", "label": "Calendar range", "defaultValue": "fortnight" },
      { "key": "calendarDayStart", "type": "string", "label": "Calendar day start", "defaultValue": "auto" },
      { "key": "calendarDayEnd", "type": "string", "label": "Calendar day end", "defaultValue": "auto" },
      { "key": "classifier", "type": "string", "label": "Classifier", "defaultValue": "off" }
    ]
```

No `options`/`enum` field — this manifest's existing convention keeps valid-choice enforcement in
`Panel.qml`'s `ButtonGroup` `options` lists and in `Model.js` clamp functions, not in the schema
itself (`historyDays`/`logLevel` follow the same pattern already). No `ui/*.qml` control is added
for any of the four new keys in this stage: `calendarRange`/`calendarDayStart`/`calendarDayEnd`
are stage 5's UI, `classifier` is stage 6's (ruling R-M). Their only job here is that a fresh
clone starts in a valid, documented state.

- [ ] **Step 2: Surface the Toggl 400 body**

In `toggl_api.py`, the `TogglClient.request` `except HTTPError` block currently reads:

```python
            except HTTPError as error:
                status = int(error.code)
                retryable = status == 429 or status >= 500
                if not mutation and retryable and attempts < MAX_RETRIES:
                    delay = _safe_retry_after(error.headers.get("Retry-After") if error.headers else None)
                    error.close()
                    self._sleep(delay if delay is not None else min(2 ** attempts, 4))
                    attempts += 1
                    continue
                error.close()
                raise ApiError(_http_message(status), status, retryable)
```

Change the final four lines to read the body before closing, but only for 400 — every other
status keeps its fixed, non-leaking message:

```python
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
```

- [ ] **Step 3: Give `_http_message` the new parameter**

Replace:

```python
def _http_message(status):
    if status == 401:
        return "Toggl authentication failed; run setup to refresh your token."
```

with:

```python
def _http_message(status, body=None):
    if status == 400:
        text = (body or "").strip()
        if text:
            return text[:MAX_TEXT]
        return "Toggl rejected the request."
    if status == 401:
        return "Toggl authentication failed; run setup to refresh your token."
```

Leave every other branch (403/404/409/422/429/5xx/fallback) untouched. `MAX_TEXT` (500) is
already defined at module scope — reused here rather than a new literal, matching §10.8's general
truncation rule.

- [ ] **Step 4: Add the regression test**

In `tests/test_toggl_api.py`, add near `test_mutation_does_not_retry` (both use the same
`HTTPError(url, code, msg, headers, fp)` construction with a `BytesIO` body):

```python
    def test_400_body_surfaces_verbatim(self):
        error = HTTPError(
            "https://example.test", 400, "Bad Request", Message(),
            BytesIO(b"start_date must not be earlier than 2026-06-04"),
        )
        client = toggl_api.TogglClient(
            "token",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(error),
            sleep=lambda *_: None,
        )
        with self.assertRaises(toggl_api.ApiError) as raised:
            client.request("GET", "/me/time_entries", mutation=False)
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(raised.exception.message, "start_date must not be earlier than 2026-06-04")

    def test_400_with_no_body_falls_back_to_generic_message(self):
        error = HTTPError("https://example.test", 400, "Bad Request", Message(), BytesIO(b""))
        client = toggl_api.TogglClient(
            "token",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(error),
            sleep=lambda *_: None,
        )
        with self.assertRaises(toggl_api.ApiError) as raised:
            client.request("GET", "/me/time_entries", mutation=False)
        self.assertEqual(raised.exception.message, "Toggl rejected the request.")
```

`400` is not in `retryable` (only 429/5xx are), so this exercises the non-retry branch directly —
no `sleep` call expected.

- [ ] **Step 5: Verify**

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v 2>&1 | tail -20
python3 -m py_compile toggl_api.py
bash -n build
```

Expected: `omarchy plugin validate .` exits 0; the two new tests plus every existing test pass
(`test_forbidden_does_not_request_token_replacement` in particular, confirming the new optional
parameter did not break the existing one-argument call); `py_compile` and `bash -n build` exit 0.

- [ ] **Step 6: Commit**

```bash
git add manifest.json toggl_api.py tests/test_toggl_api.py
git commit -m "feat(settings,backend): calendar/classifier schema, surface Toggl's 400 body"
```

---

### Task 2: `ui/PanelTheme.qml`, and T1/T2/T3/T5 in `Panel.qml`

Fixes four of the five theme defects while `Panel.qml` is still one file, before the split makes
the same edits harder to review as a unit. T4 (hover/selection fills) is Task 3 — it is additive
behaviour, not a like-for-like colour swap, and earns its own review pass.

**Files:**
- Create: `ui/PanelTheme.qml`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `Color.popups.{background,text,border}`, `Color.{accent,urgent}`,
  `Util.alpha(color, opacity)` — all external shell singletons in `qs.Commons`, already present.
- Produces: `PanelTheme.{surface,text,edge,textMuted,textFaint,textDisabled,accent,urgent}`,
  consumed by this task's own `Panel.qml` edits and, from Task 4/5 onward, by `ui/TimerScope.qml`
  and `ui/DayScope.qml` through their `panelTheme` required property.

- [ ] **Step 1: Write `ui/PanelTheme.qml`**

```qml
import QtQuick
import qs.Commons

// The panel's colour roles. Every Qt.darker(root.foreground, N) call site in
// Panel.qml and ui/*.qml maps to one of textMuted/textFaint/textDisabled below;
// Util.alpha keeps the hue relationship to whatever the theme sets, which
// Qt.darker() does not. See docs/2026-09-04-panel-redesign.md §9.1.
QtObject {
    readonly property color surface: Color.popups.background
    readonly property color text: Color.popups.text
    readonly property color edge: Color.popups.border

    readonly property color textMuted: Util.alpha(Color.popups.text, 0.72)
    readonly property color textFaint: Util.alpha(Color.popups.text, 0.55)
    readonly property color textDisabled: Util.alpha(Color.popups.text, 0.38)

    readonly property color accent: Color.accent
    readonly property color urgent: Color.urgent
}
```

- [ ] **Step 2: Wire the `ui/` import and instantiate the theme**

In `Panel.qml`, add the directory import after the existing `"Model.js"` import (this exact
mechanism — a bare relative directory import with no `qmldir` — is already live in the shell
itself: `plugins/notifications/Service.qml` does `import "components"` against a `components/`
folder with no `qmldir` in it):

```qml
import "Model.js" as Model
import "ui"
```

Add a `PanelTheme` instance as the first child object of `root`, immediately before the existing
`Timer { interval: 1000 … }`:

```qml
    PanelTheme {
        id: panelTheme
    }

    Timer {
        interval: 1000
```

- [ ] **Step 3: T1 — repoint `root.foreground`**

Replace:

```qml
    readonly property color foreground: bar ? bar.foreground : Color.foreground
```

with:

```qml
    readonly property color foreground: panelTheme.text
```

This is the whole T1 fix for text colour — every one of the ~40 existing `root.foreground`
reads in the file (including inside the blocks Tasks 4/5 move into `ui/TimerScope.qml` and
`ui/DayScope.qml`) now resolves through `Color.popups.text` without any of those call sites
needing to change. `root.foreground`'s old source, `bar.foreground`, is unrelated to
`root.elapsedLabel`/`root.barLabel` (the bar's own compact label — see the global constraint on
`BarWidget.qml`), so this does not touch what the bar itself renders.

T1's other two roles (`Color.popups.background`, `.border`) need no `Panel.qml` code change:
`Color.popups.border` is already what `KeyboardPanel`'s own `borderSpec` default resolves to
(verified: `Border.surfaceSpec("popups", "border", Color.popups.border, …)` in
`/usr/share/omarchy/shell/Ui/KeyboardPanel.qml`, and `Panel.qml` never overrides `borderSpec`) —
Step 6's manual check confirms this is still true, not that it newly becomes true.
`Color.popups.background` is what Step 4 below restores by deleting the overrides that were
hiding it.

- [ ] **Step 4: T2 + T5 — delete the six override pairs**

Six components pass `foreground: root.foreground; background: Color.background` into a child
that already defaults to `Color.popups.*`, discarding both the theme's text colour (T2) and its
translucency (T5) in one motion. Delete both lines from each of these six sites (five
`SearchableDropdown`s named by spec's T2, plus the `tagsField` `MultiSelect`, which carries the
identical anti-pattern although spec's "5 dropdowns" count does not name it):

1. `projectDropdown` (`SearchableDropdown`, composer) — delete `foreground: root.foreground` and
   `background: Color.background`.
2. `taskDropdown` (`SearchableDropdown`, composer) — same two lines. The `enabled: …` line
   between the dropdown's `options` and these two stays.
3. `tagsField` (`MultiSelect`, composer) — same two lines.
4. `searchDropdown` (`SearchableDropdown`, composer) — same two lines.
5. The day-block-edit project `SearchableDropdown` (inside the expanded block editor) — same two
   lines.
6. The day-block-edit task `SearchableDropdown` (inside the expanded block editor) — same two
   lines.

After deletion each of the six falls back to its own component defaults —
`SearchableDropdown.qml`: `property color foreground: Color.popups.text; property color
background: Color.popups.background`; `MultiSelect.qml` the same plus `popupBorder:
Color.popups.border` — verified against both component files. Do **not** touch the `label:`,
`value:`, `options:`, `enabled:`, `visible:`, `placeholderText:`, `emptyText:`, `onChanged:`, or
`onPopupOpenChanged:` lines on any of the six; only the two theme-override lines go.

- [ ] **Step 5: T3 — the 23 `Qt.darker` sites**

Every `Qt.darker(root.foreground, N)` maps to one of the three `panelTheme` roles. `Panel.qml`
uses four factors (1.4, 1.5, 1.6, 1.8) against three roles; neither the spec nor the guide states
the mapping (guide swatches only show 1.5/1.6/1.8, and only as the old hex values being
replaced — see this plan's open questions). This plan maps by the factors' own relative order —
1.4 and 1.5 are both light dimming and collapse onto the same, least-faded role; 1.6 sits alone in
the middle; 1.8, the majority (16 of 23 sites, mostly section-header captions and disabled-looking
states), maps to the most-faded role:

| Factor | Role | Site count |
| --- | --- | --- |
| 1.4 | `panelTheme.textMuted` | 1 |
| 1.5 | `panelTheme.textMuted` | 4 |
| 1.6 | `panelTheme.textFaint` | 2 |
| 1.8 | `panelTheme.textDisabled` | 16 |

Replace `Qt.darker(root.foreground, 1.4)` and every `Qt.darker(root.foreground, 1.5)` with
`panelTheme.textMuted`; every `Qt.darker(root.foreground, 1.6)` with `panelTheme.textFaint`; every
`Qt.darker(root.foreground, 1.8)` with `panelTheme.textDisabled`. This is a mechanical
find-and-replace by factor — every occurrence of a given factor gets the same role, with three
exceptions to read carefully because the surrounding expression is a ternary, not a bare
assignment:

- The settings-gear button: `foreground: root.settingsOpen ? Color.accent :
  Qt.darker(root.foreground, 1.4)` → only the `Qt.darker(...)` half changes, to
  `panelTheme.textMuted`.
- The day-block glyph colour: `color: blockRow.blockState === "conflict" ? Color.urgent :
  (blockRow.blockState === "applied" ? Qt.darker(root.foreground, 1.6) : (blockRow.blockProjectId
  ? Model.projectColorForEntry({ "projectId": blockRow.blockProjectId }, root.projects) ||
  Color.accent : Qt.darker(root.foreground, 1.8)))` — has two `Qt.darker` calls, one per factor;
  convert each independently to `panelTheme.textFaint` and `panelTheme.textDisabled` respectively,
  leave every other branch of the ternary untouched.
- The two "ready" ternaries — the per-block `APPLY` button
  (`foreground: blockRow.ready ? Color.background : Qt.darker(root.foreground, 1.8)`) and the
  `APPLY ASSIGNED` button (`foreground: root.daySummary.ready > 0 ? Color.background :
  Qt.darker(root.foreground, 1.8)`) — only the `Qt.darker(...)` half changes, to
  `panelTheme.textDisabled`. The `Color.background` half is contrast text drawn on a filled
  `Color.accent` pill when the button is enabled, a different role than the popup-surface fill T1
  and T5 target; leave it as `Color.background`. Same reasoning applies to the third
  `Color.background` site in the file — the main Start/Stop button's `foreground: Color.background`
  — which contains no `Qt.darker` at all and needs no edit in this step.

- [ ] **Step 6: Verify**

```bash
qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo "qmlformat exit: $?"
qmlformat ui/PanelTheme.qml >/dev/null; echo "qmlformat exit: $?"
omarchy plugin validate .; echo "validate exit: $?"
grep -c Qt.darker Panel.qml ui/*.qml
grep -c "background: Color.background" Panel.qml
```

Expected: both `qmlformat` runs and `validate` exit 0. `grep -c Qt.darker` returns 0. The second
grep returns 0 too — Step 4 removed every site of that literal pair.

Restart the shell (`omarchy-restart-shell`) and open the panel. Confirm: the panel's border is
`#89b4fa` (the aether theme's accent) on both TIMER and DAY tabs — this was already true before
this task per Step 3's note, so the check here is that it did **not** regress. Confirm the panel
surface, dropdown popups, and every previously-grey caption/meta line still render with visibly
correct (not black, not missing) colour. Check `qs -p /usr/share/omarchy/shell log` for
`qt.qml.context` warnings — none expected. Confirm `BarWidget.qml`'s bar label (the compact
`elapsedLabel`/description text next to the bar icon) still renders — this task does not touch
`BarWidget.qml` or the properties it reads, but it is the one check neither QML tool can perform
(ruling R-O).

- [ ] **Step 7: Commit**

```bash
git add ui/PanelTheme.qml Panel.qml
git commit -m "feat(theme): PanelTheme roles; fix T1/T2/T3/T5 theme defects"
```

---

### Task 3: T4 — hover fill on the two interactive row kinds

Row hover/selection is described by spec/guide as something to "use `Style.hoverFill`/
`Style.selectedFill` instead of hand-drawing" — but direct inspection finds no hand-drawn
hover/selection in the current file at all: the two interactive row kinds (recent-entries list,
day-block rows) use a bare `MouseArea { onClicked }` with no `hoverEnabled` and no background
Rectangle. This task is therefore a first addition of hover feedback, not a replacement, using
`Style.hoverFill` as the guide directs. `Style.selectedFill` is not wired to anything in this
task: no row-cursor concept exists in `Panel.qml` yet (stage 3 introduces the command-line result
cursor, stage 4 the day-block cursor — ruling R-B). Wiring `Style.selectedFill` to a selection
index that does not exist yet would be inventing stage 3/4 behaviour early, which this stage's own
brief forbids.

**Files:**
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `Style.hoverFill` (external shell singleton, `qs.Commons`, already imported).
- Produces: nothing new — purely visual.

- [ ] **Step 1: Recent-entries row**

The delegate is currently:

```qml
                                    delegate: Item {
                                        required property var modelData

                                        Layout.fillWidth: true
                                        implicitHeight: Style.space(42)

                                        RowLayout {
                                            anchors.fill: parent
                                            spacing: Style.spacing.rowGap
                                            …
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            onClicked: root.continueEntry(modelData)
                                        }

                                    }
```

Change the delegate's root type from `Item` to `Rectangle`, add a `color` binding driven by the
`MouseArea`'s hover state, and give the `MouseArea` an `id` plus `hoverEnabled: true`:

```qml
                                    delegate: Rectangle {
                                        id: recentRow

                                        required property var modelData

                                        Layout.fillWidth: true
                                        implicitHeight: Style.space(42)
                                        color: recentMouse.containsMouse ? Style.hoverFill : "transparent"

                                        RowLayout {
                                            anchors.fill: parent
                                            spacing: Style.spacing.rowGap
                                            …
                                        }

                                        MouseArea {
                                            id: recentMouse

                                            anchors.fill: parent
                                            hoverEnabled: true
                                            onClicked: root.continueEntry(modelData)
                                        }

                                    }
```

The `RowLayout` content in between (project-colour dot, description/project text, duration) is
untouched — `Rectangle` supports every `Layout.*` attached property `Item` does, so nothing else
in the delegate needs to change.

- [ ] **Step 2: Day-block row head**

The clickable region wrapping a block's top line and its "also" line is currently:

```qml
                                        Item {
                                            Layout.fillWidth: true
                                            implicitHeight: topLine.implicitHeight + (alsoLine.visible ? alsoLine.implicitHeight : 0) + Style.spacing.rowGap

                                            RowLayout {
                                                id: topLine
                                                …
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                z: -1
                                                onClicked: root.toggleBlock(modelData)
                                            }

                                            Text {
                                                id: alsoLine
                                                …
                                            }

                                        }
```

Same transform — `Item` → `Rectangle` with a hover-driven `color`, `MouseArea` gains an `id` and
`hoverEnabled: true`. Keep `z: -1` on the `MouseArea` — it exists so the click target sits behind
the `APPLY` button and other sibling controls in `topLine`, unrelated to the new fill:

```qml
                                        Rectangle {
                                            id: blockHead

                                            Layout.fillWidth: true
                                            implicitHeight: topLine.implicitHeight + (alsoLine.visible ? alsoLine.implicitHeight : 0) + Style.spacing.rowGap
                                            color: blockMouse.containsMouse ? Style.hoverFill : "transparent"

                                            RowLayout {
                                                id: topLine
                                                …
                                            }

                                            MouseArea {
                                                id: blockMouse

                                                anchors.fill: parent
                                                z: -1
                                                hoverEnabled: true
                                                onClicked: root.toggleBlock(modelData)
                                            }

                                            Text {
                                                id: alsoLine
                                                …
                                            }

                                        }
```

- [ ] **Step 3: Verify**

```bash
qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo "qmlformat exit: $?"
omarchy plugin validate .; echo "validate exit: $?"
```

Expected: both exit 0.

Restart the shell. Open the panel, hover a recent-entries row and a day-block row (with at least
one block present — open the DAY tab on a date with activity) and confirm each highlights with a
faint fill on hover and returns to transparent when the pointer leaves, without changing layout or
shifting any text. Confirm clicking still continues an entry / toggles a block's expansion exactly
as before.

- [ ] **Step 4: Commit**

```bash
git add Panel.qml
git commit -m "feat(theme): T4 — Style.hoverFill on recent-entries and day-block rows"
```

---

### Task 4: Extract `ui/TimerScope.qml`

Cuts the (already re-themed) timer-tab body out of `Panel.qml` into its own file. Purely
mechanical — no further colour or behaviour change — but it is its own task because it is the
first proof that the `root`/`panelTheme` required-property pattern this plan commits to actually
works, and because five composer ids need renaming to avoid an alias/id name collision (see this
plan's Architecture note).

**Files:**
- Create: `ui/TimerScope.qml`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `root` (the enclosing `Panel.qml` instance, exposing every `root.*` property/function
  already in use — `current`, `elapsedLabel`, `fontFamily`, `status`, `pendingAction`,
  `manualRefresh`, `cacheInfo`, `errorMessage`, `setupCommand`, `selectedProjectId`,
  `selectedTaskId`, `projects`, `projectTasks`, `tags`, `tasksAvailable`, `searchOpen`,
  `searchOptions`, `searchResults`, `projects`/`tasks`/`entries` filters used inline,
  `selectProject`, `selectTask`, `continueEntry`, `updateCurrent`, `start`, `stop`, `bootstrap`,
  `close`), `panelTheme` (from Task 2).
- Produces: `TimerScope` QML type. Public surface Panel.qml depends on:
  `descriptionField` (alias to a `TextField`, `.text`/`.forceActiveFocus()` used),
  `projectDropdown`/`taskDropdown` (alias to `SearchableDropdown`, `.value` read/written),
  `tagsField` (alias to `MultiSelect`, `.values` read/written), `searchDropdown` (alias to
  `SearchableDropdown`, `.open()` called).

- [ ] **Step 1: Write `ui/TimerScope.qml`**

```qml
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../Model.js" as Model

Item {
    id: timerScope

    required property var root
    required property var panelTheme

    readonly property alias descriptionField: descriptionInput
    readonly property alias projectDropdown: projectDropdownField
    readonly property alias taskDropdown: taskDropdownField
    readonly property alias tagsField: tagsFieldInput
    readonly property alias searchDropdown: searchDropdownField

    visible: root.activeTab === "timer"
    Layout.fillWidth: true
    implicitHeight: timerContent.implicitHeight

    ColumnLayout {
        id: timerContent

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.panelGap

        PanelHero {
            Layout.fillWidth: true
            title: root.current ? (root.current.description || "Untitled timer") : "Ready when you are"
            meta: root.current ? "TRACKING NOW" : "TOGGL TRACK"
            foreground: root.foreground

            trailingControl: Component {
                Text {
                    text: root.elapsedLabel
                    color: Color.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.display
                    font.bold: true
                }

            }

        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            TextField {
                id: descriptionInput

                Layout.fillWidth: true
                placeholderText: "What are you working on?"
                foreground: root.foreground
                onAccepted: root.current ? root.updateCurrent() : root.start()
                Keys.onEscapePressed: root.close()
            }

            Button {
                text: root.current ? "STOP" : "START"
                Layout.preferredWidth: Style.space(88)
                focusable: true
                bordered: true
                background: root.current ? Color.urgent : Color.accent
                foreground: Color.background
                accent: root.current ? Color.urgent : Color.accent
                onClicked: root.current ? root.stop() : root.start()
            }

        }

        PanelSectionHeader {
            text: "ENTRY DETAILS"
            foreground: root.foreground
        }

        SearchableDropdown {
            id: projectDropdownField

            Layout.fillWidth: true
            label: "PROJECT"
            value: String(root.selectedProjectId || "")
            options: root.projects.map(function(p) {
                return {
                    "value": String(p.id),
                    "label": p.name,
                    "description": p.clientName || ""
                };
            })
            onChanged: function(value) {
                var p = root.projects.filter(function(x) {
                    return String(x.id) === value;
                })[0];
                if (p)
                    root.selectProject(p);

            }
        }

        SearchableDropdown {
            id: taskDropdownField

            Layout.fillWidth: true
            label: "TASK"
            value: String(root.selectedTaskId || "")
            options: root.projectTasks.map(function(t) {
                return {
                    "value": String(t.id),
                    "label": t.name,
                    "description": t.projectName || ""
                };
            })
            enabled: root.tasksAvailable && !!root.selectedProjectId
            onChanged: function(value) {
                var t = root.tasks.filter(function(x) {
                    return String(x.id) === value;
                })[0];
                if (t)
                    root.selectTask(t);

            }
        }

        MultiSelect {
            id: tagsFieldInput

            Layout.fillWidth: true
            label: "TAGS"
            values: []
            options: root.tags
        }

        Toggle {
            Layout.fillWidth: true
            label: "Billable"
            description: "Mark this entry as billable"
            checked: root.billable
            onClicked: root.billable = !root.billable
        }

        SearchableDropdown {
            id: searchDropdownField

            visible: root.searchOpen
            Layout.fillWidth: true
            showLabel: false
            value: ""
            options: root.searchOptions
            placeholderText: "Search everything"
            emptyText: "No matching entries"
            onPopupOpenChanged: {
                if (!popupOpen)
                    root.searchOpen = false;

            }
            onChanged: function(value) {
                var a = value.split(":");
                var id = a.slice(1).join(":");
                if (a[0] === "project") {
                    var p = root.projects.filter(function(x) {
                        return String(x.id) === id;
                    })[0];
                    if (p)
                        root.selectProject(p);

                } else if (a[0] === "task") {
                    var t = root.tasks.filter(function(x) {
                        return String(x.id) === id;
                    })[0];
                    if (t)
                        root.selectTask(t);

                } else if (a[0] === "entry") {
                    var e = root.entries.filter(function(x) {
                        return String(x.id) === id;
                    })[0];
                    if (e)
                        root.continueEntry(e);

                }
                root.searchOpen = false;
            }
        }

        PanelSectionHeader {
            visible: !root.searchOpen && root.searchResults.recentEntries.length > 0
            text: "RECENT"
            foreground: root.foreground
        }

        Repeater {
            model: !root.searchOpen ? root.searchResults.recentEntries : []

            delegate: Rectangle {
                id: recentRow

                required property var modelData

                Layout.fillWidth: true
                implicitHeight: Style.space(42)
                color: recentMouse.containsMouse ? Style.hoverFill : "transparent"

                RowLayout {
                    anchors.fill: parent
                    spacing: Style.spacing.rowGap

                    Rectangle {
                        Layout.preferredWidth: 9
                        Layout.preferredHeight: 9
                        radius: 5
                        color: Model.projectColorForEntry(modelData, root.projects) || panelTheme.textDisabled
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Text {
                            Layout.fillWidth: true
                            text: modelData.description
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.projectName + (modelData.taskName ? " · " + modelData.taskName : "")
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            elide: Text.ElideRight
                        }

                    }

                    Text {
                        text: Model.formatDuration(Model.durationSeconds(modelData, Date.now()))
                        color: panelTheme.textMuted
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                }

                MouseArea {
                    id: recentMouse

                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.continueEntry(modelData)
                }

            }

        }

        Text {
            visible: root.status === "loading"
            text: root.manualRefresh ? "Refreshing metadata…" : (root.pendingAction ? "Updating Toggl…" : "Loading Toggl…")
            color: panelTheme.textMuted
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        Text {
            visible: root.cacheInfo && root.cacheInfo.stale === true
            text: "Using cached project data — Refresh to retry."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        RowLayout {
            visible: root.status === "error"
            Layout.fillWidth: true

            Text {
                Layout.fillWidth: true
                text: root.errorMessage
                color: Color.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
            }

            Button {
                text: "RETRY"
                focusable: true
                bordered: true
                foreground: Color.accent
                onClicked: root.bootstrap()
            }

        }

        TextField {
            visible: root.status === "error" && /helper|token|setup/i.test(root.errorMessage)
            Layout.fillWidth: true
            text: "Run setup, then retry: " + root.setupCommand
            readOnly: true
            foreground: panelTheme.textMuted
        }

    }

}
```

- [ ] **Step 2: Delete the moved block from `Panel.qml`**

Delete the entire `Item { visible: root.activeTab === "timer" … }` block (from `implicitHeight:
timerContent.implicitHeight`'s enclosing `Item` down to its closing brace) — everything Step 1
just moved.

- [ ] **Step 3: Instantiate `TimerScope` in its place**

```qml
                        TimerScope {
                            id: timerScope

                            root: root
                            panelTheme: panelTheme
                        }
```

Placed exactly where the deleted `Item` was — a direct child of `contentColumn`, immediately after
the settings `ColumnLayout`.

- [ ] **Step 4: Update `Panel.qml`'s composer functions to reach through `timerScope`**

Five functions and one toolbar handler reference the composer's ids directly; none of those ids
exist in `Panel.qml` any more. Prefix each with `timerScope.`:

`entryFields()`:
```qml
    function entryFields() {
        return {
            "description": timerScope.descriptionField.text.trim(),
            "project_id": selectedProjectId || null,
            "task_id": selectedTaskId || null,
            "tags": timerScope.tagsField.values,
            "billable": billable
        };
    }
```

`start()` — only its guard clause changes:
```qml
    function start() {
        if (!timerScope.descriptionField.text.trim() && !selectedProjectId)
            return ;

        var data = entryFields();
        data.workspace_id = selectedWorkspaceId;
        request("start", data);
    }
```

`selectProject(project)`:
```qml
    function selectProject(project) {
        selectedProjectId = Number(project.id) || 0;
        selectedTaskId = 0;
        timerScope.projectDropdown.value = String(selectedProjectId);
        timerScope.taskDropdown.value = "";
        searchOpen = false;
        timerScope.descriptionField.forceActiveFocus();
    }
```

`selectTask(task)`:
```qml
    function selectTask(task) {
        selectedTaskId = Number(task.id) || 0;
        selectedProjectId = Number(task.projectId) || 0;
        var project = selectedProject();
        timerScope.projectDropdown.value = String(selectedProjectId);
        timerScope.taskDropdown.value = String(selectedTaskId);
        searchOpen = false;
        timerScope.descriptionField.forceActiveFocus();
    }
```

`showEntry(entry)`:
```qml
    function showEntry(entry) {
        selectedProjectId = entry.projectId || 0;
        selectedTaskId = Model.taskForEntry(entry, tasks) ? entry.taskId : 0;
        timerScope.projectDropdown.value = entry.projectName === "No project" ? "" : String(selectedProjectId);
        timerScope.taskDropdown.value = selectedTask() ? String(selectedTaskId) : "";
        timerScope.descriptionField.text = entry.description === "(no description)" ? "" : entry.description;
        timerScope.tagsField.values = entry.tags || [];
        billable = entry.billable;
    }
```

`loadComposer(entry)`:
```qml
    function loadComposer(entry) {
        composerEntryId = entry ? entry.id : 0;
        if (entry) {
            showEntry(entry);
        } else {
            selectedProjectId = 0;
            selectedTaskId = 0;
            timerScope.descriptionField.text = "";
            timerScope.projectDropdown.value = "";
            timerScope.taskDropdown.value = "";
            timerScope.tagsField.values = [];
            billable = false;
        }
    }
```

The toolbar's search button, kept in `Panel.qml`:
```qml
                            PanelActionButton {
                                visible: root.activeTab === "timer"
                                iconText: "󰍉"
                                tooltipText: "Search"
                                size: Style.spacing.controlHeight
                                foreground: Color.accent
                                onClicked: {
                                    root.searchMode = "all";
                                    root.query = "";
                                    root.searchOpen = true;
                                    timerScope.searchDropdown.open();
                                }
                            }
```

- [ ] **Step 5: Verify**

```bash
qmlformat -n -i Panel.qml ui/TimerScope.qml && qmlformat Panel.qml >/dev/null; echo "Panel.qml exit: $?"
qmlformat ui/TimerScope.qml >/dev/null; echo "TimerScope.qml exit: $?"
omarchy plugin validate .; echo "validate exit: $?"
grep -c Qt.darker Panel.qml ui/*.qml
wc -l ui/TimerScope.qml Panel.qml
```

Expected: all three `qmlformat`/`validate` checks exit 0. `grep -c Qt.darker` is 0.
`ui/TimerScope.qml` is comfortably under 400 lines.

Restart the shell. On the TIMER tab: type a description, pick a project then a task from their
dropdowns, add a tag, toggle Billable, press Enter to start a timer, confirm it starts and the
running-clock/PanelHero updates each second. Click a recent-entries row and confirm it continues
that entry into the composer. Click the search icon, confirm the search dropdown opens and
filtering/selecting a project, task or entry from it behaves as before. Confirm the hover fill
added in Task 3 still highlights recent-entries rows.

- [ ] **Step 6: Commit**

```bash
git add ui/TimerScope.qml Panel.qml
git commit -m "refactor(ui): extract ui/TimerScope.qml"
```

---

### Task 5: Extract `ui/DayScope.qml`

Same mechanical move as Task 4, simpler: nothing outside the day-tab body ever references any of
its internal ids by name (confirmed — `mutateBlock`/`toggleBlock`/`blockReady`/`submitBlock`/
`applyBlock`/`applyAssigned`/`finishBlock`/`pendingSlot`, all kept in `Panel.qml`, operate on
`dayBlocks`/a `block` argument, never on a day-tab id), so no aliases and no `Panel.qml`
call-site rewrites are needed beyond the extraction itself.

**Files:**
- Create: `ui/DayScope.qml`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `root` (`dayDate`, `dayBlocks`, `daySummary`, `dayLoaded`, `dayError`, `dayRevision`,
  `status`, `pendingAction`, `requestPending`, `tasksAvailable`, `projects`, `projectOptions`,
  `tasks`, `fontFamily`, `foreground`; functions `shiftDay`, `showDay`, `toggleBlock`,
  `mutateBlock`, `blockReady`, `applyBlock`, `applyAssigned`), `panelTheme` (from Task 2).
- Produces: `DayScope` QML type, no public surface beyond `visible`/`Layout.fillWidth` —
  `Panel.qml` does not reach into it.

- [ ] **Step 1: Write `ui/DayScope.qml`**

```qml
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../Model.js" as Model

Item {
    id: dayScope

    required property var root
    required property var panelTheme

    visible: root.activeTab === "day"
    Layout.fillWidth: true
    implicitHeight: dayContent.implicitHeight

    ColumnLayout {
        id: dayContent

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.panelGap

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            PanelActionButton {
                iconText: "‹"
                tooltipText: "Previous day"
                size: Style.spacing.controlHeight
                foreground: root.foreground
                onClicked: root.shiftDay(-1)
            }

            Text {
                text: Model.dayLabel(root.dayDate)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
            }

            PanelActionButton {
                iconText: "›"
                tooltipText: "Next day"
                size: Style.spacing.controlHeight
                foreground: root.foreground
                enabled: root.dayDate < Model.todayDate()
                onClicked: root.shiftDay(1)
            }

            Button {
                text: "TODAY"
                visible: root.dayDate !== Model.todayDate()
                focusable: true
                bordered: true
                fontSize: Style.font.caption
                foreground: Color.accent
                onClicked: root.showDay(Model.todayDate())
            }

            Item {
                Layout.fillWidth: true
            }

            ColumnLayout {
                spacing: 0

                Text {
                    Layout.alignment: Qt.AlignRight
                    text: Model.compactDuration(root.daySummary.totalSeconds)
                    color: Color.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.title
                    font.bold: true
                }

                Text {
                    Layout.alignment: Qt.AlignRight
                    text: (root.dayRevision, root.daySummary.applied + " of " + root.dayBlocks.length + " assigned" + (root.dayBlocks.filter(function(block) {
                        return block.state === "conflict";
                    }).length ? " · " + root.dayBlocks.filter(function(block) {
                        return block.state === "conflict";
                    }).length + " conflicts" : ""))
                    visible: root.dayBlocks.length > 0
                    color: panelTheme.textDisabled
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                }

            }

        }

        PanelSeparator {
            foreground: root.foreground
        }

        Text {
            visible: root.status === "loading" && root.pendingAction === "day_activity"
            text: "Reading local activity…"
            color: panelTheme.textMuted
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        Text {
            Layout.fillWidth: true
            visible: root.dayError !== ""
            text: root.dayError
            color: Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.dayLoaded && root.dayError === "" && root.dayBlocks.length === 0
            text: "No tracked activity for this day. Omalog records activity through ActivityWatch on 127.0.0.1:5600."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Repeater {
            model: root.dayBlocks

            delegate: ColumnLayout {
                id: blockRow

                required property var modelData
                readonly property int rev: root.dayRevision
                readonly property string blockState: (rev, String(modelData.state))
                readonly property bool ready: (rev, root.blockReady(modelData))
                readonly property bool busy: (rev, !!modelData.busy)
                readonly property bool expanded: (rev, !!modelData.expanded)
                readonly property int blockProjectId: (rev, Number(modelData.projectId) || 0)
                readonly property int blockTaskId: (rev, Number(modelData.taskId) || 0)
                readonly property string failure: (rev, String(modelData.failure || ""))

                Layout.fillWidth: true
                spacing: Style.spacing.rowGap

                Rectangle {
                    id: blockHead

                    Layout.fillWidth: true
                    implicitHeight: topLine.implicitHeight + (alsoLine.visible ? alsoLine.implicitHeight : 0) + Style.spacing.rowGap
                    color: blockMouse.containsMouse ? Style.hoverFill : "transparent"

                    RowLayout {
                        id: topLine

                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: Style.spacing.rowGap

                        Text {
                            text: blockRow.blockState === "applied" ? "✓" : "●"
                            color: blockRow.blockState === "conflict" ? Color.urgent : (blockRow.blockState === "applied" ? panelTheme.textFaint : (blockRow.blockProjectId ? Model.projectColorForEntry({
                                "projectId": blockRow.blockProjectId
                            }, root.projects) || Color.accent : panelTheme.textDisabled))
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            text: (rev, Model.clockTime(modelData.start) + "–" + Model.clockTime(modelData.end))
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            text: (rev, Model.compactDuration(modelData.seconds))
                            color: Color.accent
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            Layout.fillWidth: true
                            text: (rev, modelData.label)
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            elide: Text.ElideRight
                        }

                        Text {
                            visible: blockRow.blockState === "applied"
                            text: "✓ APPLIED"
                            color: panelTheme.textFaint
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        Text {
                            visible: blockRow.blockState === "conflict"
                            text: "▲ CONFLICT"
                            color: Color.urgent
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        Button {
                            visible: blockRow.blockState === "pending"
                            text: blockRow.busy ? "…" : "APPLY"
                            enabled: !root.requestPending && blockRow.ready
                            focusable: true
                            bordered: true
                            fontSize: Style.font.caption
                            background: blockRow.ready ? Color.accent : "transparent"
                            foreground: blockRow.ready ? Color.background : panelTheme.textDisabled
                            onClicked: root.applyBlock(modelData)
                        }

                    }

                    MouseArea {
                        id: blockMouse

                        anchors.fill: parent
                        z: -1
                        hoverEnabled: true
                        onClicked: root.toggleBlock(modelData)
                    }

                    Text {
                        id: alsoLine

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: topLine.bottom
                        anchors.topMargin: Style.spacing.rowGap
                        visible: (rev, Model.blockAlso(modelData, 3) !== "")
                        text: (rev, "  also  " + Model.blockAlso(modelData, 3))
                        color: panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                    }

                }

                TextField {
                    Layout.fillWidth: true
                    visible: blockRow.expanded
                    text: (rev, modelData.description)
                    placeholderText: "Describe this block"
                    foreground: root.foreground
                    onTextChanged: {
                        root.mutateBlock(modelData, function() {
                            modelData.description = text;
                        });
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: blockRow.expanded
                    spacing: Style.spacing.rowGap

                    SearchableDropdown {
                        Layout.fillWidth: true
                        showLabel: false
                        value: (rev, blockRow.blockProjectId ? String(blockRow.blockProjectId) : "")
                        options: root.projectOptions
                        placeholderText: "Choose a project"
                        emptyText: "No projects"
                        onChanged: function(value) {
                            root.mutateBlock(modelData, function() {
                                modelData.projectId = Number(value) || 0;
                                modelData.taskId = 0;
                            });
                        }
                    }

                    SearchableDropdown {
                        Layout.fillWidth: true
                        showLabel: false
                        enabled: root.tasksAvailable && !!blockRow.blockProjectId
                        value: (rev, blockRow.blockTaskId ? String(blockRow.blockTaskId) : "")
                        options: Model.tasksForProject(root.tasks, blockRow.blockProjectId).map(function(task) {
                            return {
                                "value": String(task.id),
                                "label": task.name,
                                "description": task.projectName || ""
                            };
                        })
                        placeholderText: blockRow.blockProjectId ? "Choose a task" : "Choose a project first"
                        emptyText: "No tasks"
                        onChanged: function(value) {
                            root.mutateBlock(modelData, function() {
                                modelData.taskId = Number(value) || 0;
                            });
                        }
                    }

                }

                Repeater {
                    // Repeater is not an Item, so `visible` would not hide these.
                    // Gating the model keeps collapsed rows one line tall.
                    model: blockRow.expanded ? (rev, modelData.topics.slice(0, 8)) : []

                    delegate: Text {
                        required property var modelData

                        Layout.fillWidth: true
                        text: (blockRow.rev, "  " + Model.compactDuration(modelData.seconds) + "  " + modelData.name)
                        color: panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                    }

                }

                Text {
                    Layout.fillWidth: true
                    visible: blockRow.expanded && blockRow.failure !== ""
                    text: blockRow.failure
                    color: Color.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                }

                PanelSeparator {
                    foreground: root.foreground
                }

            }

        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.dayBlocks.length > 0
            spacing: Style.spacing.rowGap

            Button {
                text: "APPLY ASSIGNED · " + root.daySummary.ready
                enabled: !root.requestPending && root.daySummary.ready > 0
                focusable: true
                bordered: true
                fontSize: Style.font.caption
                background: root.daySummary.ready > 0 ? Color.accent : "transparent"
                foreground: root.daySummary.ready > 0 ? Color.background : panelTheme.textDisabled
                onClicked: root.applyAssigned()
            }

        }

    }

}
```

- [ ] **Step 2: Delete the moved block from `Panel.qml`**

Delete the entire `Item { visible: root.activeTab === "day" … }` block Step 1 just moved.

- [ ] **Step 3: Instantiate `DayScope` in its place**

```qml
                        DayScope {
                            id: dayScope

                            root: root
                            panelTheme: panelTheme
                        }
```

Placed as the next sibling of `TimerScope` inside `contentColumn`.

- [ ] **Step 4: Verify**

```bash
qmlformat -n -i Panel.qml ui/DayScope.qml && qmlformat Panel.qml >/dev/null; echo "Panel.qml exit: $?"
qmlformat ui/DayScope.qml >/dev/null; echo "DayScope.qml exit: $?"
omarchy plugin validate .; echo "validate exit: $?"
grep -c Qt.darker Panel.qml ui/*.qml
wc -l ui/DayScope.qml Panel.qml
```

Expected: all exit 0. `grep -c Qt.darker` is 0. `ui/DayScope.qml` is comfortably under 400 lines.

Restart the shell. Switch to the DAY tab, confirm today's blocks (or a nearby day with recorded
activity) render with their glyph, time range, duration, label, applied/conflict markers exactly
as before. Click a block to expand it, edit its description, pick a project and task, confirm the
`APPLY` button enables once both are set and applying it works. Confirm `APPLY ASSIGNED`'s count
and enabled state track assigned blocks. Confirm the hover fill added in Task 3 still highlights a
block row on hover. Step through Previous/Next/Today.

- [ ] **Step 5: Commit**

```bash
git add ui/DayScope.qml Panel.qml
git commit -m "refactor(ui): extract ui/DayScope.qml"
```

---

### Task 6: `ui/CalendarScope.qml` stub, and stage close-out

Per ruling R-A: `ui/CalendarScope.qml` is created **once**, here, as a stub. Stage 5 supplies its
content — this stage must not invent calendar UI. The file is not instantiated anywhere in
`Panel.qml`: no `"cal"` scope value exists yet (that three-valued rename is stage 3's job), so
there is nothing for it to be gated on. Its only job in this stage is to exist, satisfy `import
"ui"`, and satisfy `build`'s `Panel.qml ui/*.qml` glob.

**Files:**
- Create: `ui/CalendarScope.qml`

**Interfaces:**
- Consumes: nothing yet.
- Produces: `CalendarScope` QML type (unused placeholder), consumed by stage 5.

- [ ] **Step 1: Write the stub**

```qml
import QtQuick

// Stub only — ruling R-A. Stage 5 supplies week/fortnight/month content and
// wires this into Panel.qml's scope switching; stage 2 must not invent either.
Item {
    id: calendarScope

    required property var root
}
```

- [ ] **Step 2: Full-stage verification**

```bash
qmlformat -n -i Panel.qml ui/*.qml
for f in Panel.qml ui/*.qml; do qmlformat "$f" >/dev/null; echo "$f: $?"; done
omarchy plugin validate .; echo "validate: $?"
grep -c Qt.darker Panel.qml ui/*.qml
grep -rn "Color.background" Panel.qml ui/*.qml
./build --check
```

Expected: every `qmlformat` invocation exits 0. `omarchy plugin validate .` exits 0.
`grep -c Qt.darker` returns 0 for every file (the mechanical acceptance test this whole stage is
scoped around). The `Color.background` grep should show exactly three remaining hits — the
Start/Stop button's contrast-text `foreground: Color.background`, and the `Color.background`
halves of the two "ready" ternaries in `ui/DayScope.qml` (per Task 2 Step 5's note) — and no
`background: Color.background` surface-fill site anywhere. `./build --check` exits 0 (it already
globs `Panel.qml ui/*.qml` for its own `qmlformat` step and needs no change for this stage — the
new `ui/` directory did not exist before this stage started).

- [ ] **Step 3: Manual restart-and-look**

`omarchy-restart-shell`, then open the panel and work through: TIMER tab full composer flow
(start/stop, project/task/tag selection, search, recent-entries continue); DAY tab full flow
(navigate days, expand/edit/apply a block, apply-assigned); settings panel toggled open on both
tabs, confirm every previously-grey label is still legible and every `ButtonGroup` still switches
its setting; the panel border renders in the theme's accent colour on both tabs. Check `qs -p
/usr/share/omarchy/shell log` for `qt.qml.context` warnings — none expected. Confirm the bar
widget's own compact label (`BarWidget.qml`'s rendering of `root.elapsedLabel`/`root.barLabel`)
is unaffected — start a timer from the panel, confirm the bar's label updates as before (ruling
R-O).

- [ ] **Step 4: Commit**

```bash
git add ui/CalendarScope.qml
git commit -m "feat(ui): CalendarScope stub (content lands in stage 5)"
```

---

## Self-Review

**Spec coverage.** Spec §5 (the four-file split and Panel.qml's retained responsibilities) is
Tasks 2–6. Spec §9 in full (T1–T5, `ui/PanelTheme.qml`, the fixed values of §9.2) is Tasks 2–3.
Folded-in stage X work (manifest schema, `_http_message`) is Task 1.

**Rulings applied.** R-A (`CalendarScope.qml` stub only, not instantiated) — Task 6. R-E (the
settings `ColumnLayout` stays in `Panel.qml`, unclaimed by this stage beyond its own `Qt.darker`
fix) — explicitly left alone in Tasks 4/5 rather than moved into either scope file; stage 3 is who
re-gates it on the new three-valued scope. R-F (23, not 21, is the baseline and the target) —
stated up front and re-verified in Task 6. R-P (`Style.hoverFill`/`selectedFill` source from
`Color.foreground`, not `Color.popups.text`) — recorded as an unfixable external-dependency risk,
not chased.

**Deliberately out of scope for this plan**, each belonging to a later stage: the command-line
rewrite and result rows (§6, stage 3); the day-block cursor and `Ctrl+J`/`Ctrl+K` dispatch (ruling
R-B/R-C, stage 3 then stage 4); the inspect/edit drawer split (§7, stage 4); the day-block
`clockDuration` formatter (ruling R-D, stage 3); calendar content (§8, stage 5); the classifier
control (ruling R-M, stage 6). `ui/TimerScope.qml` and `ui/DayScope.qml` in this plan are
**structurally identical** to today's timer/day tab bodies — later stages rebuild their insides,
not their file boundaries.

**Test coverage not added here, and why.** Stage X's own digest (RX-10/RX-11) lists Python and
Node test bullets for `range_entries`, `classify`, `axisBounds`, and the `calendarDayStart`/`End`
override — none of those functions exist yet (`range_entries` and `classify` are not present in
`toggl_api.py` today; `axisBounds` is not present in `Model.js` today, verified). Writing tests
against functions that do not exist is not possible; those bullets belong to whichever stage
implements the function they test (stage 4/5/6), not to this one. This plan implements and tests
only what stage X's own fold-in note names as independent of 2–6: the manifest schema and the
`_http_message` fix.

**No QML test harness.** Every task that touches `Panel.qml` or a `ui/*.qml` file ends with an
explicit `qmlformat`-by-exit-status check, an `omarchy plugin validate .` check, and a named
manual restart-and-look sequence — never a QML unit test, because none exists in this repository.

**Colour-role mapping is a judgment call, not a spec value — flagged, not hidden.** R2-11 (the
digest) is explicit that neither spec nor guide states which of the three `PanelTheme` roles the
1.4 factor (one site: the settings-gear icon) should join, and the guide's own swatch table shows
only the *old* hex values at 1.5/1.6/1.8, never the new alpha roles. Task 2 Step 5 documents the
mapping this plan uses and the reasoning (factor order: 1.4 and 1.5 collapse onto the least-faded
role, 1.6 alone in the middle, 1.8 — the 16-site majority — onto the most-faded role) so a
reviewer can override it in one place rather than needing to re-derive it from 23 scattered edits.

**The three `Color.background` contrast-text sites are a deliberate non-change, not an oversight.**
R2-7 (the digest) flags these as unresolved by spec/guide and warns against "silently fixing" them
by assumption. This plan's resolution is to leave all three exactly as they are: they draw text on
a filled `Color.accent`/`Color.urgent` pill (contrast text) rather than filling a popup surface,
so T1/T5 (which are about surface fill and text-on-surface, not text-on-accent) do not name them,
and changing them carries a real risk of illegible button text with no spec value to change it to.

## Execution Handoff

Plan complete and saved to
`docs/plans/2026-09-04-stage-2-theme-and-ui-split.md`.
