# Panel Redesign — Stage 3: The Command Line and Scopes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TIMER/DAY tab strip and the always-visible PROJECT/TASK/TAGS/Billable
controls with one token-grammar command line and a three-way scope switch (`timer` / `day` /
`cal`). Delete the dead search feature. Demote the 24px `PanelHero` elapsed-time display to the
11px running strip. Ship `Model.parseCommand` and `Model.clockDuration` as pure, tested
functions so stage 4 and stage 5 inherit them instead of inventing their own.

**Depends on:** Stage 2 (merged before this plan executes). This plan consumes, without
modifying: `ui/PanelTheme.qml` (the `surface/text/edge/textMuted/textFaint/textDisabled/
accent/urgent` colour-role `QtObject`, spec §9.1), the `ui/` file split (`ui/TimerScope.qml`,
`ui/DayScope.qml`, `ui/CalendarScope.qml` already exist as stubs Panel.qml instantiates), and
the removal of `Qt.darker()` from every call site this stage touches (stage 2's own baseline;
this stage must not add a new one — see the open question on `warn`/`ok` colour roles below).

**Architecture:** No new components beyond what stage 2 created. `Panel.qml` keeps owning
state, `request()`/`handleResponse()`, the command-line `TextField`, and scope switching.
`ui/TimerScope.qml` owns the running strip, the result-row list and the hint bar, driven
entirely by properties `Panel.qml` computes and passes in. All grammar and row-composition
logic lives in `Model.js`, covered by `tests/test_model.mjs` — nothing in this stage is logic
that only a running Quickshell process could exercise, except the coloured-text overlay and
key bindings, which are qmlformat/`omarchy plugin validate`/visual-only per this repo's
standing constraint that there is no QML test harness.

