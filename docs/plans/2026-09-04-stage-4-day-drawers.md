# Panel Redesign — Stage 4: Day Scope Drawers, Inspect versus Edit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every day-scope block row six correctly-glyphed states plus a seventh
session-local "skipped" state, two independently-openable drawers (inspect: read-only
facts; edit: the only place anything gets written), and full keyboard control of the
cursor row — while every mouse path that exists today keeps working.

**Architecture:** No new components beyond what stage 2 stubbed. `ui/DayScope.qml`
receives one property, `panel` — a reference to the `Panel.qml` root — and reads its
state (`dayBlocks`, `dayCursorIndex`, `dayRevision`, `daySummary`, `dayDate`,
`dayError`, `dayLoaded`, `requestPending`, `projects`, `tasks`, `foreground`,
`fontFamily`) and calls its existing mutation functions (`mutateBlock`, `applyBlock`,
`applyAssigned`, `shiftDay`) through that one reference. `Panel.qml` keeps owning
state, `request()`, `handleResponse()`, and the command line, per spec §5's table.
`Model.js` gains the block-schema fields the backend already returns (stage 0/1) but
`prepareBlocks()` does not yet carry through, and gains `blockReady()` moved over from
`Panel.qml` so it is unit-testable.

**Tech Stack:** QML/Quickshell for `ui/DayScope.qml` and `Panel.qml`. Pure JS in
`Model.js`, covered by `tests/test_model.mjs` under Node. No Python touched in this
stage.

**Spec:** [`docs/2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §7
**Rulings:** [`docs/2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — R-B, R-C, R-D, R-J, R-N bind this stage
**Visual acceptance reference:** [`docs/design-guide.html`](../design-guide.html) §02, §03, §05

## Global Constraints

Every task's requirements implicitly include all of these.

- **`docs/design-guide.html` is the acceptance reference for every rendered value.**
  Where this plan and that page disagree about a pixel, token, glyph, colour or copy
  string, the page wins and the disagreement is a bug in this plan — stop and report it
  rather than guessing.
- **Two duration formatters coexist, deliberately (ruling R-D).**
  `Model.compactDuration()` (existing) keeps formatting `idle removed`, `switches` and
  `longest run` in the inspect drawer, and the CONT command-line rows elsewhere.
  `Model.clockDuration()` is authored by stage 3, not this stage — this stage is its
  first heavy **consumer**, for every row duration, the day-header total, and the
  factline's `active`/`wall` figures. Do not write a third formatter and do not touch
  `compactDuration`'s current behaviour.
- **The day-block cursor is `root.dayCursorIndex`, declared by stage 3 (ruling R-B).**
  This stage does not declare it and does not touch the BLOCK command-line row that
  sets it — this stage only reads it, moves it, and acts on `dayBlocks[dayCursorIndex]`.
- **Ctrl+J / Ctrl+K dispatch is wired once, by stage 3 (ruling R-C).** Stage 3's
  scope-conditioned switch in `Panel.qml` already calls `dayScope.moveCursor(direction)`
  for `root.scope === "day"`. This stage implements that one function on `ui/DayScope.qml`
  and touches nothing else on `PanelKeyCatcher` or the switch itself — "whoever touches
  the catcher second must not overwrite the first."
- **Any number of drawers may be open, on any number of rows, at once.** The accordion
  in the current `toggleBlock()` — closing every sibling's `expanded` flag — is deleted,
  not adapted.
- **A `Repeater` is not an `Item`.** `visible` on a `Repeater` element does not hide its
  output. Every dynamic list inside a drawer (topics, apps, domains, fragment timeline)
  gates its `model:` property on the owning drawer's open flag directly, exactly as the
  existing topic-breakdown Repeater already does at `Panel.qml:1622` today.
- **No `Qt.darker()` call sites.** Every dim/muted colour in `ui/DayScope.qml` comes
  from a `PanelTheme` role (`textMuted` / `textFaint` / `textDisabled`) or a direct
  `PanelTheme.accent` / `PanelTheme.urgent` reference. `grep -c Qt.darker ui/DayScope.qml`
  must return `0`.
- **`Style.cornerRadius` resolves to 0.** Nothing is rounded.
- **QML signal handlers declare their parameters.** `onChanged: function(value) { … }`.
- **No `;` after a QML object member.** A parse error both `qmlformat` and
  `omarchy plugin validate` report with zero output.
- **Check `qmlformat`'s exit status directly; never pipe it.**
- **`BarWidget.qml` is hand-reviewed**, not gated by either QML tool — untouched by this
  stage, so nothing to re-review here, but do not add an import that reaches it.
- **`PanelKeyCatcher` consumes `j k h l x`** before a focused editor sees them, and the
  edit drawer's two fields must correctly trip `root.editorFocused` (already computed
  from `keyCatcher.Window.activeFocusItem instanceof TextInput/TextEdit`) so those
  letters, and spaces, can be typed into them. Per spec §7.5, the inspect drawer holds no
  editors, so the catcher stays active while it is open — this stage does not touch
  `editorFocused`'s definition, only relies on it already excluding the always-focused
  command-line field (stage 3's contract, not re-verified here beyond the spec's own
  sentence confirming it).
- **Never reuse `start` or `continue` for the edit drawer's apply action.** Only
  `create_entry`, via the existing `submitBlock()` / `applyBlock()` / `applyAssigned()`
  machinery — reused unchanged, not rebuilt.
- **In-place block mutation needs `dayRevision`.** Every field flip on a block goes
  through `root.mutateBlock(block, applyFn)`, never a direct assignment, or the
  `Repeater`'s delegates (kept alive to avoid stealing `TextField` focus) will not
  observe the change.
- **There is no QML test harness in this repository.** QML verification is
  `qmlformat` exit 0, `omarchy plugin validate` exit 0, and a shell restart plus visual
  check against the design guide. Say so at every QML task rather than inventing one.
  Logic that can be expressed as pure JS goes in `Model.js`, covered by
  `tests/test_model.mjs`, deliberately, so it is the one part of this stage a computer
  checks.
- **Editing QML requires `omarchy-restart-shell`,** not `reloadConfig` and never
  `rescanPlugins`, which is not in this shell's IPC surface and exits 0 regardless.

## File Structure

| File | Responsibility |
| --- | --- |
| `Model.js` | modified — `prepareBlocks()` carries the new block fields; `blockReady()` moves here from `Panel.qml` and gains `!guessed` |
| `tests/test_model.mjs` | modified — new-field passthrough, `blockReady()` |
| `ui/DayScope.qml` | modified — day header, six-plus-one row states, inspect drawer, edit drawer, keyboard dispatch; assumed created as an empty stub by stage 2 per spec §5's four-file split |
| `Panel.qml` | modified — instantiate `DayScope`, delete the inline day-block `ColumnLayout`/`Repeater` it replaces, delete `toggleBlock()`, delete the local `blockReady()`, update its three call sites to `Model.blockReady()` |

---

### Task 1: `Model.js` — carry the new block fields, move `blockReady()` over

**Files:**
- Modify: `Model.js`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Consumes: nothing new. `day_activity`'s block schema already carries
  `idle_seconds`, `fragments`, `longest_fragment_seconds`, `domains[{name,seconds}]`,
  `timeline[{offset,seconds,topic,idle}]` (stage 0/1, merged).
- Produces:
  - `prepareBlocks(blocks, entries)` — extended return shape: `idleSeconds`,
    `fragments`, `longestFragmentSeconds`, `domains: [{name,seconds}]`,
    `timeline: [{offset,seconds,topic,idle}]`, `createdWith: String`, `guessed: false`,
    `skipped: false`, `inspectOpen: false`, `editOpen: false`. The single `expanded`
    flag is removed.
  - `blockReady(block) => Boolean` — new `Model.js` export, moved from
    `Panel.qml:532-534`, with `!block.guessed` added to its existing checks.

