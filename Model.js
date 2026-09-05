.pragma library

function number(value, fallback) {
  var parsed = Number(value)
  return isFinite(parsed) ? parsed : fallback
}

function durationSeconds(entry, now) {
  if (!entry) return 0
  var start = new Date(entry.start || entry.started_at).getTime()
  if (!isFinite(start)) return number(entry.duration, 0)
  var end = entry.stop || entry.stopped_at ? new Date(entry.stop || entry.stopped_at).getTime() : now
  return Math.max(0, Math.floor((end - start) / 1000))
}

// A stopped entry's duration, or a running one's as of now. The calendar
// strips use this per entry; historical entries always have a stop.
function durationSecondsOf(entry) { return durationSeconds(entry, Date.now()) }

function formatDuration(seconds) {
  seconds = Math.max(0, Math.floor(number(seconds, 0)))
  var hours = Math.floor(seconds / 3600)
  var minutes = Math.floor((seconds % 3600) / 60)
  var secs = seconds % 60
  return (hours ? hours + ":" : "") + (hours ? String(minutes).padStart(2, "0") : minutes) + ":" + String(secs).padStart(2, "0")
}

function timerLabel(entry, now) { return entry ? formatDuration(durationSeconds(entry, now)) : "" }

function clockTime(isoValue) {
  var value = new Date(isoValue)
  if (!isFinite(value.getTime())) return "--:--"
  return String(value.getHours()).padStart(2, "0") + ":" + String(value.getMinutes()).padStart(2, "0")
}

function isoDate(value) {
  return value.getFullYear() + "-" + String(value.getMonth() + 1).padStart(2, "0") + "-" + String(value.getDate()).padStart(2, "0")
}

function todayDate() { return isoDate(new Date()) }

function shiftDate(dateValue, days) {
  var parts = String(dateValue || "").split("-")
  var value = parts.length === 3 ? new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])) : new Date()
  value.setDate(value.getDate() + (Number(days) || 0))
  return isoDate(value)
}

var DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
var MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
var MONTH_NAMES_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

function dayLabel(dateValue) {
  var parts = String(dateValue || "").split("-")
  if (parts.length !== 3) return String(dateValue || "")
  var value = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
  if (!isFinite(value.getTime())) return String(dateValue)
  return DAY_NAMES[value.getDay()] + " " + value.getDate() + " " + MONTH_NAMES[value.getMonth()] + " " + value.getFullYear()
}

function prepareBlocks(blocks, entries) {
  var byId = {}
  ;(entries || []).forEach(function(entry) { if (entry && entry.id !== undefined) byId[String(entry.id)] = entry })
  return (blocks || []).map(function(block) {
    var conflict = block.conflict || null
    var owner = conflict && byId[String(conflict.id)]
    var createdWith = String((owner && (owner.created_with || owner.createdWith)) || "")
    var seconds = number(block.seconds, 0)
    var span = number(block.span_seconds, seconds)
    return {
      start: block.start,
      end: block.end,
      seconds: seconds,
      spanSeconds: span,
      // idle_seconds is span - active (spec 10.3); derive it when the backend
      // omits it so older cached payloads still render the facts line.
      idleSeconds: number(block.idle_seconds, Math.max(0, span - seconds)),
      fragments: number(block.fragments, 0),
      longestFragmentSeconds: number(block.longest_fragment_seconds, 0),
      label: String(block.label || ""),
      topics: namedSeconds(block.topics),
      // apps changed from [String] to [{name, seconds}] (spec 10.3, the one
      // non-additive edit). Accept both so a stale cache still renders.
      apps: namedSeconds(block.apps),
      domains: namedSeconds(block.domains),
      domain: String(block.domain || ""),
      timeline: (block.timeline || []).map(function(tick) {
        return { offset: number(tick.offset, 0), seconds: number(tick.seconds, 0), topic: String(tick.topic || ""), idle: !!tick.idle }
      }),
      conflict: conflict,
      // Closest past records for a pending block (stage 7, ruling R-AK):
      // [{description, project_id, task_id, score, seen}], best first.
      history: Array.isArray(block.history) ? block.history : [],
      // Ranked project candidates from the backend (ruling R-AO): the usage
      // prior blended with embedding similarity. The model never votes here.
      projects: Array.isArray(block.projects) ? block.projects : [],
      // Which description candidate is showing; Tab walks the list.
      candidateIndex: 0,
      modelDescription: "",
      // Ours renders as applied; anyone else's overlap is a conflict to resolve.
      state: !block.applied ? "pending" : (createdWith.indexOf("omarchy-toggl-track") === 0 ? "applied" : "conflict"),
      createdWith: createdWith,
      description: String(block.label || ""),
      projectId: 0,
      taskId: 0,
      // Set by the classifier (stage 6). A guessed row renders "~" and is not
      // ready until the user touches it (spec 7.5).
      guessed: false,
      // Session-local dismissal (ruling R-N). Still counts toward the total.
      skipped: false,
      busy: false,
      failure: "",
      // Two independent drawers (spec 7.2). Either, both or neither may be open.
      inspecting: false,
      editing: false
    }
  })
}

// [{name, seconds}] from either that shape or a bare list of names.
function namedSeconds(items) {
  return (items || []).map(function(item) {
    if (typeof item === "string") return { name: item, seconds: 0 }
    return { name: String((item && item.name) || ""), seconds: number(item && item.seconds, 0) }
  })
}

// The seven row states of spec 7.1 plus R-N's skipped, in precedence order.
// busy wins over everything because it describes what is happening now;
// applied and conflict come from the server and cannot be changed here.
function blockState(block) {
  if (!block) return "unassigned"
  if (block.busy) return "inflight"
  if (block.state === "applied") return "applied"
  if (block.state === "conflict") return "conflict"
  if (block.skipped) return "skipped"
  if (!block.projectId || !String(block.description || "").trim()) return "unassigned"
  if (block.guessed) return "guessed"
  return "ready"
}

function blockGlyph(state) {
  return ({ applied: "\u2713", ready: "\u25cf", guessed: "\u25cf", unassigned: "\u25cc", conflict: "\u25b2", inflight: "\u25cd", skipped: "\u232b" })[state] || "\u25cf"
}

// Whether Enter may write this block. Spec 7.5: a guessed row is not ready
// until confirmed, so a batch apply can never write an unreviewed guess.
// Skipped rows stay applicable on purpose (R-N): skipping is a visual
// dismissal, not a lock, and Enter on one is an explicit choice.
function blockReady(block) {
  return !!block && block.state === "pending" && !block.busy && !block.guessed && !!block.projectId && String(block.description || "").trim().length > 0
}

function blockAlso(block, maxItems) {
  var topics = (block && block.topics) || []
  maxItems = Math.max(0, Number(maxItems) || 3)
  return topics.slice(1, 1 + maxItems).map(function(topic) { return topic.name }).filter(Boolean).join(" · ")
}

function blockSummary(blocks) {
  var total = 0, ready = 0, applicable = 0, unassigned = 0, applied = 0, conflicts = 0, skipped = 0
  ;(blocks || []).forEach(function(block) {
    // Every block counts toward the day, skipped ones included (R-N).
    total += number(block.seconds, 0)
    var state = blockState(block)
    if (state === "applied") { applied += 1; return }
    if (state === "conflict") { conflicts += 1; return }
    if (state === "skipped") { skipped += 1; return }
    if (state === "unassigned") { unassigned += 1; return }
    // "ready" and "guessed" both read as READY on the count line, which is
    // what the guide renders; only genuinely ready rows are applicable.
    ready += 1
    if (blockReady(block)) applicable += 1
  })
  return { totalSeconds: total, ready: ready, applicable: applicable, unassigned: unassigned, applied: applied, conflicts: conflicts, skipped: skipped }
}

