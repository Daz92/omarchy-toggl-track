# Panel redesign — design specification

**Date:** 2026-09-04
**Status:** awaiting review
**Baseline commit:** 65ae1c0
**Visual reference:** [`docs/design-guide.html`](design-guide.html)

---

## 1. Summary

The panel becomes one command line with three scopes — **timer**, **day**, **calendar** —
replacing the current two-tab layout, its four always-visible entry controls, and its
hidden search dropdown.

Day rows gain two distinct drawers: a read-only **inspect** drawer that reports what the
machine actually recorded, and an **edit** drawer that changes what gets written to Toggl.

A **calendar scope** shows a week, a fortnight or a month, with each range presenting the
detail its cell size honestly supports.

A **local classifier** — `llama-server` plus a 378 MB GGUF model, both installed by `setup` —
names and assigns day blocks in one grammar-constrained call per day load.

Alongside these, the spec fixes five theme-coordination defects, nine performance defects,
and one shipped setting that is broken in production.

It also adds a **24-hour ring-buffered log** in the install directory, and the **`build`
and `install` scripts** the plugin needs before it can be shared — a release gate that
refuses to tag a version that would not work once cloned, and a local install path for
development and offline use.

### Click cost

| Flow | Today | After |
| --- | --- | --- |
| Start a timer with project and task | 6 clicks | 0 (keybind, type, Enter) |
| Continue a recent entry | 2 clicks | 0 |
| Assign and apply one day block | 6 clicks + typing | 0 |
| Apply a full 10-block day | ~60 clicks + 10 descriptions | 1 |
| See what a block actually contained | not possible | 1 key |
| See the month | not possible | 1 key |

---

## 2. Goals

1. Reduce the common paths to zero clicks without removing any mouse path.
2. Separate reading from writing in the day view.
3. Make a month of tracked time visible in the panel.
4. Make the panel obey the theme the way the built-in shell plugins do.
5. Remove the measured sources of sluggishness without introducing a daemon.
6. Surface information the backend already computes and currently discards.

## 3. Non-goals

- No daemon. `toggl_api.py` continues to handle exactly one JSON request per process and exit.
- No third-party Python packages. Standard library only, network I/O via `urllib`.
- No editing or deleting of existing Toggl entries beyond the running timer.
- No cloud inference. Window titles do not leave the machine.
- No change to `segment_blocks`' grouping model. Blocks separated by a real pause stay.

---

## 4. Verified constraints

These were measured during design and they bound what the implementation may do.

### 4.1 Toggl rejects any `start_date` older than 91 days

Probed read-only against the live workspace through the repo's own `TogglClient`.

| Request | Result |
| --- | --- |
| 30-day window | 200, 69 entries, oldest 2026-08-05 |
| 90-day window | 200, 114 entries, oldest 2026-06-08 |
| 92-day window | 200, `start_date` 2026-06-04 |
| 93-day window | **400** |
| 180 / 365 / 730-day window | **400** |
| `start_date` −95d, no `end_date` | **400** |
| `since` −30d | 200, 72 entries |
| `since` −365d | **400** |

The server's own message, which `_http_message(400)` currently discards:

```
start_date must not be earlier than 2026-06-04
```

**`historyDays: 365` is therefore a broken setting shipped today.** It appears in
`manifest.json` defaults, in the settings `ButtonGroup`, and is accepted by
`_history_days`. Selecting it makes every `sync` fail with 400, and the panel reports
"Toggl request failed." with no indication of the cause.

The 1000-entry cap reported elsewhere by Toggl users could not be reproduced and is
unreachable: 90 days of this account is 114 entries, and the window cannot exceed 92 days.
It is dropped from the risk list.

### 4.2 `meta=true` returns the metadata inline

Confirmed field set on `GET /me/time_entries?meta=true`:

```
at, billable, client_id, client_name, description, duration, duronly, id, pid,
project_active, project_billable, project_color, project_id, project_name,
server_deleted_at, start, stop, tag_ids, tags, task_active, task_id, task_name,
tid, uid, user_avatar_url, user_id, user_name, wid, workspace_id
```

This replaces the five lookup maps built by `_metadata_maps` and supplies
`project_color` per entry, which the calendar needs.

### 4.3 The panel ignores the shell's surface colour roles

Counted in the current source:

| Usage | `Panel.qml` | built-in `dev-gallery` |
| --- | --- | --- |
| `Qt.darker(foreground, N)` | 21 | 0 |
| `Color.popups.*` | 0 | 3 |
| `Style.normalFill` / `hoverFill` / `selectedFill` | 0 | 5 |

`Color.popups.{background,text,border}` exists and every built-in popup surface uses it.

---

## 5. Architecture

No new components. The existing shape holds:

```
BarWidget.qml ──Loader──> Panel.qml ──Process(stdin/stdout JSON)──> toggl_api.py
                              │                                          │
                          Model.js                          Toggl API v9 (HTTPS)
                       (pure helpers)                   ActivityWatch (127.0.0.1:5600)
                                                        llama-server (127.0.0.1:8127)
```

`llama-server` joins ActivityWatch as a second localhost HTTP dependency reached with
`urllib`. It is optional: every feature degrades to its pre-classifier behaviour when the
server is absent.