This task leaves the current inline day-block UI in `Panel.qml` reading a now-missing
`.expanded` field — every `visible: blockRow.expanded` binding there evaluates to
`undefined`, i.e. `false`. The drawers appear permanently closed until Task 6 replaces
that UI wholesale. The panel still loads and does not crash; nothing here is a
regression a user can hit, since Task 6 lands in the same work session before this ships.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model.mjs`, after the existing `prepareBlocks` tests (currently
ending around line 97):

```js
test("prepareBlocks carries idle, fragment, domain and timeline fields through", () => {
  const blocks = [{
    seconds: 8712, span_seconds: 9660, idle_seconds: 948, fragments: 63,
    longest_fragment_seconds: 660, label: "x",
    domains: [{ name: "bitbucket.org", seconds: 1740 }],
    timeline: [
      { offset: 0, seconds: 840, topic: "Zed", idle: false },
      { offset: 840, seconds: 60, topic: "", idle: true }
    ]
  }]
  const prepared = Model.prepareBlocks(blocks, [])
  assert.equal(prepared[0].idleSeconds, 948)
  assert.equal(prepared[0].fragments, 63)
  assert.equal(prepared[0].longestFragmentSeconds, 660)
  assert.deepEqual(prepared[0].domains, [{ name: "bitbucket.org", seconds: 1740 }])
  assert.deepEqual(prepared[0].timeline, [
    { offset: 0, seconds: 840, topic: "Zed", idle: false },
    { offset: 840, seconds: 60, topic: "", idle: true }
  ])
})

test("prepareBlocks defaults idle/fragment/domain/timeline fields when absent", () => {
  const prepared = Model.prepareBlocks([{ seconds: 60, label: "x" }], [])
  assert.equal(prepared[0].idleSeconds, 0)
  assert.equal(prepared[0].fragments, 0)
  assert.equal(prepared[0].longestFragmentSeconds, 0)
  assert.deepEqual(prepared[0].domains, [])
  assert.deepEqual(prepared[0].timeline, [])
})

test("prepareBlocks replaces the single expanded flag with per-drawer flags", () => {
  const prepared = Model.prepareBlocks([{ seconds: 60, label: "x" }], [])
  assert.equal(prepared[0].guessed, false)
  assert.equal(prepared[0].skipped, false)
  assert.equal(prepared[0].inspectOpen, false)
  assert.equal(prepared[0].editOpen, false)
  assert.equal(prepared[0].expanded, undefined)
})

test("prepareBlocks records createdWith for an applied block, empty for a pending one", () => {
  const blocks = [
    { seconds: 60, applied: true, conflict: { id: 5 } },
    { seconds: 60, applied: false }
  ]
  const entries = [{ id: 5, created_with: "omarchy-toggl-track/day" }]
  const prepared = Model.prepareBlocks(blocks, entries)
  assert.equal(prepared[0].createdWith, "omarchy-toggl-track/day")
  assert.equal(prepared[1].createdWith, "")
})

test("blockReady requires state pending, no busy request, a project, a description and no unconfirmed guess", () => {
  const ready = { state: "pending", busy: false, guessed: false, projectId: 4, description: "Work" }
  assert.equal(Model.blockReady(ready), true)
  assert.equal(Model.blockReady({ ...ready, guessed: true }), false)
  assert.equal(Model.blockReady({ ...ready, busy: true }), false)
  assert.equal(Model.blockReady({ ...ready, projectId: 0 }), false)
  assert.equal(Model.blockReady({ ...ready, description: "   " }), false)
  assert.equal(Model.blockReady({ ...ready, state: "applied" }), false)
  assert.equal(Model.blockReady(null), false)
  assert.equal(Model.blockReady(undefined), false)
})
```

Add `blockReady` to the exported-function object at the top of the file (currently
lines 14-19):

```js
const Model = new Function(`${source}\nreturn {
  compactDuration, clockTime, isoDate, todayDate, shiftDate, dayLabel,
  prepareBlocks, blockAlso, blockSummary, formatDuration, clampHistory,
  clampBlockMinutes, historyFloor, boundedShiftDate, blockReady,
  searchItems, normalizeProject, normalizeTask, applySummaryDelta
}`)()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node tests/test_model.mjs
```

Expected: `FAIL prepareBlocks carries idle, fragment, domain and timeline fields
through` and the four tests after it, plus a `TypeError: Model.blockReady is not a
function` from the last one — `prepareBlocks` does not yet return these fields and
`blockReady` does not exist in `Model.js`.

- [ ] **Step 3: Extend `prepareBlocks()` and add `blockReady()`**

Replace `prepareBlocks()` in `Model.js` (currently lines 65-94):

```js
function prepareBlocks(blocks, entries) {
  var byId = {}
  ;(entries || []).forEach(function(entry) { if (entry && entry.id !== undefined) byId[String(entry.id)] = entry })
  return (blocks || []).map(function(block) {
    var conflict = block.conflict || null
    var owner = conflict && byId[String(conflict.id)]
    var createdWith = String((owner && (owner.created_with || owner.createdWith)) || "")
    return {
      start: block.start,
      end: block.end,
      seconds: number(block.seconds, 0),
      spanSeconds: number(block.span_seconds, number(block.seconds, 0)),
      idleSeconds: number(block.idle_seconds, 0),
      fragments: number(block.fragments, 0),
      longestFragmentSeconds: number(block.longest_fragment_seconds, 0),
      label: String(block.label || ""),
      topics: (block.topics || []).map(function(topic) {
        return { name: String(topic.name || ""), seconds: number(topic.seconds, 0) }
      }),
      apps: block.apps || [],
      domains: (block.domains || []).map(function(domain) {
        return { name: String(domain.name || ""), seconds: number(domain.seconds, 0) }
      }),
      domain: String(block.domain || ""),
      timeline: (block.timeline || []).map(function(tick) {
        return { offset: number(tick.offset, 0), seconds: number(tick.seconds, 0), topic: String(tick.topic || ""), idle: !!tick.idle }
      }),
      conflict: conflict,
      createdWith: createdWith,
      // Ours renders as applied; anyone else's overlap is a conflict to resolve.
      state: !block.applied ? "pending" : (createdWith.indexOf("omarchy-toggl-track") === 0 ? "applied" : "conflict"),
      description: String(block.label || ""),
      projectId: 0,
      taskId: 0,
      // classify() (stage 6) sets guessed true alongside description/projectId.
      // blockReady() below requires !guessed, so an unconfirmed guess can never
      // reach applyQueue.
      guessed: false,
      // Session-local dismissal (Backspace, ui/DayScope.qml). Reset on every
      // prepareBlocks() call, i.e. on every day reload, by design — "for this
      // session" per spec S7.5.
      skipped: false,
      busy: false,
      failure: "",
      inspectOpen: false,
      editOpen: false
    }
  })
}

