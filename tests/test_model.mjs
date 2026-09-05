// Runs the QML helper module under plain node.
// Usage: node tests/test_model.mjs
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, "..", "Model.js"), "utf8")
  .split("\n")
  .filter((line) => !line.trim().startsWith(".pragma"))
  .join("\n")

const Model = new Function(`${source}\nreturn {
  enrichmentSnapshot, enrichmentPayload, mergeEnrichment,
  clockTime, isoDate, todayDate, shiftDate, dayLabel,
  prepareBlocks, blockAlso, blockSummary, formatDuration, clampHistory,
  clampBlockMinutes, historyFloor, boundedShiftDate,
  searchItems, normalizeProject, normalizeTask, normalizeTag, scoreMatch,
  blockState, blockGlyph, blockReady, countLine, blockMeta, blockFacts, blockFilter, paletteIndex,
  hourOfDay, axisBounds, axisOverrideValid, weekStart, monthStart, monthEnd, shiftMonths, calendarRangeBounds,
  shiftCalendarAnchor, canPageCalendarBackward, calendarGridDates, isoWeekLabel, shortDateLabel, calendarHeaderLabel,
  calendarFloorHint, calendarDayTotals, calendarRangeTotal, calendarConflictDates, calendarFilter,
  classifyBlockPayload, classifyProjectPayload, classifyGuessFor, guessProjectFromTopics, applyProjectGuesses, historyGuessFor, applyHistoryGuesses,
  descriptionCandidates, cycleDescription, suggestionFor, helpSections,
  parseCommand, commandSegments, clockDuration, rowDuration, commandRows,
  stripAtFragment, stripSlashFragment, bindProject, bindTask, bindingsAfterTextEdit
}`)()

let failures = 0
function test(name, fn) {
  try {
    fn()
  } catch (error) {
    failures += 1
    console.error(`FAIL ${name}\n  ${error.message}`)
    return
  }
  console.log(`ok   ${name}`)
}


test("shiftDate crosses month and year boundaries", () => {
  assert.equal(Model.shiftDate("2026-08-31", 1), "2026-09-01")
  assert.equal(Model.shiftDate("2026-03-01", -1), "2026-02-28")
  assert.equal(Model.shiftDate("2026-12-31", 1), "2027-01-01")
  assert.equal(Model.shiftDate("2024-03-01", -1), "2024-02-29")
})

test("dayLabel renders the approved header format", () => {
  assert.equal(Model.dayLabel("2026-08-26"), "Wed 26 Aug 2026")
  assert.equal(Model.dayLabel(""), "")
})

test("clockTime is local wall time and survives bad input", () => {
  const when = new Date(2026, 7, 26, 9, 12)
  assert.equal(Model.clockTime(when.toISOString()), "09:12")
  assert.equal(Model.clockTime("nonsense"), "--:--")
})

test("prepareBlocks separates our own entries from foreign conflicts", () => {
  const blocks = [
    { start: "a", end: "b", seconds: 60, label: "one", topics: [{ name: "one", seconds: 60 }] },
    { start: "c", end: "d", seconds: 60, label: "two", topics: [], applied: true, conflict: { id: 1 } },
    { start: "e", end: "f", seconds: 60, label: "three", topics: [], applied: true, conflict: { id: 2 } }
  ]
  const entries = [
    { id: 1, created_with: "omarchy-toggl-track/day" },
    { id: 2, created_with: "toggl-web" }
  ]
  const prepared = Model.prepareBlocks(blocks, entries)
  assert.deepEqual(prepared.map((block) => block.state), ["pending", "applied", "conflict"])
  assert.equal(prepared[0].description, "one")
  assert.equal(prepared[0].projectId, 0)
  assert.equal(prepared[0].inspecting, false)
  assert.equal(prepared[0].editing, false)
})

test("prepareBlocks treats an unmatched conflict id as foreign", () => {
  const prepared = Model.prepareBlocks([{ seconds: 1, applied: true, conflict: { id: 99 } }], [])
  assert.equal(prepared[0].state, "conflict")
})

test("prepareBlocks does not alias the caller's objects", () => {
  const original = { seconds: 1, label: "keep", topics: [] }
  const prepared = Model.prepareBlocks([original], [])
  prepared[0].description = "changed"
  assert.equal(original.label, "keep")
  assert.equal(original.description, undefined)
})

test("prepareBlocks falls back to seconds when span is absent", () => {
  const prepared = Model.prepareBlocks([{ seconds: 300, label: "x", topics: [] }], [])
  assert.equal(prepared[0].spanSeconds, 300)
  assert.equal(Model.prepareBlocks([{ seconds: 300, span_seconds: 900, label: "x" }], [])[0].spanSeconds, 900)
})

test("blockAlso lists the topics after the headline", () => {
  const block = { topics: [{ name: "Jira" }, { name: "term:vault" }, { name: "Slack" }, { name: "Mail" }, { name: "Docs" }] }
  assert.equal(Model.blockAlso(block, 3), "term:vault · Slack · Mail")
  assert.equal(Model.blockAlso({ topics: [{ name: "only" }] }, 3), "")
  assert.equal(Model.blockAlso({}, 3), "")
})

test("blockSummary counts total, ready, unassigned and applied", () => {
  const blocks = [
    { seconds: 600, state: "pending", projectId: 5, description: "ready" },
    { seconds: 300, state: "pending", projectId: 0, description: "no project" },
    { seconds: 120, state: "pending", projectId: 5, description: "   " },
    { seconds: 900, state: "applied", projectId: 5, description: "done" },
    { seconds: 60, state: "conflict", projectId: 0, description: "clash" }
  ]
  const summary = Model.blockSummary(blocks)
  assert.equal(summary.totalSeconds, 1980)
  assert.equal(summary.ready, 1)
  assert.equal(summary.unassigned, 2)
  assert.equal(summary.applied, 1)
  assert.equal(summary.conflicts, 1)
})

test("blockSummary tolerates empty input", () => {
  assert.deepEqual(Model.blockSummary([]), { totalSeconds: 0, ready: 0, applicable: 0, unassigned: 0, applied: 0, conflicts: 0, skipped: 0 })
})

test("clampBlockMinutes accepts only offered choices", () => {
  assert.equal(Model.clampBlockMinutes(2), 2)
  assert.equal(Model.clampBlockMinutes("15"), 15)
  assert.equal(Model.clampBlockMinutes(7), 5)
  assert.equal(Model.clampBlockMinutes(0), 5)
  assert.equal(Model.clampBlockMinutes(-3), 5)
  assert.equal(Model.clampBlockMinutes(null), 5)
  assert.equal(Model.clampBlockMinutes(""), 5)
  assert.equal(Model.clampBlockMinutes(undefined), 5)
})

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
test("clampHistory accepts 92, the largest window the API allows", () => {
  assert.equal(Model.clampHistory(92), 92)
})
test("clampHistory clamps 93 because the API floor is 91 days", () => {
  assert.equal(Model.clampHistory(93), 90)
})
test("historyFloor is 91 days before the given day", () => {
  assert.equal(Model.historyFloor("2026-09-03"), "2026-06-04")
})
test("historyFloor crosses a month boundary", () => {
  assert.equal(Model.historyFloor("2026-03-01"), "2025-11-30")
})
test("boundedShiftDate moves freely inside the history window", () => {
  assert.equal(Model.boundedShiftDate("2026-08-01", -1, "2026-09-03"), "2026-07-31")
  assert.equal(Model.boundedShiftDate("2026-08-01", 1, "2026-09-03"), "2026-08-02")
})
test("boundedShiftDate refuses to cross the history floor", () => {
  const floor = Model.historyFloor("2026-09-03")
  assert.equal(Model.boundedShiftDate(floor, -1, "2026-09-03"), floor)
})
test("boundedShiftDate allows landing exactly on the floor", () => {
  const floor = Model.historyFloor("2026-09-03")
  const dayAfterFloor = Model.shiftDate(floor, 1)
  assert.equal(Model.boundedShiftDate(dayAfterFloor, -1, "2026-09-03"), floor)
})
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
// Realistic multi-word names, drawn from spec S6.5 and the stage-3b brief's
// measured examples. Every RANK case below sorts this same pool so a fixture
// gap can't quietly make a query's rivals easier to beat.
const SCORE_NAMES = [
  "Research and Development",
  "Shipyard",
  "NW-075 Northwind Voyager Testing",
  "Travel Day",
  "NW-092-H370 Wild Harbour",
  "NW-091 Northwind Venturer Upgrade Testing & Validation",
  "Growth: Paper & Presentation Development",
  "NW-088 Bluefin Protection Study",
]

function bestMatch(query, names) {
  var winner = null, best = -1
  names.forEach((name) => {
    var score = Model.scoreMatch(query, name)
    if (score > best) { best = score; winner = name }
  })
  return winner
}

const RANK = [
  ["rd", "Research and Development"],
  ["nvt", "NW-075 Northwind Voyager Testing"],
  ["trav", "Travel Day"],
  ["wild", "NW-092-H370 Wild Harbour"],
  ["091", "NW-091 Northwind Venturer Upgrade Testing & Validation"],
  ["gppd", "Growth: Paper & Presentation Development"],
  ["bluefin", "NW-088 Bluefin Protection Study"],
  ["upgrade", "NW-091 Northwind Venturer Upgrade Testing & Validation"],
]

RANK.forEach(([query, expected]) => {
  test(`scoreMatch: "${query}" ranks "${expected}" first`, () => {
    assert.equal(bestMatch(query, SCORE_NAMES), expected)
  })
})

test("scoreMatch: rule 4 (significant-word acronym) is load-bearing -- without it \"rd\" would reach Shipyard through the substring \"...ya-rd\"", () => {
  const rd = Model.scoreMatch("rd", "Research and Development")
  const shipyard = Model.scoreMatch("rd", "Shipyard")
  assert.ok(rd > 0 && shipyard > 0, "both must actually match for this to test anything")
  assert.ok(rd > shipyard)
})