`Panel.qml` is at 1525 lines and will grow. It is split into four files under a new
`ui/` directory, each owning one scope, with `Panel.qml` retaining panel state, request
dispatch and response handling:

| File | Owns |
| --- | --- |
| `Panel.qml` | state, `request()`, `handleResponse()`, the command line, scope switching |
| `ui/TimerScope.qml` | running strip, result rows |
| `ui/DayScope.qml` | day header, block rows, inspect and edit drawers |
| `ui/CalendarScope.qml` | the three ranges |
| `ui/PanelTheme.qml` | the colour roles of §9, as a singleton-style `QtObject` |

This split is part of the work, not a follow-up. Each scope file must stay under
roughly 400 lines.

---

## 6. The command line

One `TextField` at the top of the panel, focused when the panel opens.

### 6.1 Token grammar

| Sigil | Binds | Source |
| --- | --- | --- |
| `@name` | `project_id` | `projects`, active only |
| `@project/task` | `task_id` **and** `project_id` | `Model.tasksForProject()` |
| `#name` | appends to `tags[]` | `tags`, repeatable |
| `$` | toggles `billable` | no argument |
| everything unsigilled | `description` | — |

Rules:

1. `@project/task` always sets both ids. `start` and `continue` reject a task without a
   project — enforced by `test_start_rejects_task_without_project` and
   `test_continue_rejects_task_without_project`.
2. An unmatched `@` stays plain description text and never silently drops. The result row
   reads `no project` rather than guessing.
3. Completion is local. `projects`, `tasks` and `tags` are in memory after `sync`, so no
   keystroke starts a `Process`. This is required, not merely preferred: `request()`
   returns early while `requestPending` is set, so a per-keystroke request would be
   dropped silently.
4. The ghost suffix is the completion. `Tab` accepts it; `Enter` acts on the selected row.

### 6.2 Parsing

`Model.parseCommand(text, projects, tasks, tags)` is a new pure function returning:

```js
{
  description: String,
  projectId: Number,        // 0 when unset
  taskId: Number,           // 0 when unset
  tags: [String],
  billable: Boolean,
  completion: String,       // ghost suffix, "" when none
  unmatched: [String]       // sigil tokens that matched nothing
}
```

It is pure and lives in `Model.js` so it is covered by `tests/test_model.mjs`.

### 6.3 Scopes

Scope chips sit at the right of the input: `timer`, `day`, `cal`.

- `Ctrl+D` → day, `Ctrl+L` → calendar, `Ctrl+T` → timer.
- Typing filters within the current scope. Matching results from other scopes appear
  below, prefixed by their own glyph.
- The `TIMER`/`DAY` `ButtonGroup` is deleted. `Tab` cannot reach it — `onTabRequested`
  switches Omarchy panels, not tabs inside this one.
- `searchMode`, the search `PanelActionButton`, and the stranded search
  `SearchableDropdown` are deleted.

### 6.4 Result rows

One line each, 22 px, with a leading glyph encoding what `Enter` will do:

| Glyph | Row kind | `Enter` |
| --- | --- | --- |
| `↵` | compose from what is typed | `start` |
| `⟲` | past entry | `continue` |
| `▤` | project | scope the filter to it |
| `◷` | day block | jump to day scope, cursor on that block |

### 6.5 Fuzzy project and task resolution (R-S)

Added 2026-09-04. Supersedes §6.1's exact-match reading of `@name` and `@project/task`, and
§6.1 rule 4's ghost-completion behaviour for `@` tokens. The measured justification is in
ruling R-S; the short version is that `@` binds a whitespace-free token while 20 of the 25
active projects in the live workspace are multi-word, so the grammar could not express them.

**The `@` token is a query, not a name.** It stays whitespace-free. It is never required to
equal a project name, and no name is ever rewritten or abbreviated in the data.

#### `Model.scoreMatch(query, name)`

Pure, in `Model.js`, covered by `tests/test_model.mjs`. Returns a number; 0 means no match.
Rules, highest-scoring first, with a small penalty for longer names throughout so a specific
match outranks a general one:

1. the whole name starts with the query
2. any word starts with the query — earlier words score higher
3. the acronym of all word initials starts with the query
4. the acronym of SIGNIFICANT word initials starts with the query, dropping the stopwords
   `and of the for a to in on up &`
5. the acronym of a trailing run of words starts with the query, so a leading job code can be
   skipped
6. the query is a substring of some word, at a word boundary
7. the query is a substring anywhere
8. the query is a subsequence of the name

Rules 4 and 5 are load-bearing, not refinements. Without 4, `rd` ranks `Shipyard` above
`Research and Development` on the substring `…ya-rd`. Without 5, `nvt` cannot reach
`Northwind Voyager Testing` past its `NW-075` prefix. Rule 8 alone is unusable: it ranks
`Growth: Paper & Presentation Development` above `Travel Day` for `trav`.

#### Interaction

- Typing `@frag` ranks active projects and emits them as `▤ PROJ` rows, capped at the guide's
  8. `Enter` on one binds the project: the `@frag` token is removed from the command text
  exactly as a resolved sigil is today, and the binding shows in the START row's meta.
- **There is no ghost completion for an `@` token.** Completing to a name that contains spaces
  is the defect this section exists to remove — `Tab` must never insert one. `Tab` keeps its
  meaning for every other completion.