// "2 APPLIED · 2 READY · 1 UNASSIGNED · 1 CONFLICT" -- the guide's count line.
// Zero categories are omitted; the guide only ever shows non-zero ones.
function countLine(summary) {
  var parts = []
  if (summary.applied) parts.push(summary.applied + " APPLIED")
  if (summary.ready) parts.push(summary.ready + " READY")
  if (summary.unassigned) parts.push(summary.unassigned + " UNASSIGNED")
  if (summary.conflicts) parts.push(summary.conflicts + " CONFLICT")
  if (summary.skipped) parts.push(summary.skipped + " SKIPPED")
  return parts.join(" \u00b7 ")
}

// The trailing text of a row, per state (guide 05). Applied and conflict
// must never look alike: they differ in glyph, colour AND this text.
function blockMeta(block, projects, tasks) {
  var state = blockState(block)
  if (state === "unassigned") return "\u2014 unassigned \u2014"
  if (state === "conflict") return "conflict \u00b7 manual"
  if (state === "inflight") return "writing\u2026"
  if (state === "skipped") return "skipped"
  return projectMeta(projects, tasks, block.projectId, block.taskId)
}

// The inspect drawer's facts line: active, wall, idle removed, switches,
// longest run. Durations at or over an hour are HhMM; under an hour they are
// bare minutes -- the guide mixes both on this one line (R-D2).
function blockFacts(block) {
  var facts = []
  facts.push(clockDuration(block.seconds) + " active")
  facts.push(clockDuration(block.spanSeconds) + " wall")
  if (block.idleSeconds > 0) facts.push(rowDuration(block.idleSeconds) + " idle removed")
  if (block.fragments > 0) facts.push(block.fragments + " switches")
  if (block.longestFragmentSeconds > 0) facts.push("longest run " + rowDuration(block.longestFragmentSeconds))
  return facts
}

// A stable slot in an n-colour palette for a topic, app or domain name, so
// the same name is the same colour in the timeline and in every bar list, and
// across days. djb2 over the lowercased name; pure and deterministic.
function paletteIndex(name, n) {
  n = Math.max(1, Number(n) || 8)
  var text = String(name || "").toLowerCase()
  var hash = 5381
  for (var i = 0; i < text.length; i++) hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0
  return Math.abs(hash) % n
}

// "filter blocks" (guide 02): the command line narrows the day list by
// label, description, topic, app or domain. Empty query keeps everything.
function blockFilter(blocks, query) {
  query = String(query || "").trim().toLowerCase()
  if (!query) return blocks || []
  return (blocks || []).filter(function(block) {
    var hay = [block.label, block.description].concat(
      (block.topics || []).map(function(t) { return t.name }),
      (block.apps || []).map(function(a) { return a.name }),
      (block.domains || []).map(function(d) { return d.name })
    ).join("\n").toLowerCase()
    return hay.indexOf(query) !== -1
  })
}

function compactDescription(description, maxLength) {
  description = String(description || "Untitled")
  maxLength = Math.max(2, Number(maxLength) || 24)
  return description.length > maxLength ? description.slice(0, maxLength - 1) + "…" : description
}

function normalizeProject(project) {
  project = project || {}
  var active = project.active === undefined ? !project.archived : !!project.active
  return {
    id: project.id,
    workspaceId: project.workspace_id || project.workspaceId || null,
    name: String(project.name || "Unnamed project"),
    clientId: project.client_id || project.clientId || null,
    clientName: String(project.client_name || project.client || ""),
    client: String(project.client_name || project.client || ""),
    archived: !!project.archived,
    active: active,
    billable: !!project.billable,
    color: String(project.color || ""),
    status: String(project.status || (active ? "active" : "archived")),
    isPrivate: !!(project.is_private !== undefined ? project.is_private : project.isPrivate),
    externalReference: String(project.external_reference || project.externalReference || ""),
    createdAt: project.created_at || project.createdAt || "",
    at: project.at || "",
    startDate: project.start_date || project.startDate || "",
    endDate: project.end_date || project.endDate || "",
    estimatedHours: project.estimated_hours || project.estimatedHours || null,
    estimatedSeconds: project.estimated_seconds || project.estimatedSeconds || null,
    fixedFee: project.fixed_fee !== undefined ? project.fixed_fee : project.fixedFee
  }
}

function normalizeTask(task) {
  task = task || {}
  return {
    id: task.id,
    workspaceId: task.workspace_id || task.workspaceId || null,
    projectId: task.project_id || task.projectId || null,
    name: String(task.name || "Unnamed task"),
    active: task.active === undefined ? String(task.status || "active") !== "archived" : !!task.active,
    status: String(task.status || (task.active === false ? "inactive" : "active")),
    at: task.at || "",
    estimatedSeconds: task.estimated_seconds || task.estimatedSeconds || null,
    trackedSeconds: task.tracked_seconds || task.trackedSeconds || 0,
    clientId: task.client_id || task.clientId || null,
    clientName: String(task.client_name || task.clientName || ""),
    projectName: String(task.project_name || task.projectName || ""),
    projectColor: String(task.project_color || task.projectColor || ""),
    projectBillable: !!(task.project_billable !== undefined ? task.project_billable : task.projectBillable),
    projectIsPrivate: !!(task.project_is_private !== undefined ? task.project_is_private : task.projectIsPrivate),
    externalReference: String(task.external_reference || task.externalReference || "")
  }
}

function safeProjectColor(project) {
  var color = String(project && project.color || "")
  return /^#[0-9a-f]{6}$/i.test(color) ? color : ""
}

function projectStatus(project) {
  if (!project || project.archived) return "archived"
  var status = String(project.status || "").trim().toLowerCase()
  return status || "active"
}

function humanizeStatus(status) {
  return String(status || "active").replace(/[-_]+/g, " ").replace(/\b\w/g, function(letter) { return letter.toUpperCase() })
}

function projectSearchText(project) {
  project = normalizeProject(project)
  return [project.name, project.clientName, project.externalReference, projectStatus(project), project.billable ? "billable" : "non-billable", project.isPrivate ? "private" : "shared"].join(" ").toLowerCase()
}

function taskSearchText(task) {
  task = normalizeTask(task)
  return [task.name, task.projectName, task.clientName, task.externalReference, task.status].join(" ").toLowerCase()
}

// Stopwords dropped when building the SIGNIFICANT-word acronym (rules 4-5).
// "&" is listed as its own token because it can appear as a whitespace-
// separated word on its own, same as "and".
var SCORE_STOPWORDS = { "and": true, "of": true, "the": true, "for": true, "a": true, "to": true, "in": true, "on": true, "up": true, "&": true }

function scoreAcronym(words) {
  return words.map(function(word) { return word.charAt(0) }).join("")
}

function scoreIsSubsequence(query, text) {
  var qi = 0
  for (var i = 0; i < text.length && qi < query.length; i++) if (text.charAt(i) === query.charAt(qi)) qi++
  return qi === query.length
}