test("scoreMatch: rule 5 (trailing-run acronym) is load-bearing -- without it \"nvt\" could not skip the NW-075 job code", () => {
  assert.ok(Model.scoreMatch("nvt", "NW-075 Northwind Voyager Testing") > 0)
})

test("scoreMatch: an empty query scores 0 for every name", () => {
  SCORE_NAMES.forEach((name) => assert.equal(Model.scoreMatch("", name), 0))
})

test("scoreMatch: a query matching nothing scores 0", () => {
  assert.equal(Model.scoreMatch("zzqx", "Travel Day"), 0)
})

test("scoreMatch: matching is case-insensitive", () => {
  assert.equal(Model.scoreMatch("TRAV", "travel day"), Model.scoreMatch("trav", "Travel Day"))
  assert.ok(Model.scoreMatch("Bluefin", "NW-088 BLUEFIN PROTECTION STUDY") > 0)
})

test("scoreMatch: a shorter name outranks a longer one at the same rule", () => {
  // Both match rule 1, the whole name starting with the query.
  assert.ok(Model.scoreMatch("op", "Ops") > Model.scoreMatch("op", "Ops Extended Longer Name"))
})


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

test("parseCommand: a trailing partial project name is still typing, but offers no ghost", () => {
  // Spec 6.5 (amended 2026-09-04): there is no ghost completion for an @
  // token any more, matched project name or not -- see the multi-word
  // tests below for why. The token is still "in progress" rather than
  // "wrong": unbound, and NOT reported in unmatched.
  const result = Model.parseCommand("refactor @ac", projects, tasks, [])
  assert.equal(result.completion, "")
  assert.equal(result.projectId, 0, "not bound until Enter on a PROJ row")
  assert.equal(result.description, "refactor @ac", "unresolved token stays in the text")
  assert.deepEqual(result.unmatched, [], "still typing, not flagged wrong")
})

test("parseCommand: a unique project-prefix match never completes into a multi-word name", () => {
  // The bug this fix round closed: the old completion was the matched
  // name sliced by character count, not by word boundary, so a short
  // fragment of a genuinely multi-word name still produced a tail
  // containing a space -- e.g. "@Res" against "Research and Development"
  // used to yield "earch and Development". The existing fixtures above
  // only ever used single-word project names ("acme"), which is exactly
  // why this was never caught. Real, single-fixture, multi-word names:
  // 20 of the user's 25 active projects are multi-word.
  const multiWord = [
    Model.normalizeProject({ id: 900, name: "Research and Development", active: true }),
  ]
  const short = Model.parseCommand("note @Res", multiWord, [], [])
  assert.equal(short.completion, "", "would have been \"earch and Development\"")
  assert.equal(short.projectId, 0, "still typing, not bound")
  assert.deepEqual(short.unmatched, [])

  const longer = Model.parseCommand("note @Research", multiWord, [], [])
  assert.equal(longer.completion, "", "would have been \" and Development\"")
  assert.equal(longer.projectId, 0)

  // A punctuation-heavy real name (client codes like "NW-092-H370"),
  // exercised the same way.
  const punctuated = [
    Model.normalizeProject({ id: 901, name: "NW-092-H370 Wild Harbour", active: true }),
  ]
  const withDash = Model.parseCommand("note @NW-092", punctuated, [], [])
  assert.equal(withDash.completion, "")
  const bare = Model.parseCommand("note @OSP", punctuated, [], [])
  assert.equal(bare.completion, "")
})

test("parseCommand: a unique task-prefix match binds both ids, matching the guide's own example", () => {
  // design-guide.html:441 and :1418-1423 both render this exact moment as
  // "acme · backend" and let Enter commit it -- the project half matched
  // exactly, and the task half is a unique prefix of the project's only
  // candidate, so both ids bind and the token is spoken for (cleared from
  // description) even though "back" itself isn't the full task name.
  // completion is "" (spec 6.5, amended 2026-09-04) -- see the multi-word
  // task-name test below for why: task names are multi-word too.
  const result = Model.parseCommand("refactor @acme/back", projects, tasks, [])
  assert.equal(result.completion, "")
  assert.equal(result.projectId, 1)
  assert.equal(result.taskId, 10)
  assert.equal(result.description, "refactor")
})

test("parseCommand: a unique task-prefix match never completes into a multi-word task name either", () => {
  // Task names are multi-word too (median 22 chars, longest 77 in the
  // user's workspace) -- the task-half branch had the identical defect as
  // the project-half one above, e.g. "@acme/Site" against "Site Survey
  // and Inspection" used to yield "completion" == " Survey and Inspection".
  const project = [Model.normalizeProject({ id: 1, name: "acme", active: true })]
  const multiWordTasks = [
    Model.normalizeTask({ id: 20, project_id: 1, name: "Site Survey and Inspection", active: true }),
  ]
  const result = Model.parseCommand("refactor @acme/Site", project, multiWordTasks, [])
  assert.equal(result.completion, "", "would have been \" Survey and Inspection\"")
  assert.equal(result.projectId, 1, "the project half still binds")
  assert.equal(result.taskId, 20, "the task half still binds -- only the ghost is gone")
})

test("parseCommand: an exact project with an empty task fragment binds projectId only", () => {
  // "@acme/" -- the project half is done and exact, the task half hasn't
  // been started yet. There's nothing to complete or bind a task to, but
  // discarding the project the user already finished typing would repeat
  // finding 3.
  const result = Model.parseCommand("refactor @acme/", projects, tasks, [])
  assert.equal(result.projectId, 1)
  assert.equal(result.taskId, 0)
  assert.equal(result.completion, "")
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
  assert.equal(Model.clockDuration(348000), "96h40")
})

test("rowDuration: bare minutes under an hour, clockDuration at or above", () => {
  assert.equal(Model.rowDuration(2700), "45m")
  assert.equal(Model.rowDuration(960), "16m")
  assert.equal(Model.rowDuration(3540), "59m")
  assert.equal(Model.rowDuration(8700), "2h25")
})

test("clockDuration and rowDuration round 3599s up to 1h00 consistently", () => {
  assert.equal(Model.clockDuration(3599), "1h00")
  assert.equal(Model.rowDuration(3599), "1h00")
})

test("parseCommand: sigil matching is case-insensitive", () => {
  // Both the exact-project and exact-task arms lowercase both sides, so a
  // shouted token binds the same ids as a typed one.
  const shouted = Model.parseCommand("refactor @ACME/BACKEND", projects, tasks, [])
  assert.equal(shouted.projectId, 1)
  assert.equal(shouted.taskId, 10)
  assert.equal(shouted.description, "refactor")
  assert.deepEqual(shouted.unmatched, [])
})

test("parseCommand: an ambiguous prefix is unmatched, not a guess and not a completion", () => {
  // "b" prefixes "backend" and nothing else among project names, but among
  // acme's tasks it prefixes only "backend" -- use a project fragment that
  // genuinely prefixes two active projects to exercise the >1-candidate arm.
  const ambiguous = [
    Model.normalizeProject({ id: 1, name: "backend", active: true }),
    Model.normalizeProject({ id: 2, name: "backoffice", active: true }),
  ]
  const result = Model.parseCommand("standup @back", ambiguous, [], [])
  assert.equal(result.projectId, 0, "two candidates must never bind one of them")
  assert.equal(result.completion, "", "a ghost suffix would be a guess between two projects")
  assert.deepEqual(result.unmatched, ["@back"])
  assert.equal(result.description, "standup @back", "an unmatched sigil token stays visible in the description")
})

test("parseCommand: a lone @ is neither unmatched nor a completion", () => {
  // The user has typed the sigil and nothing after it. Flagging that as
  // unmatched would put a red "no project" on every first keystroke.
  const result = Model.parseCommand("standup @", projects, tasks, [])
  assert.deepEqual(result.unmatched, [])
  assert.equal(result.completion, "")
  assert.equal(result.description, "standup @")
})

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

test("commandRows: empty text has no START row, up to ten distinct recent entries, one nearest open block", () => {
  // Distinct, deliberately out-of-order timestamps -- so this proves the most
  // recent entries are picked, not just any of them.
  const entries = [
    entry({ id: 2, description: "b", start: "2026-09-04T09:00:00.000Z", stop: "2026-09-04T09:10:00.000Z" }),
    entry({ id: 4, description: "d", start: "2026-09-04T11:00:00.000Z", stop: "2026-09-04T11:10:00.000Z" }),
    entry({ id: 1, description: "a", start: "2026-09-04T08:00:00.000Z", stop: "2026-09-04T08:10:00.000Z" }),
    entry({ id: 3, description: "c", start: "2026-09-04T10:00:00.000Z", stop: "2026-09-04T10:10:00.000Z" }),
  ]
  const blocks = [block({ state: "applied" }), block({ state: "pending" })]
  const rows = Model.commandRows("", projects, tasks, [], entries, blocks, Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0)
  const contRows = rows.filter((r) => r.kind === "continue")
  assert.deepEqual(contRows.map((r) => r.target.id), [4, 3, 2, 1], "most recent first")
  const blockRows = rows.filter((r) => r.kind === "block")
  assert.equal(blockRows.length, 1)
  assert.equal(blockRows[0].target.state, "pending")
})

test("commandRows: the recent list caps at ten and shows each description once", () => {
  const many = []
  for (let i = 0; i < 14; i++) {
    const hour = String(8 + i).padStart(2, "0")
    many.push(entry({ id: 100 + i, description: "task " + i,
      start: "2026-09-04T" + hour + ":00:00.000Z", stop: "2026-09-04T" + hour + ":10:00.000Z" }))
  }
  // The same work logged three times is one thing to continue, not three.
  many.push(entry({ id: 200, description: "task 13", start: "2026-09-03T08:00:00.000Z", stop: "2026-09-03T08:10:00.000Z" }))
  many.push(entry({ id: 201, description: "task 13", start: "2026-09-02T08:00:00.000Z", stop: "2026-09-02T08:10:00.000Z" }))
  const rows = Model.commandRows("", projects, tasks, [], many, [], Date.now()).filter((r) => r.kind === "continue")
  assert.equal(rows.length, 10)
  assert.equal(new Set(rows.map((r) => r.label)).size, 10)
})