- With a project bound, a last token that **starts with `/`** ranks that project's tasks by the
  same function and emits them as `◈ TASK` rows **alongside** the CONT and BLOCK rows, never
  replacing them. A slash elsewhere in a word — `a/b`, `9/3`, `docs/readme` — is ordinary
  description text and triggers nothing. Binding a task follows the same rule.
- An `@frag` that scores nothing anywhere stays plain description text and the row reads
  `no project`, exactly as §6.1 rule 2 already requires. Nothing about the unmatched case
  changes.

#### Binding is state, not text

The defect has three faces and they share one cause: **the command text cannot carry a
multi-word name**, so anything that writes a name back into the text is circular.

1. `Tab` inserts the ghost, which is the full name — the parser then rejects it.
2. `Enter` on a `▤ PROJ` row calls `scopeToProject`, which writes
   `head + "@" + project.name` — same rejection.
3. Typing the name by hand — same rejection.

Therefore a resolved project and task live in **panel state**, not in the command text:

- `Panel.qml` gains `boundProjectId` and `boundTaskId`, both `0` when unset.
- `Enter` on a `▤ PROJ` row sets `boundProjectId`, clears `boundTaskId`, and REMOVES the
  `@frag` token from the command text. It never writes a name back.
- `Enter` on a `◈ TASK` row sets `boundTaskId` and removes the `/frag` token.
- The START row's effective ids are `boundProjectId || parsed.projectId` and
  `boundTaskId || parsed.taskId`, so a name typed out exactly still works and needs no
  special case.
- The binding is visible in the START row's meta, which already renders `project · task`.
- Clearing the command line clears both bindings. Selecting a different `▤ PROJ` row
  replaces the project and clears the task, since a task never outlives its project.

`Model.parseCommand` stays pure and text-only; it does not know about the bindings. The
panel composes the two.

#### What does not change

Names are never shortened in the data or in the API payloads. Display shortening remains
elision, as the guide specifies. `Model.parseCommand`'s return shape is unchanged, and its
`completion` field simply stays empty for `@` tokens.

---

## 7. Day scope

### 7.1 Row states

Six states, each a real branch in `Model.prepareBlocks()` or `blockReady()`.

| Glyph | State | Meaning |
| --- | --- | --- |
| `✓` | applied | an entry with `created_with: omarchy-toggl-track/...` covers the block |
| `●` | ready | description and project both set; `Enter` writes it |
| `●` + `~` | ready, guessed | classifier supplied the name or project; unconfirmed |
| `◌` | unassigned | falls back to the block's own topics |
| `▲` | conflict | a foreign entry overlaps; never written over |
| `◍` | in flight | `create_entry` is running for this row |

Applied and conflict must differ in glyph, colour **and** trailing text. They look alike
at a glance and mean opposite things.

### 7.2 Two drawers

`Space` opens **inspect**. `e` opens **edit**. The left rule is the entire signal:

- **Inspect** — dim rule, no focusable control, nothing writes.
- **Edit** — accent rule, bordered fields with focus rings.

Any number of drawers may be open. `toggleBlock()`'s current behaviour of collapsing every
sibling is removed.

The `Repeater` gotcha applies to both: a `Repeater` is not an `Item`, so `visible` does not
hide its output. Drawer contents must be gated on the **model**, as the existing topic
breakdown already is.

### 7.3 Inspect drawer contents

| Element | Source |
| --- | --- |
| facts line: active, wall, idle removed, switches, longest run | `seconds`, `span_seconds`, `idle_seconds`, `fragments`, `longest_fragment_seconds` |
| fragment timeline across the wall span, idle hatched | new `fragments` array (§10.3) |
| topic bars with seconds | `topics[]`, exists today |
| app bars with seconds | `apps[]`, **shape change** (§10.3) |
| domain bars with seconds | `domains[]`, **new** (§10.3) |
| written-entry id and `created_with`, when applied | `conflict` payload |

### 7.4 Edit drawer contents

Description field, a project/task field using the same token grammar as the command line,
and a one-line reminder that applying writes a completed historical entry.

Applying continues to use `create_entry`. It must never reuse `start` or `continue` —
both call `_stop_current` and would stop the running timer.

### 7.5 Keyboard

| Key | Action |
| --- | --- |
| `Space` | open or close the inspect drawer on the cursor row |
| `e` | open the edit drawer on the cursor row |
| `Enter` | apply the cursor row, when `blockReady()` |
| `Shift+Enter` | apply every ready row via `applyQueue` |
| `Backspace` | mark the row skipped for this session; it stays visible and still counts toward the day total |
| `Ctrl+J` / `Ctrl+K` | move the cursor |

`Shift+Enter` applies only rows that are ready. A guessed row is not ready until
confirmed, so a batch apply can never write an unreviewed guess.

Batch apply continues to drain an explicit `applyQueue` pumped from each `create_entry`
response, because `request()` handles one call at a time.

`PanelKeyCatcher` uses `Keys.priority: Keys.BeforeItem` and consumes `j k h l x`. It must
continue to be told to stand down via `blocked: root.editorFocused`, computed from
`keyCatcher.Window.activeFocusItem`. `Window` only attaches to an `Item`, so it must stay
attached to `keyCatcher` and not to the `KeyboardPanel`.

The inspect drawer contains no editors, so the catcher stays active while inspecting.