// Spec S6.5: ranks a project or task name against a whitespace-free query
// fragment. Pure; 0 means no match, higher ranks first. Rules 4 and 5 are
// load-bearing (see spec), not refinements, and rule 8 must stay the lowest
// tier -- see the brief for the measured failures each one prevents.
function scoreMatch(query, name) {
  query = String(query || "").trim().toLowerCase()
  name = String(name || "")
  if (!query) return 0
  var lower = name.toLowerCase()
  var words = lower.split(/\s+/).filter(function(word) { return word.length > 0 })
  if (!words.length) return 0

  var TIER = 1000000
  var penalty = Math.min(TIER - 1, name.length)

  // 1. the whole name starts with the query
  if (lower.indexOf(query) === 0) return 8 * TIER - penalty

  // 2. any word starts with the query -- earlier words score higher
  for (var i = 0; i < words.length; i++) {
    if (words[i].indexOf(query) === 0) return 7 * TIER - i * 100 - penalty
  }

  var significant = words.filter(function(word) { return !SCORE_STOPWORDS[word] })

  // 3. the acronym of all word initials starts with the query
  if (scoreAcronym(words).indexOf(query) === 0) return 6 * TIER - penalty

  // 4. the acronym of SIGNIFICANT word initials starts with the query
  if (scoreAcronym(significant).indexOf(query) === 0) return 5 * TIER - penalty

  // 5. the acronym of a trailing run of words starts with the query, so a
  // leading job code can be skipped. Starts at 1: a full run is rule 4.
  for (var start = 1; start < significant.length; start++) {
    if (scoreAcronym(significant.slice(start)).indexOf(query) === 0) return 4 * TIER - start * 100 - penalty
  }

  // 6. the query is a substring of some word, at a word boundary
  for (var j = 0; j < words.length; j++) {
    var word = words[j]
    for (var k = 0; k < word.length; k++) {
      var atBoundary = k === 0 || !/[a-z0-9]/i.test(word.charAt(k - 1))
      if (atBoundary && word.indexOf(query, k) === k) return 3 * TIER - penalty
    }
  }

  // 7. the query is a substring anywhere
  if (lower.indexOf(query) !== -1) return 2 * TIER - penalty

  // 8. the query is a subsequence of the name -- lowest tier, see the brief
  if (scoreIsSubsequence(query, lower)) return 1 * TIER - penalty

  return 0
}

function tasksForProject(tasks, projectId) {
  return (tasks || []).map(normalizeTask).filter(function(task) { return String(task.projectId) === String(projectId) && task.active })
}

function projectMetadataLabels(project) {
  project = normalizeProject(project)
  var labels = []
  if (project.clientName) labels.push("Client " + project.clientName)
  if (project.externalReference) labels.push("Ref " + project.externalReference)
  labels.push(humanizeStatus(projectStatus(project)))
  if (project.billable) labels.push("Billable")
  if (project.isPrivate) labels.push("Private")
  return labels
}

function projectForEntry(entry, projects) {
  var id = entry && (entry.projectId || entry.project_id)
  for (var i = 0; i < (projects || []).length; i++) if (String(projects[i].id) === String(id)) return projects[i]
  return null
}

function projectColorForEntry(entry, projects) { return safeProjectColor(projectForEntry(entry, projects)) }

function taskProjectColor(task, projects) {
  var color = String(task && (task.projectColor || task.project_color) || "")
  return /^#[0-9a-f]{6}$/i.test(color) ? color : projectColorForEntry({ projectId: task && (task.projectId || task.project_id) }, projects)
}

function normalizeEntry(entry) {
  entry = entry || {}
  return { id: entry.id, description: String(entry.description || "(no description)"), projectId: entry.project_id || entry.projectId || null, taskId: entry.task_id || entry.taskId || null, taskName: String(entry.task_name || entry.taskName || ""), projectName: String(entry.project_name || entry.projectName || "No project"), clientName: String(entry.client_name || entry.clientName || ""), tags: entry.tags || [], billable: !!entry.billable, start: entry.start || entry.started_at || "", stop: entry.stop || entry.stopped_at || "", workspaceId: entry.workspace_id || entry.workspaceId || null }
}

function normalizeTag(tag) { return typeof tag === "string" ? tag : String((tag || {}).name || "") }

// Inputs arrive already normalised from Panel.qml's applyData(). Renormalising
// here rebuilt a 25-field object per project on every keystroke.
// The keyboard map, in one place (ruling R-AQ). The help overlay renders it,
// the hint bars quote from it and the README is written from it, so a key that
// exists in one and not the others cannot happen.
function helpSections(scope) {
  var everywhere = {
    title: "Anywhere",
    keys: [
      ["^t", "Timer scope"],
      ["^d", "Day scope"],
      ["^l", "Calendar scope"],
      ["↑ ↓", "Move the cursor"],
      ["PgUp PgDn", "Scroll a page"],
      ["Home End", "Jump to top or bottom"],
      ["^r", "Reload"],
      ["^,", "Settings"],
      ["^o", "Open Toggl on the web"],
      ["^? or ?", "This help"],
      ["esc", "Close"]
    ]
  }
  var timer = {
    title: "Timer",
    keys: [
      ["↵", "Start, or continue the selection"],
      ["^j ^k", "Move the cursor while typing"],
      ["^s", "Stop the running timer"],
      ["@name", "Bind a project"],
      ["/name", "Bind a task (project first)"]
    ]
  }
  var day = {
    title: "Day",
    keys: [
      ["j k", "Move the cursor"],
      ["h l", "Previous or next day"],
      ["t", "Jump to today"],
      ["space", "Inspect the block"],
      ["e", "Edit the block"],
      ["⇥", "Cycle the wording"],
      ["↵", "Apply this block"],
      ["⇧↵", "Apply every ready block"],
      ["⌫", "Skip the block"]
    ]
  }
  var calendar = {
    title: "Calendar",
    keys: [
      ["h j k l", "Move the day cursor"],
      ["← →", "Previous or next period"],
      ["t", "Jump to today"],
      ["w", "Cycle week, fortnight, month"],
      ["a", "Axis settings"],
      ["↵", "Open that day"]
    ]
  }
  var scoped = scope === "day" ? day : (scope === "cal" ? calendar : timer)
  // Letters only act on a row when the command line is empty; with text typed
  // they type. Said once here rather than repeated on every row.
  return [scoped, everywhere]
}

// How many past entries the timer scope offers to continue from.
var RECENT_ENTRY_ROWS = 10