**Tech Stack:** QML/Quickshell for `Panel.qml` and `ui/TimerScope.qml`. Node for `Model.js`
tests (`tests/test_model.mjs`). No Python changes in this stage.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §6
**Rulings:** [`docs/2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — R-B, R-C, R-D, R-E, R-G, R-H, R-I, R-O bind this stage
**Visual acceptance reference:** [`docs/design-guide.html`](../design-guide.html) §01 ("Timer scope")

## Pre-flight amendments (2026-09-04, against merged stage 2 at `a4c5a7e`)

This plan was written against a *predicted* stage 2, not the one that shipped. Four
defects were found by checking it against the merged tree. **These amendments bind; where
they and the task text below disagree, these win.**

### P1 · Task 1 Steps 3-4 encode the superseded R-D. Use R-D2.

The task text calls `compactDuration` "the hybrid `45m`/`2h25` formatter". It is not.
`Model.js:26-33` renders `2h 25m` — hours, space, minutes, `m` suffix — and the design
guide contains **zero** spaced `Xh Ym` strings (`grep -c "h [0-9]\+m" docs/design-guide.html`
returns 0). Task 1's own tests never assert `compactDuration` at or above an hour, so the
wrong claim would have survived them.

Per **R-D2** (see the rulings file, section 6):

- Author `clockDuration(seconds)` → always `HhMM`, zero-padded, hours uncapped
  (`0h00`, `0h50`, `2h25`, `96h40`). Keep Step 3's implementation, but replace its comment
  block, which cites the wrong sibling.
- Author `rowDuration(seconds)` → bare minutes under an hour, `clockDuration` at or above
  (`45m`, `16m`, `2h25`). Used by the CONT rows and, in stage 4, the facts line.
- **Delete `compactDuration` and its two tests.** Replace Step 4 entirely: instead of
  re-commenting `compactDuration`, remove it, drop it from the test harness export list,
  and migrate its three call sites — `ui/DayScope.qml:72` (day header total), `:181`
  (block duration) and `:319` (inspect app lines) — to `clockDuration`. The guide renders
  all three zero-padded, `0h14` included. Do not keep it as a spare: a formatter whose
  output the guide never shows is a trap for stages 4-6.
- Any task text below that names `compactDuration` as a consumer (Task 2's Interfaces
  block, its harness export list, and its row-composition code) means `rowDuration`.

`formatDuration` (`HH:MM:SS`, the running timer label) is untouched and unrelated.

### P2 · `Panel.qml` does not instantiate `CalendarScope`. This stage must add it.

The Depends-on block claims all three scope files "already exist as stubs Panel.qml
instantiates". `grep -n CalendarScope Panel.qml` returns nothing — stage 2 created the file
under R-A but wired nothing. `Panel.qml` instantiates `PanelTheme` (:721), `TimerScope`
(:1050) and `DayScope` (:1057) only.

No task below adds it, so as written the `cal` chip would switch to a blank body. **Task 3
gains a step:** instantiate `CalendarScope` beside `DayScope`, gated
`visible: root.scope === "cal"`, passing `root` and `panelTheme` exactly as its siblings do.
R-E's "empty settings section is acceptable" covers the settings column, not a body that
does not exist.

### P3 · The `activeTab` rename must span `ui/*.qml`, and so must its verification.

Task 3 Step 2 enumerates lines in `Panel.qml` only, and Step 4 verifies with
`grep -c activeTab Panel.qml`. Two more references live outside that file:
`ui/DayScope.qml:13` and `ui/TimerScope.qml:18`, both `visible: root.activeTab === "..."`.
Renaming only in `Panel.qml` leaves both bound to an undefined property, which evaluates
false — the day scope would become permanently invisible while every gate stayed green.
Task 3's own Step 4 acceptance ("DAY scope must look and behave exactly as before") would
fail, but only under a shell restart, and only if someone switched scopes.

Rename across `Panel.qml` and `ui/*.qml`, and verify with
`grep -c activeTab Panel.qml ui/*.qml` — every file must report `0`.

### P4 · Stale line numbers and two "stub" claims.

The stage 2 final-review fix wave (`a560b11`..`02925fe`) shifted every line number in
`Panel.qml` and `ui/*.qml` by a few lines. **Treat every `file:line` below as a hint and
locate by content.** Two specific claims are wrong rather than merely stale: Task 5 calls
`ui/TimerScope.qml` "stage 2's stub" and lists "instantiate `TimerScope`" as work.
`ui/TimerScope.qml` is 317 lines and already instantiated at `Panel.qml:1050`; Task 5
rewrites it in place and adds no instantiation.

### P5 · Tasks 5 and 6 assume a file layout stage 2 changed. They must merge.

Both tasks place the legacy composer in `Panel.qml`: Task 5 lists "Modify `Panel.qml` —
instantiate `TimerScope`, remove `PanelHero`" and points at a `PanelHero` block "at
`Panel.qml:1038-1055`"; Task 6 targets "everything between the `TimerScope`..." at
`Panel.qml:1057-1203`. **None of it is in `Panel.qml`.** Stage 2 moved every one of those
controls into `ui/TimerScope.qml`, where they sit today: `PanelHero` at :29, the project and
task `SearchableDropdown`s at :80 and :103, the tags `MultiSelect` at :127, the Billable
`Toggle` at :136, and the stranded search `SearchableDropdown` at :145.

What `Panel.qml` kept is the *state and the wiring*: `searchMode` (:32), `searchOpen` (:33),
`selectedProjectId` (:34), the `searchResults` and `projectTasks` bindings (:74-75), and
eighteen sites reaching into the view through five `readonly property alias` exposures that
`ui/TimerScope.qml` declares at :12-16 (`descriptionField`, `projectDropdown`, `taskDropdown`,
`tagsField`, `searchDropdown`).

That coupling is what breaks the split. Task 5 says "replace the stub's contents entirely" —
correct for the real file, but doing so deletes those five aliases, and `Panel.qml`'s eighteen
references to them do not go away until Task 6. **Task 5 as written leaves a panel that does
not load**, which violates the requirement that every task end with an independently testable
deliverable, and Task 5's own acceptance step (restart the shell, confirm the timer scope
renders) could not pass.

**Ruling: Tasks 5 and 6 merge into one dispatch.** A view and the state that drives it cannot
be removed in separate commits when the view owns the accessors the state reaches through.
There is no reviewer verdict that accepts one and rejects the other. The merged task rewrites
`ui/TimerScope.qml` wholesale (running strip, result rows, hint bar — Task 5's content) and, in
the same commit, removes from `Panel.qml` the composer state, the `searchMode`/`searchOpen`/
`selectedProjectId` properties, the dead search bindings, and every one of the eighteen alias
reference sites (Task 6's content). Task 6's own deletion targets are then re-located by
content in `ui/TimerScope.qml` rather than by the line numbers it quotes for `Panel.qml`.

Task 6's `Panel.qml`-resident targets — the `searchMode` property, the search
`PanelActionButton`, and the scope `ButtonGroup` — are real and stay as Task 6 describes them.

---

## Global Constraints

Every task's requirements implicitly include all of these.

- **QML: multi-line, one property per line.** Run `qmlformat -n -i` after editing.
- **No `;` after an object member in QML.** `Item { Text {} ; Text {} }` is a parse error and
  both `qmllint`/`qmlformat` report it with **zero output**. If a file fails to parse silently,
  look for `};` between sibling objects first.
- **Never pipe `qmllint` and read `$?`.** It writes nothing on failure, so `qmllint x.qml | tail`
  returns *tail's* exit status. Check status directly, or use `qmlformat`.
- **QML signal handlers declare their parameters.** `onChanged: function(value) { … }`, never the
  injected form.
- **`BarWidget.qml` cannot be gated by either QML tool** and is not touched by this stage at all
  — it is hand-reviewed only to confirm R-O (below) still holds.
- **A `Repeater` is not an `Item`.** `visible` does not hide its output — gate on the model.
- **`PanelKeyCatcher` (vendored at `/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml`, not part of
  this repo and not editable) consumes `j k h l x`, Tab, Return/Enter, Space and Escape before a
  focused editor sees them,** via `KeyboardPanel { focusTarget: keyCatcher }` — this is a
  Quickshell keyboard-grab mechanism, not ordinary Qt focus-chain delivery, and it is why
  `blocked: root.editorFocused` exists. **This stage's command-line `TextField` is itself a
  `TextInput`, so once it has focus `root.editorFocused` becomes true and `PanelKeyCatcher`
  stands down almost permanently** (the command line is focused by default per R3-1 and stays
  focused through normal use). See Task 4's design note — this is why Ctrl+D/L/T/J/K, Tab and
  Enter are bound directly on the command-line field's own `Keys.onPressed`/`onAccepted` rather
  than through `PanelKeyCatcher`'s signals, and why this is a deliberate, documented deviation
  from R-C's literal "lives on the shared `PanelKeyCatcher`" wording — see Open Question 1.
- **`Style.cornerRadius` resolves to 0.** Nothing is rounded, anywhere this stage draws a
  `Rectangle`.
- **Theme values come from `Style.*`, `Color.*` and `ui/PanelTheme.qml`, never `Qt.darker()`.**
  This stage introduces new UI; every colour in it must resolve through one of those three, with
  one confirmed exception — see Open Question 2 (`warn`/`ok` token colours have no existing
  role anywhere in this shell).
- **Colour-role mapping used throughout this stage** (guide token → this repo's real value).
  **CORRECTED 2026-09-04 — this table originally mapped `--dim18` to `textFaint` and omitted
  `--dim16` entirely, contradicting the table stage 2 published at
  `docs/plans/2026-09-04-stage-2-theme-and-ui-split.md:429-438`. Stage 2's table is
  authoritative: `ui/DayScope.qml` already obeys it, and `textFaint` at alpha 0.55 composites
  to a 0.616 channel scale against the guide's `--dim16` at 0.625 — near-exact. The wrong
  table here is why `textFaint` was asked to serve two different guide tiers, a defect no
  per-task reviewer could see without reading another stage's plan.**
  `--fg` → `PanelTheme.text`; `--dim15` → `PanelTheme.textMuted`; `--dim16` →
  `PanelTheme.textFaint`; `--dim18` → `PanelTheme.textDisabled`; `--accent` → `PanelTheme.accent` (identical to `Color.accent`);
  `--fill-selected` → `Style.selectedFill`; `--fill-hover` → `Style.hoverFill`; `--fill-normal`
  → `Style.normalFill`.
- **`docs/design-guide.html` is the acceptance reference for every rendered value** — pixel,
  token, glyph, copy string, keybinding. Where this plan and that page disagree, the page wins
  and the disagreement is a bug in this plan, not something to guess past.
- **There is no QML test harness in this repository.** Do not invent one. QML verification is
  `qmlformat` exit 0, `omarchy plugin validate .` exit 0, and a shell restart plus visual check
  against the guide. Logic that can be tested lives in `Model.js` and is pushed there
  deliberately, exactly as this stage's assignment requires.
- **Editing QML requires `omarchy-restart-shell`,** never `reloadConfig` or `rescanPlugins` (the
  latter is not in this shell's IPC surface and exits 0 regardless of whether anything happened).
- **Never let a keystroke start a `Process`.** Every completion/filter/result-row update is a
  pure `Model.*` call over `root.projects`/`root.tasks`/`root.tags`/`root.entries`/
  `root.dayBlocks`, all already in memory after `sync`/`bootstrap`/`day_activity` (R3-5).
- Each task must end with a working plugin — `qmlformat` and `omarchy plugin validate .` both
  exit 0, and the panel opens without a blank/broken screen. No task may leave the panel unable
  to load.

## File Structure

| File | Responsibility |
| --- | --- |
| `Model.js` | modified — `parseCommand`, `commandSegments`, `clockDuration`, `commandRows` (all new, all pure) |
| `tests/test_model.mjs` | modified — coverage for all four new functions |
| `Panel.qml` | modified — `scope` (renamed from `activeTab`), the command-line `TextField`, scope chips, key bindings, `dayCursorIndex`, row-action dispatch functions; legacy composer/search/tab-strip deleted |
| `ui/TimerScope.qml` | modified — stage 2's stub filled in: running strip, result-row `Repeater`, hint bar |

---

### Task 1: `Model.js` — the token grammar and the two duration formatters

**Files:**
- Modify: `Model.js`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Consumes: `tasksForProject`, `normalizeProject`, `normalizeTask`, `number` (all pre-existing,
  same file, called unqualified).
- Produces: `Model.parseCommand(text, projects, tasks, tags)` → `{ description, projectId,
  taskId, tags, billable, completion, unmatched }` exactly per spec §6.2/R3-7. `Model.
  commandSegments(text)` → `[{ text, cls }]` where `cls` is `"plain" | "proj" | "tag" | "bill"`,
  purely syntactic (no project/task lookup), consumed by Task 4's coloured-text overlay.
  `Model.clockDuration(seconds)` → always-hour, zero-padded `"HhMM"` string (R-D).

This task adds no consumer yet — nothing in the running panel calls these functions until Task
2 (`commandRows`, which calls `parseCommand`) and Task 4 (the command line, which calls
`commandSegments` and reads `parsed.completion`). That is deliberate and safe: these are pure
additions to a `.pragma library` file with no side effects, so the plugin's current behaviour is
untouched until later tasks wire them in.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model.mjs`. First widen the destructured export list at the top of the
file:

```js
const Model = new Function(`${source}\nreturn {
  compactDuration, clockTime, isoDate, todayDate, shiftDate, dayLabel,
  prepareBlocks, blockAlso, blockSummary, formatDuration, clampHistory,
  clampBlockMinutes, historyFloor, boundedShiftDate,
  searchItems, normalizeProject, normalizeTask, normalizeTag, applySummaryDelta,
  parseCommand, commandSegments, clockDuration
}`)()
```

Then append these tests (before the trailing `if (failures) { ... }` block):

```js
const projects = [
  Model.normalizeProject({ id: 1, name: "acme", client_name: "Acme Corp", active: true }),
  Model.normalizeProject({ id: 2, name: "backoffice", client_name: "Acme Corp", active: true }),
  Model.normalizeProject({ id: 3, name: "zeta", client_name: "Zeta Inc", active: false }),
]
const tasks = [
  Model.normalizeTask({ id: 10, project_id: 1, name: "backend", active: true }),
  Model.normalizeTask({ id: 11, project_id: 1, name: "frontend", active: true }),
]

test("parseCommand: @name binds project_id", () => {
  const result = Model.parseCommand("refactor @acme", projects, tasks, [])
  assert.equal(result.projectId, 1)
  assert.equal(result.taskId, 0)
  assert.equal(result.description, "refactor")
  assert.deepEqual(result.unmatched, [])
})

test("parseCommand: @project/task binds task_id and project_id together", () => {
  const result = Model.parseCommand("refactor @acme/backend", projects, tasks, [])
  assert.equal(result.projectId, 1)
  assert.equal(result.taskId, 10)
  assert.equal(result.description, "refactor")
})

test("parseCommand: #tag is repeatable", () => {
  const result = Model.parseCommand("fix bug #urgent #followup", projects, tasks, [])
  assert.deepEqual(result.tags, ["urgent", "followup"])
  assert.equal(result.description, "fix bug")
})

test("parseCommand: $ toggles billable, recomputed fresh each call", () => {
  const once = Model.parseCommand("consulting $", projects, tasks, [])
  assert.equal(once.billable, true)
  assert.equal(once.description, "consulting")
  const twice = Model.parseCommand("consulting $ $", projects, tasks, [])
  assert.equal(twice.billable, false)
})

test("parseCommand: an unmatched @ stays plain description text, never dropped", () => {
  const result = Model.parseCommand("meeting @nonexistent", projects, tasks, [])
  assert.equal(result.projectId, 0)
  assert.equal(result.description, "meeting @nonexistent")
  assert.deepEqual(result.unmatched, ["@nonexistent"])
})

test("parseCommand: a bare description has no sigils at all", () => {
  const result = Model.parseCommand("just typing away", projects, tasks, [])
  assert.equal(result.description, "just typing away")
  assert.equal(result.projectId, 0)
  assert.equal(result.taskId, 0)
  assert.deepEqual(result.tags, [])
  assert.equal(result.billable, false)
  assert.equal(result.completion, "")
  assert.deepEqual(result.unmatched, [])
})

test("parseCommand: taskId is never nonzero while projectId is 0 -- a matched project with an unresolved task binds neither", () => {
  const result = Model.parseCommand("@acme/doesnotexist", projects, tasks, [])
  assert.equal(result.projectId, 0)
  assert.equal(result.taskId, 0)
  assert.deepEqual(result.unmatched, ["@acme/doesnotexist"])
})

test("parseCommand: an inactive project never binds, even on an exact name match", () => {
  const result = Model.parseCommand("old work @zeta", projects, tasks, [])
  assert.equal(result.projectId, 0)
  assert.deepEqual(result.unmatched, ["@zeta"])
})

test("parseCommand: ghost completion on a trailing partial project name", () => {
  const result = Model.parseCommand("refactor @ac", projects, tasks, [])
  assert.equal(result.completion, "me")
  assert.equal(result.projectId, 0, "not bound until the ghost is accepted")
  assert.equal(result.description, "refactor @ac", "unresolved token stays in the text")
})

test("parseCommand: ghost completion on a trailing partial task name, matching the guide's own example", () => {
  const result = Model.parseCommand("refactor @acme/back", projects, tasks, [])
  assert.equal(result.completion, "end")
  assert.equal(result.taskId, 0)
})

test("parseCommand: no ghost once the trailing token is followed by a space", () => {
  const result = Model.parseCommand("refactor @ac ", projects, tasks, [])
  assert.equal(result.completion, "")
  assert.deepEqual(result.unmatched, ["@ac"])
})

test("commandSegments: colours the @ sigil and its whole token as one span, including the @", () => {
  const segments = Model.commandSegments("refactor @acme/back")
  assert.deepEqual(segments, [
    { text: "refactor ", cls: "plain" },
    { text: "@acme/back", cls: "proj" },
  ])
})

test("commandSegments: #tag and bare $ each get their own class", () => {
  const segments = Model.commandSegments("fix #urgent now $")
  assert.deepEqual(segments, [
    { text: "fix ", cls: "plain" },
    { text: "#urgent", cls: "tag" },
    { text: " now ", cls: "plain" },
    { text: "$", cls: "bill" },
  ])
})

test("clockDuration: always hour-and-minutes, zero-padded, matching the guide's day rows", () => {
  assert.equal(Model.clockDuration(0), "0h00")
  assert.equal(Model.clockDuration(3000), "0h50")
  assert.equal(Model.clockDuration(8700), "2h25")
  assert.equal(Model.clockDuration(29100), "8h05")
})

test("clockDuration and compactDuration deliberately disagree under an hour -- see R-D", () => {
  assert.equal(Model.compactDuration(3000), "50m")
  assert.equal(Model.clockDuration(3000), "0h50")
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node tests/test_model.mjs`
Expected: `FAIL` on every test added in Step 1 (the destructured names are `undefined`), all
other pre-existing tests still `ok`.

- [ ] **Step 3: Implement `parseCommand`**

In `Model.js`, add after `clampReminder` at the end of the file:

```js
// Token grammar for the command line (spec S6.1 / rulings R-C, R-D context).
// Pure: no Process, no QML access -- covered by tests/test_model.mjs.
//
//   @name          -> project_id, exact case-insensitive match against an
//                      active project's name
//   @project/task  -> project_id AND task_id together, via tasksForProject();
//                      never partially bound -- either both ids land or
//                      neither does (see the taskId-without-projectId test)
//   #name          -> appended to tags[], repeatable, never gated on the
//                      known tags[] list -- Toggl auto-creates a new tag on
//                      submit, and neither the spec nor the guide define an
//                      "unmatched tag" UX the way rule 2 defines one for @
//                      (see this plan's open questions)
//   $              -> toggles billable; recomputed fresh from the whole
//                      string on every call (an odd number of bare "$"
//                      tokens means true), so this stays pure
//   everything else -> description
//
// An unmatched @ (rule 2) is left untouched in the description and its raw
// text (with the @) is also reported in `unmatched`, so a result row can
// read "no project" instead of guessing (R3-4/R3-31).
//
// `completion` is the ghost suffix (R3-6): only the trailing token, with no
// trailing whitespace after it, is ever "in progress". A trailing @token
// that prefixes exactly one active project (or, once the project part is an
// exact match, exactly one of that project's tasks) is left unbound and
// unflagged as unmatched, with its ghost in `completion`. Zero prefix
// matches means "wrong", not "still typing" -- that lands in `unmatched`.
function parseCommand(text, projects, tasks, tags) {
  text = String(text || "")
  projects = projects || []
  tasks = tasks || []

  var activeProjects = projects.filter(function(p) { return p.active })
  var parts = text.split(/(\s+)/)
  var words = []
  for (var i = 0; i < parts.length; i += 2) {
    if (parts[i] !== "") words.push({ index: i, text: parts[i] })
  }
  var endsWithSpace = /\s$/.test(text)

  var projectId = 0
  var taskId = 0
  var tagList = []
  var billable = false
  var unmatched = []
  var completion = ""
  var keep = parts.slice()

  words.forEach(function(word, wi) {
    var isLast = !endsWithSpace && wi === words.length - 1
    var w = word.text

    if (w.charAt(0) === "@") {
      var frag = w.slice(1)
      var slash = frag.indexOf("/")
      var projFrag = slash === -1 ? frag : frag.slice(0, slash)
      var taskFrag = slash === -1 ? "" : frag.slice(slash + 1)
      var exactProject = activeProjects.filter(function(p) {
        return String(p.name).toLowerCase() === projFrag.toLowerCase()
      })[0]

      if (exactProject && slash === -1) {
        projectId = Number(exactProject.id) || 0
        taskId = 0
        keep[word.index] = ""
        return
      }

      if (exactProject) {
        var projTasks = tasksForProject(tasks, exactProject.id)
        var exactTask = projTasks.filter(function(t) {
          return String(t.name).toLowerCase() === taskFrag.toLowerCase()
        })[0]
        if (exactTask) {
          projectId = Number(exactProject.id) || 0
          taskId = Number(exactTask.id) || 0
          keep[word.index] = ""
          return
        }
        if (isLast) {
          if (taskFrag.length === 0) return
          var taskPrefixes = projTasks.filter(function(t) {
            return String(t.name).toLowerCase().indexOf(taskFrag.toLowerCase()) === 0
          })
          if (taskPrefixes.length === 1) {
            completion = taskPrefixes[0].name.slice(taskFrag.length)
            return
          }
        }
        unmatched.push(w)
        return
      }

      if (isLast && slash === -1) {
        if (projFrag.length === 0) return
        var projPrefixes = activeProjects.filter(function(p) {
          return String(p.name).toLowerCase().indexOf(projFrag.toLowerCase()) === 0
        })
        if (projPrefixes.length === 1) {
          completion = projPrefixes[0].name.slice(projFrag.length)
          return
        }
      }
      unmatched.push(w)
      return
    }

    if (w.charAt(0) === "#") {
      var tagName = w.slice(1)
      if (tagName.length) tagList.push(tagName)
      keep[word.index] = ""
      return
    }

    if (w === "$") {
      billable = !billable
      keep[word.index] = ""
      return
    }
  })

  var description = keep.join("").replace(/\s+/g, " ").trim()

  return {
    description: description,
    projectId: projectId,
    taskId: taskId,
    tags: tagList,
    billable: billable,
    completion: completion,
    unmatched: unmatched
  }
}

// Purely syntactic highlighting for the command line's live text (R3-21/
// R3-22): colours follow the sigil characters as typed, regardless of
// whether the token actually resolves to a real project/task/tag -- that
// resolution is parseCommand's job, not this one. Needs no projects/tasks/
// tags list at all.
function commandSegments(text) {
  text = String(text || "")
  var parts = text.split(/(\s+)/)
  var segments = []
  var plain = ""
  function flushPlain() {
    if (plain) { segments.push({ text: plain, cls: "plain" }); plain = "" }
  }
  parts.forEach(function(part) {
    if (part === "") return
    if (/^\s+$/.test(part)) { plain += part; return }
    if (part.charAt(0) === "@") { flushPlain(); segments.push({ text: part, cls: "proj" }); return }
    if (part.charAt(0) === "#") { flushPlain(); segments.push({ text: part, cls: "tag" }); return }
    if (part === "$") { flushPlain(); segments.push({ text: part, cls: "bill" }); return }
    plain += part
  })
  flushPlain()
  return segments
}

// The always-hour, zero-padded formatter used by day rows, the day header,
// the facts line and calendar totals (e.g. "0h50", "8h05"). compactDuration
// (above) is the hybrid "45m"/"2h25" formatter used by CONT rows and the
// running strip's own duration badges. The two differ on purpose -- see R-D
// in docs/2026-09-04-stage-2-6-rulings.md -- do not unify them.
function clockDuration(seconds) {
  seconds = Math.max(0, Math.floor(number(seconds, 0)))
  var hours = Math.floor(seconds / 3600)
  var minutes = Math.round((seconds % 3600) / 60)
  if (minutes === 60) { hours += 1; minutes = 0 }
  return hours + "h" + String(minutes).padStart(2, "0")
}
```

- [ ] **Step 4: Point `compactDuration` at its sibling**

`compactDuration` (existing, `Model.js:26-33`) gets the other half of the R-D comment. Replace
its current one-line-above context:

```js
function compactDuration(seconds) {
```

with:

```js
// The hybrid "45m"/"2h25" formatter used by CONT rows and the running
// strip's own duration badges. clockDuration (below) is the always-hour,
// zero-padded formatter used by day rows, the day header, the facts line
// and calendar totals. The two differ on purpose -- see R-D in
// docs/2026-09-04-stage-2-6-rulings.md -- do not unify them.
function compactDuration(seconds) {
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node tests/test_model.mjs`
Expected: `all model checks passed`, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add Model.js tests/test_model.mjs
git commit -m "feat(model): add parseCommand, commandSegments and clockDuration"
```

---

### Task 2: `Model.js` — composing the command-line result rows

**Files:**
- Modify: `Model.js`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Consumes: `Model.parseCommand` (Task 1), `searchItems`, `compactDuration`, `clockDuration`
  (Task 1), `clockTime`, `isoDate`, `todayDate`, `dayLabel` (all pre-existing or Task 1, same
  file).
- Produces: `Model.commandRows(text, projects, tasks, tags, entries, blocks, now)` → `[{ glyph,
  verb, label, meta, kind, target }]`, `kind` one of `"start" | "continue" | "project" |
  "block"`. This is the array named in the stage's `interfaces_produced` as "command-line result
  rows" — Task 5 renders it, Task 4's Enter handler dispatches on `.kind`, and a BLOCK-kind row's
  `.target` is the exact object reference living in `root.dayBlocks`, so `indexOf` on it in Task
  4's jump-to-day handler is reliable.

Row composition rules, derived from R3-12 (cross-scope results), R3-16/17 (glyph/verb/action
table) and R3-30/R3-31 (the guide's two worked examples):

- **Empty text:** no START row (nothing to start). Up to 3 recent entries as CONT rows, plus the
  single nearest not-yet-applied day block as a BLOCK row if one exists. This is this plan's own
  resolution of a gap the guide leaves open — see this plan's open questions.
- **Text contains `@`:** exactly a START row (label = the text *before* the last `@`, trimmed —
  not `parsed.description`, which still carries an unresolved `@` token verbatim per rule 2 and
  would otherwise leak half-typed sigil text into what Enter is about to submit; meta = the
  bound project/task from `parsed.projectId`/`parsed.taskId` or `"no project"` when the token
  hasn't resolved) followed by one PROJ row per active project whose `Model.projectSearchText`
  contains the fragment after that last `@`, up to the part before any `/` (R3-30 — reusing
  `projectSearchText` is what makes a client-name-only fragment like `Corp` surface every project
  under that client, even one that doesn't share the fragment in its own name). Capped at 8 rows,
  matching this codebase's existing `topics.slice(0, 8)` convention. No CONT, no BLOCK rows in
  this branch — they are day/entry-continuation results, orthogonal to "which project do you
  mean."
- **Text has no `@`:** a START row (label = verbatim `parsed.description`, meta = `"no project"`
  since `projectId` is necessarily 0 with no `@`), then the single best-matching recent entry as
  a CONT row and the single best-matching not-yet-applied day block as a BLOCK row, each omitted
  when there is no match (R3-31). The BLOCK row here **is** the cross-scope result R3-12
  describes — it originates from day scope's own data and carries its own glyph, even while
  `root.scope === "timer"`. Stage 5's calendar scope has no queryable content yet (R-A), so
  nothing from `cal` is ever cross-surfaced by this stage.

- [ ] **Step 1: Write the failing tests**

Widen the destructured export list again:

```js
const Model = new Function(`${source}\nreturn {
  compactDuration, clockTime, isoDate, todayDate, shiftDate, dayLabel,
  prepareBlocks, blockAlso, blockSummary, formatDuration, clampHistory,
  clampBlockMinutes, historyFloor, boundedShiftDate,
  searchItems, normalizeProject, normalizeTask, normalizeTag, applySummaryDelta,
  parseCommand, commandSegments, clockDuration, commandRows
}`)()
```

Append:

```js
function block(overrides) {
  return Object.assign({
    start: "2026-09-04T09:20:00.000Z", end: "2026-09-04T11:45:00.000Z",
    seconds: 8700, label: "Refactor day segmentation", state: "pending", topics: [],
  }, overrides)
}
function entry(overrides) {
  return Object.assign({
    id: 1, description: "Reviewing PRs", projectId: 1, projectName: "acme",
    taskId: 10, taskName: "backend", start: "2026-09-04T11:50:00.000Z",
    stop: "2026-09-04T12:40:00.000Z",
  }, overrides)
}

test("commandRows: empty text has no START row, up to 3 recent entries, one nearest open block", () => {
  const entries = [entry({ id: 1 }), entry({ id: 2 }), entry({ id: 3 }), entry({ id: 4 })]
  const blocks = [block({ state: "applied" }), block({ state: "pending" })]
  const rows = Model.commandRows("", projects, tasks, [], entries, blocks, Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0)
  assert.equal(rows.filter((r) => r.kind === "continue").length, 3)
  const blockRows = rows.filter((r) => r.kind === "block")
  assert.equal(blockRows.length, 1)
  assert.equal(blockRows[0].target.state, "pending")
})

test("commandRows: @ present -> START + PROJ rows only, matched via projectSearchText on the client name", () => {
  // "Corp" is a fragment of the shared client name ("Acme Corp") and is not
  // itself a prefix of either project's own name, so parseCommand leaves it
  // unbound (meta stays "no project") while the row composer still surfaces
  // both of that client's projects via projectSearchText, exactly as R3-30
  // describes for a client-name-only fragment.
  const rows = Model.commandRows("refactor @Corp", projects, tasks, [], [], [], Date.now())
  assert.equal(rows[0].kind, "start")
  assert.equal(rows[0].label, "refactor", "the label is the text before the @, not parsed.description -- an unresolved @ token must not show up as a comedy of garbled text in what START is about to submit")
  assert.equal(rows[0].meta, "no project")
  const projRows = rows.filter((r) => r.kind === "project")
  assert.deepEqual(projRows.map((r) => r.target.id).sort(), [1, 2], "both acme projects match the client-name fragment")
})

test("commandRows: no @ -> START + best CONT + best BLOCK, matching the guide's worked example", () => {
  const entries = [entry({ id: 1, description: "Reviewing PRs" })]
  const blocks = [block({ label: "Reviewing PRs", start: "2026-09-04T11:50:00.000Z", seconds: 3000, state: "pending" })]
  const rows = Model.commandRows("Reviewing", projects, tasks, [], entries, blocks, Date.now())
  assert.equal(rows[0].kind, "start")
  assert.equal(rows[0].label, "Reviewing")
  assert.equal(rows[1].kind, "continue")
  assert.equal(rows[1].label, "Reviewing PRs")
  assert.equal(rows[2].kind, "block")
  assert.equal(rows[2].meta.indexOf("0h50"), 0, "BLOCK rows use clockDuration's always-hour form, not compactDuration's")
})

test("commandRows: a START row with a bound project shows 'project · task' in meta, not 'no project'", () => {
  const rows = Model.commandRows("refactor @acme/backend", projects, tasks, [], [], [], Date.now())
  assert.equal(rows[0].meta, "acme · backend")
})

test("commandRows: an applied block never surfaces as a BLOCK row match", () => {
  const blocks = [block({ label: "Reviewing PRs", state: "applied" })]
  const rows = Model.commandRows("Reviewing", projects, tasks, [], [], blocks, Date.now())
  assert.equal(rows.filter((r) => r.kind === "block").length, 0)
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node tests/test_model.mjs`
Expected: `FAIL commandRows: ...` for every new test (the function does not exist yet).

- [ ] **Step 3: Implement**

Append to `Model.js`, after `clockDuration`:

```js
function taskNameById(tasks, taskId) {
  if (!taskId) return ""
  var match = (tasks || []).filter(function(t) { return Number(t.id) === Number(taskId) })[0]
  return match ? match.name : ""
}

function projectMeta(projects, tasks, projectId, taskId) {
  if (!projectId) return "no project"
  var project = (projects || []).filter(function(p) { return Number(p.id) === Number(projectId) })[0]
  var pname = project ? project.name : ""
  var tname = taskNameById(tasks, taskId)
  return tname ? pname + " · " + tname : pname
}

function startRow(parsed, projects, tasks) {
  return {
    glyph: "↵", verb: "START",
    label: parsed.description || "",
    meta: projectMeta(projects, tasks, parsed.projectId, parsed.taskId),
    kind: "start", target: parsed
  }
}

function continueRow(entry, now) {
  var seconds = durationSeconds(entry, now)
  return {
    glyph: "⟲", verb: "CONT",
    label: entry.description || "(no description)",
    meta: (entry.projectName || "No project") + (entry.taskName ? " · " + entry.taskName : "") + "  " + compactDuration(seconds),
    kind: "continue", target: entry
  }
}

function projectMatches(projects, fragment) {
  fragment = String(fragment || "").toLowerCase()
  if (!fragment) return []
  return projects.filter(function(p) {
    return p.active && projectSearchText(p).indexOf(fragment) !== -1
  }).sort(function(a, b) {
    return String(a.name).localeCompare(String(b.name))
  }).slice(0, 8)
}

function projectRow(project, entries) {
  var count = (entries || []).filter(function(e) { return Number(e.projectId) === Number(project.id) }).length
  return {
    glyph: "▤", verb: "PROJ",
    label: (project.clientName ? project.clientName + " / " : "") + project.name,
    meta: count + " entries",
    kind: "project", target: project
  }
}

// The nearest not-yet-applied block whose label matches query (or, with an
// empty query, simply the nearest not-yet-applied block). Blocks arrive in
// chronological order from Model.prepareBlocks, so the last pending match is
// the nearest one to "now".
function bestOpenBlock(blocks, query) {
  query = String(query || "").trim().toLowerCase()
  var candidates = (blocks || []).filter(function(block) {
    return block.state !== "applied" && (!query || String(block.label || "").toLowerCase().indexOf(query) !== -1)
  })
  return candidates.length ? candidates[candidates.length - 1] : null
}

function blockRow(block) {
  var start = new Date(block.start)
  var day = isFinite(start.getTime()) ? isoDate(start) : ""
  return {
    glyph: "◷", verb: "BLOCK",
    label: clockTime(block.start) + " " + (block.label || "(untitled)"),
    meta: clockDuration(block.seconds) + "  " + (day === todayDate() ? "today" : dayLabel(day)),
    kind: "block", target: block
  }
}

// Composes the command-line result rows shown in timer scope (spec S6.4,
// R3-12, R3-30, R3-31). Consumes parseCommand's output plus the same
// in-memory lists Panel.qml already holds after sync -- no Process call,
// ever (spec S6.1 rule 3).
function commandRows(text, projects, tasks, tags, entries, blocks, now) {
  text = String(text || "")
  var trimmed = text.trim()
  var parsed = parseCommand(text, projects, tasks, tags)
  var rows = []

  if (!trimmed.length) {
    searchItems(entries, projects, tasks, "", "all", 0).recentEntries.slice(0, 3).forEach(function(entry) {
      rows.push(continueRow(entry, now))
    })
    var idleBlock = bestOpenBlock(blocks, "")
    if (idleBlock) rows.push(blockRow(idleBlock))
    return rows
  }

  if (trimmed.indexOf("@") !== -1) {
    // The START row's label is the text before the @, not parsed.description
    // -- an @ token that has not (yet) resolved is still sitting verbatim in
    // parsed.description (parseCommand never drops it, per rule 2), and
    // showing that raw, half-typed sigil text in what Enter is about to
    // submit would be wrong. meta still comes from parseCommand's own
    // resolution, so a token that DOES exactly resolve shows its real
    // project/task here, matching R3-30.
    var at = text.lastIndexOf("@")
    rows.push({
      glyph: "↵", verb: "START",
      label: text.slice(0, at).trim(),
      meta: projectMeta(projects, tasks, parsed.projectId, parsed.taskId),
      kind: "start", target: parsed
    })
    var fragment = text.slice(at + 1).split(/\s+/)[0].split("/")[0]
    projectMatches(projects, fragment).forEach(function(project) {
      rows.push(projectRow(project, entries))
    })
    return rows
  }

  rows.push(startRow(parsed, projects, tasks))
  var contEntry = searchItems(entries, projects, tasks, trimmed, "all", 0).entries[0]
  if (contEntry) rows.push(continueRow(contEntry, now))
  var openBlock = bestOpenBlock(blocks, trimmed)
  if (openBlock) rows.push(blockRow(openBlock))
  return rows
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node tests/test_model.mjs`
Expected: `all model checks passed`, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add Model.js tests/test_model.mjs
git commit -m "feat(model): compose command-line result rows from parseCommand"
```

---

### Task 3: `Panel.qml` — rename `activeTab` to `scope`, re-gate settings for three scopes

**Files:**
- Modify: `Panel.qml`

**Interfaces:**
- Produces: `root.scope` (`"timer" | "day" | "cal"`), replacing `root.activeTab`. Consumed by
  Task 4/5 of this stage and, per the stage sequencing in the rulings, by stage 4's `ui/
  DayScope.qml` and stage 5's `ui/CalendarScope.qml` visibility gating.

This task is a mechanical, behaviour-preserving rename plus one new branch (R-E). It claims the
settings `ColumnLayout` (`Panel.qml:906-1024` today) for this stage, as the rulings require, and
leaves a **working, unbroken** panel for `scope === "cal"` even though stage 5 has not landed —
an empty settings section for that scope is correct, not a bug.

- [ ] **Step 1: Rename the property**

```qml
    property string activeTab: "timer"
```

becomes:

```qml
    property string scope: "timer"
```

- [ ] **Step 2: Rename every other occurrence**

There are 20 remaining lines referencing `activeTab` in the current file (some with two
occurrences on one line). Replace `root.activeTab` → `root.scope` and the two bare `activeTab`
references (inside `handleResponseBody`, where `root.` is implicit) → `scope`, at every one of:
`Panel.qml:668, 672, 849, 851, 852, 864, 867, 871, 912, 917, 926, 940, 949, 958, 967, 976, 985,
994, 1004, 1012, 1027, 1327`. None of these change behaviour beyond the rename — every
`"timer"`/`"day"` comparison and every `.toLowerCase()` assignment stays exactly as it reads
today, just spelled `scope` instead of `activeTab`.

Two of these need care because they read `root.activeTab` twice on one line — do not
accidentally leave one occurrence renamed and the other not:

```qml
                                tooltipText: root.activeTab === "day" ? "Reload day" : "Refresh"
                                foreground: Color.accent
                                onClicked: root.activeTab === "day" ? root.loadDay() : root.sync(true, false)
```

```qml
                                tooltipText: root.scope === "day" ? "Reload day" : "Refresh"
                                foreground: Color.accent
                                onClicked: root.scope === "day" ? root.loadDay() : root.sync(true, false)
```

(This one deliberately keeps its binary `day` vs. everything-else shape — `cal` scope also gets
a plain metadata refresh via `sync(true, false)`, a safe default with no `cal`-specific refresh
defined yet.)

- [ ] **Step 3: Add the third branch to the settings section header**

`Panel.qml:911-914` today:

```qml
                            PanelSectionHeader {
                                text: root.activeTab === "day" ? "DAY SETTINGS" : "TIMER SETTINGS"
                                foreground: root.foreground
                            }
```

becomes:

```qml
                            PanelSectionHeader {
                                text: root.scope === "day" ? "DAY SETTINGS" : (root.scope === "cal" ? "CALENDAR SETTINGS" : "TIMER SETTINGS")
                                foreground: root.foreground
                            }
```

No content is added for `scope === "cal"` in this stage — R-E is explicit that an empty section
is acceptable here, and stage 5 supplies the calendar's own controls. Every existing `visible:
root.scope === "timer"` / `"day"` child in this `ColumnLayout` (renamed in Step 2) already
naturally hides itself for `"cal"`, so no additional `visible` guard is needed to keep the
binding non-broken.

- [ ] **Step 4: Verify**

Run: `qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo $?`
Run: `grep -c activeTab Panel.qml`
Expected: `qmlformat` exits 0; the grep returns `0` (every occurrence renamed).
Run: `omarchy plugin validate .; echo $?`
Expected: exits 0.
Restart the shell (`omarchy-restart-shell`) and open the panel: TIMER and DAY scopes must look
and behave exactly as before this task (this is a pure rename), and there must be no QML
warnings in `qs -p /usr/share/omarchy/shell log` about an undefined `scope`/`activeTab`.

- [ ] **Step 5: Commit**

```bash
git add Panel.qml
git commit -m "refactor(panel): rename activeTab to scope, add the cal branch"
```

---

### Task 4: `Panel.qml` — the command-line `TextField`

**Files:**
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `Model.parseCommand`, `Model.commandSegments`, `Model.commandRows` (Tasks 1-2),
  `ui/PanelTheme.qml` (stage 2).
- Produces: `root.commandText` (string), `root.commandParsed` (readonly, `Model.parseCommand`
  output), `root.commandRows` (readonly, `Model.commandRows` output), `root.resultCursorIndex`
  (int, clamped selection into `commandRows`), `root.dayCursorIndex: -1` (R-B — declared here,
  meaning assigned to by this stage; stage 4 of the redesign, i.e. the day-scope work that comes
  *after* this plan, is what makes the value mean anything for cursor movement or drawer
  targeting). Also produces `root.setScope(name)`, `root.moveResultCursor(delta)`, `root.
  acceptCompletion()`, `root.activateSelectedRow()` and the row-kind dispatch functions
  `root.startFromCommand(parsed)`, `root.scopeToProject(project)`, `root.jumpToBlock(block)`.

This task **adds** the command line and its result list alongside the still-present legacy
composer controls (`descriptionField`, the `SearchableDropdown`s, etc. — untouched by this
task). That is deliberate: it keeps every task in this plan landing a strictly-working,
never-regressed panel, and confines the risky "delete the old thing" step to Task 6, after the
replacement is proven. Expect the panel to look briefly redundant (two ways to start a timer)
between this task and Task 6 — that is expected, not a bug to fix here.

**Design note — why Ctrl+D/L/T/J/K, Tab and Enter are NOT wired through `PanelKeyCatcher`'s
signals, despite R-C's "lives on the shared PanelKeyCatcher" wording:** `PanelKeyCatcher` (the
vendored, unmodifiable component at `/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml`) only
recognises bare `j`/`k`/`h`/`l`/`x`/Tab/Return/Escape/Space; it has no modifier-key awareness at
all — `event.text === "j"` does not match when Ctrl is held (that key combination's `event.text`
is a control character, not `"j"`), so a Ctrl+J keypress falls through every one of its
conditions untouched. Worse, since the command-line field is a real `TextInput` (needed for
proper cursor/selection/IME/backspace behaviour — `PanelKeyCatcher`'s own `textKey` signal has no
way to represent Backspace at all, so hand-rolling text entry through it is not viable), it will
have focus for essentially the entire time the panel is open, which makes `root.editorFocused`
true and `PanelKeyCatcher` stand down almost permanently once this task lands (exactly the
existing, verified `blocked: root.editorFocused` behaviour from the day-slot editors, applying
here too — this must hold, or the letters `j`/`k`/`h`/`l`/`x` could never be typed into the
command line). **This plan honours R-C's actual intent** — one shared, scope-conditioned dispatch
point that stage 4 of the redesign slots `dayScope.moveCursor()` into without re-wiring anything
— **by putting the `switch (root.scope)` in a plain `Panel.qml` function** (`root.
moveResultCursor`/`root.setScope`, see Step 3), called from the command-line field's own `Keys.
onPressed` instead of from a `PanelKeyCatcher` signal. This is flagged for confirmation in this
plan's open questions.

- [ ] **Step 1: Add the new properties**

After `property string activeTab: "timer"` was renamed to `scope` in Task 3, add these
properties immediately below it in `Panel.qml`:

```qml
    property string commandText: ""
    property int resultCursorIndex: 0
    property int dayCursorIndex: -1
    readonly property var commandParsed: Model.parseCommand(root.commandText, root.projects, root.tasks, root.tags)
    readonly property var commandRows: Model.commandRows(root.commandText, root.projects, root.tasks, root.tags, root.entries, root.dayBlocks, Date.now())
```

- [ ] **Step 2: Add the row-action functions**

Add these functions near `continueEntry` (existing, `Panel.qml:407-412`):

```qml
    function setScope(name) {
        if (["timer", "day", "cal"].indexOf(name) === -1) return;

        root.scope = name;
        if (name === "day" && !root.dayLoaded)
            root.loadDay();

    }

    function moveResultCursor(delta) {
        // Stage 4 of the redesign slots dayScope.moveCursor() into this
        // same switch for root.scope === "day" -- see R-C. Do not re-wire
        // the caller when that lands; add the branch here.
        if (root.scope !== "timer") return;

        var count = root.commandRows.length;
        if (!count) return;
        root.resultCursorIndex = (root.resultCursorIndex + delta + count) % count;
    }

    function acceptCompletion() {
        var completion = root.commandParsed.completion;
        if (completion) root.commandText = root.commandText + completion;
    }

    function startFromCommand(parsed) {
        if (!parsed.description.trim() && !parsed.projectId) return;

        request("start", {
            "description": parsed.description,
            "project_id": parsed.projectId || null,
            "task_id": parsed.taskId || null,
            "tags": parsed.tags,
            "billable": parsed.billable,
            "workspace_id": root.selectedWorkspaceId
        });
        root.commandText = "";
    }

    function scopeToProject(project) {
        var at = root.commandText.lastIndexOf("@");
        var head = at === -1 ? root.commandText : root.commandText.slice(0, at);
        root.commandText = head + "@" + project.name;
        root.resultCursorIndex = 0;
    }

    function jumpToBlock(block) {
        // dayDate is left untouched: a BLOCK-kind row only ever comes from
        // root.dayBlocks, which already belongs to root.dayDate, so there is
        // nothing to reconcile.
        root.scope = "day";
        root.dayCursorIndex = root.dayBlocks.indexOf(block);
    }

    function activateSelectedRow() {
        var row = root.commandRows[root.resultCursorIndex];
        if (!row) return;

        if (row.kind === "start")
            root.startFromCommand(row.target);
        else if (row.kind === "continue")
            root.continueEntry(row.target);
        else if (row.kind === "project")
            root.scopeToProject(row.target);
        else if (row.kind === "block")
            root.jumpToBlock(row.target);

    }
```

- [ ] **Step 3: Reset the result cursor whenever the text or the row list changes**

Add near the other single-purpose `on...Changed` handlers (e.g. next to `onSettingsChanged`):

```qml
    onCommandTextChanged: root.resultCursorIndex = 0
```

- [ ] **Step 4: Build the command-line `TextField`**

Insert this as the first child of `contentColumn` (immediately above the existing `RowLayout`
that holds the TIMER/DAY `ButtonGroup`, `Panel.qml:844` today):

```qml
                        Rectangle {
                            id: cmdBox

                            Layout.fillWidth: true
                            implicitHeight: Style.spacing.controlHeight
                            color: Style.normalFill
                            border.color: PanelTheme.accent
                            border.width: 1
                            radius: Style.cornerRadius

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Style.spacing.controlPaddingX
                                anchors.rightMargin: Style.spacing.controlPaddingX
                                spacing: Style.spacing.rowGap

                                Text {
                                    text: "›"
                                    color: PanelTheme.accent
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                }

                                Item {
                                    Layout.fillWidth: true
                                    implicitHeight: cmdInput.implicitHeight

                                    TextInput {
                                        id: cmdInput

                                        anchors.fill: parent
                                        color: "transparent"
                                        selectionColor: PanelTheme.accent
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        clip: true
                                        focus: true
                                        cursorVisible: true
                                        text: root.commandText
                                        cursorDelegate: Rectangle {
                                            width: 6.6
                                            height: 13
                                            color: PanelTheme.text
                                            SequentialAnimation on opacity {
                                                loops: Animation.Infinite
                                                running: cmdInput.cursorVisible && cmdInput.activeFocus
                                                PauseAnimation { duration: 530 }
                                                PropertyAction { value: 0 }
                                                PauseAnimation { duration: 530 }
                                                PropertyAction { value: 1 }
                                            }
                                        }
                                        onTextChanged: root.commandText = text
                                        onAccepted: root.activateSelectedRow()
                                        Keys.onTabPressed: function(event) {
                                            root.acceptCompletion();
                                            event.accepted = true;
                                        }
                                        Keys.onPressed: function(event) {
                                            if (event.key === Qt.Key_Escape) {
                                                root.close();
                                                event.accepted = true;
                                                return ;
                                            }
                                            if (!(event.modifiers & Qt.ControlModifier))
                                                return ;

                                            if (event.key === Qt.Key_D) {
                                                root.setScope("day");
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_L) {
                                                root.setScope("cal");
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_T) {
                                                root.setScope("timer");
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_J) {
                                                root.moveResultCursor(1);
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_K) {
                                                root.moveResultCursor(-1);
                                                event.accepted = true;
                                            }
                                        }
                                    }

                                    Text {
                                        anchors.fill: parent
                                        textFormat: Text.StyledText
                                        font: cmdInput.font
                                        elide: Text.ElideNone
                                        text: {
                                            var segments = Model.commandSegments(root.commandText);
                                            var colorFor = {
                                                "plain": PanelTheme.text,
                                                "proj": PanelTheme.accent,
                                                // No PanelTheme/Color role exists for warn/ok --
                                                // literal per the guide, see this plan's open
                                                // questions.
                                                "tag": "#f9e2af",
                                                "bill": "#a6e3a1"
                                            };
                                            var html = segments.map(function(segment) {
                                                var escaped = segment.text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                                                return "<font color=\"" + colorFor[segment.cls] + "\">" + escaped + "</font>";
                                            }).join("");
                                            if (root.commandParsed.completion)
                                                html += "<font color=\"" + PanelTheme.textFaint + "\">" + root.commandParsed.completion + "</font>";

                                            return html;
                                        }
                                    }

                                }

                                Row {
                                    spacing: 2

                                    Repeater {
                                        model: ["timer", "day", "cal"]

                                        delegate: Rectangle {
                                            id: chip

                                            required property string modelData
                                            readonly property bool on: root.scope === modelData

                                            implicitWidth: chipLabel.implicitWidth + 10
                                            implicitHeight: chipLabel.implicitHeight
                                            color: on ? Style.selectedFill : "transparent"

                                            Text {
                                                id: chipLabel

                                                anchors.centerIn: parent
                                                text: chip.modelData
                                                color: chip.on ? PanelTheme.text : PanelTheme.textFaint
                                                font.family: root.fontFamily
                                                font.pixelSize: Style.font.caption
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: root.setScope(chip.modelData)
                                            }

                                        }

                                    }

                                }

                            }

                        }
```

- [ ] **Step 5: Focus the command line when the panel opens**

`Panel.qml`'s `open()` function (`Panel.qml:124-129`) does not currently force focus anywhere.
Add a call at the end of it, satisfying R3-1 ("focused when the panel opens"):

```qml
    function open() {
        controller.show();
        if (!current && status === "idle")
            bootstrap(false);

        Qt.callLater(function() {
            cmdInput.forceActiveFocus();
        });
    }
```

`Qt.callLater` is needed because `cmdInput` is created lazily inside the `KeyboardPanel`'s
content and is not guaranteed to exist synchronously the instant `open()` runs.

- [ ] **Step 6: Verify**

Run: `qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo $?`
Run: `omarchy plugin validate .; echo $?`
Expected: both exit 0.
Restart the shell and open the panel: the command line sits at the top, is focused immediately,
accepts typed text, and the border, chevron and scope chips render at the R3-10/R3-20 sizes and
colours. Type `@acme` (or whatever project names actually exist in the connected workspace) and
confirm the sigil renders in accent colour. Press Ctrl+D and confirm the `day` chip highlights
and the scope switches; Ctrl+T returns to `timer`. The old composer controls below are still
present and still work — that is expected until Task 6.

- [ ] **Step 7: Commit**

```bash
git add Panel.qml
git commit -m "feat(panel): add the command-line TextField and scope chips"
```

---

### Task 5: `ui/TimerScope.qml` — running strip, result rows, hint bar

**Files:**
- Modify: `ui/TimerScope.qml` (stage 2's stub)
- Modify: `Panel.qml` — instantiate `TimerScope`, remove `PanelHero`

**Interfaces:**
- Consumes: `root.current`, `root.elapsedLabel` (both pre-existing, untouched by this stage —
  see R-O), `root.commandRows`, `root.resultCursorIndex` (Task 4), `ui/PanelTheme.qml` (stage
  2).
- Produces: nothing new outside this file; it is a pure view over properties `Panel.qml` passes
  in.

This task directly replaces `PanelHero` with the running strip (R-H — "Stage 3 replaces the hero
with the strip", not a phased coexistence, unlike Task 4/6's composer swap) and adds the
result-row `Repeater` and hint bar. The legacy composer controls below this block are untouched
here and still deleted in Task 6.

- [ ] **Step 1: Write `ui/TimerScope.qml`**

Replace the stub's contents entirely with:

```qml
import QtQuick
import QtQuick.Layouts
import qs.Commons
import "PanelTheme.qml" as PanelThemeType

ColumnLayout {
    id: root

    required property var currentEntry
    required property string elapsedLabel
    required property string fontFamily
    required property var rows
    required property int cursorIndex

    signal rowActivated(int index)

    readonly property QtObject theme: PanelThemeType {
    }

    spacing: Style.spacing.panelGap

    RowLayout {
        Layout.fillWidth: true
        spacing: Style.spacing.rowGap
        visible: !!root.currentEntry

        Rectangle {
            implicitWidth: 7
            implicitHeight: 7
            color: root.theme.accent
        }

        Text {
            text: root.elapsedLabel
            color: root.theme.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.weight: Font.Medium
            font.variant: Font.NoVariant
        }

        Text {
            Layout.fillWidth: true
            text: root.currentEntry ? root.currentEntry.description : ""
            color: root.theme.text
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
        }

        Text {
            text: root.currentEntry ? (root.currentEntry.projectName + (root.currentEntry.taskName ? " · " + root.currentEntry.taskName : "")) : ""
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0

        Repeater {
            model: root.rows

            delegate: Item {
                id: rowItem

                required property var modelData
                required property int index

                Layout.fillWidth: true
                implicitHeight: Style.space(22)

                Rectangle {
                    anchors.fill: parent
                    color: rowItem.index === root.cursorIndex ? Style.selectedFill : (rowMouse.containsMouse ? Style.hoverFill : "transparent")
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 2
                    anchors.rightMargin: 2
                    spacing: Style.spacing.rowGap

                    Text {
                        Layout.preferredWidth: 11
                        text: rowItem.modelData.glyph
                        color: rowItem.index === root.cursorIndex ? root.theme.accent : root.theme.textFaint
                        horizontalAlignment: Text.AlignHCenter
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        Layout.preferredWidth: 52
                        text: rowItem.modelData.verb
                        color: rowItem.index === root.cursorIndex ? root.theme.accent : root.theme.textFaint
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        font.letterSpacing: 0.6
                    }

                    Text {
                        Layout.fillWidth: true
                        text: rowItem.modelData.label
                        color: root.theme.text
                        elide: Text.ElideRight
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        text: rowItem.modelData.meta
                        color: root.theme.textFaint
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                }

                MouseArea {
                    id: rowMouse

                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.rowActivated(rowItem.index)
                }

            }

        }

    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 14

        Text {
            text: "↵ act"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

        Text {
            text: "⇥ complete"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

        Text {
            text: "^j/^k move"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

        Text {
            text: "^d day"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

        Text {
            text: "^l calendar"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

        Text {
            text: "esc close"
            color: root.theme.textFaint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
        }

    }

}
```

This hint bar is timer scope's own, fixed set (R3-26 — no `^t timer` hint while already in
timer). It does not yet vary by `root.scope`, because stage 4/5 own day/calendar scope's own
hint rows; wiring a scope-conditioned hint bar across all three scopes belongs to whichever of
those stages lands last, not this one, since this component is instantiated only while `scope
=== "timer"`.

- [ ] **Step 2: Instantiate `TimerScope` in place of `PanelHero`, in `Panel.qml`**

Replace the `PanelHero` block (`Panel.qml:1038-1055` today):

```qml
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
```

with:

```qml
                                TimerScope {
                                    Layout.fillWidth: true
                                    currentEntry: root.current
                                    elapsedLabel: root.elapsedLabel
                                    fontFamily: root.fontFamily
                                    rows: root.commandRows
                                    cursorIndex: root.resultCursorIndex
                                    onRowActivated: function(index) {
                                        root.resultCursorIndex = index;
                                        root.activateSelectedRow();
                                    }
                                }
```

Add the import this file needs, at the top of `Panel.qml` next to the existing `import qs.Ui`:

```qml
import "ui" as Ui
```

and qualify the new instantiation as `Ui.TimerScope { ... }` if stage 2's `ui/` directory has no
`qmldir` registering these as bare, unqualified types — **verify which form stage 2's actual
file split produces before this step; see this plan's open questions.** This plan writes the
unqualified `TimerScope { ... }` form above on the assumption that stage 2 either registers a
`qmldir` for `ui/` or that `Panel.qml` imports each `ui/*.qml` file individually (e.g. `import
"ui/TimerScope.qml" as TimerScope`); if stage 2 instead passes theme access via a required
`theme` property rather than `ui/TimerScope.qml` importing `PanelTheme.qml` directly, replace
every `root.theme.X`/`PanelThemeType` reference in Step 1 accordingly.

- [ ] **Step 3: Verify**

Run: `qmlformat -n -i Panel.qml ui/TimerScope.qml && qmlformat Panel.qml >/dev/null; echo $?`
Run: `qmlformat ui/TimerScope.qml >/dev/null; echo $?`
Run: `omarchy plugin validate .; echo $?`
Expected: all exit 0.
Restart the shell. With a timer running, confirm the running strip renders at 11px with an
accent dot, clock, description and meta, in that order (R3-23), and that it is visibly smaller
than the deleted 24px `PanelHero` was. With nothing running, confirm the strip is simply absent
(no idle-state mock exists in the guide to match against — see this plan's open questions) and
the result rows still render below the command line. Confirm the hint bar shows exactly the six
R3-26 strings, in that order.

- [ ] **Step 4: Commit**

```bash
git add Panel.qml ui/TimerScope.qml
git commit -m "feat(timer): running strip and result rows replace PanelHero"
```

---

### Task 6: `Panel.qml` — delete the legacy composer, tab strip and search

**Files:**
- Modify: `Panel.qml`

**Interfaces:**
- Produces: nothing new. Removes `searchMode`, `searchOpen`, `selectedProjectId`,
  `selectedTaskId`, `billable`, `composerEntryId`, `searchResults`, `projectOptions` *is kept*
  (still used by day-scope block editing — see the note below), `taskOptions` and `tagOptions`
  are removed (dead/composer-only), `searchOptions`, and the functions `entryFields`, `start`
  (replaced by `startFromCommand` in Task 4), `stop` *is kept* (see this plan's open questions —
  there is no UI path to it after this task, but nothing else in the redesign defines one
  either, so it is left in place rather than deleted outright), `updateCurrent`, `showEntry`,
  `loadComposer`, `selectProject`, `selectTask`, `selectedProject`, `selectedTask`.

Now that Task 4/5 have proven the command line fully replaces starting, continuing and browsing
entries, this task is a pure, low-risk deletion pass. Every block below is quoted from the
current file so the deletion is unambiguous; delete each quoted block exactly, in the order
given (later line numbers shift as earlier ones are removed — work top-to-bottom in one pass, or
delete bottom-to-top to avoid re-computing line numbers).

- [ ] **Step 1: Delete the composer-state properties**

Delete these three lines (originally `Panel.qml:30-31, 34`):

```qml
    property string searchMode: "all"
    property bool searchOpen: false
```

and:

```qml
    property bool billable: false
```

Also delete `selectedProjectId`/`selectedTaskId` (originally `Panel.qml:32-33`) and
`composerEntryId` (originally `Panel.qml:50`):

```qml
    property int selectedProjectId: 0
    property int selectedTaskId: 0
```

```qml
    property int composerEntryId: 0
```

- [ ] **Step 2: Delete the composer-state readonly properties**

Delete `searchResults`, `taskOptions`, `tagOptions` and `searchOptions` in full (originally
`Panel.qml:72, 83-89, 90-95, 96-114`). Keep `projectTasks` and `projectOptions` — `projectOptions`
still feeds day-scope's block-edit `SearchableDropdown`s, unrelated to the deleted composer.

```qml
    readonly property var searchResults: Model.searchItems(entries, projects, tasks, query, searchMode, selectedProjectId)
```

```qml
    readonly property var taskOptions: projectTasks.map(function(t) {
        return {
            "value": String(t.id),
            "label": t.name,
            "description": t.projectName || ""
        };
    })
    readonly property var tagOptions: tags.map(function(t) {
        return {
            "value": String(t),
            "label": String(t)
        };
    })
    readonly property var searchOptions: searchResults.projects.map(function(p) {
        return {
            "value": "project:" + p.id,
            "label": p.name,
            "description": p.clientName || ""
        };
    }).concat(searchResults.tasks.map(function(t) {
        return {
            "value": "task:" + t.id,
            "label": t.name,
            "description": t.projectName || ""
        };
    })).concat(searchResults.entries.map(function(e) {
        return {
            "value": "entry:" + e.id,
            "label": e.description,
            "description": e.projectName + (e.taskName ? " · " + e.taskName : "")
        };
    }))
```

- [ ] **Step 3: Delete the composer functions**

Delete `entryFields`, `start` (superseded by `startFromCommand`), `updateCurrent`, `showEntry`,
`loadComposer`, `selectedProject`, `selectedTask`, `selectProject`, `selectTask` in full
(originally `Panel.qml:369-468`, everything between `refreshLabel`'s predecessor and
`refreshLabel` itself):

```qml
    function entryFields() {
        return {
            "description": descriptionField.text.trim(),
            "project_id": selectedProjectId || null,
            "task_id": selectedTaskId || null,
            "tags": tagsField.values,
            "billable": billable
        };
    }

    function start() {
        if (!descriptionField.text.trim() && !selectedProjectId)
            return ;

        var data = entryFields();
        data.workspace_id = selectedWorkspaceId;
        request("start", data);
    }
```

Delete this pair (keep `stop()` between them — do not delete it, see this plan's open
questions):

```qml
    function updateCurrent() {
        if (!current)
            return ;

        var data = entryFields();
        data.workspace_id = current.workspaceId || selectedWorkspaceId;
        data.entry_id = current.id;
        request("update", data);
    }
```

```qml
    function selectedProject() {
        return Model.projectForEntry({
            "projectId": selectedProjectId
        }, projects);
    }

    function selectedTask() {
        return Model.taskForEntry({
            "taskId": selectedTaskId
        }, tasks);
    }

    function selectProject(project) {
        selectedProjectId = Number(project.id) || 0;
        selectedTaskId = 0;
        projectDropdown.value = String(selectedProjectId);
        taskDropdown.value = "";
        searchOpen = false;
        descriptionField.forceActiveFocus();
    }

    function selectTask(task) {
        selectedTaskId = Number(task.id) || 0;
        selectedProjectId = Number(task.projectId) || 0;
        var project = selectedProject();
        projectDropdown.value = String(selectedProjectId);
        taskDropdown.value = String(selectedTaskId);
        searchOpen = false;
        descriptionField.forceActiveFocus();
    }

    function showEntry(entry) {
        selectedProjectId = entry.projectId || 0;
        selectedTaskId = Model.taskForEntry(entry, tasks) ? entry.taskId : 0;
        projectDropdown.value = entry.projectName === "No project" ? "" : String(selectedProjectId);
        taskDropdown.value = selectedTask() ? String(selectedTaskId) : "";
        descriptionField.text = entry.description === "(no description)" ? "" : entry.description;
        tagsField.values = entry.tags || [];
        billable = entry.billable;
    }

    function loadComposer(entry) {
        composerEntryId = entry ? entry.id : 0;
        if (entry) {
            showEntry(entry);
        } else {
            selectedProjectId = 0;
            selectedTaskId = 0;
            descriptionField.text = "";
            projectDropdown.value = "";
            taskDropdown.value = "";
            tagsField.values = [];
            billable = false;
        }
    }
```

`applyData()` (`Panel.qml:320-359`) calls `showEntry(current)` when a new `current` entry
arrives — that call site is now dead code calling a deleted function. Delete the whole `if`
block that calls it:

```qml
        var currentChanged = (current && current.id) !== oldCurrentId;
        var needsTaskResolution = !oldTasksLoaded && tasksLoaded && current && current.taskId && Model.taskForEntry(current, tasks) && String(selectedTaskId) !== String(current.taskId);
        if (current && (currentChanged || needsTaskResolution))
            showEntry(current);

        refreshLabel();
```

becomes:

```qml
        refreshLabel();
```

(`oldCurrentId` and `oldTasksLoaded`, computed a few lines above this block, become unused too —
delete their declarations as well: `var oldCurrentId = current && current.id;` and `var
oldTasksLoaded = tasksLoaded;`.)

`handleResponseBody`'s `stop` handling (`Panel.qml:675-680`) also calls `loadComposer(null)` —
replace that call with nothing (the running-strip visibility already reacts to `root.current`
becoming `null` on its own):

```qml
            } else if (["start", "stop", "update", "continue"].indexOf(action) >= 0) {
                if (action === "stop")
                    loadComposer(null);

                sync(false, false);
            }
```

becomes:

```qml
            } else if (["start", "stop", "update", "continue"].indexOf(action) >= 0) {
                sync(false, false);
            }
```

- [ ] **Step 4: Delete the TIMER/DAY `ButtonGroup` and the search button**

Delete (originally `Panel.qml:847-856`):

```qml
                            ButtonGroup {
                                options: ["TIMER", "DAY"]
                                value: root.scope === "timer" ? "TIMER" : "DAY"
                                onChanged: function(value) {
                                    root.scope = value.toLowerCase();
                                    if (root.scope === "day" && !root.dayLoaded)
                                        root.loadDay();

                                }
                            }
```

and, a few lines below it, the search button (originally `Panel.qml:870-882`):

```qml
                            PanelActionButton {
                                visible: root.scope === "timer"
                                iconText: "󰍉"
                                tooltipText: "Search"
                                size: Style.spacing.controlHeight
                                foreground: Color.accent
                                onClicked: {
                                    root.searchMode = "all";
                                    root.query = "";
                                    root.searchOpen = true;
                                    searchDropdown.open();
                                }
                            }
```

- [ ] **Step 5: Delete the entry-composer content and the search dropdown**

Delete the description field + START/STOP row, the `ENTRY DETAILS` header, both
`SearchableDropdown`s, the `MultiSelect`, the `Toggle`, and the stranded search
`SearchableDropdown` (originally `Panel.qml:1057-1203`, everything between the `TimerScope`
instance from Task 5 and the `PanelSectionHeader{text:"RECENT"}` line):

```qml
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Style.spacing.rowGap

                                    TextField {
                                        id: descriptionField

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
                                    id: projectDropdown
                                    ...
                                }

                                SearchableDropdown {
                                    id: taskDropdown
                                    ...
                                }

                                MultiSelect {
                                    id: tagsField
                                    ...
                                }

                                Toggle {
                                    Layout.fillWidth: true
                                    label: "Billable"
                                    description: "Mark this entry as billable"
                                    checked: root.billable
                                    onClicked: root.billable = !root.billable
                                }

                                SearchableDropdown {
                                    id: searchDropdown
                                    ...
                                }
```

(`...` above stands for each dropdown's full existing body — delete the whole component, not
just its opening tag; use the file you are editing as the source of truth for the exact bounds,
not this plan's elision.)

The `RECENT` section right after it (`PanelSectionHeader{text:"RECENT"}` and its `Repeater` over
`root.searchResults.recentEntries`, originally `Panel.qml:1205-1271`) also depended on the
now-deleted `searchResults`/`searchOpen` — delete it too, since the command line's own CONT rows
(Task 2/5) supersede it:

```qml
                                PanelSectionHeader {
                                    visible: !root.searchOpen && root.searchResults.recentEntries.length > 0
                                    text: "RECENT"
                                    foreground: root.foreground
                                }

                                Repeater {
                                    model: !root.searchOpen ? root.searchResults.recentEntries : []
                                    ...
                                }
```

- [ ] **Step 6: Full verification pass**

Run: `node tests/test_model.mjs`
Expected: `all model checks passed`.
Run: `qmlformat -n -i Panel.qml ui/TimerScope.qml && qmlformat Panel.qml >/dev/null; echo $?`
Run: `qmlformat ui/TimerScope.qml >/dev/null; echo $?`
Expected: both exit 0.
Run: `omarchy plugin validate .; echo $?`
Expected: exits 0.
Run: `grep -n "searchMode\|searchOpen\|searchResults\|searchOptions\|descriptionField\|projectDropdown\|taskDropdown\|tagsField\b\|loadComposer\|selectProject\|selectTask\|PanelHero\|ButtonGroup" Panel.qml`
Expected: no matches (the `ButtonGroup` used for `WORKSPACE`/`HISTORY`/`IDLE REMINDER`/`LOG
DETAIL`/`BREAK` in the settings section is a *different* `ButtonGroup` component usage than the
deleted TIMER/DAY one — re-run this grep and manually confirm every remaining `ButtonGroup` hit
is one of those five, not a stray leftover of the deleted tab strip).
Restart the shell (`omarchy-restart-shell`) and, against `docs/design-guide.html` §01 side by
side:
  - The panel opens with the command line focused, no PROJECT/TASK/TAGS/Billable controls, no
    START/STOP button, no TIMER/DAY tab strip, no search icon, visible anywhere.
  - Typing `something @` (or a real project name) produces START/PROJ rows; clearing it back to
    a plain query produces START/CONT/BLOCK rows if matching data exists.
  - Ctrl+D/Ctrl+L/Ctrl+T switch the scope chip highlight and the underlying `root.scope`.
  - Pressing Enter on the selected START row starts a real Toggl timer (verify in the Toggl web
    UI or by re-opening the panel and seeing the running strip).
  - **R-O check:** with a timer running, confirm the bar widget's own compact label (the text
    rendered directly on the Omarchy bar, driven by `root.barLabel`/`root.elapsedLabel` via
    `BarWidget.qml`, untouched by this entire plan) still shows the elapsed time and description
    exactly as it did before this stage. This is the one acceptance point this stage cannot
    verify with either QML tool, per `BarWidget.qml`'s hand-review-only status.
  - Day scope (Ctrl+D) still shows day blocks, still supports assigning a project/task per block
    and applying it, exactly as before this entire stage — none of this stage's deletions touch
    day-scope code.

- [ ] **Step 7: Commit**

```bash
git add Panel.qml
git commit -m "refactor(panel): delete the legacy composer, tab strip and search"
```

---

## Open Questions

1. **How does `ui/TimerScope.qml` actually reach `ui/PanelTheme.qml`, per stage 2's real
   implementation?** Spec §5 calls `ui/PanelTheme.qml` "a singleton-style `QtObject`" but does
   not say whether stage 2 registers it as a true QML singleton (`pragma Singleton` + a `ui/
   qmldir`, giving every file bare `PanelTheme.accent`-style access) or has `Panel.qml`
   instantiate one `PanelTheme` and pass it down to each `ui/*.qml` file as a required `theme`
   property. This plan was written without stage 2 having landed in this repository (no `ui/`
   directory exists yet at the time of writing), so Task 5 makes a concrete choice — `ui/
   TimerScope.qml` imports `PanelTheme.qml` directly and instantiates its own instance — and
   flags it for correction against stage 2's actual output before this plan executes. If stage 2
   instead passes a `theme` property, every `root.theme.X` reference in Task 5 (and every direct
   `PanelTheme.X` reference in Task 4) needs the corresponding rename, but the values and logic
   around them do not change.

2. **`--warn` (`#f9e2af`) and `--ok` (`#a6e3a1`) — the tag-token and billable-token colours in
   R3-21 — have no corresponding role anywhere in this shell.** `ui/PanelTheme.qml` (spec §9.1)
   exposes only `surface/text/edge/textMuted/textFaint/textDisabled/accent/urgent`, and the
   shell's own `Color` singleton (`/usr/share/omarchy/shell/Commons/Color.qml`) exposes only
   `foreground/background/accent/urgent/muted` plus per-surface groups (`bar`, `popups`,
   `tooltip`, ...) — none of them a warning-yellow or success-green role. This is a genuine
   conflict between two of this project's own hard rules: "theme values come from `Style.*` and
   `Color.*`, never literals" versus "the guide wins for a rendered value, to the dot." Task 4
   resolves it in the guide's favour with two literal hex colours, each commented in place to
   explain why, but this deserves an explicit decision (add real roles to `ui/PanelTheme.qml` in
   stage 2/6's theme work, or confirm the literal is acceptable) rather than staying silently
   decided by this plan.

3. **R-C's Ctrl+J/Ctrl+K "lives on the shared `PanelKeyCatcher`" wording versus this stage's
   actual implementation.** As documented at length in Task 4's design note, `PanelKeyCatcher`
   cannot distinguish a Ctrl-held keypress from a bare one, and the command-line field holding
   focus almost permanently means `PanelKeyCatcher` stands down for nearly the whole time the
   panel is open regardless. This plan implements the *intent* of R-C (one shared,
   scope-conditioned switch that a later stage slots a day-scope branch into) as a plain function
   on `Panel.qml`, called directly from the command-line field's `Keys.onPressed`, rather than
   through a `PanelKeyCatcher` signal. Confirm this reading is acceptable, or that stage 4 (the
   day-scope stage that comes after this plan) can still slot `dayScope.moveCursor()` into `root.
   moveResultCursor`'s `if (root.scope !== "timer") return;` guard as intended.

4. **Empty-command-line default rows (Task 2's `commandRows` empty-text branch) are this plan's
   own invention, not a literal requirement.** The guide's `resultsFor("")` fallback is a
   hardcoded static example (`restRows`, captured once from the page's own initial DOM) used
   purely for its typing-animation demo, not a specified "nothing typed yet" behaviour — neither
   spec §6 nor the guide states what the result list should show before the user types anything.
   This plan's choice (up to 3 recent entries as CONT rows, plus the single nearest open block)
   is a reasonable default built from data already in memory, but it is a genuine invention where
   the source documents are silent, flagged here rather than presented as derived from them.

5. **There is no Stop control and no way to edit the running entry's description without
   starting a new one, after this stage.** This is R3-15a from the stage's own requirement
   digest, carried forward unresolved: the guide's section 01 mock never shows a Stop
   affordance or keybinding, and Toggl's own `start` semantics auto-stop the previous entry
   server-side, but there is no shown mechanism to simply stop tracking with nothing new queued
   to start. `root.stop()` is deliberately left in place (untouched, uncalled by any UI this
   stage adds) rather than deleted, so the capability is not lost, but it needs a product
   decision — a keybinding, a command-line verb, or an explicit decision that this is
   intentionally out of scope — before it can be considered resolved.

6. **The idle (no timer running) rendering of the running strip has no reference anywhere in the
   guide** — R3-15b from the digest, also carried forward. This plan resolves it by hiding the
   running strip entirely (`visible: !!root.currentEntry`) when idle, leaving the command line
   and result rows as the entire idle-state UI. This is a reasonable default, not a value taken
   from the guide, since none exists to take.
