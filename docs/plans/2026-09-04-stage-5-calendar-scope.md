# Panel Redesign — Stage 5: Calendar scope (week, fortnight, month)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the calendar scope — three ranges (week/fortnight/month) cycled with `w` or the `W · 2W · M`
chips, a derived-with-override time axis for week, per-day flags, a week-total column, and the
`range_entries` backend action that feeds all three — pixel-for-pixel against
`docs/design-guide.html` section 04, behaviourally per spec §8 and §10.2, and per the
`2026-09-04-stage-2-6-rulings.md` rulings where the two disagree.

**Architecture:** No new processes and no new persistence. `range_entries` is a fourth
Toggl-Track-only read action in `toggl_api.py`, following `day_activity`'s pattern exactly
(`meta=true`, the existing `HISTORY_FLOOR_DAYS`/`HISTORY_MAX_DAYS` constants, the existing
`ValidationError`). `Model.js` gains a self-contained "calendar math" layer — pure functions for
range bounds, paging, the axis derivation, and per-day aggregation — so every rule in spec §8.1 is
independently node-tested rather than trusted to render correctly. `Panel.qml` gains calendar state
and wires `range_entries` (and, for week view only, a small number of `day_activity` calls) through
the *existing* `request()`/`enqueue()`/`pumpQueue()` queue — no second queue, no daemon. `ui/CalendarScope.qml`
is pure rendering: every value it shows was already computed by `Model.js` or fetched by `Panel.qml`.

**Tech Stack:** Python 3 standard library only. QML/Quickshell (`ui/CalendarScope.qml`,
`Panel.qml`). Node for `Model.js` tests. No third-party packages.

**Spec:** [`../2026-09-04-panel-redesign.md`](../2026-09-04-panel-redesign.md) §8, §10.2
**Rulings:** [`../2026-09-04-stage-2-6-rulings.md`](../2026-09-04-stage-2-6-rulings.md) — binding
where it disagrees with the spec.
**Visual acceptance reference:** [`../design-guide.html`](../design-guide.html) section `04 · CALENDAR SCOPE`

---

## Global Constraints

Every task's requirements implicitly include all of these.

- **This plan depends on stages 2 and 3 having landed first**, per the rulings' sequencing
  (`2 → 3 → {4, 5}`). Stage 2 creates `ui/CalendarScope.qml` as a minimal stub (rulings R-A) and
  `ui/PanelTheme.qml` (spec §9.1). Stage 3 renames `Panel.qml`'s `activeTab` to a three-valued
  `scope` (`"timer" | "day" | "cal"`), authors `Model.clockDuration()` (rulings R-D), and writes a
  scope-conditioned dispatch inside `PanelKeyCatcher`'s signal handlers (rulings R-C). Task 3 below
  shows the *current* (pre-stage-3) text of every block it touches so the diff's intent is
  unambiguous, and calls out explicitly, at each such point, that the executing engineer must locate
  the equivalent post-stage-3 code (renamed to `scope`) rather than assume the shown text still
  matches verbatim. If stages 2/3 have not actually landed when this plan is executed, stop and
  escalate rather than inventing their interfaces.
- **`PanelKeyCatcher` is a shell component, not owned by this repo** (`/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml`).
  It already emits `moveRequested(dx, dy)` for `hjkl`/arrows, `returnRequested()` for Enter,
  `activateRequested()` for Enter/Space, `deleteRequested()` for `x`, and `textKey(text)` for every
  other single character (covers `w` and `a`). Stage 5 never edits this file; it only adds a
  `root.scope === "cal"` branch to the dispatch stage 3 already wrote inside `Panel.qml`'s handlers
  for these signals.
- **Color/role mapping, binding for every QML task below** (derived from the guide's own `:root`
  tokens at `docs/design-guide.html:11-20`, cross-checked against `ui/PanelTheme.qml` (spec §9.1) and
  `/usr/share/omarchy/shell/Commons/Style.qml`):

  | Guide token | Value | QML |
  | --- | --- | --- |
  | `--fg` | `#cdd6f4` | `theme.text` |
  | `--accent` | `#89b4fa` | `theme.accent` |
  | `--urgent` | `#f38ba8` | `theme.urgent` |
  | `--warn` | `#f9e2af` | `theme.warn` (see Task 4 Step 1 — add if `ui/PanelTheme.qml` doesn't have it yet) |
  | `--dim15` | `#898fa3` (brightest dim) | `theme.textMuted` (alpha 0.72) |
  | `--dim16` | `#808599` (middle dim) | `theme.textFaint` (alpha 0.55) |
  | `--dim18` | `#727788` (faintest) | `theme.textDisabled` (alpha 0.38) |
  | `--fill-normal` | `rgba(205,214,244,0.04)` | `Style.normalFill` (alpha 0.04 — exact match) |
  | `--fill-hover` | `rgba(205,214,244,0.08)` | `Style.hoverFill` (alpha 0.08 — exact match) |
  | `--fill-selected` | `rgba(205,214,244,0.18)` | `Style.selectedFill` (alpha 0.18 — exact match) |
  | `--border-normal` | `rgba(205,214,244,0.40)` | `Style.normalBorderColor` (alpha 0.40 — exact match) |

  Every other one-off alpha in the guide's calendar CSS (0.06, 0.10, 0.18 as a neutral tint, 0.20,
  0.22, 0.28, 0.32, 0.35) has no matching named token, so it is applied as a literal alpha argument
  to `Util.alpha(theme.text, N)` (a neutral `rgba(205,214,244,…)` tint) or `Qt.rgba(0, 0, 0, N)` (a
  black overlay tint, e.g. the weekend/`.calweek` backgrounds) — never as a bare hex/rgba literal.
  This satisfies "no raw color literal where a token exists": no token exists for these, and the
  literal *number* is a guide-sourced, rendered value, exactly the case the guide is authoritative for.
- **`ui/PanelTheme.qml` is instantiated locally, not a singleton.** Its own spec §9.1 code sample is
  a plain `QtObject { … }`, not `pragma Singleton`. Every consuming file in `ui/` declares
  `PanelTheme { id: theme }` as a child object (same-directory QML files are auto-importable by
  filename with no `import` statement) and reads `theme.surface` / `theme.text` / etc. Do not invent
  a singleton `qmldir` registration for it.
- **Project colours (`project_color`) are never remapped through `PanelTheme`/`Style`.** Spec §8.5 /
  rulings R5-42: they come from Toggl and are the one palette a theme must not touch.
- **QML: multi-line, one property per line.** Run `qmlformat -n -i` after editing.
- **Never a `;` after a QML object member.** A parse error both tools report with zero output.
- **Never pipe `qmllint` and read `$?`.** It writes nothing on failure, so a broken file reads as green.
- **QML signal handlers declare their parameters.** `onChanged: function(value) { … }`.
- **`Style.cornerRadius` resolves to 0.** Nothing in the calendar grid is rounded.
- **A `Repeater` is not an `Item`; `visible` does not hide it.** Gate on the model instead.
- **`PanelKeyCatcher` consumes `j k h l x`** before a focused editor sees them; irrelevant here since
  the calendar scope has no text editors, but the axis settings' `NumberField`s (Task 6) do gain
  keyboard focus, so their container must set `blocked: root.editorFocused` exactly like the rest of
  the panel already does.
- **Python: standard library only. No daemon.** One request per process, exactly as `day_activity`
  and every other action already work.
- **Toggl rejects `start_date` earlier than `today − 91`.** `HISTORY_FLOOR_DAYS = 91`,
  `HISTORY_MAX_DAYS = 92` already exist in `toggl_api.py`; reuse them, do not redefine them.
- **There is no QML test harness in this repository.** `qmlformat` proves syntax,
  `omarchy plugin validate` proves the manifest, `qmllint` proves lint cleanliness, and everything
  else is verified by `omarchy-restart-shell` plus a visual check against the guide. Logic that CAN
  be tested — every date/range/axis computation in this plan — is pushed into `Model.js` and
  node-tested instead of trusted to render correctly; this is why Task 1 is large.
- **Each task must end with a working plugin.** No task may leave the panel unable to load.

### Two scoping decisions this plan makes that no source resolves — read before implementing

Both are called out again, with full reasoning, in `open_questions` of the assignment response, and
are implemented exactly as described here so the plan stays fully executable. Confirm or override
before/while implementing; do not silently pick a third behaviour.

1. **The `range_entries` 92-day span cap (spec §10.2) truncates and sets `clamped: true`, exactly like
   the floor.** The spec states the cap but never its enforcement, and no §12 test bullet exists for
   it either way (digest contradiction, not resolved by the rulings). Truncating is chosen because it
   is the *only* enforcement style this action already uses elsewhere in the same response (the floor
   clamp, one paragraph above it in the same spec section) and matches the codebase's dominant
   convention for "value larger than we support" (`_history_days`, `Model.clampHistory`) — reject is
   reserved for a request that is *entirely* unusable (end before the floor), not one that is simply
   too wide. See Task 2 Step 3.
2. **The fortnight/month `◌`/`▲` per-day flags are populated opportunistically, from whatever
   `day_activity`-shaped block data happens to already be cached client-side (week-view visits and
   day-scope visits), never by fetching all 30–42 days' ActivityWatch activity for a month grid.**
   Spec §8.4 requires both flags on every range; §10.2 defines only `range_entries`, which returns
   entries, never blocks; the only block-data producer in the entire action surface is `day_activity`,
   one action per one day. Live-fetching AW activity for a 42-cell month grid on every page would be
   the single most expensive thing this plugin does, is nowhere budgeted in spec §10.7, and is outside
   this plan's authorized surface (spec §8 + §10.2 only — not a new batched backend action). A day
   with no cached block data simply shows no flag: absence of evidence is never rendered as a false
   "no unapplied blocks" claim. Week view gets full, live flag coverage for free, because axis
   derivation (rule 1) already needs every visible day's blocks anyway. See Task 3 Step 4 and Task 4
   Step 5.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `Model.js` | modified — calendar range/paging math, `axisBounds`, `axisOverrideValid`, per-day aggregation. All pure, all node-tested. |
| `tests/test_model.mjs` | modified |
| `toggl_api.py` | modified — `range_entries` dispatch action |
| `tests/test_toggl_api.py` | modified |
| `manifest.json` | modified — `calendarRange`, `calendarDayStart`, `calendarDayEnd` settings |
| `Panel.qml` | modified — calendar state, `range_entries`/`day_activity` request wiring, backward-nav floor guard, scope-conditioned key dispatch additions |
| `ui/CalendarScope.qml` | modified (created as a stub by stage 2 per rulings R-A) — chips, fortnight/month shared grid, week time-axis grid, flags, week-total column, axis settings sub-panel |
| `ui/PanelTheme.qml` | modified only if it is missing the `warn` role (Task 4 Step 1) — otherwise untouched, owned by stage 2 |

---

## Task 1: `Model.js` — calendar range math and axis bounds

**Files:**
- Modify: `Model.js`
- Modify: `tests/test_model.mjs`

**Interfaces:**
- Consumes: `Model.isoDate`, `Model.shiftDate`, `Model.historyFloor`, `Model.todayDate` (all existing).
- Produces (all pure, all new): `Model.hourOfDay`, `Model.axisBounds`, `Model.axisOverrideValid`,
  `Model.weekStart`, `Model.monthStart`, `Model.monthEnd`, `Model.shiftMonths`,
  `Model.calendarRangeBounds`, `Model.shiftCalendarAnchor`, `Model.canPageCalendarBackward`,
  `Model.calendarGridDates`, `Model.isoWeekLabel`, `Model.shortDateLabel`, `Model.calendarHeaderLabel`,
  `Model.calendarFloorHint`, `Model.calendarDayTotals`, `Model.calendarRangeTotal`,
  `Model.calendarConflictDates` — consumed by `Panel.qml` (Task 3) and `ui/CalendarScope.qml`
  (Tasks 4–6).