---

## 8. Calendar scope

Three ranges, cycled with `w` or by clicking the `W · 2W · M` chips. They differ in kind,
not only in scale — a smaller range buys more room per day.

### 8.1 Week

Seven day columns plus a 26 px hour gutter, with a vertical hour axis.

An entry is positioned at `top = (startHour - axisStart) * rowHeight` with
`height = durationHours * rowHeight`, coloured by `project_color`.

- Unassigned block: dashed border, no fill.
- Conflict: `Color.urgent` border with a diagonal hatch.
- Per-day totals sit under the columns.

#### Axis bounds, derived

The axis is not fixed at 08:00–19:00. `Model.axisBounds(entries, blocks, override)`
derives it from the data in the visible range:

```js
{ start: Number, end: Number, rowHeight: Number, derived: Boolean }
```

Rules, in order:

1. Take the earliest start and latest end across every entry **and** every unapplied
   block in the range — blocks count, or a day of unlogged early work would fall outside
   its own axis.
2. Floor the start to the hour, ceil the end to the hour.
3. Pad one hour each side, clamped to `[0, 24]`.
4. Enforce a minimum span of 6 hours, growing downward from the start first, then upward.
5. Enforce a maximum span of 16 hours. Beyond that the rows become unreadable, so the
   axis holds at 16 and the overflow clamps as below.
6. `rowHeight = round(156 / span)`, floored at 8 px.
7. An empty range falls back to 08:00–20:00 and sets `derived: false`.

The bounds recompute when the range changes. They do **not** recompute while the user
pages within the same range, which would make the grid jump under the cursor — paging
recomputes once, on arrival.

#### Axis bounds, overridden

Two settings, `calendarDayStart` and `calendarDayEnd`, hold integer hours or the string
`auto`. When either is an integer it wins over the derived value for that edge, so a
user can pin the start and leave the end automatic.

The override is edited in the calendar scope's settings section: two `NumberField`s
labelled *Day starts* and *Day ends*, plus a **Reset to automatic** action that writes
`auto` back to both. The current mode is stated in one line above them — either
*Automatic, from your tracked hours* or *Fixed, 07:00–21:00*.

Validation: `start < end`, both in `[0, 24]`, minimum span 4 hours. An invalid pair is
rejected at the field, not on save, and the previous value stands.

#### Overflow

An entry falling outside the axis — possible only when the bounds are overridden, since
the derived bounds always contain the data — clamps to the grid edge and draws a 2 px
marker on that edge. The axis does not scroll. A range containing any clamped entry shows
one line under the grid: *3 entries fall outside 07:00–21:00.*

### 8.2 Fortnight

Seven columns by two rows, 66 px cells, plus a week-total column. Each cell carries the
day number, the total, and a 9 px wall-time-ordered density strip in which breaks between
blocks are hatched.

### 8.3 Month

Seven columns by five or six rows, 50 px cells, plus a week-total column. Each cell
carries the day number, the total, and a 4 px project-colour stack. Untracked-but-recorded
time appears as a neutral segment, so a half-unassigned day looks half unassigned.

### 8.4 Flags and boundary

- `◌` — the day has ActivityWatch blocks nobody applied.
- `▲` — the day holds a conflict.

Nothing else is flagged.

`Enter` on a day switches to day scope for that date.

**The backward navigation control disables at the 91-day floor** and shows the reason. It
must not offer a move that would produce a 400. `Model.historyFloor(today)` returns the
earliest permitted date and is covered by a node test.

### 8.5 Project colours

Project colours come from Toggl, not from the theme. They are the only palette in the
panel a theme must not override, and they reach the panel via `project_color` from
`meta=true`.

---

## 9. Theme coordination

Five defects, all in `Panel.qml`.

| ID | Defect | Fix |
| --- | --- | --- |
| T1 | Panel paints with `bar.foreground` and `Color.background`, so a theme's `[popups]` block is ignored | Take `Color.popups.background` / `.text` / `.border` |
| T2 | Panel overrides the one correctly themed component, passing `foreground: root.foreground; background: Color.background` into all five `SearchableDropdown`s and replacing their own `Color.popups.*` defaults | Delete both overrides |
| T3 | 21 hand-rolled dim tiers via `Qt.darker()`, with 1.5 / 1.6 / 1.8 used inconsistently for the same semantic role and no theme token behind any of them | Three named roles built with `Util.alpha(Color.popups.text, …)` |
| T4 | Row hover and selection are hand-drawn | Use `Style.hoverFill` and `Style.selectedFill`, which carry the theme's `[controls]` alphas |
| T5 | `Color.background` forces the panel opaque while `popups.background-alpha` supports translucency | Use the composed role and inherit the alpha |

### 9.1 `ui/PanelTheme.qml`

```qml
QtObject {
    readonly property color surface: Color.popups.background
    readonly property color text:    Color.popups.text
    readonly property color edge:    Color.popups.border

    // Replaces every Qt.darker() call site. Alpha keeps the hue relationship
    // to whatever the theme sets; Qt.darker() does not.
    readonly property color textMuted:   Util.alpha(Color.popups.text, 0.72)
    readonly property color textFaint:   Util.alpha(Color.popups.text, 0.55)
    readonly property color textDisabled: Util.alpha(Color.popups.text, 0.38)

    readonly property color accent: Color.accent
    readonly property color urgent: Color.urgent
}
```