function searchItems(entries, projects, tasks, query, mode, projectId) {
  if (query === undefined) { query = tasks; tasks = [] }
  query = String(query || "").trim().toLowerCase()
  mode = mode || "all"
  var matches = function(value) { return String(value || "").toLowerCase().indexOf(query) !== -1 }
  var newestFirst = function(items) { return (items || []).slice().sort(function(a, b) { return new Date(b.start || 0).getTime() - new Date(a.start || 0).getTime() }) }
  var sortedProjects = (projects || []).filter(function(project) {
    return project.active && (!query || projectSearchText(project).indexOf(query) !== -1)
  }).sort(function(a, b) {
    return String(a.name).localeCompare(String(b.name)) || String(a.clientName).localeCompare(String(b.clientName))
  }).slice(0, 20)
  var scopedTasks = (tasks || []).filter(function(task) {
    return task.active && (mode !== "tasks" || String(task.projectId) === String(projectId)) && (!query || taskSearchText(task).indexOf(query) !== -1)
  }).sort(function(a, b) { return String(a.name).localeCompare(String(b.name)) }).slice(0, 20)
  // Distinct descriptions, newest first: repeating the same entry five times
  // wastes the list, and RECENT_ENTRY_ROWS of it is what the timer scope shows.
  var recentSeen = {}
  var recent = newestFirst(entries).filter(function(entry) {
    var key = String(entry.description || "").trim().toLowerCase() + "|" + (entry.projectId || 0)
    if (recentSeen[key]) return false
    recentSeen[key] = true
    return true
  }).slice(0, RECENT_ENTRY_ROWS)
  return {
    entries: newestFirst((entries || []).filter(function(entry) { return !query || matches(entry.description) || matches(entry.projectName) || matches(entry.clientName) || matches(entry.taskName) || (entry.tags || []).some(matches) })).slice(0, query ? 50 : 5),
    recentEntries: recent,
    projects: mode === "tasks" ? [] : sortedProjects,
    tasks: mode === "projects" ? [] : scopedTasks
  }
}

function uniqueProjects(projects) {
  var seen = {}, result = []
  ;(projects || []).forEach(function(project) { var item = normalizeProject(project); if (item.id !== undefined && !seen[item.id]) { seen[item.id] = true; result.push(item) } })
  return result
}

var BLOCK_MINUTES = [2, 5, 10, 15]

function clampChoice(value, choices, fallback) {
  // Number(null), Number("") and Number([]) are all 0, so reject the empty
  // cases before coercing or a missing setting silently picks a real choice.
  if (value === null || value === undefined || value === "") return fallback
  value = Number(value)
  return choices.indexOf(value) !== -1 ? value : fallback
}

function clampBlockMinutes(minutes) { return clampChoice(minutes, BLOCK_MINUTES, 5) }

// Toggl rejects any start_date earlier than today-91 with HTTP 400. 90 is the
// largest option offered, leaving margin against the 92-day hard bound.
function clampHistory(days) {
  days = Number(days)
  if (!isFinite(days) || days < 1) return 30
  return days > 92 ? 90 : Math.round(days)
}
function historyFloor(dateValue) { return shiftDate(dateValue, -91) }

// Refuses a shift that would cross the history floor, leaving dateValue
// unchanged, rather than clamping to the floor or to today -- a clamp would
// silently move the day the user is looking at instead of just stopping.
function boundedShiftDate(dateValue, days, todayValue) {
  var candidate = shiftDate(dateValue, days)
  var floor = historyFloor(todayValue || todayDate())
  return candidate < floor ? dateValue : candidate
}
function clampReminder(minutes) { minutes = Math.max(0, Math.min(1440, Number(minutes) || 0)); return Math.round(minutes) }