- [ ] **Step 1: Write the failing tests**

Open `tests/test_model.mjs`. Add every new function name to the destructured return list at the top
of the file:

```js
const Model = new Function(`${source}\nreturn {
  compactDuration, clockTime, isoDate, todayDate, shiftDate, dayLabel,
  prepareBlocks, blockAlso, blockSummary, formatDuration, clampHistory,
  clampBlockMinutes, historyFloor, boundedShiftDate,
  searchItems, normalizeProject, normalizeTask, applySummaryDelta,
  hourOfDay, axisBounds, axisOverrideValid, weekStart, monthStart, monthEnd,
  shiftMonths, calendarRangeBounds, shiftCalendarAnchor, canPageCalendarBackward,
  calendarGridDates, isoWeekLabel, shortDateLabel, calendarHeaderLabel,
  calendarFloorHint, calendarDayTotals, calendarRangeTotal, calendarConflictDates
}`)()
```

Append these tests at the end of the file, before the `if (failures) { … }` block:

```js
test("hourOfDay reads local wall-clock hour as a fraction and tolerates bad input", () => {
  const when = new Date(2026, 7, 26, 9, 30)
  assert.equal(Model.hourOfDay(when.toISOString()), 9.5)
  assert.equal(Model.hourOfDay(""), null)
  assert.equal(Model.hourOfDay("not-a-date"), null)
})

test("axisBounds floors the start, ceils the end, then pads one hour each side", () => {
  const entries = [{
    start: new Date(2026, 7, 26, 9, 15).toISOString(),
    stop: new Date(2026, 7, 26, 17, 45).toISOString(),
  }]
  assert.deepEqual(Model.axisBounds(entries, [], null), { start: 8, end: 19, rowHeight: 14, derived: true })
})

test("axisBounds includes unapplied blocks, not only entries", () => {
  const blocks = [
    { start: new Date(2026, 7, 26, 6, 0).toISOString(), end: new Date(2026, 7, 26, 7, 30).toISOString(), applied: false },
    { start: new Date(2026, 7, 26, 22, 0).toISOString(), end: new Date(2026, 7, 26, 23, 0).toISOString(), applied: true },
  ]
  // The applied block (22:00-23:00) must NOT widen the axis -- only the unapplied one counts.
  assert.deepEqual(Model.axisBounds([], blocks, null), { start: 5, end: 11, rowHeight: 26, derived: true })
})

test("axisBounds enforces the 6-hour minimum, growing the end first", () => {
  const entries = [{
    start: new Date(2026, 7, 26, 10, 0).toISOString(),
    stop: new Date(2026, 7, 26, 10, 30).toISOString(),
  }]
  assert.deepEqual(Model.axisBounds(entries, [], null), { start: 9, end: 15, rowHeight: 26, derived: true })
})

test("axisBounds enforces the 16-hour maximum, holding the span at 16", () => {
  const entries = [{
    start: new Date(2026, 7, 26, 6, 0).toISOString(),
    stop: new Date(2026, 7, 26, 23, 0).toISOString(),
  }]
  assert.deepEqual(Model.axisBounds(entries, [], null), { start: 5, end: 21, rowHeight: 10, derived: true })
})

test("axisBounds returns 08:00-20:00 with derived:false for an empty range", () => {
  assert.deepEqual(Model.axisBounds([], [], null), { start: 8, end: 20, rowHeight: 13, derived: false })
})

test("an integer calendarDayStart overrides while calendarDayEnd stays auto", () => {
  const entries = [{
    start: new Date(2026, 7, 26, 9, 0).toISOString(),
    stop: new Date(2026, 7, 26, 17, 0).toISOString(),
  }]
  const result = Model.axisBounds(entries, [], { start: 6, end: "auto" })
  assert.deepEqual(result, { start: 6, end: 18, rowHeight: 13, derived: false })
})

test("axisBounds rowHeight floors at 8px under a wide override", () => {
  assert.deepEqual(Model.axisBounds([], [], { start: 0, end: 24 }), { start: 0, end: 24, rowHeight: 8, derived: false })
})

test("axisOverrideValid rejects start >= end and spans under 4 hours", () => {
  assert.equal(Model.axisOverrideValid(10, 10), false)
  assert.equal(Model.axisOverrideValid(15, 10), false)
  assert.equal(Model.axisOverrideValid(10, 13), false)
  assert.equal(Model.axisOverrideValid(-1, 10), false)
  assert.equal(Model.axisOverrideValid(10, 25), false)
  assert.equal(Model.axisOverrideValid(10, 14), true)
})

test("weekStart returns the Monday of the containing week", () => {
  assert.equal(Model.weekStart("2026-09-03"), "2026-08-31")
  assert.equal(Model.weekStart("2026-08-31"), "2026-08-31")
  assert.equal(Model.weekStart("2026-09-06"), "2026-08-31")
})

test("monthStart/monthEnd bound a calendar month, leap years included", () => {
  assert.equal(Model.monthStart("2026-09-15"), "2026-09-01")
  assert.equal(Model.monthEnd("2026-09-15"), "2026-09-30")
  assert.equal(Model.monthEnd("2026-02-10"), "2026-02-28")
  assert.equal(Model.monthEnd("2024-02-10"), "2024-02-29")
})

test("shiftMonths crosses year boundaries and normalises to the 1st", () => {
  assert.equal(Model.shiftMonths("2026-09-15", 1), "2026-10-01")
  assert.equal(Model.shiftMonths("2026-01-15", -1), "2025-12-01")
})

test("calendarRangeBounds derives the week/fortnight/month windows shown in the guide", () => {
  assert.deepEqual(Model.calendarRangeBounds("week", "2026-09-03"), { start: "2026-08-31", end: "2026-09-06" })
  assert.deepEqual(Model.calendarRangeBounds("fortnight", "2026-09-03"), { start: "2026-08-24", end: "2026-09-06" })
  assert.deepEqual(Model.calendarRangeBounds("month", "2026-09-15"), { start: "2026-09-01", end: "2026-09-30" })
})

test("shiftCalendarAnchor pages by the range's own unit", () => {
  assert.equal(Model.shiftCalendarAnchor("week", "2026-09-03", -1), "2026-08-27")
  assert.equal(Model.shiftCalendarAnchor("fortnight", "2026-09-03", -1), "2026-08-20")
  assert.equal(Model.shiftCalendarAnchor("month", "2026-09-15", -1), "2026-08-01")
})

test("canPageCalendarBackward disables exactly at the 91-day floor", () => {
  const today = "2026-09-03"
  const floor = Model.historyFloor(today)
  assert.equal(Model.canPageCalendarBackward("week", floor, today), false)
  assert.equal(Model.canPageCalendarBackward("week", Model.shiftDate(floor, 14), today), true)
})

test("calendarGridDates pads a month to whole weeks and flags in-range days", () => {
  const dates = Model.calendarGridDates("month", "2026-09-15")
  assert.equal(dates.length, 35)
  assert.deepEqual(dates[0], { date: "2026-08-31", inRange: false })
  assert.deepEqual(dates[7], { date: "2026-09-07", inRange: true })
  assert.deepEqual(dates[dates.length - 1], { date: "2026-10-04", inRange: false })
})

test("calendarGridDates returns exactly the week/fortnight span, all in range", () => {
  assert.equal(Model.calendarGridDates("week", "2026-09-03").length, 7)
  assert.equal(Model.calendarGridDates("fortnight", "2026-09-03").length, 14)
  assert.ok(Model.calendarGridDates("week", "2026-09-03").every((d) => d.inRange))
})

test("isoWeekLabel matches the guide's own week numbering", () => {
  assert.equal(Model.isoWeekLabel("2026-08-24"), "W35")
  assert.equal(Model.isoWeekLabel("2026-08-31"), "W36")
  assert.equal(Model.isoWeekLabel("2026-09-07"), "W37")
  assert.equal(Model.isoWeekLabel("2026-09-14"), "W38")
})

test("calendarHeaderLabel matches the guide's rendered header strings", () => {
  assert.equal(Model.calendarHeaderLabel("week", "2026-09-03"), "31 Aug – 6 Sep")
  assert.equal(Model.calendarHeaderLabel("fortnight", "2026-09-03"), "24 Aug – 6 Sep")
  assert.equal(Model.calendarHeaderLabel("month", "2026-09-15"), "September 2026")
})

test("calendarFloorHint matches the guide's rendered callout, verbatim", () => {
  assert.equal(
    Model.calendarFloorHint("2026-09-03"),
    "June is as far back as Toggl will answer — start_date 4 Jun 2026"
  )
})

test("calendarDayTotals sums seconds per local calendar date", () => {
  const entries = [
    { start: "2026-09-01T09:00:00", stop: "2026-09-01T10:30:00" },
    { start: "2026-09-01T11:00:00", stop: "2026-09-01T11:15:00" },
    { start: "2026-09-02T09:00:00", stop: "2026-09-02T09:20:00" },
  ]
  assert.deepEqual(Model.calendarDayTotals(entries), { "2026-09-01": 6300, "2026-09-02": 1200 })
})

test("calendarRangeTotal sums every day's total", () => {
  const entries = [
    { start: "2026-09-01T09:00:00", stop: "2026-09-01T10:30:00" },
    { start: "2026-09-02T09:00:00", stop: "2026-09-02T09:20:00" },
  ]
  assert.equal(Model.calendarRangeTotal(entries), 5400 + 1200)
})

test("calendarConflictDates flags a day whose entries overlap, not one that doesn't", () => {
  const overlapping = [
    { start: "2026-09-01T09:00:00", stop: "2026-09-01T10:30:00" },
    { start: "2026-09-01T10:00:00", stop: "2026-09-01T10:45:00" },
  ]
  const clean = [
    { start: "2026-09-01T09:00:00", stop: "2026-09-01T10:30:00" },
    { start: "2026-09-01T11:00:00", stop: "2026-09-01T11:15:00" },
  ]
  assert.deepEqual(Model.calendarConflictDates(overlapping), { "2026-09-01": true })
  assert.deepEqual(Model.calendarConflictDates(clean), {})
})
```

- [ ] **Step 2: Run to verify failure**

Run: `node tests/test_model.mjs`

Every test added in Step 1 fails (most with `ReferenceError`/`TypeError` since the functions don't
exist yet). The pre-existing tests still pass.

- [ ] **Step 3: Implement in `Model.js`**

Add near the top, alongside the existing `DAY_NAMES`/`MONTH_NAMES` constants:

```js
var MONTH_NAMES_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
```

Append the rest at the end of the file (after `clampReminder`, which is currently the last function):