test("commandRows: @ present -> START and PROJ rows, unresolved token stays in the label", () => {
  // "Corp" is a fragment of the shared client name ("Acme Corp") and is not
  // itself a prefix of either project's own name, so parseCommand leaves it
  // unbound (meta stays "no project") while the row composer still surfaces
  // both of that client's projects via scoreMatch against the client name,
  // exactly as R3-30 describes for a client-name-only fragment. The
  // unresolved "@Corp" token is never dropped (rule 2), so it stays visible
  // in the label -- finding 1's invariant is that the label is always
  // exactly what START submits.
  const rows = Model.commandRows("refactor @Corp", projects, tasks, [], [], [], Date.now())
  assert.equal(rows[0].kind, "start")
  assert.equal(rows[0].label, "refactor @Corp", "the label must show the unresolved token, not hide it -- hiding it is finding 1's bug")
  assert.equal(rows[0].label, rows[0].target.description, "the invariant: a START row's label always equals what it will submit")
  assert.equal(rows[0].meta, "no project")
  const projRows = rows.filter((r) => r.kind === "project")
  assert.deepEqual(projRows.map((r) => r.target.id).sort(), [1, 2], "both acme projects match the client-name fragment")
})

test("commandRows: an @ token composes alongside CONT and BLOCK, never suppressing them (F3) -- design-guide.html's own worked example coexists", () => {
  // design-guide.html:441-445's §01 mock renders "refactor @acme/back" as
  // START, CONT, CONT, PROJ, BLOCK -- one list, several kinds coexisting.
  // The @ branch used to `return` immediately after pushing PROJ rows,
  // silently dropping CONT and BLOCK for every @ token typed -- and the
  // test above passes `[]` for both entries and blocks, so "PROJ rows
  // only" was true whether or not that early return existed (F10, final
  // review): it could not have caught F3.
  const entries = [entry({ id: 1, description: "Refactor onboarding notes" })]
  const blocks = [block({ label: "Refactor day segmentation", state: "pending" })]
  const rows = Model.commandRows("refactor @acme/back", projects, tasks, [], entries, blocks, Date.now())
  const kinds = rows.map((r) => r.kind)
  assert.ok(kinds.indexOf("start") !== -1)
  assert.ok(kinds.indexOf("project") !== -1, "the @ token still ranks PROJ rows")
  assert.ok(kinds.indexOf("continue") !== -1, "CONT must not vanish just because an @ token is present")
  assert.ok(kinds.indexOf("block") !== -1, "BLOCK must not vanish just because an @ token is present")
})

test("commandRows: a START row's label always equals what it submits -- finding 1's invariant, all three of the review's failure rows", () => {
  // Finding 1: Model.js used to compute the START row's *label* one way
  // (text before the last @) and hand startFromCommand a *target* whose
  // .description disagreed with it. Assert the invariant directly rather
  // than pinning three example strings, so any future divergence between
  // the two fails here regardless of what the strings happen to be.
  const cases = [
    "refactor @acme/back",    // finding 3: exact project + unique task prefix -- both resolve and clear
    "refactor @acme fixes",   // exact project mid-sentence -- description keeps the trailing words
    "refactor @acme/backend", // fully resolved -- already agreed before this fix
  ]
  cases.forEach((text) => {
    const rows = Model.commandRows(text, projects, tasks, [], [], [], Date.now())
    const startRows = rows.filter((r) => r.kind === "start")
    assert.equal(startRows.length, 1, text)
    assert.equal(startRows[0].label, startRows[0].target.description, text)
  })
  // And the exact strings, since the invariant alone wouldn't catch a
  // regression where both sides changed together to something equally wrong.
  const back = Model.commandRows("refactor @acme/back", projects, tasks, [], [], [], Date.now()).filter((r) => r.kind === "start")[0]
  assert.equal(back.label, "refactor")
  assert.equal(back.target.projectId, 1, "the exactly-typed project must not be discarded mid-token")
  assert.equal(back.target.taskId, 10, "a unique task prefix binds too, per finding 3")

  const fixes = Model.commandRows("refactor @acme fixes", projects, tasks, [], [], [], Date.now()).filter((r) => r.kind === "start")[0]
  assert.equal(fixes.label, "refactor fixes", "the word after the token must not be invisible in the row that is about to submit it")

  const backend = Model.commandRows("refactor @acme/backend", projects, tasks, [], [], [], Date.now()).filter((r) => r.kind === "start")[0]
  assert.equal(backend.label, "refactor")
  assert.equal(backend.target.projectId, 1)
  assert.equal(backend.target.taskId, 10)
})

test("commandRows: PROJ row label is 'client / project', meta counts entries with correct pluralisation", () => {
  const rows = Model.commandRows("refactor @Corp", projects, tasks, [], [entry({ id: 1, projectId: 1 })], [], Date.now())
  const projRows = rows.filter((r) => r.kind === "project").sort((a, b) => a.target.id - b.target.id)
  assert.equal(projRows[0].label, "Acme Corp / acme")
  assert.equal(projRows[0].meta, "1 entry", "singular for exactly one matching entry")
  assert.equal(projRows[1].label, "Acme Corp / backoffice")
  assert.equal(projRows[1].meta, "0 entries", "plural for zero matching entries")
})

test("commandRows: PROJ rows are capped at 8, even when more active projects match the fragment", () => {
  const manyProjects = []
  for (let i = 1; i <= 10; i++) {
    manyProjects.push(Model.normalizeProject({ id: 100 + i, name: "proj" + i, active: true }))
  }
  const rows = Model.commandRows("task @proj", manyProjects, [], [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "project").length, 8)
})

test("commandRows: @ branch never surfaces an inactive project, even when its own name matches the fragment", () => {
  const rows = Model.commandRows("old work @zeta", projects, tasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "project").length, 0, "zeta is inactive and must not surface as a PROJ row")
})

test("commandRows: @ branch truncates the project fragment at the first '/', matching on the project name alone", () => {
  // If the fragment were used whole ("backoffice/tasknotreal"), it would
  // match nothing -- projectSearchText never contains a "/". A match here
  // proves the fragment was truncated to "backoffice" before matching.
  const rows = Model.commandRows("refactor @backoffice/tasknotreal", projects, tasks, [], [], [], Date.now())
  const projRows = rows.filter((r) => r.kind === "project")
  assert.deepEqual(projRows.map((r) => r.target.id), [2])
})

test("commandRows: no START row for text that composes to an empty label -- a lone unresolved @ token", () => {
  const rows = Model.commandRows("@ac", projects, tasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0, "nothing precedes the @, so there is nothing to start")
  assert.ok(rows.filter((r) => r.kind === "project").length > 0, "PROJ rows still surface for the @ branch")
})

test("commandRows: no START row for text that composes to an empty label -- a FULLY RESOLVED @ token with a trailing space", () => {
  // Worse than the unresolved case: "@acme " resolves to a real project
  // (target.projectId 1), so without the fix Enter here would commit a
  // real, empty-description entry against a real project -- not just a
  // mid-typing transient. The fix is general (it suppresses on the
  // composed description being empty, not on any @-branch-specific check),
  // so this is covered by the same condition as "@ac", not a separate one.
  const rows = Model.commandRows("@acme ", projects, tasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0, "the @acme token is fully stripped from the description, leaving nothing to start")
  assert.ok(rows.filter((r) => r.kind === "project").length > 0, "PROJ rows still surface for the @ branch")
})

test("commandRows: no START row for text that composes to an empty label -- a bare billable toggle", () => {
  const rows = Model.commandRows("$", projects, tasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0, "a bare $ leaves no description behind")
})

test("commandRows: BLOCK row's today/day-label comparison is a function of now, not the real wall clock", () => {
  const blocks = [block({ label: "Reviewing PRs", start: "2030-06-15T09:20:00.000Z", state: "pending" })]
  const sameDay = Model.commandRows("Reviewing", projects, tasks, [], [], blocks, new Date("2030-06-15T18:00:00.000Z").getTime())
  const nextDay = Model.commandRows("Reviewing", projects, tasks, [], [], blocks, new Date("2030-06-16T06:00:00.000Z").getTime())
  const sameDayBlock = sameDay.filter((r) => r.kind === "block")[0]
  const nextDayBlock = nextDay.filter((r) => r.kind === "block")[0]
  assert.notEqual(sameDayBlock.meta.indexOf("today"), -1, "now on the block's own day must render 'today', regardless of the real system date")
  assert.equal(nextDayBlock.meta.indexOf("today"), -1, "now on the following day must not render 'today'")
})