Every `Qt.darker(root.foreground, N)` call site maps to one of the three muted roles. A
grep for `Qt.darker` in `Panel.qml` and `ui/*.qml` must return zero after this work.

**Visible consequence:** `Color.popups.border` falls back to `Color.accent`, so under the
current `aether` theme the panel border becomes `#89b4fa`, matching every other popup in
the shell. This is the intended outcome, not a regression.

### 9.2 Values that stay fixed

`Style.cornerRadius` resolves to 0 under this theme; nothing in the panel is rounded.
All sizes come from `Style.font.*` and `Style.spacing.*`; no literals.

---

## 10. Backend changes

### 10.1 Action surface

| Action | Status |
| --- | --- |
| `bootstrap` | changed — folds in the first `sync` (§11.1) |
| `sync` | changed — `meta=true`, clamped days, entry cache, `since` delta |
| `start` `stop` `update` `continue` | unchanged |
| `day_activity` | changed — richer blocks, cached bucket ids, cached AW events |
| `create_entry` | unchanged |
| `range_entries` | **new** |
| `classify` | **new** |

### 10.2 `range_entries`

```
→ {"action":"range_entries","workspace_id":N,"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}
← {"ok":true,"data":{"entries":[…],"start_date":…,"end_date":…,"clamped":false}}
```

- `start_date` is clamped to `today - 91`. When clamping occurs, `clamped` is `true` and
  the panel says so rather than showing a silently short range.
- A request whose `end_date` precedes the floor returns a `ValidationError`, not a 400
  from Toggl.
- The range is capped at 92 days.

### 10.3 `day_activity` block schema

Additive except for `apps`.

```json
{
  "start": "…", "end": "…",
  "seconds": 8712, "span_seconds": 9660,
  "idle_seconds": 948,
  "fragments": 63,
  "longest_fragment_seconds": 660,
  "label": "segment_blocks — toggl_api.py",
  "topics":  [{"name": "…", "seconds": 4320}],
  "apps":    [{"name": "dev.zed.Zed", "seconds": 5640}],
  "domains": [{"name": "bitbucket.org", "seconds": 1740}],
  "domain":  "bitbucket.org",
  "timeline": [{"offset": 0, "seconds": 840, "topic": "…", "idle": false}],
  "applied": false
}
```

- `apps` changes from `[String]` to `[{name, seconds}]`. `Model.prepareBlocks` passes it
  through untouched and nothing renders it today, so no consumer breaks — but the change
  is noted here because it is the one non-additive edit.
- `domains` is the weight map `segment_blocks` already builds and then discards, keeping
  only `max()`. `domain` is retained for compatibility.
- `fragments` and `longest_fragment_seconds` are two counters over `group["members"]`.
- `idle_seconds` is `span_seconds - seconds`.
- `timeline` is capped at 200 entries per block; beyond that, adjacent same-topic
  fragments merge until the cap is met.

All of these are computed inside the existing loop over `group["members"]`. No extra pass.

### 10.4 `classify`

```
→ {"action":"classify","workspace_id":N,
   "blocks":[{"index":0,"label":"…","topics":[…],"apps":[…],"domains":[…],"seconds":N}],
   "projects":[{"id":N,"name":"…","client":"…"}]}
← {"ok":true,"data":{"results":[{"index":0,"description":"…","project_id":N,"confidence":0.0}],
                     "model":"qwen3-0.6b","elapsed_ms":N}}
```

- **One call per day load**, every block in the same prompt. Never one call per row.
- Sent to `POST http://127.0.0.1:8127/v1/chat/completions` with
  `response_format: {"type": "json_schema", "json_schema": {…}}`.
- `project_id` is constrained by the schema to an **enum of the ids actually supplied**,
  plus `null`. The model cannot name a project that does not exist.
- `description` is constrained to a string with a maximum length.
- Timeout 20 s for the whole batch. On timeout, connection refused, or any non-200, the
  action returns `{"ok": true, "data": {"results": []}}` with a `degraded` flag. It is not
  an error: the day still loads with topic labels and stays fully editable.
- The classifier is never invoked by `create_entry`. Nothing it produces reaches Toggl
  without a confirmation.

### 10.5 Prompt and schema

The prompt contains, per block: the ranked topic names with seconds, the app names, the
domain names, and the duration. It contains the project list as `id — name (client)`.
It contains no window titles beyond what `_topic()` already normalised.

The schema:

```json
{
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
          "description": {"type": "string", "maxLength": 120},
          "project_id": {"enum": [/* supplied ids */, null]},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    }
  }
}
```

### 10.6 Installation

`setup` gains a second, skippable stage after the token prompt.

| Piece | Choice | Size |
| --- | --- | --- |
| Runtime | `llama.cpp` `llama-server` | ~5 MB |
| Model | `unsloth/Qwen3-0.6B-GGUF` → `Qwen3-0.6B-Q4_K_M.gguf` | 396,705,472 bytes |

- The runtime is taken from the distribution package where available, and from an upstream
  release binary otherwise.
- The model is written to `$XDG_DATA_HOME/omarchy-toggl-track/models/`. This is **data**,
  not cache: it must not go under `$XDG_CACHE_HOME`, which is TTL'd and safe to delete.