```js
// Local wall-clock hour (fractional) an ISO datetime falls on, or null if the
// value does not parse. axisBounds derives entirely in local time, consistent
// with clockTime elsewhere in this file.
function hourOfDay(isoValue) {
  if (!isoValue) return null
  var value = new Date(isoValue)
  if (!isFinite(value.getTime())) return null
  return value.getHours() + value.getMinutes() / 60 + value.getSeconds() / 3600
}

// Week-grid axis bounds, derived from the data unless overridden per edge.
// Rules run in the exact order spec section 8.1 states them; each is a
// separately node-tested step, so keep them as separate statements rather
// than collapsing the math into one expression.
function axisBounds(entries, blocks, override) {
  override = override || {}
  var hours = []
  ;(entries || []).forEach(function(entry) {
    var s = hourOfDay(entry && entry.start)
    var e = hourOfDay(entry && entry.stop)
    if (s !== null) hours.push(s)
    if (e !== null) hours.push(e)
  })
  // Rule 1: every UNAPPLIED block counts too, or a day of unlogged early work
  // would fall outside its own axis. An applied block is already covered by
  // its matching entry.
  ;(blocks || []).forEach(function(block) {
    if (!block || block.applied) return
    var s = hourOfDay(block.start)
    var e = hourOfDay(block.end)
    if (s !== null) hours.push(s)
    if (e !== null) hours.push(e)
  })

  var start, end, derived
  if (hours.length === 0) {
    // Rule 7: nothing to derive from.
    start = 8
    end = 20
    derived = false
  } else {
    derived = true
    var earliest = Math.min.apply(null, hours)
    var latest = Math.max.apply(null, hours)
    // Rule 2: floor the start, ceil the end.
    start = Math.floor(earliest)
    end = Math.ceil(latest)
    // Rule 3: pad one hour each side, clamped to the day.
    start = Math.max(0, start - 1)
    end = Math.min(24, end + 1)
    // Rule 4: minimum span 6h, grown from the end first (later), then the
    // start (earlier) if the end alone can't cover the deficit.
    if (end - start < 6) {
      var deficit = 6 - (end - start)
      var grownEnd = Math.min(24, end + deficit)
      deficit -= (grownEnd - end)
      end = grownEnd
      if (deficit > 0) start = Math.max(0, start - deficit)
    }
    // Rule 5: maximum span 16h; entries beyond it clamp per Overflow.
    if (end - start > 16) end = start + 16
  }

  // Axis bounds, overridden (spec 8.1): an integer wins over the derived
  // value for that edge; "auto" (or anything non-numeric) leaves it derived.
  // Overriding either edge means the axis as a whole is no longer "derived"
  // -- the mode line reads Fixed, not Automatic.
  if (typeof override.start === "number" && isFinite(override.start)) {
    start = override.start
    derived = false
  }
  if (typeof override.end === "number" && isFinite(override.end)) {
    end = override.end
    derived = false
  }

  var span = Math.max(1, end - start)
  // Rule 6. Only reachable below 10px under an override wide enough to push
  // span past ~19.5h -- the derived path never exceeds the rule-5 cap of 16h.
  var rowHeight = Math.max(8, Math.round(156 / span))
  return { start: start, end: end, rowHeight: rowHeight, derived: derived }
}

// Validates a candidate {start, end} axis override pair before it is written
// to calendarDayStart/calendarDayEnd. Called at the field, not on save (spec
// 8.1) -- an invalid pair must never reach axisBounds' override argument, so
// axisBounds itself does not re-validate.
function axisOverrideValid(start, end) {
  start = Number(start)
  end = Number(end)
  if (!isFinite(start) || !isFinite(end)) return false
  if (start < 0 || start > 24 || end < 0 || end > 24) return false
  if (start >= end) return false
  return (end - start) >= 4
}

function weekStart(dateValue) {
  var parts = String(dateValue || "").split("-")
  var value = parts.length === 3 ? new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])) : new Date()
  var day = value.getDay()
  var mondayOffset = day === 0 ? -6 : 1 - day
  value.setDate(value.getDate() + mondayOffset)
  return isoDate(value)
}

function monthStart(dateValue) {
  var parts = String(dateValue || "").split("-")
  if (parts.length !== 3) return todayDate()
  return parts[0] + "-" + String(parts[1]).padStart(2, "0") + "-01"
}

function monthEnd(dateValue) {
  var parts = String(dateValue || "").split("-")
  if (parts.length !== 3) return todayDate()
  var value = new Date(Number(parts[0]), Number(parts[1]), 0) // day 0 of next month = last day of this one
  return isoDate(value)
}

function shiftMonths(dateValue, months) {
  var parts = String(dateValue || "").split("-")
  var value = parts.length === 3 ? new Date(Number(parts[0]), Number(parts[1]) - 1, 1) : new Date()
  value.setMonth(value.getMonth() + (Number(months) || 0))
  return isoDate(value)
}

// Week: the Monday-start week containing anchorDate.
// Fortnight: that week plus the one before it (matches the guide's own
// "24 Aug - 6 Sep" example, which is exactly two weeks ending on the Sunday
// of the week containing 3 Sep).
// Month: the calendar month containing anchorDate, exactly (padding for the
// grid is a rendering concern -- see calendarGridDates).
function calendarRangeBounds(range, anchorDate) {
  if (range === "week") {
    var ws = weekStart(anchorDate)
    return { start: ws, end: shiftDate(ws, 6) }
  }
  if (range === "fortnight") {
    var ws2 = weekStart(anchorDate)
    return { start: shiftDate(ws2, -7), end: shiftDate(ws2, 6) }
  }
  var ms = monthStart(anchorDate)
  return { start: ms, end: monthEnd(ms) }
}

function shiftCalendarAnchor(range, anchorDate, direction) {
  if (range === "week") return shiftDate(anchorDate, 7 * direction)
  if (range === "fortnight") return shiftDate(anchorDate, 14 * direction)
  return shiftMonths(anchorDate, direction)
}

// Would paging one page backward from anchorDate produce a range whose
// start_date falls before the 91-day floor? Used to disable/hide the
// backward nav control before it ever offers a move that would 400 (spec
// 8.4 / rulings R5-41).
function canPageCalendarBackward(range, anchorDate, todayValue) {
  var candidate = shiftCalendarAnchor(range, anchorDate, -1)
  var bounds = calendarRangeBounds(range, candidate)
  return bounds.start >= historyFloor(todayValue || todayDate())
}

// Every date the grid needs to draw for `range`, in order. Week/fortnight
// are exactly their own bounds (always inRange:true -- there is no padding
// concept at those sizes). Month pads out to whole Monday-start weeks, and
// flags the padding days from the adjacent month as inRange:false so the
// renderer can draw them at reduced opacity with no total/stack (spec 8.3 /
// rulings R5-36).
function calendarGridDates(range, anchorDate) {
  var bounds = calendarRangeBounds(range, anchorDate)
  if (range !== "month") {
    var dates = []
    var cursor = bounds.start
    while (cursor <= bounds.end) {
      dates.push({ date: cursor, inRange: true })
      cursor = shiftDate(cursor, 1)
    }
    return dates
  }
  var gridStart = weekStart(bounds.start)
  var gridEnd = shiftDate(weekStart(bounds.end), 6)
  var out = []
  var monthPrefix = bounds.start.slice(0, 7)
  var cursor2 = gridStart
  while (cursor2 <= gridEnd) {
    out.push({ date: cursor2, inRange: cursor2.slice(0, 7) === monthPrefix })
    cursor2 = shiftDate(cursor2, 1)
  }
  return out
}

function isoWeekNumber(dateValue) {
  var parts = String(dateValue || "").split("-")
  if (parts.length !== 3) return 1
  var value = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])))
  var day = value.getUTCDay() || 7
  value.setUTCDate(value.getUTCDate() + 4 - day)
  var yearStart = new Date(Date.UTC(value.getUTCFullYear(), 0, 1))
  return Math.ceil(((value - yearStart) / 86400000 + 1) / 7)
}
function isoWeekLabel(dateValue) { return "W" + isoWeekNumber(dateValue) }

function shortDateLabel(dateValue) {
  var parts = String(dateValue || "").split("-")
  if (parts.length !== 3) return String(dateValue || "")
  return Number(parts[2]) + " " + MONTH_NAMES[Number(parts[1]) - 1]
}

// The dayhead .date string: "31 Aug - 6 Sep" for week/fortnight, "September
// 2026" for month -- matches docs/design-guide.html lines 674, 780, 823.
function calendarHeaderLabel(range, anchorDate) {
  var bounds = calendarRangeBounds(range, anchorDate)
  if (range === "month") {
    var parts = bounds.start.split("-")
    return MONTH_NAMES_FULL[Number(parts[1]) - 1] + " " + parts[0]
  }
  return shortDateLabel(bounds.start) + " – " + shortDateLabel(bounds.end)
}

// The backward-nav disabled explanation (spec 8.4 / rulings R5-41), copy
// pattern from docs/design-guide.html:834 -- "{Month} is as far back as
// Toggl will answer - start_date {D Mon YYYY}", where {Month} is the floor
// date's own month.
function calendarFloorHint(todayValue) {
  var floor = historyFloor(todayValue || todayDate())
  var parts = floor.split("-")
  var day = Number(parts[2])
  var month = MONTH_NAMES[Number(parts[1]) - 1]
  var monthFull = MONTH_NAMES_FULL[Number(parts[1]) - 1]
  return monthFull + " is as far back as Toggl will answer — start_date " + day + " " + month + " " + parts[0]
}

function calendarDayTotals(entries) {
  var totals = {}
  ;(entries || []).forEach(function(entry) {
    var started = new Date(entry && entry.start)
    if (!isFinite(started.getTime())) return
    var date = isoDate(started)
    totals[date] = (totals[date] || 0) + durationSeconds(entry, Date.now())
  })
  return totals
}

function calendarRangeTotal(entries) {
  var totals = calendarDayTotals(entries)
  var sum = 0
  Object.keys(totals).forEach(function(date) { sum += totals[date] })
  return sum
}

// A day is flagged for the calendar's urgent (A) glyph when two of its own
// Toggl entries overlap -- derivable from range_entries' entries alone, no
// block data required. See this plan's "scoping decisions" section for why
// this, and not a block-vs-entry conflict, is what the calendar's flag means
// for fortnight/month (week view's per-block conflict rendering is separate,
// see Task 5).
function calendarConflictDates(entries) {
  var byDate = {}
  ;(entries || []).forEach(function(entry) {
    var started = new Date(entry && entry.start)
    if (!isFinite(started.getTime())) return
    var date = isoDate(started)
    ;(byDate[date] = byDate[date] || []).push(entry)
  })
  var flagged = {}
  Object.keys(byDate).forEach(function(date) {
    var list = byDate[date].slice().sort(function(a, b) { return new Date(a.start) - new Date(b.start) })
    for (var i = 1; i < list.length; i++) {
      var prevEnd = new Date(list[i - 1].stop || list[i - 1].start).getTime()
      var curStart = new Date(list[i].start).getTime()
      if (curStart < prevEnd) { flagged[date] = true; break }
    }
  })
  return flagged
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node tests/test_model.mjs` — all tests, old and new, pass.

- [ ] **Step 5: Commit**

`git add Model.js tests/test_model.mjs && git commit -m "feat(calendar): add calendar range math and axis bounds to Model.js"`

---

## Task 2: `toggl_api.py` — the `range_entries` action

**Files:**
- Modify: `toggl_api.py`
- Modify: `tests/test_toggl_api.py`

**Interfaces:**
- Consumes: `HISTORY_FLOOR_DAYS`, `HISTORY_MAX_DAYS`, `ValidationError`, `_id`, `_field`,
  `_list_response`, `_normalized_entry`, `self.client.request`, `self._now_datetime()` (all existing).
