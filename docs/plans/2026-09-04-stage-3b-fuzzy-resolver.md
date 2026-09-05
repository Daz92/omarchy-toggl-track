# Stage 3b: Fuzzy Project and Task Resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make `@` and `/` actually select a project and a task, for names that contain
spaces — which is 20 of the user's 25 active projects and effectively all 373 of their tasks.

**Architecture:** A pure ranking function in `Model.js`; ranked `▤ PROJ` and new `◈ TASK`
rows from `commandRows`; and a binding that lives in `Panel.qml` state rather than in the
command text, because the text cannot carry a multi-word name.

**Tech Stack:** QML/Quickshell, `Model.js` under both QML's engine and plain node. No Python.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §6.5
**Rulings:** [`docs/2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — R-S
**Visual reference:** [`docs/design-guide.html`](../design-guide.html) §01

## Global Constraints

- **No `;` after a QML object member.** A parse error BOTH QML tools report with ZERO output.
- **Never pipe `qmlformat`/`qmllint` and read `$?`.** Check status directly AND confirm output
  is non-empty — a parse error gives exit 0 with no output.
- **Signal handlers declare their parameters.** `onChanged: function(value) { … }`.
- **A `Repeater` is not an `Item`** — `visible` does not hide its output; gate on the model.
- **`ui/PanelTheme.qml` has no `pragma Singleton`** — always `panelTheme.x`, never
  `PanelTheme.x`. Bare-type access is unresolved at RUNTIME and no tool catches it.
- **Colour tiers (R-R):** `--dim15`→`textMuted`, `--dim16`→`textFaint`, `--dim18`→`textDisabled`.
- **`BarWidget.qml` must stay byte-identical to master** (R-O).
- **`Model.js` runs under both QML's engine and plain node.** ES5-ish `var`/`function`.
  `String.prototype.padStart` is available and already used.
- No third-party dependencies.
- Python tests: `python3 -m unittest discover -s tests`. A bare `pytest` is rewritten by a
  shell hook here and fails misleadingly.
- **Never restart the shell or drive the live panel.** The controller does that.

---

### Task 1: `Model.scoreMatch` — the ranking function

**Files:** Modify `Model.js`, `tests/test_model.mjs`

**Interfaces:**
- Produces: `Model.scoreMatch(query, name)` → Number, 0 for no match. Higher ranks first.

Spec §6.5 lists the eight rules in priority order. Implement them exactly, with a small
penalty proportional to name length applied throughout so a shorter name outranks a longer
one at the same rule.

Two rules are load-bearing and must not be simplified away:
- The SIGNIFICANT-word acronym (dropping stopwords `and of the for a to in on up &`). Without
  it, `rd` ranks `Shipyard` above `Research and Development` on the substring `…ya-rd`.
- The acronym of a TRAILING RUN of words, so a leading job code can be skipped. Without it,
  `nvt` cannot reach `Northwind Voyager Testing` past its `NW-075` prefix.

Rule 8, plain subsequence, must be the LOWEST tier. On its own it ranks
`Growth: Paper & Presentation Development` above `Travel Day` for `trav`.

- [ ] **Step 1: Write the failing tests.** Add `scoreMatch` to the harness export list. Assert
  ORDERING, not absolute scores — the scores are an implementation detail and pinning them
  makes the suite brittle. For each case below, assert the expected name sorts first among a
  fixture of realistic multi-word names:

```js
const RANK = [
  ["rd",        "Research and Development"],
  ["nvt",       "NW-075 Northwind Voyager Testing"],
  ["trav",      "Travel Day"],
  ["wild",      "NW-092-H370 Wild Harbour"],
  ["091",       "NW-091 Northwind Venturer Upgrade Testing & Validation"],
  ["gppd",      "Growth: Paper & Presentation Development"],
  ["bluefin", "NW-088 Bluefin Protection Study"],
  ["upgrade",   "NW-091 Northwind Venturer Upgrade Testing & Validation"],
]
```

  Also assert: an empty query scores 0 for everything; a query matching nothing scores 0;
  and matching is case-insensitive.

- [ ] **Step 2: Run the tests, confirm they fail** for "scoreMatch is not a function".
- [ ] **Step 3: Implement `scoreMatch`.**
- [ ] **Step 4: Run the tests, confirm they pass.**
- [ ] **Step 5: Commit.**

---

### Task 2: ranked `▤ PROJ` rows and new `◈ TASK` rows

**Files:** Modify `Model.js`, `tests/test_model.mjs`

**Interfaces:**
- Consumes: `scoreMatch` (Task 1).
- Produces: `commandRows` emits `▤ PROJ` rows ranked by `scoreMatch` against the project's
  name AND its client name, and a new row kind `{ glyph: "◈", verb: "TASK", kind: "task" }`.

Replace the current `searchItems`-based PROJ selection in the `@` branch with `scoreMatch`
ranking, keeping the guide's 8-row cap. The PROJ row's `label` and `meta` are unchanged —
`clientName / name` and the entry count — because the guide fixes those.

Add the `/frag` branch: when the caller passes a bound project id and the text's last token
is or contains an unresolved `/frag`, emit `◈ TASK` rows for that project's active tasks,
ranked by `scoreMatch`, same 8-row cap. A `◈ TASK` row's `label` is the task name, its `meta`
is the owning project's name, and its `num` is `""`.

`commandRows` gains two trailing parameters, `boundProjectId` and `boundTaskId`, both
defaulting to 0. They only affect the START row's effective ids and the `/frag` branch; every
existing call shape must keep working, so add them at the END of the signature and test that
omitting them behaves exactly as today.

- [ ] **Step 1: Write the failing tests** — a `/frag` with a bound project emits ranked TASK
  rows; without a bound project it emits none; the 8-row cap holds for both kinds; the START
  row's ids prefer the bound ids over the parsed ones; and omitting the two new parameters
  reproduces today's rows exactly.
- [ ] **Step 2: Run, confirm failure. Step 3: Implement. Step 4: Run, confirm pass. Step 5: Commit.**

---

### Task 3: binding state and row actions in `Panel.qml`

**Files:** Modify `Panel.qml`

**Interfaces:**
- Consumes: Task 2's row kinds and `commandRows` signature.
- Produces: `root.boundProjectId`, `root.boundTaskId`.

Per spec §6.5's "Binding is state, not text":

- Add `property int boundProjectId: 0` and `property int boundTaskId: 0`.
- `Enter` on a `▤ PROJ` row sets `boundProjectId`, clears `boundTaskId`, and REMOVES the
  `@frag` token from `commandText`. **Delete `scopeToProject` entirely** — writing
  `head + "@" + project.name` back into the text is the defect, not a step toward the fix.
- `Enter` on a `◈ TASK` row sets `boundTaskId` and removes the `/frag` token.
- `startFromCommand` submits `boundProjectId || parsed.projectId` and
  `boundTaskId || parsed.taskId`.
- Clearing `commandText` to empty clears both bindings. Selecting a different PROJ row
  replaces the project and clears the task.
- **`Tab` must never insert a name containing spaces.** `parseCommand` already returns an
  empty `completion` for a multi-word match; confirm `acceptCompletion` cannot produce one,
  and if it can, gate it.
- Pass both bound ids to `Model.commandRows`.

- [ ] **Step 1: Add the properties and the two row actions.**
- [ ] **Step 2: Delete `scopeToProject` and repoint its caller.**
- [ ] **Step 3: Thread the bound ids through `commandRows` and `startFromCommand`.**
- [ ] **Step 4: Verify** — `qmlformat` exit 0 with non-empty output; `omarchy plugin validate .`
  exit 0; `grep -n scopeToProject Panel.qml` returns nothing; `./build --check` OK.
- [ ] **Step 5: Commit.**

---

### Task 4: render `◈ TASK` rows and the bound state

**Files:** Modify `ui/TimerScope.qml`

**Interfaces:** Consumes Task 2's row kinds and Task 3's properties.

The row delegate is kind-agnostic today — glyph, verb, label, meta, num — so a `◈ TASK` row
should render with no change. **Verify that and say so explicitly; do not add a branch that
is not needed.**

What does need care: the guide has no design for "a project is bound but its token is gone
from the text". The START row's meta already renders `project · task` from the row data, so
the binding is visible there with no new element. **Confirm that is true with a bound project
and no `@` token in the text**, and if it is not, the minimal addition is to make it true —
not a new chip or badge, which the guide does not have.

- [ ] **Step 1: Verify the delegate renders a TASK row unchanged.**
- [ ] **Step 2: Confirm the START row's meta shows a bound project with no token in the text.**
- [ ] **Step 3: Verify** — `qmlformat`, `validate`, `./build --check`, `node tests/test_model.mjs`.
- [ ] **Step 4: Commit.**