test("commandRows: now works identically as a Date object or as a Date.now()-style millisecond number", () => {
  // Task 4's QML side calls commandRows(..., Date.now()) -- a number.
  // durationSeconds (via continueRow) tolerates either shape by coercion,
  // but isoDate (via `today`, for blockRow) requires a real Date and throws
  // on a number -- so commandRows must normalise internally rather than
  // relying on the caller's shape.
  const now = new Date("2030-06-15T18:00:00.000Z")
  const entries = [entry({ id: 1, description: "Reviewing PRs", start: "2030-06-15T11:50:00.000Z", stop: "" })]
  const blocks = [block({ label: "Reviewing PRs", start: "2030-06-15T09:20:00.000Z", state: "pending" })]
  const withDate = Model.commandRows("Reviewing", projects, tasks, [], entries, blocks, now)
  const withNumber = Model.commandRows("Reviewing", projects, tasks, [], entries, blocks, now.getTime())
  assert.deepEqual(withDate, withNumber)
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
  assert.equal(rows[2].meta.indexOf("0h50"), 0, "BLOCK rows use clockDuration's always-hour form, not rowDuration's")
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

test("commandRows: a CONT row's duration lives in num, not meta -- a long project/task must not clip it", () => {
  // The bug this guards against: with everything (glyph, verb, label, meta)
  // sharing one row, a long project/task string pushed the duration past
  // the panel's right edge, where it silently clipped. Splitting the
  // duration into its own never-eliding column only works if meta itself
  // no longer carries it.
  const entries = [entry({ id: 1, description: "Reviewing PRs", start: "2026-09-04T11:00:00.000Z", stop: "2026-09-04T11:50:00.000Z" })]
  const rows = Model.commandRows("Reviewing", projects, tasks, [], entries, [], Date.now())
  const contRow = rows.filter((r) => r.kind === "continue")[0]
  assert.equal(contRow.meta, "acme · backend", "meta holds only project/task, no duration")
  assert.equal(contRow.num, "50m", "the duration moved here instead, via rowDuration's under-an-hour form")
})

test("commandRows: a BLOCK row keeps its leading duration in meta and has no num", () => {
  const blocks = [block({ label: "Reviewing PRs", start: "2026-09-04T11:50:00.000Z", seconds: 3000, state: "pending" })]
  const rows = Model.commandRows("Reviewing", projects, tasks, [], [], blocks, Date.now())
  const blockRow = rows.filter((r) => r.kind === "block")[0]
  assert.equal(blockRow.meta.indexOf("0h50"), 0, "unlike CONT, BLOCK's number stays first in meta -- the guide never moves it")
  assert.equal(blockRow.num, "")
})

test("commandRows: every row kind exposes a num key, whether or not it is used", () => {
  // All four kinds can appear in a single call now that F3 removed the @
  // branch's early return -- design-guide.html:441-445's own mock shows
  // exactly this shape (START, CONT, CONT, PROJ, BLOCK). This used to need
  // two separate calls, combined, to reach all four kinds at all.
  const entries = [entry({ id: 1, description: "Reviewing PRs" })]
  const blocks = [block({ label: "Reviewing PRs", start: "2026-09-04T11:50:00.000Z", seconds: 3000, state: "pending" })]
  const rows = Model.commandRows("Reviewing @acme", projects, tasks, [], entries, blocks, Date.now())
  const kinds = new Set(rows.map((r) => r.kind))
  assert.ok(kinds.has("start") && kinds.has("continue") && kinds.has("project") && kinds.has("block"), "this worked example must cover all four kinds, or the assertion below proves nothing")
  for (const row of rows) {
    assert.equal(typeof row.num, "string", `${row.kind} row is missing its num key`)
  }
})

test("commandRows: a trailing slash binds the project without leaking the token", () => {
  // "@acme/" bound the project but left the raw token in the description, so
  // Enter wrote "refactor @acme/" to Toggl under that project. One "/" after a
  // resolved "@acme" is all it took.
  const start = Model.commandRows("refactor @acme/", projects, tasks, [], [], [], Date.now()).filter((r) => r.kind === "start")[0]
  assert.equal(start.target.projectId, 1)
  assert.equal(start.target.description, "refactor", "the token is spoken for by projectId, not left in the description")
  assert.equal(start.label, start.target.description)
})

test("commandRows: an ambiguous task half keeps the project it already resolved", () => {
  // The shared fixture has exactly one task starting with "back", which is the
  // only reason the guide's showcase "@acme/back" resolves at all -- so this
  // needs its own pair to reach the ambiguous branch. The project half is a
  // finished exact match, so discarding it and falling back to "no project"
  // was the remaining half of the mid-token bug. Ambiguous is not wrong.
  const twoBacks = [
    Model.normalizeTask({ id: 10, project_id: 1, name: "backend", active: true }),
    Model.normalizeTask({ id: 12, project_id: 1, name: "backoffice work", active: true }),
  ]
  const start = Model.commandRows("refactor @acme/back", projects, twoBacks, [], [], [], Date.now()).filter((r) => r.kind === "start")[0]
  assert.equal(start.target.projectId, 1, "the project stays bound")
  assert.equal(start.target.taskId, 0, "nothing unique to bind the task to")
  assert.equal(start.meta.indexOf("no project"), -1)
  assert.equal(start.label, start.target.description)
})

// --- Stage 3b Task 2: scoreMatch-ranked PROJ rows, and the new TASK row kind ---

test("commandRows: PROJ rows are ranked by scoreMatch, not alphabetically -- a worse-tier name-prefix match must not outrank a whole-name/client-name prefix", () => {
  // Alphabetically "Alpha Holdings" sorts before "Zulu Co", which is exactly
  // what the old projectMatches (localeCompare on project.name) would have
  // returned. scoreMatch ranks them the other way: "Alpha Holdings" only
  // reaches rule 2 (a later word, "Holdings", starts with "hold"), while
  // "Zulu Co" reaches rule 1 through its CLIENT name ("Holding Group" itself
  // starts with "hold") -- proving both that ranking replaced alphabetical
  // order and that the client name is scored too.
  const localProjects = [
    Model.normalizeProject({ id: 301, name: "Alpha Holdings", client_name: "", active: true }),
    Model.normalizeProject({ id: 302, name: "Zulu Co", client_name: "Holding Group", active: true }),
  ]
  const rows = Model.commandRows("expense @hold", localProjects, [], [], [], [], Date.now())
  const projRows = rows.filter((r) => r.kind === "project")
  assert.deepEqual(projRows.map((r) => r.target.id), [302, 301], "the whole-name/client-name prefix match must rank above the later-word match, reversing alphabetical order")
})

test("commandRows: a bound project with an unresolved /frag emits ranked TASK rows", () => {
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const boundTasks = [
    Model.normalizeTask({ id: 50, project_id: 500, name: "Planning", active: true }),
    Model.normalizeTask({ id: 51, project_id: 500, name: "Site Plan Review", active: true }),
    Model.normalizeTask({ id: 52, project_id: 500, name: "Execution", active: true }),
  ]
  const rows = Model.commandRows("notes /plan", boundProjects, boundTasks, [], [], [], Date.now(), 500, 0)
  const taskRows = rows.filter((r) => r.kind === "task")
  assert.deepEqual(taskRows.map((r) => r.target.id), [50, 51], "ranked by scoreMatch against the task name -- whole-name prefix beats a later-word prefix")
  assert.equal(taskRows[0].glyph, "◈")
  assert.equal(taskRows[0].verb, "TASK")
  assert.equal(taskRows[0].label, "Planning", "label is the task name")
  assert.equal(taskRows[0].meta, "Northwind Venture", "meta is the owning project's name")
  assert.equal(taskRows[0].num, "")
})

test("commandRows: no bound project -> a /frag emits no TASK rows", () => {
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const boundTasks = [Model.normalizeTask({ id: 50, project_id: 500, name: "Planning", active: true })]
  const rows = Model.commandRows("notes /plan", boundProjects, boundTasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "task").length, 0)
})

test("commandRows: a bound project with no /frag in the last token emits no TASK rows", () => {
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const boundTasks = [Model.normalizeTask({ id: 50, project_id: 500, name: "Planning", active: true })]
  const rows = Model.commandRows("just plain notes", boundProjects, boundTasks, [], [], [], Date.now(), 500, 0)
  assert.equal(rows.filter((r) => r.kind === "task").length, 0)
})

test("commandRows: TASK rows are capped at 8, even when more active tasks match the fragment", () => {
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const manyTasks = []
  for (let i = 1; i <= 10; i++) {
    manyTasks.push(Model.normalizeTask({ id: 600 + i, project_id: 500, name: "task" + i, active: true }))
  }
  const rows = Model.commandRows("notes /task", boundProjects, manyTasks, [], [], [], Date.now(), 500, 0)
  assert.equal(rows.filter((r) => r.kind === "task").length, 8)
})

test("commandRows: TASK ranking only considers the bound project's own ACTIVE tasks", () => {
  const boundProjects = [
    Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true }),
    Model.normalizeProject({ id: 501, name: "Other Venture", active: true }),
  ]
  const boundTasks = [
    Model.normalizeTask({ id: 50, project_id: 500, name: "Planning", active: true }),
    Model.normalizeTask({ id: 53, project_id: 500, name: "Planning Archive", active: false }),
    Model.normalizeTask({ id: 54, project_id: 501, name: "Planning Elsewhere", active: true }),
  ]
  const rows = Model.commandRows("notes /plan", boundProjects, boundTasks, [], [], [], Date.now(), 500, 0)
  const taskRows = rows.filter((r) => r.kind === "task")
  assert.deepEqual(taskRows.map((r) => r.target.id), [50], "the inactive task and the other project's task must not surface")
})

test("commandRows: the START row's effective ids prefer the bound ids over the parsed ones", () => {
  // Plain text resolves nothing on its own (parsed.projectId/taskId are 0),
  // so the bound ids from panel state must carry the START row -- both its
  // meta (already rendering 'project · task') and its target, since that
  // target is what startFromCommand submits to Toggl.
  const rows = Model.commandRows("Reviewing PRs", projects, tasks, [], [], [], Date.now(), 1, 10)
  const start = rows.filter((r) => r.kind === "start")[0]
  assert.equal(start.meta, "acme · backend")
  assert.equal(start.target.projectId, 1)
  assert.equal(start.target.taskId, 10)
  assert.equal(start.label, start.target.description, "the invariant holds even for a cloned target")
})

test("commandRows: bound ids also carry the START row's meta inside the @ branch", () => {
  // hasAt short-circuits to PROJ rows only, but the START row itself is
  // pushed before that branch runs, so a bound project must still show in
  // its meta even while a fresh, unrelated @fragment is being typed.
  const rows = Model.commandRows("refactor @somethingnew", projects, tasks, [], [], [], Date.now(), 1, 10)
  const start = rows.filter((r) => r.kind === "start")[0]
  assert.equal(start.meta, "acme · backend")
})

test("commandRows: a name typed out exactly still resolves its own ids -- bound ids of 0 do not override it", () => {
  const rows = Model.commandRows("refactor @acme/backend", projects, tasks, [], [], [], Date.now(), 0, 0)
  const start = rows.filter((r) => r.kind === "start")[0]
  assert.equal(start.target.projectId, 1)
  assert.equal(start.target.taskId, 10)
})