- Produces: `TogglAPI.range_entries(payload)` and the `"range_entries"` dispatch action —
  `{"action":"range_entries","workspace_id":N,"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}` →
  `{"ok":true,"data":{"entries":[…],"start_date":…,"end_date":…,"clamped":false}}` — consumed by
  `Panel.qml` (Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_toggl_api.py`, near `EntryCacheTest` (it reuses that file's existing `FakeClient`
and `TestClock`, both already imported/defined at the top of the file):

```python
class RangeEntriesTest(unittest.TestCase):
    def _api(self, responses, clock=None):
        client = FakeClient(responses)
        return toggl_api.TogglAPI(client, cache_root=None, clock=clock or TestClock()), client

    def test_clamps_start_date_to_the_floor_and_sets_clamped(self):
        api, client = self._api([[]])
        result = api.range_entries({
            "workspace_id": 4, "start_date": "2026-01-01", "end_date": "2026-08-19",
        })
        floor = (TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)).isoformat()
        self.assertEqual(result["start_date"], floor)
        self.assertTrue(result["clamped"])

    def test_does_not_clamp_a_range_already_inside_the_floor(self):
        api, client = self._api([[]])
        result = api.range_entries({
            "workspace_id": 4, "start_date": "2026-08-01", "end_date": "2026-08-19",
        })
        self.assertEqual(result["start_date"], "2026-08-01")
        self.assertFalse(result["clamped"])

    def test_rejects_end_date_entirely_below_the_floor(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "2020-01-01", "end_date": "2020-01-07"})

    def test_rejects_end_date_before_start_date(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "2026-08-10", "end_date": "2026-08-01"})

    def test_rejects_a_malformed_date(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "not-a-date", "end_date": "2026-08-19"})

    def test_caps_the_span_at_92_days_and_sets_clamped(self):
        api, client = self._api([[]])
        floor = TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)
        future_end = TestClock()().date() + timedelta(days=5)
        result = api.range_entries({
            "workspace_id": 4, "start_date": floor.isoformat(), "end_date": future_end.isoformat(),
        })
        self.assertTrue(result["clamped"])
        span = (
            datetime.strptime(result["end_date"], "%Y-%m-%d").date()
            - datetime.strptime(result["start_date"], "%Y-%m-%d").date()
        ).days + 1
        self.assertEqual(span, toggl_api.HISTORY_MAX_DAYS)
        # end_date, what the caller actually asked to see, is never moved.
        self.assertEqual(result["end_date"], future_end.isoformat())

    def test_fetches_with_meta_true_and_filters_by_workspace(self):
        api, client = self._api([[
            {"id": 1, "workspace_id": 4, "project_color": "#0b83d9",
             "start": "2026-08-10T09:00:00Z", "stop": "2026-08-10T10:00:00Z"},
            {"id": 2, "workspace_id": 9,
             "start": "2026-08-10T09:00:00Z", "stop": "2026-08-10T10:00:00Z"},
        ]])
        result = api.range_entries({"workspace_id": 4, "start_date": "2026-08-01", "end_date": "2026-08-19"})
        self.assertEqual([e["id"] for e in result["entries"]], [1])
        self.assertEqual(result["entries"][0]["project_color"], "#0b83d9")
        _, _, params, _, _ = client.calls[0]
        self.assertEqual(params.get("meta"), "true")
        self.assertEqual(params.get("start_date"), "2026-08-01")
        self.assertEqual(params.get("end_date"), "2026-08-19")

    def test_dispatches_from_the_action_string(self):
        api, client = self._api([[]])
        result = api.dispatch({
            "action": "range_entries", "workspace_id": 4,
            "start_date": "2026-08-01", "end_date": "2026-08-19",
        })
        self.assertEqual(result["start_date"], "2026-08-01")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_toggl_api.RangeEntriesTest -v`

Every test fails with `AttributeError: 'TogglAPI' object has no attribute 'range_entries'`.

- [ ] **Step 3: Implement `range_entries`**

In `toggl_api.py`, add a module-level helper near `_history_days` (around line 954), reusing the
same date-parsing shape `day_activity` already uses inline:

```python
def _range_date(payload, name):
    try:
        return datetime.strptime(str(payload.get(name)), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(name + " must be an ISO date (YYYY-MM-DD).")
```

Add the method to the `TogglAPI` class, near `day_activity` (around line 1431):

```python
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
```

- [ ] **Step 4: Wire the dispatch action**

In `dispatch()`, add the branch immediately after `create_entry`'s and before the final `raise`:

```python
        if action == "create_entry":
            return self.create_entry(payload)
        if action == "range_entries":
            return self.range_entries(payload)
        raise ValidationError("unsupported action.")
```

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Run: `python3 -m py_compile toggl_api.py tests/test_toggl_api.py`

All tests pass; compilation is clean.

- [ ] **Step 6: Commit**

`git add toggl_api.py tests/test_toggl_api.py && git commit -m "feat(backend): add the range_entries action"`

---

## Task 3: `manifest.json` + `Panel.qml` — calendar state and request wiring

**Files:**
- Modify: `manifest.json`
- Modify: `Panel.qml`

**Interfaces:**
- Consumes: `Model.axisBounds`, `Model.axisOverrideValid`, `Model.calendarRangeBounds`,
  `Model.shiftCalendarAnchor`, `Model.canPageCalendarBackward`, `Model.calendarGridDates`,
  `Model.historyFloor`, `Model.todayDate`, `Model.shiftDate`, `Model.prepareBlocks` (existing) —
  from Task 1 and pre-existing `Model.js`. `root.request`/`enqueue`/`pumpQueue`,
  `root.showDay`/`loadDay`, `root.persist`, `root.setting` (all existing). `root.scope` and the
  scope-conditioned `PanelKeyCatcher` dispatch (stage 3 — see Global Constraints note on this).
- Produces: `root.calendarRange`, `calendarDayStart`, `calendarDayEnd`, `calendarAnchorDate`,
  `calendarEntries`, `calendarStartDate`, `calendarEndDate`, `calendarClamped`, `calendarLoaded`,
  `calendarError`, `calendarBlocksByDate`, `calendarCursorDate`, `calendarGridDates`,
  `calendarAxis`, `calendarCanPageBackward`; functions `loadCalendarRange()`, `setCalendarRange(range)`,
  `cycleCalendarRange()`, `shiftCalendarRange(direction)`, `moveCalendarCursor(dx, dy)`,
  `openCalendarCursorDay()`, `setCalendarAxisOverride(edge, hours)`, `resetCalendarAxis()` —
  consumed by `ui/CalendarScope.qml` (Tasks 4–6).

- [ ] **Step 1: `manifest.json` settings**

Add to `defaults`:

```json
      "calendarRange": "fortnight",
      "calendarDayStart": "auto",
      "calendarDayEnd": "auto"
```

Add to `schema` (after the `dayBlockMinutes` entry):

```json
      { "key": "calendarRange", "type": "string", "label": "Calendar range", "defaultValue": "fortnight" },
      { "key": "calendarDayStart", "type": "string", "label": "Calendar axis: day starts", "defaultValue": "auto" },
      { "key": "calendarDayEnd", "type": "string", "label": "Calendar axis: day ends", "defaultValue": "auto" }
```

Verify: `omarchy plugin validate .` exits 0.

- [ ] **Step 2: Add calendar state properties to `Panel.qml`**

Add near the existing day-scope properties (after `daySummary`, before the `editorFocused` comment):

```qml
    property string calendarRange: clampCalendarRange(setting("calendarRange", "fortnight"))
    property var calendarDayStart: parseAxisSetting(setting("calendarDayStart", "auto"))
    property var calendarDayEnd: parseAxisSetting(setting("calendarDayEnd", "auto"))
    property string calendarAnchorDate: Model.todayDate()
    property var calendarEntries: []
    property string calendarStartDate: ""
    property string calendarEndDate: ""
    property bool calendarClamped: false
    property bool calendarLoaded: false
    property string calendarError: ""
    // date (YYYY-MM-DD) -> Model.prepareBlocks() output for that date.
    // Populated opportunistically by every successful day_activity response,
    // whichever scope asked for it -- see this plan's "scoping decisions"
    // note on why fortnight/month flags are never eagerly fetched.
    property var calendarBlocksByDate: ({})
    property string calendarCursorDate: Model.todayDate()
    // Tracks which date the in-flight day_activity request (if any) is for,
    // so a FAILURE response -- which carries no `data.date` -- can tell
    // whether it belongs to the open Day scope or to a background calendar
    // block prefetch, and only touch dayError/dayLoaded in the former case.
    property string pendingDayActivityDate: ""
    readonly property var calendarOverride: ({"start": calendarDayStart, "end": calendarDayEnd})
    readonly property var calendarGridDates: Model.calendarGridDates(calendarRange, calendarAnchorDate)
    readonly property var calendarVisibleBlocks: {
        var out = [];
        for (var i = 0; i < calendarGridDates.length; i++) {
            var perDay = calendarBlocksByDate[calendarGridDates[i].date];
            if (perDay) out = out.concat(perDay);
        }
        return out;
    }
    // Recomputes whenever calendarEntries/calendarVisibleBlocks change, which
    // only happens on a fresh range_entries/day_activity response landing --
    // i.e. exactly "on arrival", never mid-page (spec 8.1's "bounds recompute
    // ... never mid-page" is satisfied for free by this being a reactive
    // binding over data that itself only changes on arrival).
    readonly property var calendarAxis: Model.axisBounds(calendarEntries, calendarVisibleBlocks.filter(function(b) { return !b.applied; }), calendarOverride)
    readonly property bool calendarCanPageBackward: Model.canPageCalendarBackward(calendarRange, calendarAnchorDate, Model.todayDate())
```

`calendarVisibleBlocks` entries are `Model.prepareBlocks()` output (they carry a `.state`, not a raw
`.applied`), so `calendarAxis`'s filter above reads `!b.applied` where `prepareBlocks` writes a
boolean `applied` passthrough from the raw block — confirm this against `Model.prepareBlocks`
(`Model.js:65-94`): the prepared block object does **not** carry the original `applied` boolean, only
`.state` (`"pending" | "applied" | "conflict"`). Fix the filter to match what `axisBounds` actually
needs — the *raw*, unprepared block shape (`{start, end, applied}`), not the prepared one. Store raw
blocks in `calendarBlocksByDate` (Step 4 does this) and keep a *second*, prepared array only for
flag/UI use where `.state` is needed:

```qml
    readonly property var calendarVisibleBlocks: {
        var out = [];
        for (var i = 0; i < calendarGridDates.length; i++) {
            var perDay = calendarBlocksByDate[calendarGridDates[i].date];
            if (perDay) out = out.concat(perDay.raw);
        }
        return out;
    }
    readonly property var calendarAxis: Model.axisBounds(calendarEntries, calendarVisibleBlocks, calendarOverride)
```

- [ ] **Step 3: Add the parsing/clamping helper functions**

Add near `clampBlockMinutes`'s call sites, or any convenient function group — these are simple glue,
not independently tested (the digest's testable list names only `Model.axisBounds`/override validity
as requiring node coverage; range/setting parsing this thin is exercised end-to-end by the manual
verification in Task 4-6, consistent with how `activeTab`/`searchMode` parsing already works
untested elsewhere in this file):

```qml
    function clampCalendarRange(value) {
        return ["week", "fortnight", "month"].indexOf(value) >= 0 ? value : "fortnight";
    }

    function parseAxisSetting(value) {
        if (value === "auto" || value === undefined || value === null || value === "")
            return "auto";
        var n = Number(value);
        return isFinite(n) ? n : "auto";
    }
```

- [ ] **Step 4: Add the request functions**

```qml
    function loadCalendarRange() {
        if (selectedWorkspaceId <= 0) {
            noteClient("errors", "request_dropped", "range_entries");
            return;
        }
        var bounds = Model.calendarRangeBounds(calendarRange, calendarAnchorDate);
        calendarError = "";
        request("range_entries", {
            "workspace_id": selectedWorkspaceId,
            "start_date": bounds.start,
            "end_date": bounds.end
        });
        if (calendarRange === "week")
            loadCalendarWeekBlocks(bounds);
    }

    // Week view is the only range whose grid needs block data (the time
    // axis and the unassigned/conflict boxes both need it) -- fortnight and
    // month never fetch it proactively, see this plan's "scoping decisions"
    // note. Skips a date already cached, so re-entering a week already
    // visited this session costs nothing.
    function loadCalendarWeekBlocks(bounds) {
        var cursor = bounds.start;
        while (cursor <= bounds.end) {
            if (!calendarBlocksByDate[cursor])
                request("day_activity", {
                    "workspace_id": selectedWorkspaceId,
                    "date": cursor,
                    "min_block_minutes": dayBlockMinutes
                });
            cursor = Model.shiftDate(cursor, 1);
        }
    }

    function setCalendarRange(range) {
        var next = clampCalendarRange(range);
        if (next === calendarRange)
            return;
        calendarRange = next;
        persist({"calendarRange": calendarRange});
        calendarLoaded = false;
        calendarEntries = [];
        loadCalendarRange();
    }

    function cycleCalendarRange() {
        var ranges = ["week", "fortnight", "month"];
        setCalendarRange(ranges[(ranges.indexOf(calendarRange) + 1) % ranges.length]);
    }

    function shiftCalendarRange(direction) {
        if (direction < 0 && !calendarCanPageBackward)
            return;
        calendarAnchorDate = Model.shiftCalendarAnchor(calendarRange, calendarAnchorDate, direction);
        calendarLoaded = false;
        calendarEntries = [];
        loadCalendarRange();
    }

    function moveCalendarCursor(dx, dy) {
        var dates = calendarGridDates.map(function(d) { return d.date; });
        var index = dates.indexOf(calendarCursorDate);
        if (index < 0)
            index = 0;
        if (calendarRange === "week")
            index = Math.max(0, Math.min(dates.length - 1, index + dx));
        else
            index = Math.max(0, Math.min(dates.length - 1, index + dx + dy * 7));
        calendarCursorDate = dates[index];
    }

    function openCalendarCursorDay() {
        root.scope = "day";
        root.showDay(calendarCursorDate);
    }

    function setCalendarAxisOverride(edge, hours) {
        var candidateStart = edge === "start" ? hours : calendarDayStart;
        var candidateEnd = edge === "end" ? hours : calendarDayEnd;
        var effectiveStart = candidateStart === "auto" ? calendarAxis.start : candidateStart;
        var effectiveEnd = candidateEnd === "auto" ? calendarAxis.end : candidateEnd;
        if (!Model.axisOverrideValid(effectiveStart, effectiveEnd))
            return false;
        if (edge === "start")
            calendarDayStart = hours;
        else
            calendarDayEnd = hours;
        persist({"calendarDayStart": calendarDayStart, "calendarDayEnd": calendarDayEnd});
        return true;
    }

    function resetCalendarAxis() {
        calendarDayStart = "auto";
        calendarDayEnd = "auto";
        persist({"calendarDayStart": "auto", "calendarDayEnd": "auto"});
    }
```

- [ ] **Step 5: Persist the new settings and re-derive them on external change**

Current text of `persist()`:

```qml
    function persist(values) {
        var e = {
            "id": moduleName,
            "workspaceId": selectedWorkspaceId,
            "historyDays": historyDays,
            "idleReminderMinutes": idleReminderMinutes,
            "dayBlockMinutes": dayBlockMinutes,
            "logLevel": logLevel
        };
```

Change to:

```qml
    function persist(values) {
        var e = {
            "id": moduleName,
            "workspaceId": selectedWorkspaceId,
            "historyDays": historyDays,
            "idleReminderMinutes": idleReminderMinutes,
            "dayBlockMinutes": dayBlockMinutes,
            "logLevel": logLevel,
            "calendarRange": calendarRange,
            "calendarDayStart": calendarDayStart,
            "calendarDayEnd": calendarDayEnd
        };
```

Current text of `onSettingsChanged`:

```qml
    onSettingsChanged: {
        selectedWorkspaceId = Number(setting("workspaceId", 0)) || 0;
        historyDays = Model.clampHistory(setting("historyDays", 30));
        idleReminderMinutes = Model.clampReminder(setting("idleReminderMinutes", 0));
        dayBlockMinutes = Model.clampBlockMinutes(setting("dayBlockMinutes", 5));
        var level = String(setting("logLevel", "info"));
        logLevel = logLevels.indexOf(level) >= 0 ? level : "info";
    }
```

Change to:

```qml
    onSettingsChanged: {
        selectedWorkspaceId = Number(setting("workspaceId", 0)) || 0;
        historyDays = Model.clampHistory(setting("historyDays", 30));
        idleReminderMinutes = Model.clampReminder(setting("idleReminderMinutes", 0));
        dayBlockMinutes = Model.clampBlockMinutes(setting("dayBlockMinutes", 5));
        var level = String(setting("logLevel", "info"));
        logLevel = logLevels.indexOf(level) >= 0 ? level : "info";
        calendarRange = clampCalendarRange(setting("calendarRange", "fortnight"));
        calendarDayStart = parseAxisSetting(setting("calendarDayStart", "auto"));
        calendarDayEnd = parseAxisSetting(setting("calendarDayEnd", "auto"));
    }
```

- [ ] **Step 6: Handle `range_entries` and `day_activity` responses**

Current text of `handleResponseBody`'s failure branch for `day_activity` (near the top of the
function, inside the `if (!response.ok) { … }` block):

```qml
                if (action === "day_activity") {
                    status = "ready";
                    dayLoaded = true;
                    dayError = message;
                    daySummary = Model.blockSummary([]);
                    return ;
                }
```

Change to (only touch Day scope's own state when the failed request was actually for the open day —
see Step 2's `pendingDayActivityDate` property; a background calendar week-block prefetch failing
for an unrelated date must not blank out an already-loaded Day scope):

```qml
                if (action === "day_activity") {
                    status = "ready";
                    if (pendingDayActivityDate === dayDate) {
                        dayLoaded = true;
                        dayError = message;
                        daySummary = Model.blockSummary([]);
                    }
                    return ;
                }
                if (action === "range_entries") {
                    status = "ready";
                    calendarLoaded = true;
                    calendarError = message;
                    return ;
                }
```

Current text of the success branch:

```qml
            if (action === "day_activity") {
                status = "ready";
                dayLoaded = true;
                dayBlocks = Model.prepareBlocks(response.data.blocks, response.data.entries);
                daySummary = Model.blockSummary(dayBlocks);
                slotChanged();
                return ;
            }
```

Change to (cache every response's blocks into `calendarBlocksByDate`, keyed by the response's own
`date` — reliable even when several day_activity requests are in flight in sequence for different
dates — and only mutate the Day-scope-facing properties when the response is for the day currently
open):

```qml
            if (action === "day_activity") {
                status = "ready";
                var prepared = Model.prepareBlocks(response.data.blocks, response.data.entries);
                var rawBlocks = Array.isArray(response.data.blocks) ? response.data.blocks : [];
                var byDate = calendarBlocksByDate;
                byDate[response.data.date] = {"raw": rawBlocks, "prepared": prepared};
                calendarBlocksByDate = Object.assign({}, byDate);
                if (response.data.date === dayDate) {
                    dayLoaded = true;
                    dayBlocks = prepared;
                    daySummary = Model.blockSummary(dayBlocks);
                    slotChanged();
                }
                return ;
            }
            if (action === "range_entries") {
                status = "ready";
                calendarLoaded = true;
                calendarEntries = response.data.entries || [];
                calendarStartDate = response.data.start_date || "";
                calendarEndDate = response.data.end_date || "";
                calendarClamped = !!response.data.clamped;
                return ;
            }
```

Reconcile Step 2's `calendarVisibleBlocks`/`calendarAxis` with the `{"raw": …, "prepared": …}` shape
now stored per date:

```qml
    readonly property var calendarVisibleBlocks: {
        var out = [];
        for (var i = 0; i < calendarGridDates.length; i++) {
            var perDay = calendarBlocksByDate[calendarGridDates[i].date];
            if (perDay) out = out.concat(perDay.raw);
        }
        return out;
    }
    readonly property var calendarAxis: Model.axisBounds(calendarEntries, calendarVisibleBlocks, calendarOverride)
```

- [ ] **Step 7: Track which date a day_activity request is for**

Current text of `request()`:

```qml
    function request(action, data) {
        if (requestPending) {
            enqueue(action, data);
            return ;
        }
        requestPending = true;
        pendingAction = action;
```

Change to:

```qml
    function request(action, data) {
        if (requestPending) {
            enqueue(action, data);
            return ;
        }
        requestPending = true;
        pendingAction = action;
        if (action === "day_activity")
            pendingDayActivityDate = (data && data.date) || "";
```

- [ ] **Step 8: Fix `enqueue()`'s coalescing key for `day_activity`**

`day_activity` is already in `coalescingActions` (`["sync", "bootstrap", "day_activity"]`), which
today coalesces by action name alone — correct for Day scope's own repeated calls for the *same*
date, wrong for week view's up-to-7 calls for *different* dates, which would otherwise collapse into
just the last one queued.

Current text of `enqueue()`:

```qml
    function enqueue(action, data) {
        var queue = requestQueue.slice();
        if (coalescingActions.indexOf(action) >= 0) {
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
        }
```

Change to:

```qml
    function enqueue(action, data) {
        var queue = requestQueue.slice();
        // day_activity coalesces per-date, not per-action: Day scope's
        // repeated calls for the SAME date are still the same refresh, but
        // the calendar's week-block prefetch fires up to 7 calls for 7
        // DIFFERENT dates and every one of them must survive the queue.
        var coalesceKey = function(a, d) { return a === "day_activity" ? (d && d.date) || "" : ""; };
        if (coalescingActions.indexOf(action) >= 0) {
            var key = coalesceKey(action, data);
            for (var i = 0; i < queue.length; i++) {
                if (queue[i].action === action && coalesceKey(queue[i].action, queue[i].data) === key) {
                    queue[i] = {
                        "action": action,
                        "data": data
                    };
                    requestQueue = queue;
                    return ;
                }
            }
        }
```

- [ ] **Step 9: Enter calendar scope loads it**

Extend the existing "load the newly-entered scope's data once bootstrap/sync completes" checks.
Current text, inside the `if (action === "bootstrap") { … }` branch (pre-stage-3; stage 3 renames
`activeTab` to `scope` — locate the equivalent line by its content, not this exact string, once stage
3 has landed):

```qml
                if (root.activeTab === "day" && !root.dayLoaded)
                    root.loadDay();
```

and, inside the `else if (action === "sync") { … }` branch:

```qml
            } else if (action === "sync") {
                if (activeTab === "day" && !dayLoaded)
                    loadDay();

            } else if ( ...
```

Add an analogous calendar branch immediately after each of the two lines above (using `scope`, the
post-stage-3 property name):

```qml
                if (root.scope === "cal" && !root.calendarLoaded)
                    root.loadCalendarRange();
```

```qml
                if (scope === "cal" && !calendarLoaded)
                    loadCalendarRange();
```

Additionally, wherever stage 3's scope-switch mechanism sets `root.scope = "cal"` (a chip/tab click
handler, or a keybinding such as the rulings' referenced `Ctrl+L`) — locate that code and add a call
to `root.loadCalendarRange()` guarded by `!root.calendarLoaded`, exactly mirroring how entering Day
scope already triggers `loadDay()`. This plan cannot show that exact edit because stage 3's scope
switcher is not yet present in this repository snapshot; find it by searching `Panel.qml` for where
`scope` is assigned a literal `"day"` and add the calendar case beside it.

- [ ] **Step 10: Extend the scope-conditioned key dispatch**

Stage 3 (rulings R-C) writes a `root.scope`-conditioned switch inside `Panel.qml`'s handlers for
`PanelKeyCatcher`'s `moveRequested`, `returnRequested`, and `textKey` signals. Add a `"cal"` branch to
each, calling the functions Step 4 added:

- `onMoveRequested: function(dx, dy)` — when `root.scope === "cal"`, call `root.moveCalendarCursor(dx, dy)` and return, without falling through to the other branches.
- `onReturnRequested: function()` — when `root.scope === "cal"` and the axis settings sub-panel
  (Task 6) is not focused, call `root.openCalendarCursorDay()` and return.
- `onTextKey: function(text)` — when `root.scope === "cal"`: `text === "w"` calls
  `root.cycleCalendarRange()`; `text === "a"` (week range only) toggles the axis settings sub-panel
  (Task 6 adds the property this toggles); anything else falls through unchanged.

Locate the actual switch by searching `Panel.qml` for `moveRequested`, `returnRequested`, and
`textKey` handler assignments — do not create a second, competing set of handlers on `keyCatcher`
(QML rejects two handlers for the same signal on the same object).

- [ ] **Step 11: Verify**

Run: `qmlformat -n -i Panel.qml && qmlformat Panel.qml >/dev/null; echo $?` — must print `0`.
Run: `omarchy plugin validate .` — exits 0.
Manual: `omarchy-restart-shell`, open the panel, confirm it still opens with no visible change (the
calendar scope UI does not exist until Task 4) and that Day scope and Timer scope still work exactly
as before.

- [ ] **Step 12: Commit**

`git add manifest.json Panel.qml && git commit -m "feat(calendar): wire range_entries/day_activity requests and calendar state"`

---

## Task 4: `ui/CalendarScope.qml` — scaffold, chips, fortnight/month grid, flags, navigation

**Files:**
- Modify: `ui/CalendarScope.qml` (stub created by stage 2)
- Modify: `ui/PanelTheme.qml` (only if it lacks a `warn` role)

**Interfaces:**
- Consumes: everything Task 3 produced on `Panel.qml` (referenced here as `p`, the parent panel —
  match whatever composition convention `ui/DayScope.qml`/`ui/TimerScope.qml` already established
  for reaching root panel state, adjusting the exact property/binding name below if theirs differs);
  `Model.calendarHeaderLabel`, `calendarFloorHint`, `calendarDayTotals`, `calendarRangeTotal`,
  `calendarConflictDates`, `isoWeekLabel`, `clockDuration` (stage 3).
- Produces: the visible fortnight/month `.calgrid` and header/chips/hints for all three ranges (week's
  own grid body is Task 5; the axis settings sub-panel is Task 6).

- [ ] **Step 1: Add the `warn` role to `ui/PanelTheme.qml` if it is missing**

Run: `grep -n "warn" ui/PanelTheme.qml`

If nothing matches, add a `warn` role immediately after the `urgent` role, matching the guide's own
literal token at `docs/design-guide.html:14` (`--warn: #f9e2af`) — there is no `Color.warn` in the
shell's `Color` singleton to derive it from (confirmed:
`grep -c "property color warn" /usr/share/omarchy/shell/Commons/Color.qml` returns `0`), so this is
one of the few genuinely fixed, non-theme-derived values in the panel, alongside project colours:

```qml
    readonly property color warn: "#f9e2af"
```

If the grep already found a `warn` role (added by an earlier stage), this step is a no-op — do not
add a duplicate property.

- [ ] **Step 2: Scaffold the file**

Replace the stub content of `ui/CalendarScope.qml` with:

```qml
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../Model.js" as Model

Item {
    id: root

    // Reference to the parent Panel.qml instance carrying all calendar
    // state and functions from this plan's Task 3. Match whatever
    // composition convention ui/DayScope.qml / ui/TimerScope.qml already
    // use to reach root panel state (a `panel` property is this plan's
    // assumption; rename this and every `p.` reference below to match if
    // theirs differs).
    property var panel: null
    readonly property var p: panel

    implicitHeight: column.implicitHeight

    PanelTheme { id: theme }

    readonly property var dayTotals: Model.calendarDayTotals(p ? p.calendarEntries : [])
    readonly property var conflictDates: Model.calendarConflictDates(p ? p.calendarEntries : [])
    readonly property int rangeTotal: Model.calendarRangeTotal(p ? p.calendarEntries : [])
    readonly property var weekRows: {
        var dates = p ? p.calendarGridDates : [];
        var rows = [];
        for (var i = 0; i < dates.length; i += 7)
            rows.push(dates.slice(i, i + 7));
        return rows;
    }

    ColumnLayout {
        id: column

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.md

        RowLayout {
            id: header

            Layout.fillWidth: true
            spacing: Style.spacing.lg

            Text {
                text: "‹"
                color: p && p.calendarCanPageBackward ? theme.textFaint : Util.alpha(theme.textMuted, 0.18)
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
                MouseArea {
                    anchors.fill: parent
                    enabled: p && p.calendarCanPageBackward
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: p.shiftCalendarRange(-1)
                }
            }

            Text {
                text: p ? Model.calendarHeaderLabel(p.calendarRange, p.calendarAnchorDate) : ""
                color: theme.text
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.weight: Font.Medium
            }

            Text {
                text: "›"
                color: theme.textFaint
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: p.shiftCalendarRange(1)
                }
            }

            RowLayout {
                spacing: 2

                Repeater {
                    model: [
                        {"value": "week", "label": "W"},
                        {"value": "fortnight", "label": "2W"},
                        {"value": "month", "label": "M"}
                    ]
                    delegate: Rectangle {
                        id: chip
                        required property var modelData
                        readonly property bool on: p && p.calendarRange === modelData.value
                        implicitWidth: chipLabel.implicitWidth + 12
                        implicitHeight: chipLabel.implicitHeight + 2
                        color: on ? Style.selectedFill : "transparent"
                        border.color: on ? Style.normalBorderColor : "transparent"
                        border.width: 1
                        radius: Style.cornerRadius

                        Text {
                            id: chipLabel
                            anchors.centerIn: parent
                            text: chip.modelData.label
                            color: chip.on ? theme.text : theme.textDisabled
                            font.family: p ? p.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: p.setCalendarRange(chip.modelData.value)
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                text: p ? Model.clockDuration(root.rangeTotal) : ""
                color: theme.accent
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.title
                font.weight: Font.Bold
            }
        }

        // Month only: "N TRACKED DAYS · M WITH UNAPPLIED BLOCKS"
        // (guide-only addition, rulings/digest R5-33 -- N = days with a
        // total > 0, M = days carrying the ◌ flag among the ones this
        // session has cached block data for; see this plan's scoping note).
        RowLayout {
            Layout.fillWidth: true
            visible: p && p.calendarRange === "month"
            Layout.topMargin: -8

            Item { Layout.fillWidth: true }

            Text {
                text: root.monthCountsLabel
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                font.letterSpacing: 0.08 * Style.font.caption
            }
        }

        // The backward-nav floor explanation (spec 8.4 / rulings R5-41),
        // shown whenever paging one more page back is disabled.
        RowLayout {
            Layout.fillWidth: true
            visible: p && !p.calendarCanPageBackward
            spacing: Style.spacing.sm

            Text {
                text: "‹"
                color: Util.alpha(theme.textMuted, 0.18)
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
            }
            Text {
                text: p ? Model.calendarFloorHint(Model.todayDate()) : ""
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Util.alpha(theme.text, 0.10)
        }

        // ---- grid body: week gets its own component (Task 5); fortnight
        // and month share the .calgrid template (rulings R5-35). ----
        Loader {
            Layout.fillWidth: true
            sourceComponent: p && p.calendarRange === "week" ? weekGridComponent : sharedGridComponent
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Util.alpha(theme.text, 0.10)
        }

        RowLayout {
            id: hints
            Layout.fillWidth: true
            spacing: Style.spacing.xxl

            Text {
                text: "↵ open day"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                text: p && p.calendarRange === "week" ? "hl day" : "hjkl move"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                text: "w cycle range"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                visible: p && p.calendarRange === "week"
                text: "a axis"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                visible: p && p.calendarRange === "month"
                text: "◌ unapplied blocks"
                color: theme.warn
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                visible: p && p.calendarRange === "month"
                text: "▲ conflict"
                color: theme.urgent
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
            Text {
                visible: p && p.calendarRange === "month"
                text: "^d back to day"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }
        }
    }

    function monthCountsLabel() {
        var tracked = 0, unapplied = 0;
        var dates = p ? p.calendarGridDates : [];
        for (var i = 0; i < dates.length; i++) {
            var d = dates[i];
            if (!d.inRange) continue;
            if ((root.dayTotals[d.date] || 0) > 0) tracked += 1;
            var cached = p.calendarBlocksByDate[d.date];
            if (cached && cached.prepared.some(function(b) { return b.state === "pending"; })) unapplied += 1;
        }
        return tracked + " TRACKED DAYS · " + unapplied + " WITH UNAPPLIED BLOCKS";
    }
    readonly property string monthCountsLabel: monthCountsLabel()

    Component {
        id: weekGridComponent
        Item { implicitHeight: 0 } // replaced by Task 5
    }

    Component {
        id: sharedGridComponent
        // implemented in Step 3
    }
}
```

`monthCountsLabel` is declared twice above (as a function and as a `readonly property string` calling
it) — QML does not allow a property and a function to share one identifier. Remove the function
declaration and keep only:

```qml
    readonly property string monthCountsLabel: {
        var tracked = 0, unapplied = 0;
        var dates = p ? p.calendarGridDates : [];
        for (var i = 0; i < dates.length; i++) {
            var d = dates[i];
            if (!d.inRange) continue;
            if ((root.dayTotals[d.date] || 0) > 0) tracked += 1;
            var cached = p.calendarBlocksByDate[d.date];
            if (cached && cached.prepared.some(function(b) { return b.state === "pending"; })) unapplied += 1;
        }
        return tracked + " TRACKED DAYS · " + unapplied + " WITH UNAPPLIED BLOCKS";
    }
```

- [ ] **Step 3: The shared fortnight/month `.calgrid`**

Replace the `sharedGridComponent`'s empty body with (matches `docs/design-guide.html` `.calgrid`,
`.caldow`, `.calcell`/`.fncell`, `.calweek` CSS at lines 220-244, 278-292):

```qml
    Component {
        id: sharedGridComponent

        ColumnLayout {
            spacing: 4

            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: ["M", "T", "W", "T", "F", "S", "S", "Σ"]
                    delegate: Text {
                        required property string modelData
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: modelData
                        color: theme.textDisabled
                        font.family: p ? p.fontFamily : Style.font.family
                        font.pixelSize: Style.font.caption
                        font.letterSpacing: 0.1 * Style.font.caption
                    }
                }
            }

            Repeater {
                model: root.weekRows
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: 4

                    property real cellHeight: p && p.calendarRange === "fortnight" ? 66 : 50

                    Repeater {
                        model: modelData
                        delegate: Rectangle {
                            id: cell
                            required property var modelData

                            readonly property string date: modelData.date
                            readonly property bool inRange: modelData.inRange
                            readonly property real total: root.dayTotals[date] || 0
                            readonly property bool isToday: date === Model.todayDate()
                            readonly property bool isSelected: date === (p ? p.calendarCursorDate : "")
                            readonly property bool isWeekend: {
                                var d = new Date(date);
                                var wd = d.getDay();
                                return wd === 0 || wd === 6;
                            }
                            readonly property bool hasConflict: !!root.conflictDates[date]
                            readonly property var cachedBlocks: p ? p.calendarBlocksByDate[date] : null
                            readonly property bool hasUnapplied: !!(cachedBlocks && cachedBlocks.prepared.some(function(b) { return b.state === "pending"; }))

                            Layout.fillWidth: true
                            Layout.preferredHeight: parent.cellHeight
                            opacity: (p && p.calendarRange === "month" && !inRange) ? 0.32 : 1
                            color: isWeekend ? Qt.rgba(0, 0, 0, 0.22) : (isSelected ? Style.selectedFill : "transparent")
                            border.width: 1
                            border.color: isToday ? theme.accent : Util.alpha(theme.text, 0.10)

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 2

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: String(Number(cell.date.split("-")[2]))
                                        color: theme.textDisabled
                                        font.family: p ? p.fontFamily : Style.font.family
                                        font.pixelSize: Style.font.caption
                                    }
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        visible: cell.inRange && cell.hasUnapplied
                                        text: "◌"
                                        color: theme.warn
                                        font.pixelSize: 9
                                    }
                                    Text {
                                        visible: cell.inRange && cell.hasConflict
                                        text: "▲"
                                        color: theme.urgent
                                        font.pixelSize: 9
                                    }
                                }

                                Text {
                                    text: (cell.inRange && cell.total > 0) ? Model.clockDuration(cell.total) : "—"
                                    color: (cell.inRange && cell.total > 0) ? theme.text : theme.textDisabled
                                    font.family: p ? p.fontFamily : Style.font.family
                                    font.pixelSize: Style.font.bodySmall
                                }

                                Item { Layout.fillHeight: true }

                                // Project-colour stack (month, 4px) / density
                                // strip (fortnight, 9px). Task 5 owns the
                                // week grid, not this component; fortnight's
                                // strip needs wall-time block ordering, which
                                // requires the same per-day block cache as
                                // week's axis -- only rendered when this
                                // session has already cached that date's
                                // blocks (see this plan's scoping note), so
                                // it degrades to just the project stack
                                // (still correct, just less detailed) when
                                // it hasn't.
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: p && p.calendarRange === "fortnight" ? 9 : 4
                                    spacing: 1
                                    visible: cell.inRange && cell.total > 0

                                    Repeater {
                                        model: root.projectSegments(cell.date)
                                        delegate: Rectangle {
                                            required property var modelData
                                            Layout.fillHeight: true
                                            Layout.preferredWidth: 1
                                            Layout.fillWidth: true
                                            color: modelData.color
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 52
                        Layout.preferredHeight: parent.cellHeight
                        color: Qt.rgba(0, 0, 0, 0.18)
                        border.width: 1
                        border.color: Util.alpha(theme.text, 0.06)

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 5
                            Item { Layout.fillHeight: true }
                            Text {
                                Layout.alignment: Qt.AlignRight
                                text: Model.clockDuration(root.weekRowTotal(modelData))
                                color: theme.accent
                                font.family: p ? p.fontFamily : Style.font.family
                                font.pixelSize: Style.font.bodySmall
                            }
                            Text {
                                Layout.alignment: Qt.AlignRight
                                text: modelData.length ? Model.isoWeekLabel(modelData[0].date) : ""
                                color: theme.textDisabled
                                font.family: p ? p.fontFamily : Style.font.family
                                font.pixelSize: 9
                                font.letterSpacing: 0.08 * 9
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }
    }

    function weekRowTotal(dates) {
        var sum = 0;
        for (var i = 0; i < dates.length; i++) sum += (root.dayTotals[dates[i].date] || 0);
        return sum;
    }

    // Proportional project-colour segments for one day, from range_entries'
    // own entries (never fortnight's density-strip gap hatching, which needs
    // wall-time block ordering this component does not have -- see the
    // comment above). Falls back to a single neutral segment when the day
    // has time but every entry is missing a project colour.
    function projectSegments(date) {
        var entries = (p ? p.calendarEntries : []).filter(function(e) {
            return String(e.start || "").slice(0, 10) === date;
        });
        if (!entries.length) return [];
        var byColor = {};
        var order = [];
        entries.forEach(function(e) {
            var color = e.project_color || "";
            var seconds = Model.durationSeconds ? Model.durationSeconds(e, Date.now()) : 0;
            if (!(color in byColor)) { byColor[color] = 0; order.push(color); }
            byColor[color] += seconds;
        });
        return order.map(function(color) {
            return {"color": color || Qt.rgba(0.804, 0.839, 0.957, 0.18), "seconds": byColor[color]};
        });
    }
```

`Model.durationSeconds` is not in the destructured `Model` export CalendarScope needs — QML's
`import "../Model.js" as Model` pulls in the *whole module*, not a curated subset like the node test
harness does, so every top-level function in `Model.js` (including `durationSeconds`, already
existing) is directly callable as `Model.durationSeconds(...)` with no further wiring needed. Remove
the `Model.durationSeconds ?` guard above; it is always defined:

```qml
            var seconds = Model.durationSeconds(e, Date.now());
```

- [ ] **Step 4: `hjkl`/Enter cursor wiring**

Already implemented by `Panel.qml`'s `moveCalendarCursor`/`openCalendarCursorDay` (Task 3). No
additional code needed in `ui/CalendarScope.qml` for this — the `isSelected` binding in Step 3 already
reflects `p.calendarCursorDate`, which those functions mutate.

- [ ] **Step 5: Confirm the flags scoping decision is visible in code**

Re-read the `hasUnapplied`/`hasConflict` computed properties added in Step 3. `hasConflict` is always
correct (pure `entries`-derived, spec §8 never distinguishes an entries-only vs. block-derived
conflict for the *calendar*, only for Day scope's row states). `hasUnapplied` is correct exactly for
the dates whose blocks this session has already cached — confirm the comment above `calendarBlocksByDate`
(Task 3 Step 2) and the one above the density-strip `RowLayout` (Step 3) both explain this; a reviewer
reading only `ui/CalendarScope.qml` should not be surprised that a month grid's `◌` sometimes
doesn't appear for a day that does have unapplied blocks that just haven't been fetched yet.

- [ ] **Step 6: Verify**

Run: `qmlformat ui/CalendarScope.qml >/dev/null; echo $?` — must print `0`.
Run: `qmllint -I /usr/share/omarchy/shell ui/CalendarScope.qml; echo $?` — must print `0`.
Run: `qmlformat Panel.qml >/dev/null; echo $?` (unaffected by this task, but confirm still `0`).
Manual: `omarchy-restart-shell`, `qs -p /usr/share/omarchy/shell log` open in a second terminal.
Open the panel, enter calendar scope (however stage 3 binds it), confirm the fortnight grid renders
with no `qt.qml.context` warnings in the log, matches `docs/design-guide.html` section 04's `2W` mock
pixel-for-pixel (66px cells, 4px gap, 52px week-total column), press `w` twice to reach month, confirm
the `M` mock's 50px cells and the "N TRACKED DAYS · M WITH UNAPPLIED BLOCKS" line, press `w` once more
to reach week — confirm no crash even though the grid body is still empty (Task 5).

- [ ] **Step 7: Commit**

`git add ui/CalendarScope.qml ui/PanelTheme.qml && git commit -m "feat(calendar): fortnight/month grid, chips, flags, backward-nav"`

---

## Task 5: `ui/CalendarScope.qml` — week time-axis grid

**Files:**
- Modify: `ui/CalendarScope.qml`

**Interfaces:**
- Consumes: `p.calendarAxis` (`Model.axisBounds`'s output, Task 3), `p.calendarEntries`,
  `p.calendarVisibleBlocks`, `p.calendarClamped`.
- Produces: the week grid body (replaces `weekGridComponent`'s stub from Task 4).

- [ ] **Step 1: The week grid**

Replace `weekGridComponent`'s body (matches `docs/design-guide.html` `.wkgrid`/`.wkdow`/`.wkhours`/
`.wkcol`/`.wkev`/`.wktot` CSS at lines 251-276; geometry per rulings R-K: the drawn axis is whatever
`calendarAxis.start`/`.end` derive to, labelled accordingly, never the mock's illustrative
`08:00–19:00` text):

```qml
    Component {
        id: weekGridComponent

        ColumnLayout {
            spacing: 2

            readonly property var axis: p ? p.calendarAxis : {"start": 8, "end": 20, "rowHeight": 13, "derived": false}
            readonly property var dates: p ? p.calendarGridDates : []
            readonly property var hourMarks: {
                var marks = [];
                for (var h = axis.start; h <= axis.end; h += 2) marks.push(h);
                return marks;
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                Item { Layout.preferredWidth: 26 }
                Repeater {
                    model: parent.parent.dates
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 0
                        readonly property bool isToday: modelData.date === Model.todayDate()
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: Model.DAY_NAMES_FULL ? Model.DAY_NAMES_FULL[new Date(modelData.date).getDay()] : ""
                            color: isToday ? theme.accent : theme.textDisabled
                            font.family: p ? p.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.letterSpacing: 0.08 * Style.font.caption
                        }
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: String(Number(modelData.date.split("-")[2]))
                            color: isToday ? theme.accent : theme.textMuted
                            font.family: p ? p.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                ColumnLayout {
                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 156
                    Repeater {
                        model: hourMarks
                        delegate: Text {
                            required property int modelData
                            text: String(modelData).padStart(2, "0")
                            color: theme.textDisabled
                            font.pixelSize: 9
                            horizontalAlignment: Text.AlignRight
                            Layout.preferredWidth: 26
                            Layout.preferredHeight: (modelData - axis.start) * axis.rowHeight * 0 // positioned via y below
                        }
                    }
                }

                Repeater {
                    model: dates
                    delegate: Rectangle {
                        id: col
                        required property var modelData
                        readonly property string date: modelData.date
                        readonly property bool isToday: date === Model.todayDate()
                        readonly property var dayEntries: (p ? p.calendarEntries : []).filter(function(e) {
                            return String(e.start || "").slice(0, 10) === date;
                        })
                        readonly property var dayBlocks: {
                            var cached = p ? p.calendarBlocksByDate[date] : null;
                            return cached ? cached.raw.filter(function(b) { return !b.applied; }) : [];
                        }
                        readonly property bool hasActivity: dayEntries.length > 0 || dayBlocks.length > 0

                        Layout.fillWidth: true
                        Layout.preferredHeight: 156
                        color: isToday ? Util.alpha(theme.accent, 0.06) : Qt.rgba(0, 0, 0, hasActivity ? 0.20 : 0.28)

                        // Hour gridlines every rowHeight px, replicating
                        // .wkcol's repeating-linear-gradient.
                        Repeater {
                            model: Math.floor(156 / Math.max(1, axis.rowHeight))
                            delegate: Rectangle {
                                required property int modelData
                                visible: col.hasActivity
                                y: modelData * axis.rowHeight
                                width: parent.width
                                height: 1
                                color: Util.alpha(theme.text, 0.07)
                            }
                        }

                        Repeater {
                            model: col.dayEntries
                            delegate: Rectangle {
                                required property var modelData
                                readonly property real startHour: Math.max(axis.start, Math.min(axis.end, Model.hourOfDay(modelData.start)))
                                readonly property real endHour: Math.max(axis.start, Math.min(axis.end, Model.hourOfDay(modelData.stop) || axis.end))
                                readonly property bool overflowTop: Model.hourOfDay(modelData.start) < axis.start
                                readonly property bool overflowBottom: Model.hourOfDay(modelData.stop) > axis.end

                                y: (startHour - axis.start) * axis.rowHeight
                                width: parent.width
                                height: Math.max(2, (endHour - startHour) * axis.rowHeight)
                                color: modelData.project_color || Qt.rgba(0.804, 0.839, 0.957, 0.18)

                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    text: modelData.description || ""
                                    color: "#0d1016"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                    clip: true
                                }

                                Rectangle {
                                    visible: parent.overflowTop
                                    anchors.top: parent.top
                                    width: parent.width
                                    height: 2
                                    color: theme.urgent
                                }
                                Rectangle {
                                    visible: parent.overflowBottom
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 2
                                    color: theme.urgent
                                }
                            }
                        }

                        Repeater {
                            model: col.dayBlocks
                            delegate: Rectangle {
                                required property var modelData
                                readonly property real startHour: Math.max(axis.start, Math.min(axis.end, Model.hourOfDay(modelData.start)))
                                readonly property real endHour: Math.max(axis.start, Math.min(axis.end, Model.hourOfDay(modelData.end) || axis.end))
                                readonly property bool isConflict: !!modelData.conflict

                                y: (startHour - axis.start) * axis.rowHeight
                                width: parent.width
                                height: Math.max(2, (endHour - startHour) * axis.rowHeight)
                                color: "transparent"
                                border.width: 1
                                border.color: isConflict ? theme.urgent : Util.alpha(theme.text, 0.35)

                                Text {
                                    visible: !parent.isConflict
                                    anchors.centerIn: parent
                                    text: "◌"
                                    color: theme.textMuted
                                    font.pixelSize: 9
                                }
                                Text {
                                    visible: parent.isConflict
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    text: modelData.label || ""
                                    color: theme.urgent
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                    clip: true
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 3
                spacing: 2
                Item { Layout.preferredWidth: 26 }
                Repeater {
                    model: dates
                    delegate: Text {
                        required property var modelData
                        readonly property real total: root.dayTotals[modelData.date] || 0
                        readonly property bool isToday: modelData.date === Model.todayDate()
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: total > 0 ? Model.clockDuration(total) : "—"
                        color: isToday ? theme.accent : (total > 0 ? theme.textMuted : theme.textDisabled)
                        font.family: p ? p.fontFamily : Style.font.family
                        font.pixelSize: Style.font.caption
                    }
                }
            }

            // Overflow line (spec 8.1 Overflow / rulings): only ever
            // reachable with an override, since derived bounds always
            // contain the data.
            RowLayout {
                Layout.fillWidth: true
                visible: p && p.calendarClamped
                spacing: Style.spacing.sm
                Text {
                    text: "▸"
                    color: theme.urgent
                    font.pixelSize: Style.font.caption
                }
                Text {
                    text: root.overflowCountLabel
                    color: theme.textDisabled
                    font.family: p ? p.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                }
            }
        }
    }

    readonly property string overflowCountLabel: {
        var axis = p ? p.calendarAxis : {"start": 8, "end": 20};
        var count = 0;
        (p ? p.calendarEntries : []).forEach(function(e) {
            var s = Model.hourOfDay(e.start), en = Model.hourOfDay(e.stop);
            if ((s !== null && s < axis.start) || (en !== null && en > axis.end)) count += 1;
        });
        var startLabel = String(axis.start).padStart(2, "0") + ":00";
        var endLabel = String(axis.end).padStart(2, "0") + ":00";
        return count + " entries fall outside " + startLabel + " – " + endLabel;
    }
```

The hour-gutter column above (`ColumnLayout` with a `Repeater` over `hourMarks`) positions labels by
list order inside a plain `ColumnLayout`, which does not reproduce the guide's absolute
`top:{n}px` positioning (`.wkhours span { position: absolute; … }`). Replace it with an `Item` and
absolutely-positioned children, matching the guide exactly:

```qml
                Item {
                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 156
                    Repeater {
                        model: hourMarks
                        delegate: Text {
                            required property int modelData
                            text: String(modelData).padStart(2, "0")
                            color: theme.textDisabled
                            font.pixelSize: 9
                            horizontalAlignment: Text.AlignRight
                            width: 22
                            x: 0
                            y: (modelData - axis.start) * axis.rowHeight - 4
                        }
                    }
                }
```

`Model.DAY_NAMES_FULL` referenced in the day-of-week header does not exist — `Model.js` only has the
abbreviated `DAY_NAMES` (`["Sun","Mon",…]`). The guide's week header shows three-letter, all-caps
day names (`MON`, `TUE`, …, `docs/design-guide.html:684-686`). Use the existing `Model.DAY_NAMES`
uppercased instead of inventing a new constant:

```qml
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: Model.DAY_NAMES[new Date(modelData.date).getDay()].toUpperCase()
                            color: isToday ? theme.accent : theme.textDisabled
                            font.family: p ? p.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.letterSpacing: 0.08 * Style.font.caption
                        }
```

- [ ] **Step 2: Verify**

Run: `qmlformat ui/CalendarScope.qml >/dev/null; echo $?` — must print `0`.
Run: `qmllint -I /usr/share/omarchy/shell ui/CalendarScope.qml; echo $?` — must print `0`.
Manual: `omarchy-restart-shell`, open the panel, enter calendar scope, press `w` until week range
shows. Confirm: 26px gutter + 7 columns, 156px column height, entries positioned by
`top = (startHour - axisStart) * rowHeight`, unassigned blocks render dashed with no fill and `◌`
when there's no room for a label, conflict blocks render with an urgent border and a label, per-day
totals sit in their own row under the grid (today's total in accent), and — with `calendarDayStart`/
`calendarDayEnd` overridden to something narrow enough to clip real data (Task 6 needed to set this
via UI, or set it directly through the panel's settings for this check) — the overflow line and edge
markers appear. Compare pixel-for-pixel against `docs/design-guide.html` section 04's `W` mock,
remembering rulings R-K: the *rendered axis label* will not literally read `08:00–19:00` unless that
happens to be what this account's real data derives — the 156px/13px *geometry* is what must match.

- [ ] **Step 3: Commit**

`git add ui/CalendarScope.qml && git commit -m "feat(calendar): week time-axis grid, entry positioning, overflow"`

---

## Task 6: `ui/CalendarScope.qml` — axis settings sub-panel

**Files:**
- Modify: `ui/CalendarScope.qml`

**Interfaces:**
- Consumes: `p.calendarDayStart`, `calendarDayEnd`, `calendarAxis`, `setCalendarAxisOverride`,
  `resetCalendarAxis` (all Task 3); `qs.Ui`'s `NumberField` (shell component,
  `/usr/share/omarchy/shell/Ui/NumberField.qml` — `label`, `value`, `from`, `to`, `stepSize`,
  `modified(value)` signal, all pre-existing).
- Produces: the `AXIS` sub-panel (`docs/design-guide.html` mock at lines 728-745), toggled by the
  `a` key (Task 3 Step 10) while in week range.

- [ ] **Step 1: Add the sub-panel property and section**

Add a property near the top of `Item { id: root }`:

```qml
    property bool axisSettingsOpen: false
```

Add, as a sibling of the `hints` `RowLayout` inside `column` (after it, so it appears below the
hints row when open — matches the guide's `AXIS` mock being a *separate* mock, shown here as an
expandable section rather than a second panel, per spec §8.1 "edited in the calendar scope's
settings section"):

```qml
        ColumnLayout {
            Layout.fillWidth: true
            visible: p && p.calendarRange === "week" && root.axisSettingsOpen
            spacing: Style.spacing.sm

            Text {
                text: "CALENDAR AXIS"
                color: theme.textDisabled
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                font.letterSpacing: 0.12 * Style.font.caption
            }

            Text {
                text: root.axisModeLabel
                color: theme.textMuted
                font.family: p ? p.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                NumberField {
                    id: startField
                    Layout.fillWidth: true
                    label: "Day starts"
                    from: 0
                    to: 24
                    stepSize: 1
                    value: p ? (p.calendarDayStart === "auto" ? p.calendarAxis.start : p.calendarDayStart) : 8
                    foreground: theme.text
                    accent: theme.accent
                    onModified: function(value) {
                        if (!p.setCalendarAxisOverride("start", value))
                            value = startField.value; // rejected: field keeps its prior value
                    }
                }

                NumberField {
                    id: endField
                    Layout.fillWidth: true
                    label: "Day ends"
                    from: 0
                    to: 24
                    stepSize: 1
                    value: p ? (p.calendarDayEnd === "auto" ? p.calendarAxis.end : p.calendarDayEnd) : 20
                    foreground: theme.text
                    accent: theme.accent
                    onModified: function(value) {
                        if (!p.setCalendarAxisOverride("end", value))
                            value = endField.value;
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Reset to automatic"
                    color: theme.textMuted
                    font.family: p ? p.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                    padding: 0
                    leftPadding: 7
                    rightPadding: 7
                    topPadding: 2
                    bottomPadding: 2
                    background: Rectangle {
                        color: "transparent"
                        border.width: 1
                        border.color: Style.normalBorderColor
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: p.resetCalendarAxis()
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }
```

- [ ] **Step 2: The mode line**

Add near the other computed properties at the top of the file:

```qml
    readonly property string axisModeLabel: {
        if (!p) return "";
        if (p.calendarDayStart === "auto" && p.calendarDayEnd === "auto")
            return "Automatic, from your tracked hours";
        var start = (p.calendarDayStart === "auto" ? p.calendarAxis.start : p.calendarDayStart);
        var end = (p.calendarDayEnd === "auto" ? p.calendarAxis.end : p.calendarDayEnd);
        return "Fixed, " + String(start).padStart(2, "0") + ":00–" + String(end).padStart(2, "0") + ":00";
    }
```

This matches R5-26 exactly: `"Automatic, from your tracked hours"` when both edges are `"auto"`,
`"Fixed, HH:00–HH:00"` (the *actual* pinned/effective hour pair, mixed auto+fixed included) otherwise.

- [ ] **Step 3: Blocked editor focus**

The `NumberField`'s internal `QQC.SpinBox` is editable (`editable: true`) and takes keyboard focus.
Confirm that `Panel.qml`'s root `PanelKeyCatcher` already sets `blocked: root.editorFocused` (it
does, pre-existing) and that `root.editorFocused`'s check —
`item instanceof TextInput || item instanceof TextEdit` — correctly recognises this field's focused
state: `QQC.SpinBox`'s `contentItem` is a `TextInput` (per `NumberField.qml`'s own `contentItem: TextInput { … }`),
so this is already covered with no further change needed. Verify by focusing a `Day starts` field
after this task and confirming `h`/`j`/`k`/`l`/`x` type into it instead of moving the calendar cursor.

- [ ] **Step 4: Verify**

Run: `qmlformat ui/CalendarScope.qml >/dev/null; echo $?` — must print `0`.
Run: `qmllint -I /usr/share/omarchy/shell ui/CalendarScope.qml; echo $?` — must print `0`.
Manual: `omarchy-restart-shell`, enter calendar scope, switch to week range, press `a`. Confirm the
`CALENDAR AXIS` section appears with the mode line, two `NumberField`s labelled "Day starts"/"Day
ends", and a "Reset to automatic" pill. Set start above (end − 4), confirm the field does not commit
(rejected at the field, per spec §8.1 — verify by checking `p.calendarDayStart` is unchanged in a
debug print or by observing the axis does not shift). Set a valid pair, confirm the week grid's axis
shifts to match and the mode line reads "Fixed, HH:00–HH:00". Click "Reset to automatic", confirm both
fields return to the derived values and the mode line reads "Automatic, from your tracked hours".
Confirm `qs -p /usr/share/omarchy/shell log` shows no `qt.qml.context` warnings throughout.

- [ ] **Step 5: Commit**

`git add ui/CalendarScope.qml && git commit -m "feat(calendar): axis override settings sub-panel"`

---

## Final verification (all tasks complete)

- [ ] Run: `python3 -m unittest discover -s tests` — all pass.
- [ ] Run: `node tests/test_model.mjs` — all pass.
- [ ] Run: `omarchy plugin validate .` — exits 0.
- [ ] Run: `qmlformat Panel.qml ui/CalendarScope.qml ui/PanelTheme.qml >/dev/null; echo $?` — `0`.
- [ ] Run: `qmllint -I /usr/share/omarchy/shell Panel.qml ui/CalendarScope.qml; echo $?` — `0`
      (`ui/PanelTheme.qml` and `BarWidget.qml` remain hand-reviewed per the standing constraints).
- [ ] Run: `grep -c "Qt.darker" ui/CalendarScope.qml` — `0`.
- [ ] Manual: `omarchy-restart-shell`; open the panel; visit every one of week/fortnight/month via
      both the `w` key and the chip clicks; page backward until the control disables at the 4 Jun
      2026 floor (or today's real equivalent) and confirm no request is issued past that point
      (watch `logs/toggl.jsonl` or the terminal for a 400 that never happens); open a day from each
      range via Enter; confirm `Ctrl+D`/whatever stage 4 binds still returns from Day scope to the
      calendar. Compare every rendered pixel value against `docs/design-guide.html` section 04.