- The download is verified against a pinned SHA-256 before first use. A mismatch aborts
  and leaves no partial file in place.
- A `systemd --user` unit runs `llama-server` on `127.0.0.1:8127`. The unit is installed
  but only enabled when the user opts in.
- `setup` must remain runnable to completion with the classifier declined. Declining is
  the default on a non-interactive run.

Rejected: **Ollama**, roughly 1 GB installed for one endpoint. **gemma-3-270m-qat**
(230 MB), built for fine-tuning and weak at zero-shot instruction following.

### 10.7 Performance fixes

| ID | Fix |
| --- | --- |
| P1 | `bootstrap` performs the first `sync` in the same process. One Python start and one `secret-tool` call on open instead of two. |
| P2 | `sync` uses `since` for delta refresh once a full window is cached, clamped to the 91-day floor. |
| P3 | Entries join the TTL cache as a new `entries` kind, keyed by workspace and window. |
| P4 | ActivityWatch bucket ids cache for 24 h; they are stable. |
| P5 | Raw ActivityWatch events cache per date for 10 minutes, so changing the break setting re-segments without re-fetching. `segment_blocks` stays the single implementation. |
| P6 | `day_activity` accepts the day's entries from the caller instead of refetching them. |
| P7 | `searchItems()` stops calling `normalizeProject` / `normalizeTask`; `applyData` already normalised both on arrival. One-line change, per-keystroke effect. |
| P8 | `request()` queues instead of silently dropping. A bounded queue of 8, coalescing duplicate actions, with the pending action shown. |
| P9 | `daySummary` is computed incrementally on mutation rather than recomputed across all blocks on every `dayRevision` bump. |

All cached values remain derivable and disposable. Nothing durable enters the cache.

### 10.8 Logging

The plugin writes a log so a user reporting a problem has something to attach, and so the
performance claims in §10.7 can be checked rather than believed.

#### Location

`<plugin dir>/logs/toggl.jsonl`, where the plugin dir is
`os.path.dirname(os.path.abspath(__file__))` — the directory
`omarchy plugin add` cloned into, normally
`~/.config/omarchy/plugins/daz.toggl-track/`.

Two consequences of putting logs inside the install directory, both accepted:

1. **In a dev install the plugin dir is a symlink into the git working tree**, which is
   the current setup here. `logs/` must be added to `.gitignore` in the same change, or
   every log write dirties the repo.
2. **`omarchy plugin remove` deletes the logs with the plugin.** That is the correct
   behaviour for a log that belongs to the install.

`logs/` is created on first write with mode `0700`. If the directory cannot be created or
written — a read-only install, a permissions problem — logging disables itself silently
for that process and the request proceeds. **Logging never raises into the request path.**

#### Format

One JSON object per line, so the file is greppable, tailable, and parseable without a
reader.

```json
{"ts":"2026-09-04T09:14:22.108Z","lvl":"info","action":"sync","ms":412,"ok":true,
 "http":[{"path":"/me/time_entries","status":200,"ms":244,"bytes":48210}],
 "cache":{"workspace":"fresh","entries":"miss"},"counts":{"entries":114,"projects":37}}
```

Common fields: `ts` (RFC 3339, UTC, milliseconds), `lvl`, `action`, `ms`, `ok`.
Event-specific fields are added flat alongside. Errors carry `status` and `error`.

#### Levels

| Level | Emits |
| --- | --- |
| `off` | nothing; the file is not created |
| `errors` | failures only |
| `info` | **default** — one record per action, with timings, HTTP statuses, cache states and counts |
| `debug` | adds ActivityWatch bucket ids, per-block segmentation timings, and the classifier prompt and response |

#### Redaction

Enforced at the writer, not left to call sites.

- The API token is never logged in any form, at any level. The existing guarantee that it
  never reaches a URL, argv or log is extended by a test over the log writer.
- Window titles, topic names, entry descriptions and project names are **not logged at
  `info`**. Counts and durations are. This matters: the whole reason classification is
  local is that titles do not leave the machine, and a log in the install directory would
  quietly undo that.
- `debug` does log them, and the settings control says so plainly.
- Any string field is truncated to 500 characters.

#### Ring buffer

Bounded by **age first, size second**.

- Appends use a single `write()` on a file opened `O_APPEND`, which is atomic for records
  of this size. No lock is taken on the common path.
- When the file exceeds `LOG_MAX_BYTES` (1 MiB), the writing process takes an exclusive
  `fcntl.flock`, rewrites the file keeping only records with `ts` within the last
  **24 hours**, and releases.
- If the file still exceeds 1 MiB after that prune, the oldest surviving records are
  dropped until it fits. Age is the primary bound; size is the backstop.
- A malformed line is dropped during the prune rather than aborting it.
- Pruning happens at most once per process, after the record is appended, so it never
  delays the response.

At `info`, one record per action and a few actions per panel open, 1 MiB holds far more
than 24 hours — the size bound will rarely be the one that fires.

#### Panel-side events

`Panel.qml` does not write files. Events worth recording that never reach the helper —
a dropped request, a queue overflow, a QML-side parse failure — accumulate in a bounded
in-memory array of 32 and ride along on the next request as an optional `client_log`
field. The helper flushes them into the same file with `"src":"qml"`. This costs no extra
process.

### 10.9 Settings