test("commandRows: omitting the two new trailing parameters reproduces today's rows exactly", () => {
  const entries = [entry({ id: 1, description: "Reviewing PRs" })]
  const blocks = [block({ label: "Reviewing PRs", start: "2026-09-04T11:50:00.000Z", seconds: 3000, state: "pending" })]
  const now = Date.now()
  const omitted = Model.commandRows("Reviewing", projects, tasks, [], entries, blocks, now)
  const explicitZero = Model.commandRows("Reviewing", projects, tasks, [], entries, blocks, now, 0, 0)
  assert.deepEqual(omitted, explicitZero)

  const atOmitted = Model.commandRows("refactor @acme/backend", projects, tasks, [], [], [], now)
  const atExplicitZero = Model.commandRows("refactor @acme/backend", projects, tasks, [], [], [], now, 0, 0)
  assert.deepEqual(atOmitted, atExplicitZero)
})

// --- Fix round 1 (review findings 2 and 6): the /frag trigger is a leading
// sigil, not a substring, and TASK rows never suppress CONT/BLOCK ---

test("commandRows: an ordinary slash in the last token is NOT a task selector -- a date, a path, an unfinished word -- and the CONT row it would have matched still surfaces", () => {
  // Each of these is spec's own list of everyday false positives for the
  // superseded "contains" reading. A task named "Backend" is deliberately
  // present and WOULD have matched the old "a/b" -> taskFrag "b" extraction
  // (a word-prefix hit), so this also proves the trigger itself changed,
  // not just that these particular fragments happen to score 0.
  const boundProjects = [Model.normalizeProject({ id: 700, name: "Northwind Venture", active: true })]
  const boundTasks = [Model.normalizeTask({ id: 70, project_id: 700, name: "Backend", active: true })]
  const cases = [
    { text: "meeting 9/3", description: "Meeting 9/3 sync" },
    { text: "update docs/readme", description: "Update docs/readme notes" },
    { text: "fix the a/b", description: "Fix the a/b testing rollout" },
  ]
  cases.forEach(function(c) {
    const entries = [entry({ id: 1, description: c.description })]
    const rows = Model.commandRows(c.text, boundProjects, boundTasks, [], entries, [], Date.now(), 700, 0)
    assert.deepEqual(rows.map((r) => r.kind), ["start", "continue"], c.text + " -- a spurious TASK row, or a swallowed CONT row, both show up here")
  })
})

test("commandRows: a bound project's /frag TASK rows coexist with CONT and BLOCK -- one kind never replaces another", () => {
  // "ph2" -> "Phase 2 Test Report" is R-S's own validated example (a
  // subsequence match, the lowest tier, but still non-zero). Both a leading
  // "/ph2" and "notes /ph2" reach the same task via the same trailing
  // fragment; both must show the TASK row AND the matching CONT/BLOCK rows
  // in the same result -- this is the assertion that fails before the fix
  // (the early return swallowed continue/block) and passes after.
  const boundProjects = [Model.normalizeProject({ id: 700, name: "Northwind Venture", active: true })]
  const boundTasks = [Model.normalizeTask({ id: 71, project_id: 700, name: "Phase 2 Test Report", active: true })]
  const entries = [entry({ id: 1, description: "Notes /ph2 review" })]
  const blocks = [block({ label: "Notes /ph2 review", state: "pending" })]

  const bare = Model.commandRows("/ph2", boundProjects, boundTasks, [], entries, blocks, Date.now(), 700, 0)
  assert.deepEqual(bare.map((r) => r.kind), ["start", "task", "continue", "block"], "the raw '/ph2' token IS the (unresolved) description text, so START still appears alongside task, continue and block")
  assert.equal(bare[1].label, "Phase 2 Test Report")
  // F5: the START row must not submit the raw task-selector token as the
  // entry's description -- Enter here used to create a Toggl entry
  // literally described "/ph2" (the same key that just bound the
  // project). With nothing else typed, stripping it leaves nothing, so
  // this row exists only because a project is bound (F6).
  assert.equal(bare[0].label, "", "the /frag token must be stripped from the START row's label, mirroring @'s own stripping")
  assert.equal(bare[0].label, bare[0].target.description, "the invariant holds even when the /frag strips the label to empty")

  const withWords = Model.commandRows("notes /ph2", boundProjects, boundTasks, [], entries, blocks, Date.now(), 700, 0)
  assert.deepEqual(withWords.map((r) => r.kind), ["start", "task", "continue", "block"], "with more description ahead of the fragment, the same coexisting set still holds")
  assert.equal(withWords[1].label, "Phase 2 Test Report")
  assert.equal(withWords[0].label, "notes", "F5: the /frag token must be stripped from the START row's label, not submitted as part of the description")
})


// --- Stage 3b fix round 2: D1 (empty fragment browses, doesn't rank
// nothing), D3 (the bind/clear state machine can't stick) ---