// Moved from Panel.qml so it is covered by tests/test_model.mjs. A guessed row
// is not ready until the user has touched it (which clears guessed elsewhere),
// so a batch apply built from dayBlocks.filter(blockReady) can never include an
// unreviewed guess.
function blockReady(block) {
  return !!block && block.state === "pending" && !block.busy && !block.guessed && !!block.projectId && String(block.description || "").trim().length > 0
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node tests/test_model.mjs
```

Expected: every test prints `ok`, `0` failures reported at the end.

- [ ] **Step 5: Commit**

```bash
git add Model.js tests/test_model.mjs
git commit -m "feat(model): carry idle/fragment/domain/timeline fields, move blockReady into Model.js

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `ui/DayScope.qml` — day header and the seven row states

**Files:**
- Modify: `ui/DayScope.qml` (stub from stage 2)
- Modify: `Panel.qml` — instantiate `DayScope`, delete the inline day-block UI it replaces

**Interfaces:**
- Consumes:
  - `Model.clockDuration(seconds) => String` — stage 3, pattern `<H>h<MM>`, both
    segments always present, minutes zero-padded, no space, no unit letters (ruling R-D).
  - `Model.blockReady`, `Model.prepareBlocks` — Task 1.
  - `Model.clockTime(isoValue) => String`, `Model.dayLabel(dateValue) => String` — existing.
  - `Model.blockSummary(blocks) => {totalSeconds,ready,unassigned,applied,conflicts}` — existing.
  - `root.dayBlocks`, `root.dayCursorIndex`, `root.dayRevision`, `root.daySummary`,
    `root.dayDate`, `root.dayError`, `root.dayLoaded`, `root.projects`,
    `root.fontFamily`, `root.shiftDay(days)` — `Panel.qml` state (existing, plus
    `dayCursorIndex` from stage 3 per ruling R-B).
  - `ui/PanelTheme.qml` roles `text`, `textMuted` (0.72 alpha), `textFaint` (0.55),
    `textDisabled` (0.38), `accent`, `urgent` — stage 2, per spec §9.1. **Gap found and
    flagged in this plan's Self-Review**: neither `ui/PanelTheme.qml`'s spec nor any
    `qs.Commons.Color` role covers the guide's `--warn` token, needed here for the
    guessed-row `~` marker. This task references `PanelTheme.warn`, assuming stage 2's
    plan is amended to add it (see Self-Review) — if it is not, the one line below
    marked `// PanelTheme.warn` needs a real value before this task can visually match
    the guide.
- Produces:
  - `ui/DayScope.qml`'s `panel` property — the contract every later task in this stage
    builds on: `DayScope { panel: root; ... }` inside `Panel.qml`.
  - `rowState(block) => String` — one of `"applied" "ready" "guessed" "unassigned"
    "conflict" "inflight" "skipped"`, a pure function on `dayScope`, not `Model.js`,
    because it reads no external data beyond the block itself and stays local to this
    file's rendering — no other file needs it.

This task defines the **skipped** row state per ruling R-N, which neither the spec nor
the guide render anywhere. Design decision, stated here because R-N requires it:
skip is a session-local dismissal, gated to `state === "pending"` rows only (marking an
already-applied or already-conflicting row "skipped" is meaningless, so `Backspace` is a
no-op there — implemented in Task 5). It does **not** change `blockReady()` — the spec's
only stated exclusion from readiness is an unconfirmed guess (§7.5), and a skipped row
stays fully applicable via `Enter` or `Shift+Enter` if the user changes their mind
without first un-skipping it, avoiding a silent behaviour change nothing asked for. It
renders with glyph `⌫` (the same character the hint row already uses for the skip key,
so the row-state glyph and its own keybinding hint read as one idea) at
`PanelTheme.textFaint`, the same tier as `unassigned` — the dimmest tier, since a skipped
row is explicitly set aside — with label, duration and trailing text (`"skipped"`) at the
same tier. It still contributes to `daySummary.totalSeconds` unconditionally, because
`blockSummary()` (`Model.js`, unmodified by this stage) sums every block's `seconds`
regardless of state — nothing here excludes it.

- [ ] **Step 1: Write `ui/DayScope.qml`'s header and row rendering**

```qml
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../Model.js" as Model

Item {
    id: dayScope

    // Panel.qml's root. DayScope is presentation and interaction only, per spec
    // S5's architecture table — Panel.qml keeps state, request() and
    // handleResponse(). Every mutation goes back through panel.mutateBlock(),
    // panel.applyBlock() etc. so dayRevision keeps bumping correctly.
    property var panel: null

    implicitHeight: column.implicitHeight

    function rowState(block) {
        if (block.busy)
            return "inflight"
        if (block.state === "applied")
            return "applied"
        if (block.state === "conflict")
            return "conflict"
        if (block.skipped)
            return "skipped"
        if (!block.projectId || !String(block.description || "").trim())
            return "unassigned"
        if (block.guessed)
            return "guessed"
        return "ready"
    }

    function glyphFor(kind) {
        return ({
            applied: "✓", ready: "●", guessed: "●", unassigned: "◌",
            conflict: "▲", inflight: "◍", skipped: "⌫"
        })[kind]
    }

    function glyphColorFor(kind) {
        if (kind === "applied")
            return PanelTheme.textMuted
        if (kind === "ready" || kind === "guessed")
            return PanelTheme.accent
        if (kind === "conflict")
            return PanelTheme.urgent
        return PanelTheme.textFaint
    }

    function labelColorFor(kind) {
        if (kind === "applied")
            return PanelTheme.textMuted
        if (kind === "unassigned" || kind === "skipped")
            return PanelTheme.textFaint
        return PanelTheme.text
    }

    function durationColorFor(kind) {
        if (kind === "applied")
            return PanelTheme.textMuted
        if (kind === "skipped")
            return PanelTheme.textFaint
        return PanelTheme.accent
    }

    function projectLabel(block) {
        var list = dayScope.panel.projects || []
        for (var i = 0; i < list.length; i++) {
            if (String(list[i].id) === String(block.projectId)) {
                var client = list[i].clientName
                return (client ? client + " · " : "") + list[i].name
            }
        }
        return ""
    }

    function trailingFor(kind, block) {
        if (kind === "unassigned")
            return "— unassigned —"
        if (kind === "conflict")
            return "conflict · manual"
        if (kind === "inflight")
            return "writing…"
        if (kind === "skipped")
            return "skipped"
        var label = dayScope.projectLabel(block)
        // guide R4-7: the guess marker is its own colour, not the label's —
        // rendered inline via rich text rather than a second Text element, to
        // keep the row a single grid cell wide.
        return kind === "guessed" ? label + " <font color=\"" + PanelTheme.warn + "\">~</font>" : label
    }

    function trailingColorFor(kind) {
        if (kind === "conflict")
            return PanelTheme.urgent
        return PanelTheme.textFaint
    }

    function countLine() {
        var s = dayScope.panel.daySummary
        return s.applied + " APPLIED · " + s.ready + " READY · " + s.unassigned + " UNASSIGNED · " + s.conflicts + " CONFLICT"
    }

    ColumnLayout {
        id: column

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.rowGap

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            Text {
                text: "‹"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.bodySmall

                MouseArea {
                    anchors.fill: parent
                    onClicked: dayScope.panel.shiftDay(-1)
                }
            }

            Text {
                text: Model.dayLabel(dayScope.panel.dayDate)
                color: PanelTheme.text
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.weight: Font.Medium
            }

            Text {
                text: "›"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.bodySmall

                MouseArea {
                    anchors.fill: parent
                    onClicked: dayScope.panel.shiftDay(1)
                }
            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text: (dayScope.panel.dayRevision, Model.clockDuration(dayScope.panel.daySummary.totalSeconds))
                color: PanelTheme.accent
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
            }
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignRight
            visible: dayScope.panel.dayBlocks.length > 0
            text: (dayScope.panel.dayRevision, dayScope.countLine())
            color: PanelTheme.textFaint
            font.family: dayScope.panel.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
        }

        PanelSeparator {
            Layout.fillWidth: true
            foreground: dayScope.panel.foreground
        }

        Text {
            visible: dayScope.panel.dayLoaded === false
            text: "Reading local activity…"
            color: PanelTheme.textFaint
            font.family: dayScope.panel.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        Text {
            Layout.fillWidth: true
            visible: dayScope.panel.dayError !== ""
            text: dayScope.panel.dayError
            color: PanelTheme.urgent
            font.family: dayScope.panel.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: dayScope.panel.dayLoaded && dayScope.panel.dayError === "" && dayScope.panel.dayBlocks.length === 0
            text: "No tracked activity for this day. Omalog records activity through ActivityWatch on 127.0.0.1:5600."
            color: PanelTheme.textFaint
            font.family: dayScope.panel.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Repeater {
            model: dayScope.panel.dayBlocks

            delegate: Rectangle {
                id: blockRow

                required property var modelData
                required property int index

                readonly property int rev: dayScope.panel.dayRevision
                readonly property string kind: (rev, dayScope.rowState(modelData))
                readonly property bool selected: (rev, index === dayScope.panel.dayCursorIndex)

                Layout.fillWidth: true
                implicitHeight: 22
                color: selected ? Style.selectedFill : (rowHover.hovered ? Style.hoverFill : "transparent")

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 2
                    anchors.rightMargin: 2
                    spacing: Style.spacing.rowGap

                    Text {
                        Layout.preferredWidth: 11
                        horizontalAlignment: Text.AlignHCenter
                        text: (blockRow.rev, dayScope.glyphFor(blockRow.kind))
                        color: dayScope.glyphColorFor(blockRow.kind)
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        Layout.preferredWidth: 36
                        text: (blockRow.rev, Model.clockTime(blockRow.modelData.start))
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        Layout.preferredWidth: 34
                        text: (blockRow.rev, Model.clockDuration(blockRow.modelData.seconds))
                        color: dayScope.durationColorFor(blockRow.kind)
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: (blockRow.rev, blockRow.modelData.description)
                        color: dayScope.labelColorFor(blockRow.kind)
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                        textFormat: Text.RichText
                        text: (blockRow.rev, dayScope.trailingFor(blockRow.kind, blockRow.modelData))
                        color: dayScope.trailingColorFor(blockRow.kind)
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }

                HoverHandler {
                    id: rowHover
                }
            }
        }
    }
}
```

- [ ] **Step 2: Instantiate `DayScope` from `Panel.qml`, delete the inline block it replaces**

The current inline day UI runs from the `dayhead`-equivalent `ColumnLayout` through the
`APPLY ASSIGNED` `RowLayout` (verified against master at commit `65ae1c0`,
`Panel.qml:1371-1677` inclusive of the surrounding container — if stage 2/3 already
moved surrounding structure, locate this block by its content: it starts at the
`Model.compactDuration(root.daySummary.totalSeconds)` `Text` and ends at the
`APPLY ASSIGNED · ` `Button`). Delete that whole span and replace it with:

```qml
DayScope {
    id: dayScope
    Layout.fillWidth: true
    panel: root
}
```

Delete `Panel.qml`'s `toggleBlock()` function (currently lines 524-530) — its
sibling-collapsing behaviour is exactly what ruling R-B and spec §7.2 remove, and
Task 5 replaces it with per-drawer open calls that never touch a sibling row.

Delete `Panel.qml`'s local `blockReady()` function (currently lines 532-534). Update
its three call sites — `submitBlock()` (line 537), `applyBlock()` (line 568) and
`applyAssigned()`'s filter (line 579) — from `blockReady(block)` /
`dayBlocks.filter(blockReady)` to `Model.blockReady(block)` /
`dayBlocks.filter(Model.blockReady)`.

- [ ] **Step 3: `qmlformat`**

```bash
qmlformat -n -i ui/DayScope.qml Panel.qml
qmlformat ui/DayScope.qml Panel.qml >/dev/null; echo "exit: $?"
```

Expected: `exit: 0`, checked directly, not piped.

- [ ] **Step 4: `omarchy plugin validate`**

```bash
omarchy plugin validate .
```

Expected: exit 0.

- [ ] **Step 5: Restart and look at it**

```bash
omarchy-restart-shell
```

Open the panel, switch to day scope, and load a day with at least one block in each of
applied/ready/guessed/unassigned/conflict state (or point `dayDate` at a day known to
have a mix). Compare against `design-guide.html` §02 and §05 side by side:

- Six-state gallery matches glyph, colour and trailing text exactly for
  applied/ready/guessed/unassigned/conflict/in-flight.
- The day header shows the total in `<H>h<MM>` and the count line reads
  `N APPLIED · N READY · N UNASSIGNED · N CONFLICT`.
- The row grid columns line up: an 11px glyph, then time, then duration, then a
  filling label, then trailing text flush right.
- No `Qt.darker` colour anywhere in this view — confirm with `grep -c Qt.darker
  ui/DayScope.qml`, expect `0`.

- [ ] **Step 6: Commit**

```bash
git add ui/DayScope.qml Panel.qml
git commit -m "feat(day): render day header and the seven row states in ui/DayScope.qml

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Inspect drawer — facts, fragment timeline, topic/app/domain bars

**Files:**
- Modify: `ui/DayScope.qml`

**Interfaces:**
- Consumes: `block.spanSeconds`, `.idleSeconds`, `.fragments`, `.longestFragmentSeconds`,
  `.topics[]`, `.apps[]`, `.domains[]`, `.timeline[]`, `.conflict`, `.createdWith` — Task 1.
  `Model.compactDuration()` — existing, for `idle removed` / `switches` / `longest run`.
  `Model.clockDuration()` — stage 3, for `active` / `wall`.
- Produces: `Rectangle { onClicked: ... }` on the row (mouse path for opening inspect,
  since the six-state row rendering in Task 2 shipped with no interaction yet).

The design guide's inspect-drawer markup (§03) colours the fragment timeline and the
TOPICS bars per-project (`--p-backend` / `--p-docs` / `--p-support`). The block schema
those bars are drawn from — `topics[]` is `{name, seconds}`, `timeline[]` is
`{offset, seconds, topic, idle}` (spec §10.3, already merged, unchanged) — carries no
project id, colour or app field per fragment, and a block has exactly one project
assignment for its whole span, not one per fragment. There is no data path that lets a
single block's timeline or topic bars legitimately carry three different colours. This
plan resolves it the only way buildable against the actual schema: fragment-timeline
ticks and TOPICS bars render with the same flat neutral fill the guide itself already
uses for APPS (`rgba(205,214,244,0.34)`, per R4-15) — TOPICS and APPS end up visually
identical in tint; only DOMAINS keeps a distinct fill (`rgba(137,180,250,0.45)`, R4-16,
since that one is already flat in the guide, not per-item). This is a deliberate
departure from the guide's literal rendering, flagged in this plan's Self-Review and
`open_questions` for confirmation, not a silent substitution.

- [ ] **Step 1: Add the click-to-open interaction to the row from Task 2**

Inside `blockRow`'s `Rectangle` (Task 2), add:

```qml
MouseArea {
    anchors.fill: parent
    z: -1
    onClicked: {
        dayScope.panel.dayCursorIndex = blockRow.index
        dayScope.panel.mutateBlock(blockRow.modelData, function() {
            blockRow.modelData.inspectOpen = !blockRow.modelData.inspectOpen
        })
    }
}
```

- [ ] **Step 2: Add the inspect drawer**

Inside `blockRow`'s `Rectangle`, as a sibling to the row `RowLayout` (so the drawer sits
directly under its row and the `Rectangle`'s `implicitHeight` must switch from a fixed
`22` to `column.implicitHeight` to make room — update Task 2's `implicitHeight: 22` to
`implicitHeight: inner.implicitHeight`):

```qml
ColumnLayout {
    id: inner
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 22
        anchors.leftMargin: 2
        anchors.rightMargin: 2
        spacing: Style.spacing.rowGap
        // ... Task 2's five Text elements move here unchanged ...
    }

    Rectangle {
        id: inspectDrawer

        readonly property bool open: (blockRow.rev, blockRow.modelData.inspectOpen)

        Layout.fillWidth: true
        Layout.leftMargin: 19
        Layout.topMargin: 4
        Layout.bottomMargin: 6
        visible: inspectDrawer.open
        implicitHeight: inspectDrawer.open ? inspectColumn.implicitHeight + 18 : 0
        color: "transparent"
        border.width: 0

        Rectangle {
            width: 1
            height: parent.height
            color: Qt.rgba(0.804, 0.839, 0.957, 0.22)
        }

        ColumnLayout {
            id: inspectColumn
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 9
            anchors.bottomMargin: 9
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                Text {
                    textFormat: Text.RichText
                    text: "<font color=\"" + PanelTheme.text + "\">" + Model.clockDuration(blockRow.modelData.seconds) + "</font> active"
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: Model.clockDuration(blockRow.modelData.spanSeconds) + " wall"
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: Model.compactDuration(blockRow.modelData.idleSeconds) + " idle removed"
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: blockRow.modelData.fragments + " switches"
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: "longest run " + Model.compactDuration(blockRow.modelData.longestFragmentSeconds)
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 16
                spacing: 1

                Repeater {
                    model: inspectDrawer.open ? blockRow.modelData.timeline : []

                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillHeight: true
                        Layout.fillWidth: true
                        Layout.preferredWidth: Math.max(1, modelData.seconds)
                        opacity: modelData.idle ? 1.0 : 0.85
                        color: modelData.idle ? "transparent" : Qt.rgba(0.804, 0.839, 0.957, 0.34)

                        // Idle ticks: the guide's repeating 45deg hatch, approximated
                        // as three thin diagonal bars since QML has no CSS
                        // repeating-linear-gradient primitive.
                        Repeater {
                            model: modelData.idle ? Math.ceil(width / 3) : []
                            delegate: Rectangle {
                                required property int index
                                x: index * 3
                                width: 1
                                height: parent.height
                                color: Qt.rgba(0.804, 0.839, 0.957, 0.10)
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                RowLayout {
                    spacing: 5
                    Rectangle {
                        width: 7
                        height: 7
                        color: Qt.rgba(0.804, 0.839, 0.957, 0.34)
                    }
                    Text {
                        text: "active"
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }
                RowLayout {
                    spacing: 5
                    Rectangle {
                        width: 7
                        height: 7
                        color: Qt.rgba(0.804, 0.839, 0.957, 0.12)
                    }
                    Text {
                        text: "idle, removed"
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }
            }

            Text {
                text: "TOPICS"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            Repeater {
                model: inspectDrawer.open ? blockRow.modelData.topics.slice(0, 8) : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.spacing.rowGap + 7
                    spacing: Style.spacing.rowGap

                    Text {
                        Layout.preferredWidth: 34
                        text: Model.compactDuration(modelData.seconds)
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 7
                        color: Qt.rgba(0.804, 0.839, 0.957, 0.07)

                        Rectangle {
                            width: parent.width * Math.min(1, modelData.seconds / Math.max(1, blockRow.modelData.spanSeconds))
                            height: parent.height
                            color: Qt.rgba(0.804, 0.839, 0.957, 0.34)
                        }
                    }
                    Text {
                        Layout.preferredWidth: 140
                        elide: Text.ElideRight
                        text: modelData.name.length > 30 ? modelData.name.slice(0, 30) + "…" : modelData.name
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }
            }

            Text {
                text: "APPS"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            Repeater {
                model: inspectDrawer.open ? (blockRow.modelData.apps || []).slice(0, 8) : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.spacing.rowGap + 7
                    spacing: Style.spacing.rowGap

                    Text {
                        Layout.preferredWidth: 34
                        text: Model.compactDuration(modelData.seconds)
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 7
                        color: Qt.rgba(0.804, 0.839, 0.957, 0.07)

                        Rectangle {
                            width: parent.width * Math.min(1, (modelData.seconds || 0) / Math.max(1, blockRow.modelData.spanSeconds))
                            height: parent.height
                            color: Qt.rgba(0.804, 0.839, 0.957, 0.34)
                        }
                    }
                    Text {
                        Layout.preferredWidth: 140
                        elide: Text.ElideRight
                        text: String(modelData.name || "").length > 30 ? String(modelData.name).slice(0, 30) + "…" : String(modelData.name || "")
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }
            }

            Text {
                text: "DOMAINS"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            Repeater {
                model: inspectDrawer.open ? blockRow.modelData.domains.slice(0, 8) : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.spacing.rowGap + 7
                    spacing: Style.spacing.rowGap

                    Text {
                        Layout.preferredWidth: 34
                        text: Model.compactDuration(modelData.seconds)
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 7
                        color: Qt.rgba(0.804, 0.839, 0.957, 0.07)

                        Rectangle {
                            width: parent.width * Math.min(1, modelData.seconds / Math.max(1, blockRow.modelData.spanSeconds))
                            height: parent.height
                            color: Qt.rgba(0.537, 0.706, 0.980, 0.45)
                        }
                    }
                    Text {
                        Layout.preferredWidth: 140
                        elide: Text.ElideRight
                        text: modelData.name.length > 30 ? modelData.name.slice(0, 30) + "…" : modelData.name
                        color: PanelTheme.textFaint
                        font.family: dayScope.panel.fontFamily
                        font.pixelSize: Style.font.caption
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 2
                visible: blockRow.kind === "applied"
                spacing: 14

                Text {
                    text: "written as entry #" + (blockRow.modelData.conflict ? blockRow.modelData.conflict.id : "")
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: "created_with " + blockRow.modelData.createdWith
                    color: PanelTheme.textFaint
                    font.family: dayScope.panel.fontFamily
                    font.pixelSize: Style.font.caption
                }
            }
        }
    }
}
```

`Qt.rgba(0.804, 0.839, 0.957, N)` is `rgba(205,214,244,N)` (the guide's neutral base,
`--fg` at reduced alpha) expressed as QML's 0-1 channel range; `Qt.rgba(0.537, 0.706,
0.980, 0.45)` is `rgba(137,180,250,0.45)`, the accent tint R4-16 specifies for DOMAINS.

- [ ] **Step 2: `qmlformat`**

```bash
qmlformat ui/DayScope.qml >/dev/null; echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 3: Restart and look at it**

```bash
omarchy-restart-shell
```

Click a ready or applied row. Compare the opened drawer against `design-guide.html`
§03's inspect column:

- Dim rule on the left, no bordered/focusable control anywhere inside.
- Facts line: `active` highlighted, the other four dim, in the exact order and copy
  from §03: active, wall, idle removed, switches, longest run.
- Fragment timeline renders with proportional ticks and a visibly different idle
  segment; legend below it.
- TOPICS / APPS / DOMAINS sections each show seconds, a track bar and a name, in that
  column order.
- An applied row additionally shows the `written as entry #…` / `created_with …` lines;
  a non-applied row does not.
- Opening a second row's drawer does not close the first (any number of drawers open at
  once).

- [ ] **Step 4: Commit**

```bash
git add ui/DayScope.qml
git commit -m "feat(day): inspect drawer with facts, fragment timeline and topic/app/domain bars

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Edit drawer — description, project/task token field, apply wiring

**Files:**
- Modify: `ui/DayScope.qml`

**Interfaces:**
- Consumes: `Model.parseCommand(text, projects, tasks, tags) => {description, projectId,
  taskId, tags, billable, completion, unmatched}` — stage 3. `root.mutateBlock()`,
  `root.applyBlock()` — existing.
- Produces: nothing new consumed elsewhere in this stage; Task 5 reuses the drawer's
  open/close flags it sets here.

Per R4-19, this replaces the current two-`SearchableDropdown` project/task picker
(`Panel.qml:1577-1615` pre-redesign) with a single free-text field parsed by the same
token grammar as the command line. Only `@project` / `@project/task` tokens are
meaningful here — the field is not a general command composer, so any plain text typed
into it that `parseCommand` would otherwise read as `description`, `#tag` or `$`
billable is simply discarded; only `.projectId` / `.taskId` are read from the parse
result.

- [ ] **Step 1: Add the edit-drawer open/switch interactions**

Add a second `MouseArea` inside `blockRow`'s row `RowLayout` (a small hit target on the
trailing-text `Text`, so clicking the row body still opens inspect per Task 3, matching
the existing app's convention of a full-row click target for the cheap action and a
smaller one for the deliberate one):

```qml
Text {
    id: editHandle
    text: "e"
    visible: blockRow.selected
    color: PanelTheme.accent
    font.family: dayScope.panel.fontFamily
    font.pixelSize: Style.font.caption

    MouseArea {
        anchors.fill: parent
        onClicked: dayScope.openEdit(blockRow.modelData)
    }
}
```

Add to `dayScope`'s function block (alongside `rowState` etc. from Task 2):

```js
function openEdit(block) {
    dayScope.panel.mutateBlock(block, function() {
        block.editOpen = true
        block.inspectOpen = false
    })
}

function backToInspect(block) {
    dayScope.panel.mutateBlock(block, function() {
        block.editOpen = false
        block.inspectOpen = true
    })
}

function closeDrawers(block) {
    dayScope.panel.mutateBlock(block, function() {
        block.editOpen = false
        block.inspectOpen = false
    })
}
```

- [ ] **Step 2: Add the edit drawer**

As a sibling to `inspectDrawer` inside `inner` (Task 3):

```qml
Rectangle {
    id: editDrawer

    readonly property bool open: (blockRow.rev, blockRow.modelData.editOpen)

    Layout.fillWidth: true
    Layout.leftMargin: 19
    Layout.topMargin: 4
    Layout.bottomMargin: 6
    visible: editDrawer.open
    implicitHeight: editDrawer.open ? editColumn.implicitHeight + 18 : 0
    color: "transparent"

    Rectangle {
        width: 1
        height: parent.height
        color: PanelTheme.accent
    }

    ColumnLayout {
        id: editColumn
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 9
        anchors.bottomMargin: 9
        spacing: 10

        TextField {
            id: descriptionField
            Layout.fillWidth: true
            visible: editDrawer.open
            text: (blockRow.rev, blockRow.modelData.description)
            placeholderText: "Describe this block"
            foreground: PanelTheme.text
            onTextChanged: {
                if (!editDrawer.open || text === blockRow.modelData.description)
                    return
                dayScope.panel.mutateBlock(blockRow.modelData, function() {
                    blockRow.modelData.description = text
                    blockRow.modelData.guessed = false
                })
            }
        }

        TextField {
            id: projectTaskField
            Layout.fillWidth: true
            visible: editDrawer.open
            text: (blockRow.rev, dayScope.tokenTextFor(blockRow.modelData))
            placeholderText: "@project or @project/task"
            foreground: PanelTheme.text
            onTextChanged: {
                if (!editDrawer.open)
                    return
                var parsed = Model.parseCommand(text, dayScope.panel.projects, dayScope.panel.tasks, [])
                if (parsed.projectId === blockRow.modelData.projectId && parsed.taskId === blockRow.modelData.taskId)
                    return
                dayScope.panel.mutateBlock(blockRow.modelData, function() {
                    blockRow.modelData.projectId = parsed.projectId
                    blockRow.modelData.taskId = parsed.taskId
                    blockRow.modelData.guessed = false
                })
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            Text {
                text: Model.clockDuration(blockRow.modelData.seconds) + " active"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
            }
            Text {
                text: Model.clockDuration(blockRow.modelData.spanSeconds) + " wall"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
            }
            Text {
                text: blockRow.modelData.fragments + " switches"
                color: PanelTheme.textFaint
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
            }
            Text {
                Layout.fillWidth: true
                text: "writes a completed entry · never touches the running timer"
                color: PanelTheme.text
                font.family: dayScope.panel.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
            }
        }

        Text {
            Layout.fillWidth: true
            visible: String(blockRow.modelData.failure || "") !== ""
            text: blockRow.modelData.failure
            color: PanelTheme.urgent
            font.family: dayScope.panel.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
        }
    }
}
```

Add `tokenTextFor()` to `dayScope`'s function block — it renders the current
`projectId`/`taskId` back into `@project` / `@project/task` text so the field shows
something meaningful before the user has typed anything:

```js
function tokenTextFor(block) {
    if (!block.projectId)
        return ""
    var project = null
    for (var i = 0; i < dayScope.panel.projects.length; i++) {
        if (String(dayScope.panel.projects[i].id) === String(block.projectId))
            project = dayScope.panel.projects[i]
    }
    if (!project)
        return ""
    var slug = "@" + project.name
    if (!block.taskId)
        return slug
    var task = null
    for (var j = 0; j < dayScope.panel.tasks.length; j++) {
        if (String(dayScope.panel.tasks[j].id) === String(block.taskId))
            task = dayScope.panel.tasks[j]
    }
    return task ? slug + "/" + task.name : slug
}
```

Note the guessed-clearing on both fields: per R4-7, `~` disappears "the moment you touch
the row" — `onTextChanged` fires on every keystroke including the one that first opens
the field with its pre-filled text, so the `text === blockRow.modelData.description`
(and the equivalent projectId/taskId comparison) guard is what stops a guessed row from
silently un-guessing itself merely by being opened; only an actual edit clears it.

- [ ] **Step 3: `qmlformat`**

```bash
qmlformat ui/DayScope.qml >/dev/null; echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 4: Restart and look at it**

```bash
omarchy-restart-shell
```

Select an unassigned row, click `e`. Confirm:

- Accent rule on the left; both fields show a focus ring on click (qs.Ui `TextField`
  default, `Style.spacing.controlHeight` = 28px tall).
- Typing `@` plus a known project name resolves to that project once a match exists;
  `@project/task` resolves both ids.
- The reminder line reads exactly `writes a completed entry · never touches the running
  timer`.
- Applying (existing `APPLY` button, still wired to `applyBlock`, verified in Task 5)
  posts via `create_entry`, never `start`/`continue` — check `client_log` in the panel
  or `logs/toggl.jsonl` for the action name after applying.
- A guessed row (`● ~`) loses the `~` the moment either field is actually edited, not
  merely opened.

- [ ] **Step 5: Commit**

```bash
git add ui/DayScope.qml
git commit -m "feat(day): edit drawer with single token-grammar project/task field

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Keyboard dispatch, hint rows, skip, and confirming every mouse path survives

**Files:**
- Modify: `ui/DayScope.qml`

**Interfaces:**
- Consumes: `dayScope.moveCursor(direction)` is the function stage 3's
  scope-conditioned switch on `PanelKeyCatcher` calls for `root.scope === "day"`
  (ruling R-C) — this task is what makes that call resolve to something real. The exact
  key-to-signal mapping stage 3 built this on top of is not re-specified here; verified
  against the actual `qs.Ui` component
  (`/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml`) for this plan's own confidence:
  `Space` fires `activateRequested()`; `Enter`/`Return` fires both `returnRequested()`
  and `activateRequested()`; `x`/`X` fires `deleteRequested()`; unmatched single
  characters (which includes `e`, and — since Ctrl held changes `event.text` to a
  control character rather than the letter itself — `Ctrl+J`/`Ctrl+K`) fall through to
  `textKey(event.text)`. There is no signal carrying `event.modifiers`, so
  Ctrl-detection has to be done by matching the control-character text those combos
  produce (`"\n"` / `""`), not by reading a modifier flag — flagged in
  `open_questions` since it is inferred from the component's source, not proven against
  a running instance.
- Produces: `dayScope.moveCursor(direction)`, `dayScope.applyCursor()`,
  `dayScope.applyAllReady()`, `dayScope.skipCursor()`, `dayScope.toggleInspectCursor()`,
  `dayScope.editCursor()`, `dayScope.closeCursorDrawer()` — the full set of functions
  stage 3's dispatch calls into for `root.scope === "day"`.

- [ ] **Step 1: Add the cursor-acting functions**

Add to `dayScope`'s function block:

```js
function moveCursor(direction) {
    var blocks = dayScope.panel.dayBlocks
    if (blocks.length === 0)
        return
    var current = dayScope.panel.dayCursorIndex
    if (current < 0 || current >= blocks.length) {
        dayScope.panel.dayCursorIndex = direction > 0 ? 0 : blocks.length - 1
        return
    }
    dayScope.panel.dayCursorIndex = Math.max(0, Math.min(blocks.length - 1, current + direction))
}

function cursorBlock() {
    var blocks = dayScope.panel.dayBlocks
    var index = dayScope.panel.dayCursorIndex
    return (index >= 0 && index < blocks.length) ? blocks[index] : null
}

function toggleInspectCursor() {
    var block = dayScope.cursorBlock()
    if (!block)
        return
    if (block.editOpen) {
        dayScope.backToInspect(block)
        return
    }
    dayScope.panel.mutateBlock(block, function() {
        block.inspectOpen = !block.inspectOpen
    })
}

function editCursor() {
    var block = dayScope.cursorBlock()
    if (block)
        dayScope.openEdit(block)
}

function closeCursorDrawer() {
    var block = dayScope.cursorBlock()
    if (block)
        dayScope.closeDrawers(block)
}

function applyCursor() {
    var block = dayScope.cursorBlock()
    if (block && Model.blockReady(block))
        dayScope.panel.applyBlock(block)
}

function applyAllReady() {
    dayScope.panel.applyAssigned()
}

function skipCursor() {
    var block = dayScope.cursorBlock()
    if (!block || block.busy || block.state !== "pending")
        return
    dayScope.panel.mutateBlock(block, function() {
        block.skipped = !block.skipped
    })
}
```

- [ ] **Step 2: Add the three hint-row variants**

As the last child of `column` (Task 2's top-level `ColumnLayout`), below the block
`Repeater`:

```qml
RowLayout {
    Layout.fillWidth: true
    visible: dayScope.panel.dayBlocks.length > 0
    spacing: 14

    readonly property var cursor: (dayScope.panel.dayRevision, dayScope.cursorBlock())

    Text {
        visible: !!parent.cursor && parent.cursor.editOpen
        text: "EDIT"
        color: PanelTheme.accent
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
        font.letterSpacing: 1
    }
    Text {
        visible: !!parent.cursor && !parent.cursor.editOpen && parent.cursor.inspectOpen
        text: "INSPECT"
        color: PanelTheme.accent
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
        font.letterSpacing: 1
    }

    // Base hints — no drawer open on the cursor row.
    Text {
        visible: !parent.cursor || (!parent.cursor.inspectOpen && !parent.cursor.editOpen)
        text: "space inspect"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !parent.cursor || (!parent.cursor.inspectOpen && !parent.cursor.editOpen)
        text: "e edit"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !parent.cursor || (!parent.cursor.inspectOpen && !parent.cursor.editOpen)
        text: "↵ apply"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !parent.cursor || (!parent.cursor.inspectOpen && !parent.cursor.editOpen)
        text: "⇧↵ apply ready · " + dayScope.panel.daySummary.ready
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !parent.cursor || (!parent.cursor.inspectOpen && !parent.cursor.editOpen)
        text: "⌫ skip"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }

    // Inspect-open hints.
    Text {
        visible: !!parent.cursor && parent.cursor.inspectOpen && !parent.cursor.editOpen
        text: "e switch to edit"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !!parent.cursor && parent.cursor.inspectOpen && !parent.cursor.editOpen
        text: "space close"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !!parent.cursor && (parent.cursor.inspectOpen || parent.cursor.editOpen)
        text: "^j/^k next block"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }

    // Edit-open hints.
    Text {
        visible: !!parent.cursor && parent.cursor.editOpen
        text: "↵ save + apply"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !!parent.cursor && parent.cursor.editOpen
        text: "space back to inspect"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
    Text {
        visible: !!parent.cursor && parent.cursor.editOpen
        text: "esc close"
        color: PanelTheme.textFaint
        font.family: dayScope.panel.fontFamily
        font.pixelSize: Style.font.caption
    }
}
```

`Enter`'s "save + apply" while the edit drawer is open needs one more decision the
guide's copy makes explicit but the spec table does not: pressing `Enter` with the edit
drawer open applies the cursor row (same `applyCursor()` as the base case) rather than
doing nothing — `applyCursor()` already reads current field values through
`blockRow.modelData`, which `onTextChanged` keeps live, so no separate "save" step is
needed before it.

- [ ] **Step 3: Confirm the existing mouse-equivalent paths are untouched**

Per Goal 1 (spec §2) and R4-29, the row-level `APPLY` button and the panel-level
`APPLY ASSIGNED · N` button must survive unchanged. They are not part of this task's
diff — Task 2 did not remove them, and they were never part of the inline block this
plan deleted from `Panel.qml` in Task 2 Step 2 if that block's boundary is drawn
correctly (its `APPLY` button lives inside the row loop this stage now owns in
`ui/DayScope.qml`). Add them explicitly here since Task 2/3/4 did not:

Inside `blockRow`'s row `RowLayout` (alongside the glyph/time/duration/label/trailing
`Text` elements from Task 2):

```qml
Button {
    visible: blockRow.kind === "ready" || blockRow.kind === "guessed" || blockRow.kind === "unassigned" || blockRow.kind === "skipped"
    text: blockRow.modelData.busy ? "…" : "APPLY"
    enabled: !dayScope.panel.requestPending && (blockRow.rev, Model.blockReady(blockRow.modelData))
    focusable: true
    bordered: true
    fontSize: Style.font.caption
    background: (blockRow.rev, Model.blockReady(blockRow.modelData)) ? PanelTheme.accent : "transparent"
    foreground: (blockRow.rev, Model.blockReady(blockRow.modelData)) ? Color.background : PanelTheme.textFaint
    onClicked: dayScope.panel.applyBlock(blockRow.modelData)
}
```

As the last child of `column`, below the hint-row `RowLayout` from Step 2:

```qml
RowLayout {
    Layout.fillWidth: true
    visible: dayScope.panel.dayBlocks.length > 0
    spacing: Style.spacing.rowGap

    Button {
        text: "APPLY ASSIGNED · " + dayScope.panel.daySummary.ready
        enabled: !dayScope.panel.requestPending && dayScope.panel.daySummary.ready > 0
        focusable: true
        bordered: true
        fontSize: Style.font.caption
        background: dayScope.panel.daySummary.ready > 0 ? PanelTheme.accent : "transparent"
        foreground: dayScope.panel.daySummary.ready > 0 ? Color.background : PanelTheme.textFaint
        onClicked: dayScope.applyAllReady()
    }
}
```

- [ ] **Step 4: `qmlformat`**

```bash
qmlformat ui/DayScope.qml >/dev/null; echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 5: Restart and exercise every binding**

```bash
omarchy-restart-shell
```

With focus in day scope and a mix of row states loaded:

- `Ctrl+J` / `Ctrl+K` move the selection highlight down/up one row, clamped at the
  first/last row (no wraparound).
- `Space` on an unselected/closed row opens inspect; `Space` again closes it; `Space`
  while edit is open switches back to inspect (not closed outright).
- `e` opens edit from closed or from inspect.
- `Enter` on a ready row applies it (`create_entry` fires, row transitions toward
  applied once the response returns); `Enter` on an unassigned/conflict row does
  nothing.
- `Shift+Enter` applies every ready row via the existing `applyQueue` drain — watch the
  panel process one row at a time (an in-flight row shows `◍ writing…`), not all at
  once.
- `Backspace` on a pending row toggles the `⌫ skipped` state; pressing it again restores
  the row's underlying state; `Backspace` on an applied or conflict row does nothing.
  Confirm the day header total (`Model.clockDuration(daySummary.totalSeconds)`) does not
  change when a row is skipped.
- The row-level `APPLY` button and the panel-level `APPLY ASSIGNED · N` button both still
  work by mouse alone, with no keyboard interaction.
- Hint row text matches exactly: base (`space inspect · e edit · ↵ apply · ⇧↵ apply
  ready · N · ⌫ skip`), inspect (`INSPECT · e switch to edit · space close · ^j/^k next
  block`), edit (`EDIT · ↵ save + apply · space back to inspect · esc close`).
- `grep -c Qt.darker ui/DayScope.qml` returns `0`.

- [ ] **Step 6: Commit**

```bash
git add ui/DayScope.qml
git commit -m "feat(day): keyboard dispatch, hint rows, skip state, mouse paths preserved

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Integration cleanup and full-stage acceptance pass

**Files:**
- Modify: `Panel.qml` — remove any now-dead remnants of the inline day UI
- Modify: `ui/DayScope.qml` — only if the acceptance pass in this task finds a defect

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task is verification and cleanup, not features.

- [ ] **Step 1: Confirm nothing dead survives in `Panel.qml`**

```bash
grep -n "toggleBlock\|blockRow\|\.expanded\b" Panel.qml
```

Expected: no matches. If any survive, they are leftovers from Task 2 Step 2's deletion
— remove them.

```bash
grep -n "function blockReady" Panel.qml
```

Expected: no matches — the function was moved to `Model.js` in Task 1 and deleted from
`Panel.qml` in Task 2.

- [ ] **Step 2: Full requirements sweep against the design guide**

Open `design-guide.html` and the running panel side by side. Walk R4-1 through R4-35
(this plan's own digest) one by one; every one not listed in this plan's
`requirements_omitted` must visibly hold. Pay special attention to:

- R4-1 / R4-2 / R4-3: open two different rows' drawers at once, confirm neither closes
  the other; confirm the space/e/esc state machine matches §03's hint copy exactly, not
  just approximately.
- R4-9: hover fill only applies to a non-selected row; the selected row keeps
  `Style.selectedFill` regardless of hover.
- R4-31: type into an edit-drawer field, confirm the `TextField` never loses focus
  mid-keystroke (the `dayRevision`/comma-operator pattern is doing its job).
- R4-32: with an edit drawer's field focused, press `j`, `k`, `h`, `l`, `x` and confirm
  they type into the field rather than moving the cursor or deleting anything.

- [ ] **Step 3: Full test and gate run**

```bash
node tests/test_model.mjs
qmlformat ui/DayScope.qml Panel.qml >/dev/null; echo "qmlformat exit: $?"
omarchy plugin validate .
```

Expected: all node tests `ok`, `qmlformat exit: 0`, `omarchy plugin validate .` exit 0.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(day): stage 4 integration cleanup and acceptance pass

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** §7.1 (six row states) is Task 2. §7.2 (two drawers, no accordion) is
Tasks 2-4. §7.3 (inspect contents) is Task 3. §7.4 (edit contents) is Task 4. §7.5
(keyboard) is Task 5. Ruling R-N (skipped state) is defined in Task 2 and wired in
Task 5. Ruling R-B (cursor) and R-C (Ctrl+J/K dispatch) are consumed, not produced, per
their own text — Task 5 implements the `dayScope` side stage 3's switch calls into.

**Deliberately out of scope for this plan, each covered elsewhere:** §6 the command line
and its own result-row Ctrl+J/K (stage 3), §8 the calendar scope (stage 5), §9 theme
coordination's five defects beyond consuming `PanelTheme` (stage 2), §10.4-10.6 the
classifier that populates `guessed` blocks (stage 6).

**requirements_omitted, with reasons:**
- R4-12 (a new zero-padded duration formatter) — not authored here. Ruling R-D moves its
  authorship to stage 3 (`Model.clockDuration()`); this stage only consumes it. The
  digest that produced R4-12 predates the rulings.
- R4-14 (per-topic/per-tick project colouring) — not reproduced literally. No field in
  the merged `day_activity` schema supports it (verified against spec §10.3 directly);
  resolved with a flat neutral fill in Task 3, flagged in `open_questions`.

**Type consistency.** `Model.blockReady()`'s signature and behaviour (Task 1) match
every call site touched in Task 2 Step 2 and reused in Task 5 Step 3 — all now call
`Model.blockReady`, none the deleted `Panel.qml` copy. `prepareBlocks()`'s new fields
(Task 1) are exactly the fields Task 3's inspect drawer reads — `idleSeconds`,
`fragments`, `longestFragmentSeconds`, `domains`, `timeline`, `createdWith` — nothing
consumed there is left undefined by Task 1. `skipped` and `guessed` are read in Task 2's
`rowState()` and written only through `panel.mutateBlock()` in Tasks 4 and 5, never a
bare assignment, so `dayRevision` always bumps.

**A gap this plan surfaced and could not close within its own scope:** neither
`ui/PanelTheme.qml`'s spec (§9.1) nor `qs.Commons.Color` (verified directly against
`/usr/share/omarchy/shell/Commons/Color.qml`) defines a role for the design guide's
`--warn` token (`#f9e2af`). This stage needs it once, for the guessed-row `~` marker
(R4-7); stage 5 and stage 6 are likely to need it too (a calendar flag, per spec §8.4,
and the classifier's local-model warning line, per ruling R-M). Recommend stage 2's plan
— the owner of `ui/PanelTheme.qml` — add `readonly property color warn: "#f9e2af"` (or
however it composes the rest of that file's roles) so every later stage shares one
source rather than three independent literals. This plan references `PanelTheme.warn`
in Task 2 on that assumption and cannot itself amend stage 2's file.

**Open risk to watch during Task 5.** The Ctrl+J/Ctrl+K detection mechanism this plan
describes (control-character sniffing off `textKey`, since `PanelKeyCatcher` exposes no
modifier flag through any signal) is inferred from reading the actual component source,
not from a stage 3 plan document — none exists yet for this plan to read. If stage 3's
actual implementation resolves Ctrl+J/K differently, only Task 5's dependency on
`dayScope.moveCursor(direction)` being called at all is load-bearing; the function's own
body (clamped, no wraparound) does not need to change.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-04-stage-4-day-drawers.md`.