| Key | Today | After |
| --- | --- | --- |
| `historyDays` | 30 / 90 / **365** | 30 / 60 / 90 |
| `dayBlockMinutes` | 2 / 5 / 10 / 15 | unchanged |
| `idleReminderMinutes` | unchanged | unchanged |
| `calendarRange` | — | `week` / `fortnight` / `month`, default `fortnight` |
| `calendarDayStart` | — | integer hour or `auto`, default `auto` |
| `calendarDayEnd` | — | integer hour or `auto`, default `auto` |
| `classifier` | — | `off` / `local`, default `off` |
| `logLevel` | — | `off` / `errors` / `info` / `debug`, default `info` |

`_history_days` clamps any value above 92 down to 90 and rejects nothing, so a stored
`365` from an existing install silently becomes 90 on first load rather than erroring.
`Model.clampHistory` mirrors this.

---

## 11. Error handling

| Condition | Behaviour |
| --- | --- |
| `start_date` older than the floor | Clamped before the request; the panel states the clamp. Never a 400. |
| Toggl 400 | Surface the server's own message. `_http_message` stops replacing 400 bodies with a generic string. |
| `llama-server` unreachable | `classify` returns `degraded`; the day loads with topic labels. No error banner. |
| Model file missing | Same as unreachable. `setup` is suggested once, not on every load. |
| ActivityWatch unreachable | Unchanged: the day scope shows its existing guidance. |
| `create_entry` overlap rejected | Unchanged: the row moves to conflict and keeps the server message. |
| Mutation timeout or 5xx | Unchanged: **never retried.** A resent POST creates a duplicate entry. |

---

## 12. Testing

### Python — `tests/test_toggl_api.py`

- `range_entries` clamps `start_date` to the floor and sets `clamped`.
- `range_entries` rejects a range entirely below the floor with `ValidationError`.
- `_history_days` clamps 365 to 90 rather than raising.
- Block schema: `apps`, `domains`, `fragments`, `longest_fragment_seconds`,
  `idle_seconds` and `timeline` all present, with `idle_seconds == span_seconds - seconds`.
- `timeline` never exceeds 200 entries.
- `classify` returns `degraded` on connection refused, on timeout, and on a non-200.
- `classify` never emits a `project_id` outside the supplied set, given a stub server that
  tries to.
- The classifier is not reachable from `create_entry`.
- Existing guarantees retained: mutations do not retry on 5xx or timeout; the token never
  reaches a request URL.

Logging:

- A record is appended for each action, with `ok`, `ms` and the HTTP statuses.
- The token never appears in the log, for a successful request and for every error path.
- At `info`, no window title, topic name, entry description or project name is written.
- At `debug`, they are.
- Every string field is truncated to 500 characters.
- Crossing 1 MiB prunes to records within 24 hours; records older than 24 hours are gone
  and newer ones survive.
- When pruning to 24 hours still leaves the file over 1 MiB, the oldest survivors are
  dropped until it fits.
- A malformed line is dropped during a prune without aborting it.
- An unwritable `logs/` directory disables logging and the action still succeeds.
- `client_log` entries from the panel are flushed with `"src":"qml"`.

### Node — `tests/test_model.mjs`

- `parseCommand` for each sigil, for `@project/task`, for repeated `#tag`, for an
  unmatched `@`, and for a bare description.
- `parseCommand` never returns a `taskId` without a `projectId`.
- `historyFloor` returns `today - 91`.
- `clampHistory` maps 365 to 90.
- `searchItems` no longer re-normalises; passing pre-normalised input is stable.
- `axisBounds` pads one hour each side and floors/ceils to the hour.
- `axisBounds` includes unapplied blocks, not only entries.
- `axisBounds` enforces the 6-hour minimum and the 16-hour maximum span.
- `axisBounds` returns 08:00–20:00 with `derived: false` for an empty range.
- An integer `calendarDayStart` overrides while `calendarDayEnd` stays `auto`.
- An override with `start >= end`, or a span under 4 hours, is rejected.

### QML

`qmlformat Panel.qml >/dev/null` and each new `ui/*.qml` file, checked by exit status.
Never pipe `qmllint` and read `$?` — it writes nothing on failure, so a broken file
reads as green.

`BarWidget.qml` stays hand-reviewed. Both tools reject `function open(): void`, which
Quickshell's `IpcHandler` requires.

### Manual

Editing QML requires `omarchy-restart-shell`. A `reloadConfig` keeps the plugin's `Loader`
alive, so a panel edit does not appear. `rescanPlugins` is not in this shell's IPC surface
at all and exits 0 regardless.

After a restart, check `qs -p /usr/share/omarchy/shell log` for `qt.qml.context` warnings.
Every signal handler must declare its parameters — `onChanged: function(value) { … }`.

---

## 13. Build, install and distribution

### 13.1 What already exists

Omarchy distributes plugins as **git repositories**, not archives:

- `omarchy plugin add <git-url>` clones into a staging directory under
  `~/.config/omarchy/plugins/`, validates the manifest, and moves it to
  `~/.config/omarchy/plugins/<manifest.id>/`.
- `omarchy plugin update [id]` pulls git-managed plugins.
- `omarchy plugin enable <id> [placement]` and `disable`, `remove`, `list` complete the set.
- `omarchy plugin validate <folder>` checks the manifest against the schema. The repo
  passes today, exit 0.