test("commandRows: a bare @ browses ALL active projects, name-ordered and capped at 8 (D1)", () => {
  // Before this fix, scoreMatch("", name) staying 0 (correctly -- other
  // callers rely on it) meant rankProjects filtered an empty query down to
  // nothing: a bare "@" ranked 0 PROJ rows against the user's real 25 active
  // projects, where typing one more character ranked 8. There was no way to
  // browse -- you had to already know the name you were looking for.
  const names = ["Zulu", "Mike", "Alpha", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet"]
  const many = names.map((name, i) => Model.normalizeProject({ id: 800 + i, name: name, active: true }))
  const rows = Model.commandRows("@", many, [], [], [], [], Date.now())
  const projRows = rows.filter((r) => r.kind === "project")
  assert.equal(projRows.length, 8, "capped at the guide's 8-row PROJ limit, same as a scored match")
  assert.deepEqual(projRows.map((r) => r.target.name), ["Alpha", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet"], "name order, not insertion order or an invented popularity heuristic")
})

test("commandRows: a bare /frag browses ALL the bound project's active tasks, name-ordered and capped at 8 (D1)", () => {
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const names = ["Zulu Task", "Mike Task", "Alpha Task", "Delta Task", "Echo Task", "Foxtrot Task", "Golf Task", "Hotel Task", "India Task", "Juliet Task"]
  const manyTasks = names.map((name, i) => Model.normalizeTask({ id: 600 + i, project_id: 500, name: name, active: true }))
  const rows = Model.commandRows("notes /", boundProjects, manyTasks, [], [], [], Date.now(), 500, 0)
  const taskRows = rows.filter((r) => r.kind === "task")
  assert.equal(taskRows.length, 8, "capped at 8, same as a scored match")
  assert.deepEqual(taskRows.map((r) => r.target.name), ["Alpha Task", "Delta Task", "Echo Task", "Foxtrot Task", "Golf Task", "Hotel Task", "India Task", "Juliet Task"])
})

test("commandRows: a bare / against the user's real task-list shape (exactly 2 active tasks) browses both", () => {
  // The measured real-workspace case from the fix-round report: a bound
  // project with exactly 2 active tasks used to show 0 TASK rows for a bare
  // "/", which is exactly the "task list of 2 you can't browse" absurdity.
  const boundProjects = [Model.normalizeProject({ id: 500, name: "Northwind Venture", active: true })]
  const boundTasks = [
    Model.normalizeTask({ id: 50, project_id: 500, name: "Onsite Test Plan", active: true }),
    Model.normalizeTask({ id: 51, project_id: 500, name: "Test Report", active: true }),
  ]
  const rows = Model.commandRows("notes /", boundProjects, boundTasks, [], [], [], Date.now(), 500, 0)
  const taskRows = rows.filter((r) => r.kind === "task")
  assert.deepEqual(taskRows.map((r) => r.target.name), ["Onsite Test Plan", "Test Report"])
})

// --- Final review fix wave: F4 (@ is a leading sigil, not a substring),
// F6 (a bound project is visible even with nothing typed), F8 (a #tag or
// $ must not suppress the CONT/BLOCK query) ---

test("commandRows: an @ that is not the LAST token's leading character is not a project browse (F4)", () => {
  // Mirrors the three tests fix round 1 gave "/" (meeting 9/3, docs/readme,
  // fix the a/b) -- @ never had its own equivalent, and this is exactly
  // the gap that let "standup @ 9am" browse every active project.
  const cases = ["standup @ 9am", "email bob@acme.com about refactor", "meeting bob@acme.com re: sync"]
  cases.forEach(function(text) {
    const rows = Model.commandRows(text, projects, tasks, [], [], [], Date.now())
    assert.equal(rows.filter((r) => r.kind === "project").length, 0, text + " -- @ is not the last token's leading character, so it must not rank PROJ rows")
  })
})

test("commandRows: an email address mid-description does not suppress CONT/BLOCK (F3+F4 together)", () => {
  // Before the fix, hasAt was found by lastIndexOf("@") anywhere in the
  // text, so this measured failure: zero PROJ rows matched "acme.com",
  // and the early return (F3) still fired, leaving only the START row.
  const description = "email bob@acme.com about refactor"
  const entries = [entry({ id: 1, description: description })]
  const blocks = [block({ label: description, state: "pending" })]
  const rows = Model.commandRows(description, projects, tasks, [], entries, blocks, Date.now())
  assert.equal(rows.filter((r) => r.kind === "project").length, 0, "an embedded @ must not browse projects")
  assert.ok(rows.some((r) => r.kind === "continue"), "an embedded @ must not suppress the CONT match")
  assert.ok(rows.some((r) => r.kind === "block"), "an embedded @ must not suppress the BLOCK match")
})

test("stripAtFragment: strips only a trailing leading-sigil @token, never a substring @ (F4)", () => {
  assert.equal(Model.stripAtFragment("meeting @acme"), "meeting ")
  assert.equal(Model.stripAtFragment("@acme"), "")
  assert.equal(
    Model.stripAtFragment("email bob@acme.com about refactor"),
    "email bob@acme.com about refactor",
    "an @ that is not the last token's leading character must be left untouched -- this used to come back as " +
    "'email bob about refactor', silently deleting the rest of the address (F4)"
  )
  assert.equal(Model.stripAtFragment("standup @ 9am"), "standup @ 9am", "a bare @ mid-sentence is not the last token")
  assert.equal(Model.stripAtFragment("no at sign here"), "no at sign here")
})

test("stripSlashFragment: strips the trailing '/...' run, whatever precedes the slash", () => {
  // Unlike stripAtFragment above, this is NOT leading-sigil-gated (out of
  // scope for F4, which named only Model.js:873-874/:570-575) -- it is
  // only ever called from bindTask, which only fires on Enter for an
  // already-rendered TASK row, and commandRows only ever renders one when
  // the last token's FIRST character is "/" (its own leading-sigil rule,
  // Model.js:933). So a trailing slash that is embedded mid-token, like
  // "9/3", is never actually reachable here in practice -- documented,
  // not "fixed", since nothing calls it that way.
  assert.equal(Model.stripSlashFragment("notes /back"), "notes ")
  assert.equal(Model.stripSlashFragment("meeting 9/3"), "meeting 9")
})

test("commandRows: a bound project surfaces a START row even with nothing typed (F6) -- otherwise the binding is invisible the instant it lands", () => {
  // The normal binding flow lands exactly here: Enter on a PROJ row calls
  // Model.bindProject, which strips the @token down to "" (spec 6.5).
  // Before F6 there was no START row at all for empty text, so the panel
  // showed only CONT/BLOCK rows with nothing at all naming the project
  // that is, in fact, now bound.
  const rows = Model.commandRows("", projects, tasks, [], [], [], Date.now(), 1, 10)
  const start = rows.filter((r) => r.kind === "start")[0]
  assert.ok(start, "a bound project must still produce a START row when the description is empty")
  assert.equal(start.label, "", "nothing was typed, so the label stays empty -- no new visual element, per the guide")
  assert.equal(start.label, start.target.description, "the invariant holds even for an empty label")
  assert.equal(start.meta, "acme · backend", "the bound project/task is the only trace of the binding while the line is empty")
  assert.equal(start.target.projectId, 1)
  assert.equal(start.target.taskId, 10)
})

test("commandRows: with nothing bound and nothing typed, still no START row", () => {
  const rows = Model.commandRows("", projects, tasks, [], [], [], Date.now())
  assert.equal(rows.filter((r) => r.kind === "start").length, 0)
})

test("commandRows: a #tag or bare $ does not suppress the CONT/BLOCK query (F8)", () => {
  const entries = [entry({ id: 1, description: "Refactor onboarding notes" })]
  const blocks = [block({ label: "Refactor day segmentation", state: "pending" })]
  const plain = Model.commandRows("refactor", projects, tasks, [], entries, blocks, Date.now())
  assert.ok(plain.some((r) => r.kind === "continue") && plain.some((r) => r.kind === "block"), "sanity: the fixture itself matches with no sigil present")

  const tagged = Model.commandRows("refactor #work", projects, tasks, [], entries, blocks, Date.now())
  assert.ok(tagged.some((r) => r.kind === "continue"), "adding a #tag must not remove the CONT match")
  assert.ok(tagged.some((r) => r.kind === "block"), "adding a #tag must not remove the BLOCK match")

  const billed = Model.commandRows("refactor $", projects, tasks, [], entries, blocks, Date.now())
  assert.ok(billed.some((r) => r.kind === "continue"), "adding a bare $ must not remove the CONT match")
  assert.ok(billed.some((r) => r.kind === "block"), "adding a bare $ must not remove the BLOCK match")
})

test("D3: binding twice with no text change in between still lets a later clear zero both bindings", () => {
  // The Panel.qml design this replaced used a flag, set before a bind's own
  // token-removal and consumed by a commandTextChanged handler, to keep
  // that removal (commandText -> possibly "") from being mistaken for the
  // user clearing the line. That flag could stick: QML skips the change
  // notification entirely when the property's new value equals the one
  // already in place, which happens whenever a bind's resulting text is
  // IDENTICAL to what was already there -- exactly the "no text left to
  // strip" case exercised below -- so the flag would never be consumed,
  // and the NEXT genuine clear-to-empty would be silently swallowed.
  // Model.bindProject/bindTask replace the flag entirely: each returns its
  // own final ids directly, so there is nothing to leak across calls.
  const acme = Model.normalizeProject({ id: 1, name: "acme", active: true })
  const zeta = Model.normalizeProject({ id: 2, name: "zeta", active: true })

  const first = Model.bindProject("meeting @acme", acme)
  assert.equal(first.commandText, "meeting ")
  assert.equal(first.boundProjectId, 1)
  assert.equal(first.boundTaskId, 0)

  // The panel's generic commandTextChanged watcher would also run on this
  // same change (it can't tell a bind's own edit from any other) -- confirm
  // it does not undo the bind, since the text is not "".
  const afterFirst = Model.bindingsAfterTextEdit(first.commandText, first.boundProjectId, first.boundTaskId)
  assert.equal(afterFirst.boundProjectId, 1, "unaffected -- text is not empty")

  // Second bind, with NO intervening text edit, whose result is the exact
  // same string as before (no "@" left to strip) -- the case where the
  // property system would skip the change notification.
  const second = Model.bindProject(first.commandText, zeta)
  assert.equal(second.commandText, first.commandText, "nothing left to strip -- identical to the prior value")
  assert.equal(second.boundProjectId, 2, "the second bind's own id wins even though the text did not change")

  // A genuine clear -- the user selects the line and deletes it -- must
  // still zero both bindings afterward.
  const cleared = Model.bindingsAfterTextEdit("", second.boundProjectId, second.boundTaskId)
  assert.equal(cleared.boundProjectId, 0)
  assert.equal(cleared.boundTaskId, 0)
})

test("bindProject/bindTask: task never outlives a rebound project, and a bound project survives a task bind", () => {
  const acme = Model.normalizeProject({ id: 1, name: "acme", active: true })
  const backend = Model.normalizeTask({ id: 10, project_id: 1, name: "backend", active: true })

  const withTask = Model.bindTask("notes /back", 1, backend)
  assert.equal(withTask.boundProjectId, 1, "carried over unchanged, not re-derived")
  assert.equal(withTask.boundTaskId, 10)
  assert.equal(withTask.commandText, "notes ")

  const rebound = Model.bindProject(withTask.commandText + "@acme", acme)
  assert.equal(rebound.boundProjectId, 1)
  assert.equal(rebound.boundTaskId, 0, "a new project bind always clears the task")
})

// ---- stage 4: day-scope row states, summary, facts, filter -----------------

// The guide's own worked block (design-guide.html 03): 2h25 active over a 2h41
// wall, 16m idle removed, 63 switches, longest run 11m.
const guideBlock = {
  start: "2026-09-03T09:20:00Z", end: "2026-09-03T12:01:00Z",
  seconds: 8712, span_seconds: 9660, idle_seconds: 948, fragments: 63, longest_fragment_seconds: 660,
  label: "Refactor day segmentation",
  topics: [{ name: "segment_blocks — toggl_api.py", seconds: 4320 }],
  apps: [{ name: "dev.zed.Zed", seconds: 5640 }],
  domains: [{ name: "bitbucket.org", seconds: 1740 }],
  timeline: [{ offset: 0, seconds: 840, topic: "x", idle: false }, { offset: 840, seconds: 60, topic: "", idle: true }],
}

test("prepareBlocks carries the full 10.3 shape and both drawer flags", () => {
  const b = Model.prepareBlocks([guideBlock], [])[0]
  assert.equal(b.idleSeconds, 948)
  assert.equal(b.fragments, 63)
  assert.equal(b.longestFragmentSeconds, 660)
  assert.deepEqual(b.apps, [{ name: "dev.zed.Zed", seconds: 5640 }])
  assert.deepEqual(b.domains, [{ name: "bitbucket.org", seconds: 1740 }])
  assert.equal(b.timeline.length, 2)
  assert.equal(b.timeline[1].idle, true)
  assert.equal(b.inspecting, false)
  assert.equal(b.editing, false)
  assert.equal(b.guessed, false)
  assert.equal(b.skipped, false)
  assert.equal("expanded" in b, false, "the single accordion flag is gone; two drawers replace it")
})

test("prepareBlocks accepts the old bare-string apps shape and derives idle when absent", () => {
  const b = Model.prepareBlocks([{ seconds: 300, span_seconds: 400, apps: ["zen", "Slack"], topics: [] }], [])[0]
  assert.deepEqual(b.apps, [{ name: "zen", seconds: 0 }, { name: "Slack", seconds: 0 }])
  assert.equal(b.idleSeconds, 100)
})

test("blockState covers all seven states in precedence order", () => {
  const base = () => Model.prepareBlocks([guideBlock], [])[0]
  let b = base(); assert.equal(Model.blockState(b), "unassigned", "no project yet")
  b = base(); b.projectId = 1; assert.equal(Model.blockState(b), "ready")
  b = base(); b.projectId = 1; b.guessed = true; assert.equal(Model.blockState(b), "guessed")
  b = base(); b.projectId = 1; b.skipped = true; assert.equal(Model.blockState(b), "skipped")
  b = base(); b.projectId = 1; b.busy = true; b.skipped = true; assert.equal(Model.blockState(b), "inflight", "busy outranks everything")
  b = Model.prepareBlocks([{ ...guideBlock, applied: true, conflict: { id: 7 } }], [{ id: 7, created_with: "omarchy-toggl-track/day" }])[0]
  assert.equal(Model.blockState(b), "applied")
  b = Model.prepareBlocks([{ ...guideBlock, applied: true, conflict: { id: 8 } }], [{ id: 8, created_with: "web" }])[0]
  assert.equal(Model.blockState(b), "conflict")
  b.projectId = 1; assert.equal(Model.blockState(b), "conflict", "a conflict cannot be made ready from here")
})

test("blockGlyph: applied and conflict never share a glyph", () => {
  assert.equal(Model.blockGlyph("applied"), "✓")
  assert.equal(Model.blockGlyph("conflict"), "▲")
  assert.equal(Model.blockGlyph("ready"), "●")
  assert.equal(Model.blockGlyph("guessed"), "●", "the ~ marker carries guessed, not the glyph")
  assert.equal(Model.blockGlyph("unassigned"), "◌")
  assert.equal(Model.blockGlyph("inflight"), "◍")
  assert.equal(Model.blockGlyph("skipped"), "⌫")
})

test("blockReady: a guess is never ready, a skipped row still is", () => {
  const b = Model.prepareBlocks([guideBlock], [])[0]
  b.projectId = 1
  assert.equal(Model.blockReady(b), true)
  b.guessed = true
  assert.equal(Model.blockReady(b), false, "spec 7.5: unconfirmed guesses are never written")
  b.guessed = false; b.skipped = true
  assert.equal(Model.blockReady(b), true, "R-N: skip is a dismissal, not a lock")
  b.skipped = false; b.description = "   "
  assert.equal(Model.blockReady(b), false)
})

test("blockSummary counts guesses as READY on the count line but not as applicable", () => {
  const blocks = Model.prepareBlocks([guideBlock, guideBlock, guideBlock, guideBlock], [])
  blocks[0].projectId = 1
  blocks[1].projectId = 1; blocks[1].guessed = true
  blocks[2].skipped = true
  const s = Model.blockSummary(blocks)
  assert.equal(s.ready, 2, "guide 02 renders both ● rows under READY")
  assert.equal(s.applicable, 1, "⇧↵ applies only the confirmed one")
  assert.equal(s.unassigned, 1)
  assert.equal(s.skipped, 1)
  assert.equal(s.totalSeconds, 8712 * 4, "R-N: a skipped block still counts toward the day")
})

test("countLine renders the guide's count line and omits zero categories", () => {
  assert.equal(Model.countLine({ applied: 2, ready: 2, unassigned: 1, conflicts: 1, skipped: 0 }), "2 APPLIED · 2 READY · 1 UNASSIGNED · 1 CONFLICT")
  assert.equal(Model.countLine({ applied: 0, ready: 3, unassigned: 0, conflicts: 0, skipped: 0 }), "3 READY")
})

test("blockMeta gives applied and conflict different trailing text", () => {
  const projects = [Model.normalizeProject({ id: 1, name: "acme", active: true })]
  const tasks = [Model.normalizeTask({ id: 10, project_id: 1, name: "backend", active: true })]
  let b = Model.prepareBlocks([guideBlock], [])[0]
  assert.equal(Model.blockMeta(b, projects, tasks), "— unassigned —")
  b.projectId = 1; b.taskId = 10
  assert.equal(Model.blockMeta(b, projects, tasks), "acme · backend")
  b.busy = true
  assert.equal(Model.blockMeta(b, projects, tasks), "writing…")
  b = Model.prepareBlocks([{ ...guideBlock, applied: true, conflict: { id: 8 } }], [{ id: 8, created_with: "web" }])[0]
  assert.equal(Model.blockMeta(b, projects, tasks), "conflict · manual")
})

test("blockFacts reproduces the guide's facts line", () => {
  const b = Model.prepareBlocks([guideBlock], [])[0]
  assert.deepEqual(Model.blockFacts(b), ["2h25 active", "2h41 wall", "16m idle removed", "63 switches", "longest run 11m"])
  const quiet = Model.prepareBlocks([{ seconds: 600, span_seconds: 600, fragments: 1, longest_fragment_seconds: 600 }], [])[0]
  assert.deepEqual(Model.blockFacts(quiet), ["0h10 active", "0h10 wall", "1 switches", "longest run 10m"], "no idle line when nothing was removed")
})

test("blockFilter narrows by label, topic, app or domain, case-insensitively", () => {
  const blocks = Model.prepareBlocks([guideBlock, { ...guideBlock, label: "Standup", topics: [], apps: [{ name: "Slack", seconds: 1 }], domains: [] }], [])
  assert.equal(Model.blockFilter(blocks, "").length, 2)
  assert.equal(Model.blockFilter(blocks, "REFACTOR").length, 1)
  assert.equal(Model.blockFilter(blocks, "zed")[0].label, "Refactor day segmentation", "matches an app name")
  assert.equal(Model.blockFilter(blocks, "bitbucket").length, 1, "matches a domain")
  assert.equal(Model.blockFilter(blocks, "slack")[0].label, "Standup")
  assert.equal(Model.blockFilter(blocks, "nothing-here").length, 0)
})

test("paletteIndex is stable, case-insensitive and bounded", () => {
  assert.equal(Model.paletteIndex("Slack", 8), Model.paletteIndex("slack", 8), "same name, same colour, whatever the case")
  assert.equal(Model.paletteIndex("Slack", 8), Model.paletteIndex("Slack", 8))
  for (const name of ["Zed", "zen", "Slack", "bitbucket.org", "", "x"]) {
    const idx = Model.paletteIndex(name, 8)
    assert.ok(idx >= 0 && idx < 8, `${name} -> ${idx}`)
  }
  // Distinct enough to be useful: the guide's own four apps spread over more than one slot.
  const slots = new Set(["dev.zed.Zed", "zen", "Slack", "bitbucket.org"].map((n) => Model.paletteIndex(n, 8)))
  assert.ok(slots.size >= 3, "four names landing on one or two colours would defeat the palette")
})

// ---- stage 5: calendar range math and axis bounds --------------------------
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

test("calendarFilter narrows entries by project, tag or description, empty keeps all", () => {
  const entries = [
    { description: "standup", project_name: "NW-091 Northwind Venturer", tags: ["meeting"] },
    { description: "refactor", project_name: "Research and Development", tags: [] },
  ]
  assert.equal(Model.calendarFilter(entries, "").length, 2)
  assert.equal(Model.calendarFilter(entries, "northwind")[0].description, "standup")
  assert.equal(Model.calendarFilter(entries, "MEETING").length, 1)
  assert.equal(Model.calendarFilter(entries, "refactor").length, 1)
  assert.equal(Model.calendarFilter(entries, "zzz").length, 0)
})

// ---- stage 6: local classifier payloads and guess guard -----------------------
const GUESS_PROJECTS = [
  { id: 84, name: "NW-084 Northwind Venturer NX8 Deployment", active: true },
  { id: 91, name: "NW-091 Northwind Venturer Upgrade Testing & Validation", active: true },
  { id: 7, name: "Wildharbour Monitoring", active: true },
  { id: 8, name: "Archived Thing", active: false },
]

test("helpSections puts the current scope first and the shared keys last", () => {
  for (const [scope, title] of [["timer", "Timer"], ["day", "Day"], ["cal", "Calendar"]]) {
    const sections = Model.helpSections(scope)
    assert.equal(sections.length, 2)
    assert.equal(sections[0].title, title)
    assert.equal(sections[1].title, "Anywhere")
    for (const section of sections) {
      assert.ok(section.keys.length > 0)
      for (const row of section.keys) assert.equal(row.length, 2)
    }
  }
  // An unknown scope falls back to the timer's keys rather than rendering blank.
  assert.equal(Model.helpSections("nonsense")[0].title, "Timer")
})

test("helpSections documents every scope switch and the help key itself", () => {
  const shared = Model.helpSections("day")[1].keys.map((row) => row[0])
  for (const key of ["^t", "^d", "^l", "esc"]) assert.ok(shared.includes(key), key + " missing")
  assert.ok(shared.some((key) => key.indexOf("?") >= 0), "help key missing")
})

test("descriptionCandidates lists model, history and title once each, best first", () => {
  const block = { label: "omarchy: toggl", modelDescription: "panel redesign work",
    history: [{ description: "past entry", score: 0.8 }, { description: "past entry", score: 0.4 }] }
  assert.deepEqual(Model.descriptionCandidates(block), [
    { text: "panel redesign work", source: "model" },
    { text: "past entry", source: "history" },
    { text: "omarchy: toggl", source: "title" },
  ])
  // A block with nothing but its title still offers that title.
  assert.deepEqual(Model.descriptionCandidates({ label: "only a title" }), [{ text: "only a title", source: "title" }])
  assert.deepEqual(Model.descriptionCandidates(null), [])
})

test("cycleDescription walks the candidates in both directions and wraps", () => {
  const block = { label: "title", description: "title", modelDescription: "model text",
    history: [{ description: "history text", score: 0.9 }], candidateIndex: 0 }
  assert.equal(Model.cycleDescription(block, 1).source, "history")
  assert.equal(block.description, "history text")
  assert.equal(Model.cycleDescription(block, 1).source, "title")
  assert.equal(Model.cycleDescription(block, 1).source, "model")
  assert.equal(Model.cycleDescription(block, -1).source, "title")
  assert.equal(block.guessed, true)
  assert.equal(Model.cycleDescription({ label: "" }, 1), null)
})

test("suggestionFor reports the candidate on screen and its source", () => {
  const block = { label: "title", description: "title", modelDescription: "model text",
    history: [], candidateIndex: 0, projectId: 7 }
  assert.deepEqual(Model.suggestionFor(block), { description: "model text", project_id: 7, source: "model" })
  Model.cycleDescription(block, 1)
  assert.deepEqual(Model.suggestionFor(block), { description: "title", project_id: 7, source: "title" })
  assert.equal(Model.suggestionFor({ label: "", description: "", projectId: 0 }).project_id, null)
})

test("prepareBlocks carries the backend's ranked project candidates", () => {
  const prepared = Model.prepareBlocks([{ start: "a", end: "b", seconds: 60, label: "l",
    projects: [{ project_id: 7, score: 0.8, prior: 0.6, similarity: 0.9 }] }], [])
  assert.equal(prepared[0].projects[0].project_id, 7)
  assert.equal(prepared[0].candidateIndex, 0)
  assert.equal(Model.prepareBlocks([{ start: "a", end: "b", seconds: 60, label: "l" }], [])[0].projects.length, 0)
})

test("historyGuessFor prefers the backend ranking over the nearest past record", () => {
  const block = { state: "pending", projectId: 0, guessed: false, label: "l", description: "l",
    history: [{ description: "past", project_id: 3, score: 0.9 }],
    projects: [{ project_id: 9, score: 0.7 }] }
  assert.equal(Model.historyGuessFor(block).projectId, 9)
  // Ranking alone still assigns a project even with no matching past record.
  const bare = { state: "pending", projectId: 0, guessed: false, label: "l", description: "l",
    history: [], projects: [{ project_id: 9, score: 0.7 }] }
  assert.equal(Model.historyGuessFor(bare).projectId, 9)
})

test("historyGuessFor takes the best past record at score >= 0.5, else nothing", () => {
  const block = { state: "pending", projectId: 0, guessed: false, label: "omarchy: x", description: "omarchy: x",
    history: [{ description: "omarchy-toggl-track panel redesign", project_id: 7, task_id: 3, score: 0.62, seen: 4 }] }
  assert.deepEqual(Model.historyGuessFor(block), { description: "omarchy-toggl-track panel redesign", projectId: 7, taskId: 3, guessed: true })
  assert.equal(Model.historyGuessFor({ ...block, history: [{ description: "weak", project_id: 7, score: 0.49 }] }), null)
  assert.equal(Model.historyGuessFor({ ...block, history: [] }), null)
})

test("historyGuessFor never overrides a touched, assigned, guessed or applied block", () => {
  const base = { state: "pending", projectId: 0, guessed: false, label: "l", description: "l",
    history: [{ description: "past", project_id: 7, score: 0.9 }] }
  assert.equal(Model.historyGuessFor({ ...base, description: "typed" }), null)
  assert.equal(Model.historyGuessFor({ ...base, projectId: 5 }), null)
  assert.equal(Model.historyGuessFor({ ...base, guessed: true }), null)
  assert.equal(Model.historyGuessFor({ ...base, state: "applied" }), null)
})

test("applyHistoryGuesses marks blocks in place and prepareBlocks carries history through", () => {
  const prepared = Model.prepareBlocks([{ start: "2026-09-04T09:00:00Z", end: "2026-09-04T10:00:00Z", seconds: 3600, label: "l", topics: [],
    history: [{ description: "past label", project_id: 7, score: 0.8, seen: 2 }] }], [])
  assert.equal(prepared[0].history.length, 1)
  assert.equal(Model.applyHistoryGuesses(prepared), 1)
  assert.equal(prepared[0].description, "past label"); assert.equal(prepared[0].projectId, 7); assert.equal(prepared[0].guessed, true)
  assert.equal(Model.prepareBlocks([{ start: "a", end: "b", seconds: 1, label: "l" }], [])[0].history.length, 0)
})

test("guessProjectFromTopics matches a project code inside a topic", () => {
  const block = { state: "pending", projectId: 0, guessed: false, label: "omarchy", topics: [{ name: "nw-084-nven-nx8-deployment", seconds: 600 }] }
  assert.deepEqual(Model.guessProjectFromTopics(block, GUESS_PROJECTS), { projectId: 84, confidence: 0.9 })
})

test("guessProjectFromTopics matches a distinctive word unique to one project, never a shared or stop word", () => {
  const block = { state: "pending", projectId: 0, guessed: false, label: "WildHarbour Weekly Report", topics: [] }
  assert.deepEqual(Model.guessProjectFromTopics(block, GUESS_PROJECTS), { projectId: 7, confidence: 0.6 })
  const shared = { state: "pending", projectId: 0, guessed: false, label: "Northwind Venturer notes", topics: [] }
  assert.equal(Model.guessProjectFromTopics(shared, GUESS_PROJECTS), null)
  const stop = { state: "pending", projectId: 0, guessed: false, label: "deployment testing", topics: [] }
  assert.equal(Model.guessProjectFromTopics(stop, GUESS_PROJECTS), null)
})

test("guessProjectFromTopics resolves codes in topic order and ignores apps and domains", () => {
  const projects = GUESS_PROJECTS.concat([{ id: 92, name: "NW-092-H370 Wild Harbour", active: true }])
  const block = { state: "pending", projectId: 0, guessed: false, label: "omarchy", topics: [
    { name: "nw-084-nven-nx8-deployment", seconds: 900 }, { name: "NW-092 report", seconds: 300 }, { name: "NW-092 notes", seconds: 200 }] }
  assert.deepEqual(Model.guessProjectFromTopics(block, projects), { projectId: 84, confidence: 0.9 })
  const generic = { state: "pending", projectId: 0, guessed: false, label: "System Settings", topics: [], apps: [{ name: "wildharbour-app" }], domain: "wildharbour.example" }
  assert.equal(Model.guessProjectFromTopics(generic, projects.concat([{ id: 9, name: "RAID Based System Improvement", active: true }])), null)
})

test("guessProjectFromTopics leaves touched, applied, guessed and archived-only matches alone", () => {
  const base = { state: "pending", projectId: 0, guessed: false, label: "nw-084 work", topics: [] }
  assert.equal(Model.guessProjectFromTopics({ ...base, projectId: 5 }, GUESS_PROJECTS), null)
  assert.equal(Model.guessProjectFromTopics({ ...base, guessed: true }, GUESS_PROJECTS), null)
  assert.equal(Model.guessProjectFromTopics({ ...base, state: "applied" }, GUESS_PROJECTS), null)
  assert.equal(Model.guessProjectFromTopics({ ...base, label: "archived thing" }, GUESS_PROJECTS), null)
})

test("applyProjectGuesses marks matched blocks guessed in place and counts them", () => {
  const blocks = [
    { state: "pending", projectId: 0, guessed: false, label: "nw-091 checks", topics: [] },
    { state: "pending", projectId: 0, guessed: false, label: "lunch", topics: [] },
  ]
  assert.equal(Model.applyProjectGuesses(blocks, GUESS_PROJECTS), 1)
  assert.equal(blocks[0].projectId, 91); assert.equal(blocks[0].guessed, true)
  assert.equal(blocks[1].projectId, 0); assert.equal(blocks[1].guessed, false)
})

test("classifyGuessFor ignores a guess that only echoes the label with no project", () => {
  const block = { state: "pending", label: "omarchy: toggl", description: "omarchy: toggl", projectId: 0 }
  assert.equal(Model.classifyGuessFor(block, { description: "omarchy: toggl", project_id: null }), null)
  assert.deepEqual(
    Model.classifyGuessFor(block, { description: "omarchy: toggl", project_id: 7 }),
    { description: "omarchy: toggl", projectId: 7, guessed: true })
})

test("classifyBlockPayload sends only pending blocks, normalised", () => {
  const blocks = [
    { state: "pending", label: "vim", topics: [{ name: "vim", seconds: 600 }], apps: [{ name: "dev.zed.Zed", seconds: 600 }], domain: "bitbucket.org", seconds: 600 },
    { state: "applied", label: "done", topics: [], apps: [], domain: "", seconds: 300 },
    { state: "pending", guessed: true, label: "guessed already", topics: [], apps: [], domain: "", seconds: 300 },
  ]
  assert.deepEqual(Model.classifyBlockPayload(blocks), [
    { index: 0, label: "vim", start: "", topics: [{ name: "vim", seconds: 600 }], apps: [{ name: "dev.zed.Zed", seconds: 600 }], domains: [{ name: "bitbucket.org", seconds: 0 }], seconds: 600 },
  ])
})

test("classifyGuessFor takes the project the backend decided, and never re-judges it", () => {
  // Ruling R-AO retired the grounding check: the project no longer comes from
  // the model at all, so there is nothing for Model.js to second-guess.
  const block = { state: "pending", projectId: 0, guessed: false, label: "omarchy: nx8-controls",
    description: "omarchy: nx8-controls", topics: [] }
  assert.deepEqual(Model.classifyGuessFor(block, { description: "PLC firmware debugging", project_id: 84 }),
    { description: "PLC firmware debugging", projectId: 84, guessed: true })
  assert.equal(block.modelDescription, "PLC firmware debugging")
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

test("enrichment replaces only an untouched provisional guess", () => {
  const block = {state: "pending", busy: false, label: "panel", description: "previous wording",
    projectId: 7, taskId: 0, guessed: true, topics: [], apps: [], domains: [],
    history: [{description: "previous wording", project_id: 7, score: 1}]}
  const payload = Model.enrichmentPayload([block])[0]
  assert.equal(payload.index, 0)
  assert.equal(Model.mergeEnrichment(block, {signature: payload.signature, projects: [{project_id: 8}]},
    {description: "Improve panel layout", project_id: 8}, []), true)
  assert.equal(block.projectId, 8)
  assert.equal(block.description, "previous wording")
  assert.equal(block.modelDescription, "Improve panel layout")
})
test("enrichment rejects edits, restored text, applied and busy rows", () => {
  for (const change of [{description: "typed"}, {editRevision: 1}, {state: "applied"}, {busy: true}, {editing: true}]) {
    const block = {state: "pending", label: "panel", description: "panel", projectId: 0}
    const signature = Model.enrichmentSnapshot(block)
    Object.assign(block, change)
    const before = JSON.stringify(block)
    assert.equal(Model.mergeEnrichment(block, {signature, projects: [{project_id: 8}]}, null, []), false)
    assert.equal(JSON.stringify(block), before)
  }
})
test("enrichment payload preserves real indices and changed activity invalidates it", () => {
  const blocks = [{state: "applied"}, {state: "pending", label: "panel", description: "panel", topics: []}]
  const payload = Model.enrichmentPayload(blocks)
  assert.equal(payload.length, 1)
  assert.equal(payload[0].index, 1)
  blocks[1].topics.push({name: "new topic", seconds: 10})
  assert.equal(Model.mergeEnrichment(blocks[1], {signature: payload[0].signature}, null, []), false)
})

if (failures) {
  console.error(`\n${failures} failing`)
  process.exit(1)
}
console.log("\nall model checks passed")