// Token grammar for the command line (spec S6.1 / rulings R-C, R-D2 context).
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
// `completion` is `""` for every `@` token, matched or not (spec 6.5,
// amended 2026-09-04): a name is never completed into commandText, because
// completing to a name that contains spaces is the exact defect that spec
// section exists to remove, and a ghost that appears for some names but not
// others is worse than none. Selection is Enter on a ranked PROJ/TASK row
// (R-S), not Tab. A trailing @token that prefixes exactly one active
// project (or, once the project part is an exact match, exactly one of
// that project's tasks) is still left unbound and unflagged as unmatched --
// "still typing", not "wrong" -- it simply gets no ghost any more. Zero
// prefix matches still means "wrong" -- that lands in `unmatched`.
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
        // The project half is a real, exact, active project even though the
        // task half hasn't (fully) resolved -- bind projectId regardless, so
        // "@acme/back" mid-token doesn't discard a project the user already
        // finished typing. taskId only joins it when the task half is
        // additionally a unique prefix (below); a task half that is empty,
        // ambiguous, or matches nothing leaves taskId at 0.
        if (isLast) {
          if (taskFrag.length === 0) {
            // Clear keep as every other binding branch does. Without it
            // "refactor @acme/" binds the project AND leaves the raw token in
            // the description, so Enter writes "refactor @acme/" to Toggl
            // under that project. One "/" after a resolved "@acme" reaches it.
            projectId = Number(exactProject.id) || 0
            keep[word.index] = ""
            return
          }
          var taskPrefixes = projTasks.filter(function(t) {
            return String(t.name).toLowerCase().indexOf(taskFrag.toLowerCase()) === 0
          })
          if (taskPrefixes.length === 1) {
            // A unique prefix is as good as resolved -- the guide's own mock
            // (design-guide.html:441) renders this exact moment as "acme ·
            // backend" and lets Enter commit both ids. No ghost here (spec
            // 6.5, amended 2026-09-04): task names are multi-word too, so
            // completion stays "" exactly like the project-half branch below.
            // Clear keep like the exact-match branch above: the token is
            // spoken for by projectId/taskId, not left dangling in the
            // description.
            projectId = Number(exactProject.id) || 0
            taskId = Number(taskPrefixes[0].id) || 0
            keep[word.index] = ""
            return
          }
          if (taskPrefixes.length > 1) {
            // Ambiguous is not the same as wrong. The project half is still a
            // finished, exact match, so binding it costs nothing and the user
            // keeps typing to narrow the task. Discarding the project here was
            // the remaining half of the mid-token bug: two tasks sharing a
            // prefix sent "@acme/back" back to "no project". taskId stays 0
            // and no ghost is offered, since there is nothing unique to
            // complete to.
            projectId = Number(exactProject.id) || 0
            keep[word.index] = ""
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
          // Still "in progress", not "wrong" -- left out of `unmatched` and
          // unbound, exactly as before. Only the ghost is gone (spec 6.5,
          // amended 2026-09-04): completion stays "", since 20 of the 25
          // active projects behind this match are multi-word and a ghost
          // that only sometimes appears is worse than none. PROJ rows
          // (rankProjects/commandRows) are how this token actually resolves.
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

// Removes the trailing @-token (spec 6.5's "Binding is state, not text"),
// but only when "@" is the LEADING character of the LAST whitespace-
// delimited token -- exactly parseCommand's own rule (Model.js:443) and
// stripSlashFragment's rule for "/" below, never a substring found by
// lastIndexOf ANYWHERE in the text (F4, final review): the old
// lastIndexOf reading stripped an embedded email address down to
// nothing -- stripAtFragment("email bob@acme.com about refactor") came
// back as "email bob about refactor", silently deleting the rest of the
// address, and reachable any time that fragment scored against a bound
// project. An "@" that is not the last token's leading character (an
// email address, a mid-sentence "standup @ 9am") is left completely
// untouched. Never writes a name back -- see bindProject below.
function stripAtFragment(text) {
  text = String(text || "")
  var match = /(^|\s)(@\S*)(\s*)$/.exec(text)
  if (!match) return text
  return text.slice(0, match.index) + match[1] + match[3]
}

// Removes a trailing /-token (commandRows above only ever emits TASK rows
// for the LAST token). Unlike stripAtFragment above, this is not gated on
// "/" being the leading character of that token -- out of scope for F4,
// which named only stripAtFragment and commandRows's own hasAt -- but it
// is safe in practice: the only caller is bindTask, invoked only on Enter
// for an already-rendered TASK row, and commandRows only ever renders one
// when the last token's first character is already "/" (Model.js:933).
// Never writes a name back -- see bindTask below.
function stripSlashFragment(text) {
  text = String(text || "")
  return text.replace(/\/\S*(\s*)$/, "$1")
}

// The panel's next state after Enter on a PROJ row (spec 6.5). Returns
// the full {commandText, boundProjectId, boundTaskId} triple from one
// pure call, rather than Panel.qml computing and assigning the three
// separately -- moved here, and made pure, specifically so this state
// transition is unit-testable (finding D3, stage 3b fix round 2): a
// flag-based version in Panel.qml that set a "this change is mine"
// marker before touching commandText, then cleared it inside a
// commandTextChanged handler, could stick if a bind's own token-removal
// ever left the text UNCHANGED (nothing to strip, or the second of two
// binds typed with no edit in between) -- QML's property system skips
// the change notification entirely when the new value equals the one
// already in place, so the marker would never get cleared and a later
// genuine clear-to-empty would be silently swallowed. Nothing here needs
// clearing: every field of the result is computed directly from the
// arguments, every call, so there is no marker to leak. A new project
// always clears any previously bound task, since a task never outlives
// its project.
function bindProject(commandText, project) {
  return {
    commandText: stripAtFragment(commandText),
    boundProjectId: Number(project.id) || 0,
    boundTaskId: 0
  }
}

// Same idea for Enter on a TASK row: boundProjectId carries over exactly
// as passed in (never re-derived from commandText), so a project bound
// earlier survives regardless of what stripSlashFragment does to the
// text.
function bindTask(commandText, boundProjectId, task) {
  return {
    commandText: stripSlashFragment(commandText),
    boundProjectId: boundProjectId,
    boundTaskId: Number(task.id) || 0
  }
}

// Spec 6.5: clearing the command line clears both bindings. This is only
// ever called for Panel.qml's commandText property changing by ANY
// means -- typing, backspacing, or a bindProject/bindTask call's own
// token-removal -- and that is fine: bindProject/bindTask compute their
// OWN final ids (above) and assign them after this runs, so whatever
// this function decides for a bind's own text-shrink to "" is always
// overwritten a moment later. It only has the final say for a genuine
// user edit, which never has a bindProject/bindTask call following it in
// the same turn.
function bindingsAfterTextEdit(text, boundProjectId, boundTaskId) {
  if (text === "") return { boundProjectId: 0, boundTaskId: 0 }
  return { boundProjectId: boundProjectId, boundTaskId: boundTaskId }
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
// the inspect drawer's TOPICS/APPS lists and every calendar total (e.g.
// "0h50", "8h05"). rowDuration (below) is its sibling: bare minutes under an
// hour, clockDuration at or above, used by the command line's CONT rows and
// the facts line. The two differ on purpose -- see R-D2 in
// docs/2026-09-04-stage-2-6-rulings.md -- do not unify them.
function clockDuration(seconds) {
  seconds = Math.max(0, Math.floor(number(seconds, 0)))
  var hours = Math.floor(seconds / 3600)
  var minutes = Math.round((seconds % 3600) / 60)
  if (minutes === 60) { hours += 1; minutes = 0 }
  return hours + "h" + String(minutes).padStart(2, "0")
}

// The hybrid "45m"/"2h25" formatter used by the command line's CONT rows and
// the facts line. clockDuration (above) is the always-hour, zero-padded
// formatter used by day rows, the day header, the inspect drawer and
// calendar totals. The two differ on purpose -- see R-D2 in
// docs/2026-09-04-stage-2-6-rulings.md -- do not unify them.
function rowDuration(seconds) {
  seconds = Math.max(0, Math.floor(number(seconds, 0)))
  var minutes = Math.round((seconds % 3600) / 60)
  if (seconds < 3600 && minutes < 60) return minutes + "m"
  return clockDuration(seconds)
}

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

// label is passed in as the row's own effective description (see
// commandRows) -- the invariant is row.label === row.target.description,
// since target's description is what startFromCommand (Panel.qml)
// submits unchanged. The label CAN be empty (F6, final review): a bound
// project with nothing else typed still gets a START row so its meta
// names the binding -- commandRows itself decides whether there is
// anything to start at all (a description, a bound project, or both),
// which is the only thing that gates whether this is called.
function startRow(label, meta, parsed) {
  return { glyph: "↵", verb: "START", label: label, meta: meta, num: "", kind: "start", target: parsed }
}

// meta carries no duration -- unlike blockRow's, a CONT row's duration is
// rendered in its own never-eliding num column, trailing the meta (the
// guide's `.meta` / `.num` order for this row kind: description first, then
// project/task, then the number last). Splitting it out keeps a long
// project/task string from clipping the duration off the row's right edge,
// which happened when both shared one elidable Text.
function continueRow(entry, now) {
  var seconds = durationSeconds(entry, now)
  return {
    glyph: "⟲", verb: "CONT",
    label: entry.description || "(no description)",
    meta: (entry.projectName || "No project") + (entry.taskName ? " · " + entry.taskName : ""),
    num: rowDuration(seconds),
    kind: "continue", target: entry
  }
}

function byNameAscending(a, b) {
  return String(a.name).localeCompare(String(b.name))
}

// Spec S6.5/R-S: ranks active projects against a query fragment by
// scoreMatch, taking the BETTER of the project's own name and its client
// name -- the user's projects are grouped under clients like "Northwind" and
// "Northwind Internal", so client-name matching is how several of them are
// actually found. Capped at the guide's 8-row PROJ limit; this replaced a
// plain projectSearchText substring match sorted alphabetically, which is
// why an exact tie-break here still favours the shorter (scoreMatch's own
// length penalty), never the alphabetically-earlier, name.
//
// An empty query means "browse everything", not "nothing matches" (D1,
// stage 3b fix round 2): a bare "@" with 25 active projects, or a bare
// "/" against a bound project's 2 tasks, used to rank zero rows, so
// there was no way to browse -- you had to already know the name you
// were looking for. scoreMatch("", name) staying 0 is correct and other
// callers rely on it, so this is handled here instead: an empty query
// short-circuits to every active candidate in NAME order (not usage or
// recency -- the guide has no such ranking model), still capped at 8.
function rankProjects(projects, query) {
  query = String(query || "")
  var active = (projects || []).filter(function(p) {
    return p.active
  })
  if (!query) return active.slice().sort(byNameAscending).slice(0, 8)
  return active.map(function(p) {
    return { project: p, score: Math.max(scoreMatch(query, p.name), scoreMatch(query, p.clientName)) }
  }).filter(function(entry) {
    return entry.score > 0
  }).sort(function(a, b) {
    return b.score - a.score
  }).slice(0, 8).map(function(entry) {
    return entry.project
  })
}

// Spec S6.5/R-S: ranks a bound project's ACTIVE tasks against a query
// fragment by scoreMatch. Same 8-row cap, and the same empty-query
// "browse everything" fallback, as rankProjects above.
function rankTasks(tasks, projectId, query) {
  query = String(query || "")
  var candidates = tasksForProject(tasks, projectId)
  if (!query) return candidates.slice().sort(byNameAscending).slice(0, 8)
  return candidates.map(function(t) {
    return { task: t, score: scoreMatch(query, t.name) }
  }).filter(function(entry) {
    return entry.score > 0
  }).sort(function(a, b) {
    return b.score - a.score
  }).slice(0, 8).map(function(entry) {
    return entry.task
  })
}

function projectRow(project, entries) {
  var count = (entries || []).filter(function(e) { return Number(e.projectId) === Number(project.id) }).length
  return {
    glyph: "▤", verb: "PROJ",
    label: (project.clientName ? project.clientName + " / " : "") + project.name,
    meta: count + (count === 1 ? " entry" : " entries"),
    num: "",
    kind: "project", target: project
  }
}

// New row kind introduced by R-S/S6.5: a task-selection row for a bound
// project's active tasks. The glyph is invented -- the design guide's mock
// never needed one, since its example project/task names are short and
// single-word (see the stage 3b brief). meta is the owning project's name,
// never the task's own client, since a task has no client of its own.
function taskRow(task, projectName) {
  return {
    glyph: "◈", verb: "TASK",
    label: task.name,
    meta: projectName,
    num: "",
    kind: "task", target: task
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

// today is passed in (derived from commandRows's own `now`), never read off
// the wall clock directly -- two calls with the same `now` must render the
// same row regardless of when they actually run.
function blockRow(block, today) {
  var start = new Date(block.start)
  var day = isFinite(start.getTime()) ? isoDate(start) : ""
  return {
    glyph: "◷", verb: "BLOCK",
    label: clockTime(block.start) + " " + (block.label || "(untitled)"),
    // BLOCK metas are short (duration + day label) and never overflow, so
    // the duration stays inline here rather than moving to num -- the guide
    // puts BLOCK's number first, not last, and there is nothing to gain by
    // reordering it. num is empty; only continueRow's duration needed
    // splitting out.
    meta: clockDuration(block.seconds) + "  " + (day === today ? "today" : dayLabel(day)),
    num: "",
    kind: "block", target: block
  }
}

// Composes the command-line result rows shown in timer scope (spec S6.4,
// S6.5/R-S, R3-12, R3-30, R3-31). Consumes parseCommand's output plus the
// same in-memory lists Panel.qml already holds after sync -- no Process
// call, ever (spec S6.1 rule 3).
//
// boundProjectId/boundTaskId are panel STATE (spec S6.5 "Binding is state,
// not text"), trailing and defaulting to 0 so every existing call shape
// keeps working unchanged. They affect the START row's effective ids and
// label (F6: a bound project alone is enough to justify a START row; F5:
// a trailing /frag is stripped from that row's label the same way an @
// token already is) and the /frag TASK branch below; Model.parseCommand
// itself stays pure and text-only and never sees them.
function commandRows(text, projects, tasks, tags, entries, blocks, now, boundProjectId, boundTaskId) {
  text = String(text || "")
  boundProjectId = Number(boundProjectId) || 0
  boundTaskId = Number(boundTaskId) || 0
  var trimmed = text.trim()
  var parsed = parseCommand(text, projects, tasks, tags)
  // A bound id wins over whatever parseCommand resolved from the text itself,
  // so a name typed out exactly still works with no special case (spec
  // S6.5): the bound id is 0 whenever nothing is bound, and 0 || x is x.
  var effectiveProjectId = boundProjectId || parsed.projectId
  var effectiveTaskId = boundTaskId || parsed.taskId
  // now must be a Date by the time it reaches its two consumers below:
  // continueRow's durationSeconds() only ever subtracts it from another
  // timestamp, so a millisecond number would silently coerce there and hide
  // a mistake; isoDate() (for `today`, just below) calls now.getFullYear()
  // and throws outright on a plain number. Normalising once here -- rather
  // than trusting every call site -- means a caller passing Date.now() (a
  // number; Task 4's QML side does exactly this) is exactly as safe as one
  // passing `new Date()`.
  now = now instanceof Date ? now : new Date(now)
  var today = isoDate(now)
  var rows = []

  // The last whitespace-delimited token, if any -- shared by the @ and
  // /frag checks below, both of which need "is the LAST token a leading
  // sigil", exactly like parseCommand's own isLast rule (Model.js:443).
  // Finding "@" by lastIndexOf ANYWHERE in the text (the substring
  // reading F4, final review, replaces) is why "standup @ 9am" used to
  // browse every active project, and why an email address anywhere in a
  // description used to suppress CONT/BLOCK below (see F3) and, once
  // bound from, silently delete itself from the text (see F4's fix to
  // stripAtFragment, above).
  var lastToken = trimmed.length ? trimmed.split(/\s+/).pop() : ""
  var hasAt = lastToken.charAt(0) === "@"
  // Text before the last token, trimmed -- "is there anything to start
  // besides the sigil itself". Derived from the token itself, not from
  // lastIndexOf("@") (F4), so this only ever looks at the LAST token,
  // never an earlier "@" elsewhere in the string.
  var beforeLastToken = lastToken.length ? trimmed.slice(0, trimmed.length - lastToken.length).trim() : trimmed

  // F5, final review: with a project already bound, a trailing "/frag" is
  // a task selector exactly like a trailing "@frag" is a project selector
  // above -- it must not count as start-worthy description text, or Enter
  // (the same key that just bound the project) submits the raw "/frag"
  // token itself as a real Toggl entry description. Mirrors hasAt/
  // beforeLastToken; a "/" NOT in this position (a date "9/3", a path
  // "docs/readme", an unfinished word "a/b") is ordinary description text
  // and never reaches here, matching the leading-sigil rule below.
  var hasSlashFrag = !!boundProjectId && lastToken.charAt(0) === "/"
  var startDescription = hasSlashFrag ? stripSlashFragment(parsed.description).trim() : parsed.description

  // Whether a START row exists at all, and what it says once it does, are
  // two different questions -- keeping them separate is what a previous
  // version of this code got wrong. Existence follows the text typed so
  // far (and F6: OR a bound project, so the binding is never completely
  // invisible just because nothing else was typed -- see startRow's own
  // comment). The row's LABEL, whenever it exists, is always
  // startDescription -- parsed.description with a bound project's own
  // trailing /frag stripped (F5), otherwise unchanged, and always the
  // exact string startFromCommand (Panel.qml) submits.
  // row.label === row.target.description is the invariant that rules out
  // the two ever disagreeing; see tests/test_model.mjs.
  var hasStart = hasAt ? !!beforeLastToken : (!!startDescription || !!effectiveProjectId)
  if (hasStart) {
    // target stays `parsed` itself (unchanged identity) whenever the bound
    // ids agree with what parseCommand already resolved AND there is no
    // /frag to strip -- which is every existing call site, since they
    // never pass bound ids at all -- so the "omitting the two new
    // parameters reproduces today's rows exactly" guarantee holds without
    // a special case. Only a genuine override clones.
    var startTarget = parsed
    if (hasSlashFrag || effectiveProjectId !== parsed.projectId || effectiveTaskId !== parsed.taskId) {
      startTarget = {
        description: startDescription,
        projectId: effectiveProjectId,
        taskId: effectiveTaskId,
        tags: parsed.tags,
        billable: parsed.billable,
        completion: parsed.completion,
        unmatched: parsed.unmatched
      }
    }
    rows.push(startRow(startDescription, projectMeta(projects, tasks, effectiveProjectId, effectiveTaskId), startTarget))
  }

  if (hasAt) {
    // meta still comes from parseCommand's own resolution, so a token that
    // DOES exactly resolve shows its real project/task here, matching R3-30.
    var fragment = lastToken.slice(1).split("/")[0]
    rankProjects(projects, fragment).forEach(function(project) {
      rows.push(projectRow(project, entries))
    })
    // F3, final review: no `return` here any more. One row kind must
    // never exclude another -- design-guide.html:441-445's own §01 mock
    // renders "refactor @acme/back" as START, CONT, CONT, PROJ, BLOCK,
    // all coexisting in one list. This used to `return rows` right after
    // PROJ, silently dropping CONT and BLOCK for every @ token typed,
    // including one that never matched a project at all.
  }

  if (hasSlashFrag) {
    // The /frag TASK branch (spec S6.5, amended 2026-09-04): once a
    // project is bound, a LAST token that STARTS WITH "/" ranks that
    // project's active tasks and emits them as TASK rows ALONGSIDE the
    // CONT/BLOCK rows below -- one row kind must never exclude another,
    // the same principle the @ branch above now follows since F3 removed
    // its own early return (this comment used to claim @ already matched
    // that principle; it did not, until F4 made @ a leading sigil too).
    var taskFrag = lastToken.slice(1)
    var boundProject = (projects || []).filter(function(p) { return Number(p.id) === Number(boundProjectId) })[0]
    var projectName = boundProject ? boundProject.name : ""
    rankTasks(tasks, boundProjectId, taskFrag).forEach(function(task) {
      rows.push(taskRow(task, projectName))
    })
  }

  if (!trimmed.length) {
    // Ten, not three: an empty command line is the "what was I doing lately"
    // view, and the panel scrolls, so the list may as well be worth scrolling.
    searchItems(entries, projects, tasks, "", "all", 0).recentEntries.slice(0, RECENT_ENTRY_ROWS).forEach(function(entry) {
      rows.push(continueRow(entry, now))
    })
    var idleBlock = bestOpenBlock(blocks, "")
    if (idleBlock) rows.push(blockRow(idleBlock, today))
    return rows
  }

  // F8, final review: queried with parsed.description, not the raw typed
  // text -- a #tag or a bare $ is consumed by parseCommand's own `keep`
  // mechanism and must not still count against these two matches, or
  // tagging/billing a description that already had a CONT/BLOCK match
  // made both silently vanish. A raw "/frag" is deliberately NOT stripped
  // here: parseCommand never touches "/" tokens, so it is already part of
  // parsed.description untouched -- that suppression is desired (see the
  // fix-round-2 progress note this preserves), unlike #/$.
  var contEntry = searchItems(entries, projects, tasks, parsed.description, "all", 0).entries[0]
  if (contEntry) rows.push(continueRow(contEntry, now))
  var openBlock = bestOpenBlock(blocks, parsed.description)
  if (openBlock) rows.push(blockRow(openBlock, today))
  return rows
}

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

// `filter by project or tag` (guide 04): narrows the calendar's entries by a
// case-insensitive substring of project, client, task, description or tag.
function calendarFilter(entries, query) {
  query = String(query || "").trim().toLowerCase()
  if (!query) return entries || []
  return (entries || []).filter(function(e) {
    var hay = [e.project_name, e.client_name, e.task_name, e.description].concat(e.tags || []).join("\n").toLowerCase()
    return hay.indexOf(query) !== -1
  })
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
    // A block already guessed from history or a project code is settled for
    // the classifier (classifyGuessFor refuses guessed blocks); sending it
    // only spends tokens and drags the model toward its neighbours' labels.
    if (block.guessed) return
    // Rich input (ruling R-AN): the 1.7B model synthesises a description
    // from what it is shown, so it sees the top twelve titles, every app and
    // site with its seconds, and when the block started.
    out.push({
      index: index,
      label: String(block.label || ""),
      start: String(block.start || ""),
      topics: (block.topics || []).slice(0, 12).map(function(topic) {
        return { name: String(topic.name || ""), seconds: number(topic.seconds, 0) }
      }),
      apps: (block.apps || []).map(function(app) {
        return { name: String((app && app.name) || app || ""), seconds: number(app && app.seconds, 0) }
      }).filter(function(app) { return app.name }),
      domains: (block.domains && block.domains.length ? block.domains : (block.domain ? [{ name: block.domain, seconds: 0 }] : [])).map(function(domain) {
        return { name: String((domain && domain.name) || domain || ""), seconds: number(domain && domain.seconds, 0) }
      }).filter(function(domain) { return domain.name }),
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

// History guess (ruling R-AK): the user's own past label for the same
// activity, when the store is confident enough. Same guessed path as the
// classifier -- ~ glyph, Space confirms, never auto-applied. Mirrors
// toggl_api.HISTORY_GUESS_SCORE.
var HISTORY_GUESS_SCORE = 0.5

function historyGuessFor(block) {
  if (!block || block.state !== "pending" || block.projectId || block.guessed) return null
  if (String(block.description || "").trim() !== String(block.label || "").trim()) return null
  // Two independent sources. The backend's ranking (usage prior blended with
  // embedding similarity) decides the project -- measured 81% against a nearest
  // past record's 57% (ruling R-AO). A past record supplies wording, but only
  // when it is close enough to be worth showing (ruling R-AK).
  var ranked = (block.projects || [])[0]
  var best = (block.history || [])[0]
  var strong = best && number(best.score, 0) >= HISTORY_GUESS_SCORE ? best : null
  var projectId = ranked ? number(ranked.project_id, 0) : number(strong && strong.project_id, 0)
  var description = strong ? String(strong.description || "").trim() : ""
  if (!projectId && !description) return null
  return {
    description: description || String(block.label || ""),
    projectId: projectId,
    taskId: strong && projectId === number(strong.project_id, 0) ? number(strong.task_id, 0) : 0,
    guessed: true
  }
}

function applyHistoryGuesses(blocks) {
  var count = 0
  ;(blocks || []).forEach(function(block) {
    var guess = historyGuessFor(block)
    if (!guess) return
    block.description = guess.description
    block.projectId = guess.projectId
    block.taskId = guess.taskId
    block.guessed = true
    count += 1
  })
  return count
}

// Deterministic project guess from the block's own words (ruling R-AJ). A
// project code such as NW-084 appearing in a topic is near-certain; a
// distinctive word (6+ letters, unique to one project name, not generic) is a
// fair guess. Only the label and the window-title topics count -- app ids and
// web domains never name a project ("System Settings" is not the RAID System
// project). Returns { projectId, confidence } or null. Never touches the block.
var PROJECT_CODE = /(^|[^a-z0-9])([a-z]{2,5}-\d{2,4})(?=[^a-z0-9]|$)/g
var GUESS_STOP_WORDS = {
  support: 1, testing: 1, project: 1, projects: 1, development: 1, general: 1,
  internal: 1, growth: 1, research: 1, phase: 1, upgrade: 1, validation: 1,
  deployment: 1, meeting: 1, meetings: 1, admin: 1, administration: 1,
  system: 1, systems: 1, improvement: 1, management: 1, platform: 1, platforms: 1,
  service: 1, services: 1, report: 1, reports: 1, weekly: 1, monthly: 1, review: 1,
  planning: 1, training: 1, quality: 1, safety: 1, offshore: 1, executive: 1,
  engineering: 1, operations: 1, technical: 1, design: 1, software: 1, hardware: 1,
  presentation: 1, markets: 1, turnkey: 1, monitoring: 0
}

function blockWords(block) {
  var parts = [String(block.label || "")]
  ;(block.topics || []).forEach(function(topic) { parts.push(String((topic && topic.name) || topic || "")) })
  return " " + parts.join(" ").toLowerCase() + " "
}

function codesIn(text) {
  var out = [], match
  PROJECT_CODE.lastIndex = 0
  while ((match = PROJECT_CODE.exec(text)) !== null) out.push(match[2])
  return out
}

function guessProjectFromTopics(block, projects) {
  if (!block || block.state !== "pending" || block.projectId || block.guessed) return null
  var active = (projects || []).filter(function(project) { return project && project.active && project.id })
  if (!active.length) return null
  var text = blockWords(block)
  if (!text.trim()) return null

  // 1. project code, resolved in topic order (the label first, then topics
  //    ranked by seconds), so the code the block spent most time on wins.
  var byCode = {}
  active.forEach(function(project) {
    codesIn(String(project.name || "").toLowerCase()).forEach(function(code) {
      byCode[code] = byCode[code] ? "many" : project.id
    })
  })
  var found = codesIn(text)
  for (var c = 0; c < found.length; c++) {
    if (byCode[found[c]] && byCode[found[c]] !== "many") return { projectId: byCode[found[c]], confidence: 0.9 }
  }

  // 2. distinctive word unique to one project name
  var owners = {}
  active.forEach(function(project) {
    var seen = {}
    String(project.name || "").toLowerCase().split(/[^a-z]+/).forEach(function(word) {
      if (word.length < 6 || GUESS_STOP_WORDS[word] || seen[word]) return
      seen[word] = 1
      owners[word] = owners[word] ? "many" : project.id
    })
  })
  var words = Object.keys(owners)
  for (var w = 0; w < words.length; w++) {
    if (owners[words[w]] === "many") continue
    if (new RegExp("(^|[^a-z])" + words[w] + "([^a-z]|$)").test(text)) {
      return { projectId: owners[words[w]], confidence: 0.6 }
    }
  }
  return null
}

// Applies guessProjectFromTopics to freshly prepared blocks, in place, before
// they are shown; returns how many were guessed. Same guessed path as the
// classifier: ~ glyph, Space confirms, never auto-applied.
function applyProjectGuesses(blocks, projects) {
  var count = 0
  ;(blocks || []).forEach(function(block) {
    var guess = guessProjectFromTopics(block, projects)
    if (!guess) return
    block.projectId = guess.projectId
    block.guessed = true
    count += 1
  })
  return count
}

// A model-chosen project must be grounded in the block's own words (ruling
// R-AN): some word of the project's name, code or client -- 4+ letters, or a
// 3+ character token carrying a digit such as nx8 -- appears in the label or
// a title. Measured live, the 1.7B otherwise attached "Holiday" to a weekly
// report and a random OSP code to a terminal session.
function projectSupportedByBlock(block, project) {
  if (!block || !project) return false
  var text = blockWords(block)
  var words = [project.name, project.clientName, project.client].join(" ").toLowerCase().split(/[^a-z0-9]+/)
  for (var i = 0; i < words.length; i++) {
    var word = words[i]
    if (!word || GUESS_STOP_WORDS[word]) continue
    var hasDigit = /[0-9]/.test(word)
    if ((hasDigit && word.length >= 3) || (!hasDigit && word.length >= 4)) {
      if (text.indexOf(word) >= 0) return true
    }
  }
  return false
}

// The description candidates offered for one block, best first and without
// duplicates (ruling R-AP): what the model wrote, what the user wrote for
// similar activity before, and the block's own window title -- which measured
// better than anything a small model produced unaided.
function descriptionCandidates(block) {
  if (!block) return []
  var out = []
  function push(text, source) {
    text = String(text || "").trim()
    if (!text) return
    for (var i = 0; i < out.length; i++) if (out[i].text.toLowerCase() === text.toLowerCase()) return
    out.push({ text: text, source: source })
  }
  push(block.modelDescription, "model")
  ;(block.history || []).forEach(function(hit) { push(hit.description, "history") })
  push(block.label, "title")
  return out
}

function cycleDescription(block, delta) {
  var candidates = descriptionCandidates(block)
  if (!candidates.length) return null
  var index = number(block.candidateIndex, 0) + number(delta, 1)
  while (index < 0) index += candidates.length
  index = index % candidates.length
  block.candidateIndex = index
  block.description = candidates[index].text
  block.guessed = true
  return candidates[index]
}

// What the panel is offering right now, for the correction log. The backend
// compares this against what the user actually applied.
function suggestionFor(block) {
  if (!block) return null
  var candidates = descriptionCandidates(block)
  var index = number(block.candidateIndex, 0)
  var current = candidates.length ? candidates[Math.min(index, candidates.length - 1)] : null
  return {
    description: current ? current.text : String(block.description || ""),
    project_id: number(block.projectId, 0) || null,
    source: current ? current.source : "none"
  }
}

// The backend already decided the project from history and geometry, so a
// classify result carries prose plus that decision; nothing here re-judges it.
function classifyGuessFor(block, result, projects) {
  if (!block || !result) return null
  if (block.state !== "pending" || block.busy) return null
  var description = String(result.description || "").trim()
  var projectId = number(result.project_id, 0)
  if (!description && !projectId) return null
  // Record the model's phrasing even on a row that is already guessed or
  // assigned, so Tab can still reach it as a candidate (ruling R-AP).
  block.modelDescription = description
  var untouched = String(block.description || "").trim() === String(block.label || "").trim()
  if (!untouched || block.projectId || block.guessed) return null
  // A guess that only echoes the label with no project shows the row nothing
  // it does not already say, yet would flag it ~ (ruling R-AH).
  if (!projectId && description === String(block.label || "").trim()) return null
  return {
    description: description || String(block.label || ""),
    projectId: projectId,
    guessed: true
  }
}


// Identity of the activity plus every user-controlled assignment. A revision
// also detects editing then restoring the original text before a response.
function enrichmentSnapshot(block) {
  return JSON.stringify([block.start, block.end, block.seconds, block.label,
    block.topics, block.apps, block.domains, block.description, block.projectId,
    block.taskId, block.guessed, block.state, block.busy, block.editing,
    block.skipped, block.editRevision || 0])
}

function enrichmentPayload(blocks) {
  return classifyBlockPayload((blocks || []).map(function(block) {
    return Object.assign({}, block, {guessed: false})
  })).map(function(payload) {
    payload.signature = enrichmentSnapshot(blocks[payload.index])
    return payload
  })
}

function mergeEnrichment(block, enrichment, result, projects) {
  if (!block || block.state !== "pending" || block.busy || block.editing ||
      enrichment.signature !== enrichmentSnapshot(block)) return false
  // Re-run the same precedence as a synchronous day load, now with geometry.
  var next = Object.assign({}, block, {projects: enrichment.projects || [],
    description: block.label, projectId: 0, taskId: 0, guessed: false})
  applyHistoryGuesses([next])
  applyProjectGuesses([next], projects)
  var guess = classifyGuessFor(next, result, projects)
  if (guess) Object.assign(next, guess)
  ;["projects", "description", "projectId", "taskId", "guessed", "modelDescription"].forEach(function(key) {
    block[key] = next[key]
  })
  return true
}