So there is no packaging format to invent and no installer to write for the normal path.
What the repo is missing is a **release gate** — something that refuses to tag a version
that would not work once cloned — and a **local install** path for development and for
offline use.

### 13.2 `build`

A release gate, not a compilation step. There is nothing to compile: QML and Python ship
as source. `build` exits non-zero on the first failure and prints what failed.

1. `omarchy plugin validate .`
2. `python3 -m py_compile toggl_api.py tests/test_toggl_api.py`
3. `python3 -m unittest discover -s tests`
4. `node tests/test_model.mjs`
5. `bash -n setup build install`
6. `qmlformat` over `Panel.qml` and every `ui/*.qml`, **checked by exit status, never by
   piping**. `qmllint` writes nothing on failure, so `qmllint x.qml | tail` returns
   *tail's* status and a broken file reads as green.
7. `BarWidget.qml` is skipped by both tools and listed as hand-review-required, because
   `function open(): void` is rejected by `qmlformat` and required by `IpcHandler`.
8. Assert the working tree is clean and that `manifest.json`'s `version` is not already a
   git tag.
9. Assert nothing that must not ship is tracked: no `logs/`, no `*.gguf`, no
   `__pycache__/`, no token anywhere in the tree.
10. Write `dist/omarchy-toggl-track-<version>.tar.gz` and a `SHA256SUMS` beside it, for
    offline install and for release attachments. This is a convenience artifact; the git
    URL remains the supported install path.

`build --check` runs steps 1–9 and skips the artifact, for use in a pre-commit hook or CI.

### 13.3 `install`

For people not installing from git, and for development.

```
install                  # copy the working tree into ~/.config/omarchy/plugins/daz.toggl-track
install --dev            # symlink it instead, for editing in place
install --enable         # also run: omarchy plugin enable daz.toggl-track center
install --uninstall      # remove the install, keeping the token and cache (logs too, but only for --dev)
install --uninstall --purge   # also remove the secret, the cache and the model
```

- The target directory is derived from `manifest.json`'s `id`, never hard-coded, so
  renaming the plugin cannot leave an orphan.
- Refuses to overwrite an existing non-symlink install without `--force`, and says which
  one is there.
- `--dev` reproduces the symlink currently in place by hand, so the existing setup keeps
  working and is no longer undocumented.
- After installing it prints the one remaining manual step: `omarchy-restart-shell`. A
  `reloadConfig` keeps the plugin's `Loader` alive and a panel edit will not appear;
  `rescanPlugins` is not in this shell's IPC surface at all and exits 0 regardless, so it
  is indistinguishable from success and must not be suggested.
- It does not run `setup`. Token entry and the optional model download stay a separate,
  explicit step.

### 13.4 `setup`, revisited

`setup` keeps the token prompt and gains the skippable classifier stage of §10.6. It
becomes idempotent and re-runnable: an existing token is detected and kept unless
`--reset` is passed, and an already-downloaded model is verified against its checksum
rather than re-fetched.

### 13.5 Repository requirements for sharing

- `README.md` gains an install section leading with
  `omarchy plugin add <git-url> --enable`.
- `.gitignore` gains `logs/`, `dist/` and `*.gguf`.
- `manifest.json` gains the new settings of §10.9 with their defaults, so a fresh clone
  starts in a valid state.
- The model is never committed. It is 378 MB and it is downloaded by `setup`.
- `LICENSE` is already MIT and stays.

## 14. Sequencing

Each stage leaves the plugin working.

0. **Tooling and logging.** §13.2 `build`, §13.3 `install`, and the §10.8 logger with its
   `.gitignore` entry. First, because `build` is the gate every later stage is checked by,
   and because the logger is how the §10.7 performance claims get verified instead of
   asserted.
1. **Backend truth.** §10.7 P1–P9, the §10.3 block schema, `_history_days` clamping, the
   `historyDays` setting change, `meta=true`. Ships as a pure improvement with no UI change.
2. **Theme coordination.** §9 in full, including `ui/PanelTheme.qml` and the file split.
   Zero `Qt.darker` afterwards.
3. **Command line and scopes.** §6, the timer scope, deletion of the tab strip, the
   search button, and `searchMode`.
4. **Day drawers.** §7, inspect and edit, no accordion.
5. **Calendar.** §8 and `range_entries`.
6. **Classifier.** §10.4–10.6 and the `setup` stage.

Stage 6 is the only one that adds a dependency. Stages 1 and 2 are worth doing regardless
of whether the rest proceeds.

---

## 15. Resolved and open questions

**Resolved.**

1. **Week-scope hour range.** Derived from the data, with an explicit user override.
   Specified in §8.1.

**Open, both accepted as-is.**

2. **`create_entry` date floor.** The 91-day floor was measured on reads. Whether writes
   have their own limit is untested, so the calendar can page to a day it may not be able
   to write to. One probe, before stage 5. Not a blocker for stages 1–4.
3. **`llama-server` residency.** A persistent user unit holds roughly 500 MB (cpu profile) or 1.5 GB, mostly VRAM (gpu profile, ruling R-AM). Socket
   activation with an idle stop would free it between day loads at the cost of a reload
   pause on the next one. Deferred to stage 6, where it can be measured rather than
   guessed.
