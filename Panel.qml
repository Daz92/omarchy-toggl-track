import "Model.js" as Model
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "ui"

Panel {
    // What the user called this activity, for the history store
    // (ruling R-AK). Names only -- the backend keys on them.
    // What was on screen when the user hit apply, so the backend can
    // record whether they kept it or corrected it (ruling R-AP).
    // Optional enrichment cannot turn a working panel into an error.

    id: root

    property var anchorItem: null
    property var hostWidget: null
    readonly property var barIdentity: hostWidget || root
    readonly property color foreground: panelTheme.text
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    property var current: null
    property var user: null
    property var workspaces: []
    property var projects: []
    property var tags: []
    property var tasks: []
    property var entries: []
    property bool tasksAvailable: false
    property string status: "loading"
    property string errorMessage: ""
    property int errorStatus: 0
    property int selectedWorkspaceId: Number(setting("workspaceId", 0)) || 0
    property int historyDays: Model.clampHistory(setting("historyDays", 30))
    property int idleReminderMinutes: Model.clampReminder(setting("idleReminderMinutes", 0))
    property string elapsedLabel: current ? Model.timerLabel(current, Date.now()) : "—"
    property string barLabel: current ? elapsedLabel + "  " + Model.compactDescription(current.description, 24) : "Toggl"
    property bool requestPending: false
    property string pendingAction: ""
    property var requestQueue: []
    property var clientLog: []
    // Set to the just-flushed clientLog when a request is dispatched, and
    // cleared once a response for it arrives. If the helper crashes instead,
    // apiProc's onExited restores it so those events ride along on the next
    // request rather than vanishing exactly when they'd explain the crash.
    property var lostClientLog: []
    property string logLevel: String(setting("logLevel", "info"))
    property bool idleNotified: false
    property bool tasksLoaded: false
    property bool manualRefresh: false
    property var cacheInfo: null
    property string scope: "timer"
    property string commandText: ""
    property int resultCursorIndex: 0
    property int dayCursorIndex: -1
    // Spec 6.5 "Binding is state, not text": a resolved project/task lives
    // here, never in commandText, since the @ grammar can't carry a
    // multi-word name back through the parser. 0 means unset. bindProject/
    // bindTask/close below own every write to these two -- see Model.js's
    // bindProject/bindTask/bindingsAfterTextEdit for why there is no local
    // flag guarding onCommandTextChanged any more (stage 3b fix round 2,
    // finding D3).
    property int boundProjectId: 0
    property int boundTaskId: 0
    readonly property var commandParsed: Model.parseCommand(root.commandText, root.projects, root.tasks, root.tags)
    readonly property var commandRows: Model.commandRows(root.commandText, root.projects, root.tasks, root.tags, root.entries, root.dayBlocks, Date.now(), root.boundProjectId, root.boundTaskId)
    property bool settingsOpen: false
    // The keyboard reference overlay (^? or ?, or the header's ? button).
    property bool helpOpen: false
    property int dayBlockMinutes: Model.clampBlockMinutes(setting("dayBlockMinutes", 5))
    property string dayDate: Model.todayDate()
    property var dayBlocks: []
    property int dayGeneration: 0
    property var enrichmentNext: null
    property var enrichmentActive: null
    property var scopeScroll: ({
        "timer": 0,
        "day": 0,
        "cal": 0
    })
    property string dayError: ""
    property bool dayLoaded: false
    property int dayRevision: 0
    property var applyQueue: []
    // Local classifier (spec 10.4-10.6): "off" or "local". Persisted. Nothing
    // it produces reaches Toggl without a confirmation.
    readonly property var classifierChoices: ["off", "local"]
    property string classifier: classifierChoices.indexOf(String(setting("classifier", "off"))) >= 0 ? String(setting("classifier", "off")) : "off"
    property var daySummary: Model.blockSummary([])
    // The rows the day scope renders: dayBlocks narrowed by the command line's
    // "filter blocks" text (guide 02). dayCursorIndex indexes THIS list.
    readonly property var dayVisibleBlocks: dayRevision >= 0 ? Model.blockFilter(dayBlocks, scope === "day" ? commandText : "") : []
    // ---- calendar scope (spec 8, stage 5) -----------------------------------
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
    // Per date: {raw: [...], prepared: [...]} from day_activity. Raw feeds the
    // axis (it wants {start, end, applied}); prepared feeds flags and strips.
    property var calendarBlocksByDate: ({
    })
    property string calendarCursorDate: Model.todayDate()
    property string pendingDayActivityDate: ""
    property bool calendarAxisOpen: false
    readonly property var calendarOverride: ({
        "start": calendarDayStart,
        "end": calendarDayEnd
    })
    readonly property var calendarGridDates: Model.calendarGridDates(calendarRange, calendarAnchorDate)
    readonly property var calendarVisibleBlocks: {
        var out = [];
        for (var i = 0; i < calendarGridDates.length; i++) {
            var perDay = calendarBlocksByDate[calendarGridDates[i].date];
            if (perDay)
                out = out.concat(perDay.raw);

        }
        return out;
    }
    // Recomputed when the range or the loaded data changes -- not while the
    // user pages within one range (spec 8.1), which would jump the grid.
    readonly property var calendarAxis: Model.axisBounds(calendarEntries, calendarVisibleBlocks, calendarOverride)
    readonly property bool calendarCanPageBackward: Model.canPageCalendarBackward(calendarRange, calendarAnchorDate, Model.todayDate())
    // `filter by project or tag` (guide 04): the command line narrows entries.
    readonly property var calendarFilteredEntries: Model.calendarFilter(calendarEntries, scope === "cal" ? commandText : "")
    // True while a text editor owns the keyboard, so PanelKeyCatcher can stand
    // down. Checked against the live focus item because day slots create their
    // editors dynamically.
    readonly property bool editorFocused: {
        var item = keyCatcher.Window.activeFocusItem;
        return !!item && (item instanceof TextInput || item instanceof TextEdit);
    }
    readonly property var projectOptions: projects.filter(function(p) {
        return p.active;
    }).map(function(p) {
        return {
            "value": String(p.id),
            "label": p.name,
            "description": p.clientName || ""
        };
    })
    readonly property string setupCommand: String(Qt.resolvedUrl("setup")).replace(/^file:\/\//, "")
    // Coalesces by action: a second refresh queued behind a first is the same
    // refresh, and running it twice only costs a process. Restricted to the
    // refresh-shaped actions -- coalescing a create_entry would strand its
    // block at busy:true forever, because the response that would clear it
    // never comes.
    readonly property var coalescingActions: ["sync", "bootstrap", "day_activity"]
    readonly property var logLevels: ["off", "errors", "info", "debug"]

    function open() {
        controller.show();
        // The panel object outlives a close, so the scope it was left in would
        // otherwise be what greets the next open. The timer is the front door.
        setScope("timer");
        helpOpen = false;
        if (!current && status === "idle")
            bootstrap(false);

        Qt.callLater(function() {
            cmdInput.forceActiveFocus();
        });
    }

    function close() {
        controller.hide();
        keyCatcher.forceActiveFocus();
        // A binding is a short-lived selection in service of the entry the
        // user is about to start, not a persistent preference -- the guide
        // has no chip or badge design for showing one across a close/reopen,
        // so leaving it set would be state the panel believes but never
        // shows, the same hazard as the stale running timer (finding D2,
        // stage 3b fix round 2): a project bound today would silently
        // attach to a timer started tomorrow.
        root.boundProjectId = 0;
        root.boundTaskId = 0;
    }

    function toggle() {
        opened ? close() : open();
    }

    function openWeb() {
        Qt.openUrlExternally("https://track.toggl.com");
    }

    function persist(values) {
        var e = {
            "id": moduleName
        };
        for (var sk in settings) if (sk !== "id") {
            e[sk] = settings[sk];
        }
        e.workspaceId = selectedWorkspaceId;
        e.historyDays = historyDays;
        e.idleReminderMinutes = idleReminderMinutes;
        e.dayBlockMinutes = dayBlockMinutes;
        e.logLevel = logLevel;
        for (var k in values) e[k] = values[k]
        settings = e;
        if (hostWidget)
            hostWidget.settings = e;

        if (bar && bar.shell && typeof bar.shell.updateEntryInline === "function")
            bar.shell.updateEntryInline(moduleName, e);

    }

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
        if (action === "day_activity")
            pendingDayActivityDate = (data && data.date) || "";

        errorMessage = "";
        errorStatus = 0;
        status = "loading";
        var payload = data || {
        };
        payload.action = action;
        if (action === "day_activity") {
            payload.defer_enrichment = true;
            if (payload.date === dayDate)
                dayGeneration += 1;

        }
        payload.log_level = root.logLevel;
        if (clientLog.length > 0) {
            payload.client_log = clientLog;
            lostClientLog = clientLog;
            clientLog = [];
        }
        apiProc.request = JSON.stringify(payload);
        apiProc.running = true;
    }

    function enqueue(action, data) {
        var queue = requestQueue.slice();
        // day_activity coalesces PER DATE: the week grid queues up to seven for
        // different days, and by action name alone they would collapse to one.
        var coalesceKey = function coalesceKey(a, d) {
            return a === "day_activity" ? ((d && d.date) || "") : "";
        };
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
        if (queue.length >= 12) {
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

    function bootstrap(forceRefresh) {
        request("bootstrap", {
            "force_refresh": !!forceRefresh,
            "workspace_id": selectedWorkspaceId,
            "days": historyDays
        });
    }

    function sync(forceRefresh, skipCurrent) {
        if (selectedWorkspaceId > 0) {
            manualRefresh = !!forceRefresh;
            request("sync", {
                "workspace_id": selectedWorkspaceId,
                "days": historyDays,
                "force_refresh": !!forceRefresh,
                "skip_current": !!skipCurrent
            });
        } else {
            noteClient("errors", "request_dropped", "sync");
        }
    }

    function setWorkspace(id) {
        selectedWorkspaceId = Number(id) || 0;
        persist({
            "workspaceId": selectedWorkspaceId
        });
        sync(false, false);
    }

    function setHistory(days) {
        historyDays = Model.clampHistory(days);
        persist({
            "historyDays": historyDays
        });
        sync(false, false);
    }

    function setDayBlockMinutes(minutes) {
        dayBlockMinutes = Model.clampBlockMinutes(minutes);
        persist({
            "dayBlockMinutes": dayBlockMinutes
        });
        dayLoaded = false;
        loadDay();
    }

    function setReminder(minutes) {
        idleReminderMinutes = Model.clampReminder(minutes);
        persist({
            "idleReminderMinutes": idleReminderMinutes
        });
    }

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

    // Separate from timer/Apply requests: one enrichment process and one
    // replaceable latest request, never an unbounded background backlog.
    function classifyDay() {
        if (selectedWorkspaceId <= 0)
            return ;

        enrichmentNext = {
            "action": "enrich_day",
            "workspace_id": selectedWorkspaceId,
            "date": dayDate,
            "generation": dayGeneration,
            "blocks": Model.enrichmentPayload(dayBlocks).filter(function(b) {
                return !(dayBlocks[b.index].editRevision > 0);
            }),
            "projects": Model.classifyProjectPayload(projects),
            "classify": classifier === "local",
            "log_level": logLevel
        };
        pumpEnrichment();
    }

    function pumpEnrichment() {
        if (aiProc.running || enrichmentActive || !enrichmentNext)
            return ;

        enrichmentActive = enrichmentNext;
        enrichmentNext = null;
        aiProc.response = "";
        aiProc.expired = false;
        aiProc.running = true;
    }

    function finishEnrichment(raw) {
        try {
            var response = JSON.parse(raw);
            var data = response.data;
            if (!aiProc.expired && response.ok && data && data.workspace_id === selectedWorkspaceId && data.date === dayDate && data.generation === dayGeneration && enrichmentActive && enrichmentActive.classify === (classifier === "local")) {
                var results = {
                };
                (data.results || []).forEach(function(result) {
                    results[result.index] = result;
                });
                (data.blocks || []).forEach(function(item) {
                    if (Model.mergeEnrichment(dayBlocks[item.index], item, results[item.index], projects))
                        slotChanged();

                });
                daySummary = Model.blockSummary(dayBlocks);
            }
        } catch (error) {
        }
        enrichmentActive = null;
        pumpEnrichment();
    }

    // A late response can never clobber an edit: classifyGuessFor refuses once
    // the user has typed, picked a project, applied, or been guessed already.
    function applyClassifyResults(results) {
        (results || []).forEach(function(result) {
            var block = dayBlocks[result.index];
            var guess = block && Model.classifyGuessFor(block, result, projects);
            if (!guess)
                return ;

            mutateBlock(block, function() {
                block.description = guess.description;
                block.projectId = guess.projectId;
                block.guessed = guess.guessed;
            });
        });
    }

    function chooseWorkspace() {
        if (!workspaces.length) {
            status = "error";
            errorMessage = "No Toggl workspaces are available.";
            return false;
        }
        var candidates = [selectedWorkspaceId, current && current.workspaceId, user && (user.default_workspace_id || user.defaultWorkspaceId || user.workspace_id || user.workspaceId)];
        var chosen = 0;
        for (var i = 0; i < candidates.length && !chosen; i++) {
            var candidate = Number(candidates[i]) || 0;
            if (workspaces.some(function(w) {
                return Number(w.id) === candidate;
            }))
                chosen = candidate;

        }
        if (!chosen)
            chosen = Number(workspaces[0].id) || 0;

        selectedWorkspaceId = chosen;
        persist({
            "workspaceId": selectedWorkspaceId
        });
        return !!selectedWorkspaceId;
    }

    function applyData(data) {
        data = data || {
        };
        if (data.current !== undefined)
            current = data.current ? Model.normalizeEntry(data.current) : null;

        if (data.user !== undefined)
            user = data.user;

        if (data.workspaces)
            workspaces = data.workspaces;

        if (data.projects)
            projects = data.projects.map(Model.normalizeProject);

        if (data.tags)
            tags = data.tags.map(Model.normalizeTag).filter(Boolean);

        if (data.tasks) {
            tasks = data.tasks.map(Model.normalizeTask);
            tasksLoaded = true;
        }
        if (data.tasks_available !== undefined)
            tasksAvailable = !!data.tasks_available;

        if (data.entries)
            entries = data.entries.map(Model.normalizeEntry);

        refreshLabel();
    }

    function stop() {
        if (current)
            request("stop", {
            "workspace_id": current.workspaceId || selectedWorkspaceId,
            "entry_id": current.id
        });

    }

    function continueEntry(entry) {
        request("continue", {
            "workspace_id": selectedWorkspaceId || entry.workspaceId,
            "entry": entry
        });
    }

    function ensureVisible(item) {
        if (opened)
            focusScope.ensureVisible(item);

    }

    function setScope(name) {
        if (["timer", "day", "cal"].indexOf(name) === -1)
            return ;

        scopeScroll[scope] = contentFlick.contentY;
        root.scope = name;
        Qt.callLater(function() {
            contentFlick.contentY = Math.max(0, Math.min(scopeScroll[name] || 0, contentFlick.contentHeight - contentFlick.height));
        });
        if (name === "day" && !root.dayLoaded)
            root.loadDay();

        if (name === "cal" && !root.calendarLoaded)
            root.loadCalendarRange();

    }

    function clampCalendarRange(value) {
        return ["week", "fortnight", "month"].indexOf(value) >= 0 ? value : "fortnight";
    }

    function parseAxisSetting(value) {
        if (value === "auto" || value === undefined || value === null || value === "")
            return "auto";

        var n = Number(value);
        return isFinite(n) ? n : "auto";
    }

    function loadCalendarRange() {
        if (selectedWorkspaceId <= 0) {
            noteClient("errors", "request_dropped", "range_entries");
            return ;
        }
        var bounds = Model.calendarRangeBounds(calendarRange, calendarAnchorDate);
        calendarError = "";
        request("range_entries", {
            "workspace_id": selectedWorkspaceId,
            "start_date": bounds.start,
            "end_date": bounds.end
        });
        // Only the week grid draws blocks; seven day_activity calls at most,
        // and only for days not already cached.
        if (calendarRange === "week")
            loadCalendarWeekBlocks(bounds);

    }

    function loadCalendarWeekBlocks(bounds) {
        var cursor = bounds.start;
        while (cursor <= bounds.end) {
            if (!calendarBlocksByDate[cursor] && cursor <= Model.todayDate())
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
            return ;

        calendarRange = next;
        persist({
            "calendarRange": calendarRange
        });
        calendarLoaded = false;
        calendarEntries = [];
        loadCalendarRange();
    }

    function cycleCalendarRange() {
        var ranges = ["week", "fortnight", "month"];
        setCalendarRange(ranges[(ranges.indexOf(calendarRange) + 1) % ranges.length]);
    }

    function shiftCalendarRange(direction) {
        // Never offer a move that would produce a 400 (spec 8.4).
        if (direction < 0 && !calendarCanPageBackward)
            return ;

        calendarAnchorDate = Model.shiftCalendarAnchor(calendarRange, calendarAnchorDate, direction);
        var dates = calendarGridDates.map(function(d) {
            return d.date;
        });
        if (dates.indexOf(calendarCursorDate) === -1)
            calendarCursorDate = dates[0];

        calendarLoaded = false;
        calendarEntries = [];
        loadCalendarRange();
    }

    function moveCalendarCursor(dx, dy) {
        var dates = calendarGridDates.map(function(d) {
            return d.date;
        });
        var index = dates.indexOf(calendarCursorDate);
        if (index < 0)
            index = 0;

        index = Math.max(0, Math.min(dates.length - 1, index + dx + (calendarRange === "week" ? 0 : dy * 7)));
        calendarCursorDate = dates[index];
    }

    function openCalendarCursorDay() {
        root.scope = "day";
        root.commandText = "";
        root.showDay(calendarCursorDate);
    }

    function setCalendarAxisOverride(edge, hours) {
        var candidateStart = edge === "start" ? hours : calendarDayStart;
        var candidateEnd = edge === "end" ? hours : calendarDayEnd;
        var effectiveStart = candidateStart === "auto" ? calendarAxis.start : candidateStart;
        var effectiveEnd = candidateEnd === "auto" ? calendarAxis.end : candidateEnd;
        // Rejected at the field, not on save (spec 8.1): the previous value stands.
        if (!Model.axisOverrideValid(effectiveStart, effectiveEnd))
            return false;

        if (edge === "start")
            calendarDayStart = hours;
        else
            calendarDayEnd = hours;
        persist({
            "calendarDayStart": calendarDayStart,
            "calendarDayEnd": calendarDayEnd
        });
        return true;
    }

    function resetCalendarAxis() {
        calendarDayStart = "auto";
        calendarDayEnd = "auto";
        persist({
            "calendarDayStart": "auto",
            "calendarDayEnd": "auto"
        });
    }

    // One cursor key for every scope (ruling R-AQ): the arrows do not need to
    // know which list is on screen.
    function moveCursor(delta) {
        if (scope === "day")
            moveDayCursor(delta);
        else if (scope === "cal")
            moveCalendarCursor(0, delta);
        else
            moveResultCursor(delta);
    }

    // Left and right mean "the period either side of this one": the day before
    // or after in the day scope, the previous or next week/fortnight/month in
    // the calendar. The timer scope has no period, so they do nothing there.
    function shiftPeriod(delta) {
        if (scope === "day")
            shiftDay(delta);
        else if (scope === "cal")
            shiftCalendarRange(delta);
    }

    function showCalendarToday() {
        calendarAnchorDate = Model.todayDate();
        calendarCursorDate = Model.todayDate();
        calendarLoaded = false;
        calendarEntries = [];
        loadCalendarRange();
    }

    function moveResultCursor(delta) {
        // Stage 4 of the redesign slots dayScope.moveCursor() into this
        // same switch for root.scope === "day" -- see R-C. Do not re-wire
        // the caller when that lands; add the branch here.
        if (root.scope !== "timer")
            return ;

        var count = root.commandRows.length;
        if (!count)
            return ;

        root.resultCursorIndex = (root.resultCursorIndex + delta + count) % count;
    }

    function acceptCompletion() {
        var completion = root.commandParsed.completion;
        // Model.parseCommand is the source of the guarantee this checks:
        // it now returns completion: "" for every @ token, matched or not
        // (spec 6.5, amended 2026-09-04), precisely so a name is never
        // completed into commandText -- a short fragment of a multi-word
        // name (e.g. "@Nor" against "Northwind Renovations") used to slice a
        // tail that itself contained a space. This check is belt-and-braces
        // on top of that fix, not the fix itself -- do NOT delete it as
        // redundant; it is what keeps a future non-@ or non-parseCommand
        // source of `completion` from reintroducing the same defect here.
        if (completion && !/\s/.test(completion))
            root.commandText = root.commandText + completion;

    }

    function startFromCommand(parsed) {
        if (!parsed.description.trim() && !parsed.projectId)
            return ;

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

    // Enter on a PROJ row (spec 6.5 "Binding is state, not text"): the id
    // moves into panel state and the @frag token that produced the row is
    // removed from commandText -- never replaced with project.name, which
    // is exactly the circular defect this stage exists to remove. A new
    // project always clears any previously bound task, since a task never
    // outlives its project. Model.bindProject computes all three fields
    // (commandText, boundProjectId, boundTaskId) in one pure call, rather
    // than this function juggling them itself (stage 3b fix round 2,
    // finding D3): assigning commandText below may fire
    // onCommandTextChanged, which reads the OLD boundProjectId/boundTaskId
    // still in place and can momentarily clear them, but the two lines
    // after always overwrite that with this call's own correct ids --
    // unconditionally, regardless of whether that handler ran at all,
    // which is exactly the property it needs: nothing here can leak into
    // a later, unrelated bind.
    function bindProject(project) {
        var next = Model.bindProject(root.commandText, project);
        root.commandText = next.commandText;
        root.boundProjectId = next.boundProjectId;
        root.boundTaskId = next.boundTaskId;
    }

    // Enter on a TASK row: same idea, via Model.bindTask.
    function bindTask(task) {
        var next = Model.bindTask(root.commandText, root.boundProjectId, task);
        root.commandText = next.commandText;
        root.boundProjectId = next.boundProjectId;
        root.boundTaskId = next.boundTaskId;
    }

    function jumpToBlock(block) {
        // dayDate is left untouched: a BLOCK-kind row only ever comes from
        // root.dayBlocks, which already belongs to root.dayDate, so there is
        // nothing to reconcile.
        root.scope = "day";
        // The text that found this row is a timer-scope search; left in place
        // it would become the day filter and could hide the very block we jumped to.
        root.commandText = "";
        root.dayCursorIndex = root.dayBlocks.indexOf(block);
    }

    function activateSelectedRow() {
        // Same guard as moveResultCursor: commandRows and resultCursorIndex
        // exist regardless of scope (only ui/TimerScope.qml hides the rows
        // outside "timer"), so without this an off-screen row -- e.g. the
        // most recent entry's CONT row -- could be activated from day or cal
        // scope. Stage 4 slots its own day branch in beside this one.
        if (root.scope === "cal") {
            if (root.commandText === "")
                root.openCalendarCursorDay();

            return ;
        }
        if (root.scope === "day") {
            // Enter on the day list applies the cursor row when it is ready
            // (spec 7.5). Text in the field is a filter, not a description, so
            // Enter with text typed does nothing rather than start a timer.
            if (root.commandText === "")
                root.applyBlock(root.dayCursorBlock());

            return ;
        }
        if (root.scope !== "timer")
            return ;

        var row = root.commandRows[root.resultCursorIndex];
        if (!row)
            return ;

        if (row.kind === "start")
            root.startFromCommand(row.target);
        else if (row.kind === "continue")
            root.continueEntry(row.target);
        else if (row.kind === "project")
            root.bindProject(row.target);
        else if (row.kind === "task")
            root.bindTask(row.target);
        else if (row.kind === "block")
            root.jumpToBlock(row.target);
    }

    function refreshLabel() {
        elapsedLabel = current ? Model.timerLabel(current, Date.now()) : "—";
        barLabel = current ? elapsedLabel + "  " + Model.compactDescription(current.description, 24) : "Toggl";
    }

    function switchPanel(direction) {
        return bar && typeof bar.switchPanelFrom === "function" ? bar.switchPanelFrom(barIdentity, direction) : false;
    }

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

    function showDay(date) {
        dayDate = date;
        dayLoaded = false;
        dayBlocks = [];
        daySummary = Model.blockSummary([]);
        loadDay();
    }

    function shiftDay(days) {
        var target = Model.boundedShiftDate(dayDate, days);
        if (target !== dayDate)
            showDay(target);

    }

    function slotChanged() {
        dayRevision += 1;
    }

    function mutateBlock(block, apply) {
        apply();
        block.editRevision = (block.editRevision || 0) + 1;
        // A dozen blocks: recomputing beats maintaining a delta over seven counters.
        root.daySummary = Model.blockSummary(root.dayBlocks);
        root.dayRevision += 1;
    }

    // Tab walks the description candidates on the cursor row: the model's
    // phrasing, the user's own past wording, then the window title (R-AP).
    function cycleBlockDescription(delta) {
        var block = dayVisibleBlocks[dayCursorIndex];
        if (!block || block.state !== "pending")
            return false;

        var picked = null;
        mutateBlock(block, function() {
            picked = Model.cycleDescription(block, delta);
        });
        return !!picked;
    }

    // Touching a row confirms a classifier guess: the ~ disappears (spec 7.1).
    function confirmGuess(block) {
        if (block && block.guessed)
            block.guessed = false;

    }

    // Two independent drawers (spec 7.2). Any number may be open; the old
    // toggleBlock collapsed every sibling, so comparing two blocks took four clicks.
    function toggleInspect(block) {
        if (!block)
            return ;

        mutateBlock(block, function() {
            block.inspecting = !block.inspecting;
        });
    }

    function toggleEdit(block) {
        if (!block)
            return ;

        mutateBlock(block, function() {
            block.editing = !block.editing;
            confirmGuess(block);
        });
        if (!block.editing)
            cmdInput.forceActiveFocus();

    }

    // Escape inside a drawer field: shut the drawer and hand the keyboard back
    // to the command line, where the row keys live.
    function closeEdit(block) {
        if (block && block.editing)
            mutateBlock(block, function() {
            block.editing = false;
        });

        cmdInput.forceActiveFocus();
    }

    // Session-local dismissal (R-N): pending rows only, stays visible, still
    // counts toward the total, and Enter still applies it if the user insists.
    function skipBlock(block) {
        if (!block || block.state !== "pending" || block.busy)
            return ;

        mutateBlock(block, function() {
            block.skipped = !block.skipped;
        });
    }

    function setBlockDescription(block, text) {
        mutateBlock(block, function() {
            block.description = text;
            confirmGuess(block);
        });
    }

    // The edit drawer's project/task field speaks the command line's grammar.
    // "@acme/backend" binds both; a fragment ranks fuzzily and takes the top
    // hit, exactly as the command line's PROJ rows would.
    function resolveBlockToken(block, text) {
        var parsed = Model.parseCommand(String(text || ""), root.projects, root.tasks, root.tags);
        var projectId = parsed.projectId;
        var taskId = parsed.taskId;
        if (!projectId) {
            var frag = String(text || "").replace(/^\s*@/, "").split("/")[0];
            var top = Model.rankProjects(root.projects, frag)[0];
            if (top)
                projectId = Number(top.id) || 0;

        }
        if (projectId && !taskId) {
            var tfrag = String(text || "").indexOf("/") !== -1 ? String(text || "").split("/").pop() : "";
            if (tfrag) {
                var ttop = Model.rankTasks(root.tasks, projectId, tfrag)[0];
                if (ttop)
                    taskId = Number(ttop.id) || 0;

            }
        }
        mutateBlock(block, function() {
            block.projectId = projectId;
            block.taskId = taskId;
            confirmGuess(block);
        });
    }

    function blockReady(block) {
        return Model.blockReady(block);
    }

    // ---- day cursor (R-B declared it in stage 3; stage 4 gives it meaning) ---
    function dayCursorBlock() {
        var rows = root.dayVisibleBlocks;
        return rows[root.dayCursorIndex] || null;
    }

    function setDayCursor(index) {
        var count = root.dayVisibleBlocks.length;
        root.dayCursorIndex = count ? Math.max(0, Math.min(count - 1, index)) : -1;
    }

    function moveDayCursor(delta) {
        var count = root.dayVisibleBlocks.length;
        if (!count) {
            root.dayCursorIndex = -1;
            return ;
        }
        var start = root.dayCursorIndex < 0 ? (delta > 0 ? -1 : 0) : root.dayCursorIndex;
        root.dayCursorIndex = (start + delta + count) % count;
    }

    function submitBlock(block) {
        if (!blockReady(block))
            return false;

        mutateBlock(block, function() {
            block.busy = true;
            block.failure = "";
        });
        request("create_entry", {
            "workspace_id": selectedWorkspaceId,
            "start": block.start,
            "duration": Math.max(1, Math.floor(Number(block.seconds) || 0)),
            "description": String(block.description).trim(),
            "project_id": block.projectId || null,
            "task_id": block.taskId || null,
            "tags": [],
            "billable": false,
            "block": {
                "seconds": Math.max(0, Math.floor(Number(block.seconds) || 0)),
                "label": block.label,
                "topics": block.topics,
                "apps": block.apps,
                "domains": block.domains,
                "domain": block.domain
            },
            "suggested": Model.suggestionFor(block)
        });
        return true;
    }

    function pumpApplyQueue() {
        while (applyQueue.length) {
            var block = applyQueue.shift();
            if (submitBlock(block))
                return true;

        }
        return false;
    }

    function applyBlock(block) {
        if (requestPending || !blockReady(block))
            return ;

        applyQueue = [];
        submitBlock(block);
        cmdInput.forceActiveFocus();
    }

    function applyAssigned() {
        if (requestPending)
            return ;

        applyQueue = dayBlocks.filter(blockReady);
        pumpApplyQueue();
    }

    function finishBlock(block, state, failure) {
        if (!block)
            return ;

        mutateBlock(block, function() {
            block.busy = false;
            block.state = state;
            block.failure = failure || "";
        });
    }

    function pendingSlot() {
        for (var i = 0; i < dayBlocks.length; i++) {
            if (dayBlocks[i].busy)
                return dayBlocks[i];

        }
        return null;
    }

    function handleResponse(raw) {
        handleResponseBody(raw);
        Qt.callLater(root.pumpQueue);
    }

    function handleResponseBody(raw) {
        var action = pendingAction;
        requestPending = false;
        pendingAction = "";
        manualRefresh = false;
        lostClientLog = [];
        try {
            var response = JSON.parse(String(raw || "").trim());
            if (!response.ok) {
                var message = (response.error || {
                }).message || "Toggl could not complete that request.";
                if (action === "day_activity") {
                    status = "ready";
                    // A week-grid prefetch failing for another date must not
                    // blank an already-loaded day scope.
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
                if (action === "classify") {
                    // The backend already degrades to ok:true on every transport
                    // failure; this is only a validation error, and even that
                    // must not surface -- the day is loaded and editable.
                    status = "ready";
                    return ;
                }
                if (action === "create_entry") {
                    status = "ready";
                    finishBlock(pendingSlot(), "pending", message);
                    pumpApplyQueue();
                    return ;
                }
                errorStatus = Number((response.error || {
                }).status) || 0;
                // A 404 on stop or update is proof that the entry is gone --
                // stopped and deleted in the web app, or removed by another
                // client. The panel would otherwise keep painting a running
                // strip for it indefinitely, and every retry would 404 again,
                // because nothing else clears `current` on an error path.
                // Re-sync so the strip reflects what Toggl actually has.
                // "update" is dormant, not dead (F9, final review): nothing
                // currently dispatches request("update", ...) -- updateCurrent
                // was deleted along with the entry composer -- so this half of
                // the condition waits for a future stage's edit affordance.
                // Harmless to leave in place; it costs nothing while unused.
                if (errorStatus === 404 && (action === "stop" || action === "update")) {
                    current = null;
                    status = "ready";
                    errorMessage = "";
                    sync(false, false);
                    return ;
                }
                status = "error";
                errorMessage = message;
                return ;
            }
            if (action === "day_activity") {
                status = "ready";
                var prepared = Model.prepareBlocks(response.data.blocks, response.data.entries);
                var rawBlocks = Array.isArray(response.data.blocks) ? response.data.blocks : [];
                // Cache every day's blocks for the calendar, keyed by the
                // response's own date -- several may be in flight in sequence.
                var byDate = calendarBlocksByDate;
                byDate[response.data.date] = {
                    "raw": rawBlocks,
                    "prepared": prepared
                };
                calendarBlocksByDate = Object.assign({
                }, byDate);
                if (response.data.date === dayDate) {
                    dayLoaded = true;
                    // Guesses from the user's own past first (ruling R-AK), then a
                    // project code or distinctive word in the block's topics
                    // (ruling R-AJ); both land as ~ before the classifier is asked,
                    // and the classifier leaves guessed blocks alone.
                    Model.applyHistoryGuesses(prepared);
                    Model.applyProjectGuesses(prepared, projects);
                    dayBlocks = prepared;
                    daySummary = Model.blockSummary(dayBlocks);
                    slotChanged();
                    classifyDay();
                }
                return ;
            }
            if (action === "classify") {
                status = "ready";
                if (response.data)
                    applyClassifyResults(response.data.results);

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
            if (action === "create_entry") {
                status = "ready";
                finishBlock(pendingSlot(), "applied", "");
                classifyDay();
                pumpApplyQueue();
                return ;
            }
            status = "ready";
            applyData(response.data);
            if (response.data && response.data.cache !== undefined)
                cacheInfo = response.data.cache;

            if (action === "bootstrap") {
                if (response.data && response.data.workspace_id)
                    root.selectedWorkspaceId = Number(response.data.workspace_id) || 0;

                root.persist({
                    "workspaceId": root.selectedWorkspaceId
                });
                if (!root.selectedWorkspaceId)
                    root.chooseWorkspace();

                if (response.data && response.data.sync_failed)
                    root.sync(false, true);

                if (root.scope === "day" && !root.dayLoaded)
                    root.loadDay();

                if (root.scope === "cal" && !root.calendarLoaded)
                    root.loadCalendarRange();

            } else if (action === "sync") {
                if (scope === "day" && !dayLoaded)
                    loadDay();

            } else if (["start", "stop", "update", "continue"].indexOf(action) >= 0) {
                // Same "update" note as the 404 branch above (F9): dormant
                // until a future stage adds an edit affordance, harmless
                // meanwhile.
                sync(false, false);
            }
        } catch (error) {
            status = "error";
            errorMessage = "Toggl returned an unreadable response.";
            noteClient("errors", "parse_failure", "");
        }
    }

    function idleNotice() {
        if (idleNotified || !current || idleReminderMinutes < 1)
            return ;

        idleNotified = true;
        idleNotify.command = ["notify-send", "Toggl Track", "You have been idle while a timer is running."];
        idleNotify.running = true;
    }

    // So skip a START row with nothing to start, whenever any other row exists.
    // A row that cannot be meaningfully activated must never be the default
    // target of the activate key.
    function defaultCursorIndex() {
        var rows = root.commandRows;
        if (!rows || rows.length < 2)
            return 0;

        var first = rows[0];
        if (first.kind === "start" && !String(first.label || "").trim())
            return 1;

        return 0;
    }

    onDayBlocksChanged: dayGeneration += 1
    onDayDateChanged: dayGeneration += 1
    onSelectedWorkspaceIdChanged: dayGeneration += 1
    moduleName: "daz.toggl-track"
    ipcTarget: "daz.toggl-track"
    manageIpc: false
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
        var chosen = String(setting("classifier", "off"));
        classifier = classifierChoices.indexOf(chosen) >= 0 ? chosen : "off";
    }
    // commandRows also mutates on background sync (root.entries) and day
    // load (root.dayBlocks), not only when commandText changes. Resetting
    // only on text change left a same-length reorder pointing the cursor at
    // a slot that now holds a different row -- Enter would activate
    // something other than what was visually highlighted. Resetting
    // whenever the row set itself changes covers both cases.
    onCommandRowsChanged: root.resultCursorIndex = root.defaultCursorIndex()
    onDayVisibleBlocksChanged: root.setDayCursor(root.dayCursorIndex < 0 ? 0 : root.dayCursorIndex)
    // Reads root.commandText itself rather than declaring a parameter (F1,
    // final review): a property-change signal is declared `void
    // commandTextChanged()` with no argument, so a `function(text)` handler
    // here always saw `text === undefined`, and `undefined === ""` is
    // false -- the clear-both-bindings path never ran. R-S's standing
    // constraint "signal handlers declare their parameters" is about real
    // signals (e.g. a ButtonGroup's onChanged(value)); a <property>Changed
    // handler carries no parameter to declare, and applying the rule here
    // is what produced this defect.
    onCommandTextChanged: {
        var next = Model.bindingsAfterTextEdit(root.commandText, root.boundProjectId, root.boundTaskId);
        root.boundProjectId = next.boundProjectId;
        root.boundTaskId = next.boundTaskId;
    }
    Component.onCompleted: {
        status = "idle";
        bootstrap();
    }

    PanelTheme {
        id: panelTheme
    }

    Timer {
        interval: 1000
        running: !!root.current
        repeat: true
        onTriggered: root.refreshLabel()
    }

    IdleMonitor {
        id: idleMonitor

        enabled: !!root.current && root.idleReminderMinutes > 0
        timeout: root.idleReminderMinutes * 60
        onIsIdleChanged: {
            if (isIdle)
                root.idleNotice();
            else
                root.idleNotified = false;
        }
    }

    Process {
        id: idleNotify
    }

    Timer {
        id: aiDeadline

        interval: 21000
        repeat: false
        onTriggered: {
            aiProc.expired = true;
            aiProc.running = false;
        }
    }

    Process {
        id: aiProc

        property string response: ""
        property bool expired: false

        command: ["python3", String(Qt.resolvedUrl("toggl_api.py")).replace(/^file:\/\//, "")]
        stdinEnabled: true
        onStarted: {
            write(JSON.stringify(root.enrichmentActive) + "\n");
            aiDeadline.restart();
        }
        onExited: function(code) {
            aiDeadline.stop();
            Qt.callLater(function() {
                root.finishEnrichment(aiProc.response);
            });
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: aiProc.response = text
        }

    }

    Process {
        id: apiProc

        property string request: ""

        command: ["python3", String(Qt.resolvedUrl("toggl_api.py")).replace(/^file:\/\//, "")]
        stdinEnabled: true
        onStarted: {
            write(request + "\n");
            request = "";
        }
        onExited: function(code) {
            if (code !== 0 && root.requestPending) {
                root.requestPending = false;
                root.manualRefresh = false;
                root.status = "error";
                root.errorMessage = "The Toggl helper is unavailable.";
                if (root.lostClientLog.length > 0) {
                    root.clientLog = root.lostClientLog.concat(root.clientLog);
                    root.lostClientLog = [];
                }
                Qt.callLater(root.pumpQueue);
            }
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.handleResponse(text)
        }

    }

    KeyboardPanel {
        id: panel

        anchorItem: root.anchorItem
        owner: root.barIdentity
        bar: root.bar
        open: root.opened
        centerOnBar: true
        focusTarget: keyCatcher
        contentWidth: fittedContentWidth(Style.space(560))
        contentHeight: fittedContentHeight(contentColumn.implicitHeight)

        FocusScope {
            id: focusScope

            // Keyboard navigation must not walk the cursor off screen: every
            // scope calls this when its cursor row moves, and the view follows
            // only when that row is actually out of sight.
            function ensureVisible(item) {
                if (!item || !item.height)
                    return ;

                var top = item.mapToItem(contentColumn, 0, 0).y;
                var bottom = top + item.height;
                var margin = Style.spacing.rowGap;
                var limit = Math.max(0, contentFlick.contentHeight - contentFlick.height);
                if (top - margin < contentFlick.contentY)
                    contentFlick.contentY = Math.max(0, top - margin);
                else if (bottom + margin > contentFlick.contentY + contentFlick.height)
                    contentFlick.contentY = Math.min(limit, bottom + margin - contentFlick.height);
            }

            function scrollBy(delta) {
                var limit = contentFlick.contentHeight - contentFlick.height;
                if (limit <= 0)
                    return ;

                contentFlick.contentY = Math.max(0, Math.min(limit, contentFlick.contentY + delta));
            }

            anchors.fill: parent
            focus: true
            // Page/Home/End are handled here, after keyCatcher, so they bubble
            // past it — it only consumes Esc, Tab, Enter, j/k/h/l, x and text.
            Keys.priority: Keys.AfterItem
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_PageDown) {
                    focusScope.scrollBy(contentFlick.height * 0.9);
                    event.accepted = true;
                } else if (event.key === Qt.Key_PageUp) {
                    focusScope.scrollBy(-contentFlick.height * 0.9);
                    event.accepted = true;
                } else if (event.key === Qt.Key_Home) {
                    contentFlick.contentY = 0;
                    event.accepted = true;
                } else if (event.key === Qt.Key_End) {
                    focusScope.scrollBy(contentFlick.contentHeight);
                    event.accepted = true;
                }
            }

            HelpOverlay {
                root: root
                panelTheme: panelTheme
            }

            PanelKeyCatcher {
                id: keyCatcher

                anchors.fill: parent
                // Without this the catcher eats j/k/h/l/x before any focused
                // editor sees them, so those letters cannot be typed into a
                // description. Day slots add one editor per row, so detect the
                // focused item rather than naming each field.
                blocked: root.editorFocused
                onCloseRequested: root.close()
                onTabRequested: function(direction) {
                    root.switchPanel(direction);
                }
                // root.start() no longer exists -- the command line's own
                // highlighted row is the equivalent action now, same as
                // cmdInput's onAccepted below (this only fires when no text
                // editor holds focus, since keyCatcher stands down otherwise).
                onReturnRequested: root.activateSelectedRow()

                Flickable {
                    id: contentFlick

                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: contentColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height

                    ColumnLayout {
                        id: contentColumn

                        width: parent.width
                        spacing: Style.spacing.panelGap

                        ColumnLayout {
                            visible: root.settingsOpen
                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            PanelSectionHeader {
                                text: root.scope === "day" ? "DAY SETTINGS" : (root.scope === "cal" ? "CALENDAR SETTINGS" : "TIMER SETTINGS")
                                foreground: root.foreground
                            }

                            Text {
                                visible: root.scope === "timer"
                                text: "WORKSPACE"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.scope === "timer"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: root.workspaces.map(function(w) {
                                    return {
                                        "value": String(w.id),
                                        "label": w.name || w.workspace_name
                                    };
                                })
                                value: String(root.selectedWorkspaceId)
                                onChanged: function(value) {
                                    root.setWorkspace(value);
                                }
                            }

                            Text {
                                visible: root.scope === "timer"
                                text: "HISTORY (DAYS)"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.scope === "timer"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: ["30", "60", "90"]
                                value: String(root.historyDays)
                                onChanged: function(value) {
                                    root.setHistory(value);
                                }
                            }

                            Text {
                                visible: root.scope === "timer"
                                text: "IDLE REMINDER"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.scope === "timer"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: ["Off", "5m", "10m", "15m", "30m"]
                                value: root.idleReminderMinutes ? root.idleReminderMinutes + "m" : "Off"
                                onChanged: function(value) {
                                    root.setReminder(value === "Off" ? 0 : value.slice(0, -1));
                                }
                            }

                            Text {
                                visible: root.scope === "timer"
                                text: "LOG DETAIL"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                visible: root.scope === "timer"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: ["Off", "Errors", "Info", "Debug"]
                                value: root.logLevel.charAt(0).toUpperCase() + root.logLevel.slice(1)
                                onChanged: function(value) {
                                    root.setLogLevel(value.toLowerCase());
                                }
                            }

                            Text {
                                visible: root.scope === "timer" && root.logLevel === "debug"
                                Layout.fillWidth: true
                                text: "Debug records window titles and entry descriptions in the plugin's log."
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                visible: root.scope === "timer"
                                text: "CLASSIFIER"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                            }

                            ButtonGroup {
                                // R-M: mirrors LOG DETAIL. Off / Local.
                                visible: root.scope === "timer"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: ["Off", "Local"]
                                value: root.classifier.charAt(0).toUpperCase() + root.classifier.slice(1)
                                onChanged: function(value) {
                                    root.setClassifier(value.toLowerCase());
                                }
                            }

                            Text {
                                visible: root.scope === "timer" && root.classifier === "local"
                                Layout.fillWidth: true
                                text: "The local model reads window titles to name and assign day blocks. Titles never leave this machine. Install it with ./setup."
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                visible: root.scope === "day"
                                text: "BREAK — a pause at least this long starts a new block"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            ButtonGroup {
                                visible: root.scope === "day"
                                foreground: root.foreground
                                background: panelTheme.surface
                                options: ["2m", "5m", "10m", "15m"]
                                value: root.dayBlockMinutes + "m"
                                onChanged: function(value) {
                                    root.setDayBlockMinutes(value.slice(0, -1));
                                }
                            }

                            PanelSeparator {
                                // PanelSeparator sets width: parent.width, which a
                                // ColumnLayout overrides -- without this it falls back
                                // to implicitWidth 100 and renders as a stub.
                                Layout.fillWidth: true
                                foreground: root.foreground
                            }

                        }

                        Item {
                            id: runningStrip

                            // Guide's .running is timer-scope-only content, above .cmd, and
                            // only appears at all when a timer is running -- moved out of
                            // ui/TimerScope.qml (whose rows and hints stay below .cmd) so the
                            // panel's vertical order matches design-guide.html:426-448 exactly
                            // (finding 2): .running, .sep, .cmd, .rows, .sep, .hints.
                            visible: root.scope === "timer" && !!root.current
                            Layout.fillWidth: true
                            implicitHeight: runningRow.implicitHeight

                            RowLayout {
                                id: runningRow

                                anchors.left: parent.left
                                anchors.right: parent.right
                                spacing: Style.spacing.rowGap

                                Rectangle {
                                    implicitWidth: 7
                                    implicitHeight: 7
                                    color: panelTheme.accent
                                }

                                Text {
                                    text: root.elapsedLabel
                                    color: panelTheme.accent
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                    font.weight: Font.Medium
                                }

                                Text {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    text: root.current ? root.current.description : ""
                                    color: panelTheme.text
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: root.current ? (root.current.projectName + (root.current.taskName ? " \u00b7 " + root.current.taskName : "")) : ""
                                    // --dim18 -> textDisabled, not textFaint --
                                    // stage 2's colour table is authoritative
                                    // (see docs/plans/2026-09-04-stage-3-
                                    // command-line-and-scopes.md's corrected
                                    // Global Constraints entry).
                                    color: panelTheme.textDisabled
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                }

                            }

                        }

                        PanelSeparator {
                            // PanelSeparator sets width: parent.width, which a
                            // ColumnLayout overrides -- without this it falls back
                            // to implicitWidth 100 and renders as a stub.
                            Layout.fillWidth: true
                            visible: root.scope === "timer" && !!root.current
                            foreground: root.foreground
                        }

                        DayHeader {
                            id: dayHeader

                            root: root
                            panelTheme: panelTheme
                        }

                        // The command line and the panel's three action buttons share one row
                        // (ruling R-AI): the guide's .cmd is the first thing in every scope, and
                        // a chrome row above it was pure whitespace.
                        RowLayout {
                            id: cmdRow

                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            Rectangle {
                                id: cmdBox

                                Layout.fillWidth: true
                                implicitHeight: Style.spacing.controlHeight
                                color: Style.normalFill
                                border.color: panelTheme.accent
                                border.width: 1
                                radius: Style.cornerRadius

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: Style.spacing.controlPaddingX
                                    anchors.rightMargin: Style.spacing.controlPaddingX
                                    spacing: Style.spacing.rowGap

                                    Text {
                                        text: "›"
                                        color: panelTheme.accent
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                        implicitHeight: cmdInput.implicitHeight
                                        // Guide's .cmd .txt is "overflow: hidden" -- without this
                                        // the coloured overlay below paints straight over the scope
                                        // chips once the command outgrows the field.
                                        clip: true

                                        TextInput {
                                            // Day scope, empty command line: Tab walks
                                            // the cursor row's description candidates
                                            // (ruling R-AP). Falls through to the panel
                                            // switch when there is no row to cycle.

                                            id: cmdInput

                                            anchors.fill: parent
                                            color: "transparent"
                                            selectionColor: panelTheme.accent
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.bodySmall
                                            clip: true
                                            focus: true
                                            cursorVisible: true
                                            text: root.commandText
                                            onTextChanged: root.commandText = text
                                            onAccepted: root.activateSelectedRow()
                                            Keys.onPressed: function(event) {
                                                if (event.key === Qt.Key_Escape) {
                                                    // The overlay is a layer over the panel, so the
                                                    // first Escape dismisses it and only the next
                                                    // one closes the panel.
                                                    if (root.helpOpen)
                                                        root.helpOpen = false;
                                                    else
                                                        root.close();
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                                                    // F7 (final review): Tab used to be swallowed
                                                    // unconditionally into acceptCompletion, which
                                                    // Model.parseCommand's spec-6.5 "completion is
                                                    // always \"\"" guarantee makes permanently a
                                                    // no-op -- so in the panel's default focus
                                                    // state (open() forceActiveFocus'es this field)
                                                    // Omarchy's own cross-panel Tab switch, which
                                                    // docs/2026-09-04-panel-redesign.md relies on,
                                                    // was unreachable. A real completion is still
                                                    // accepted here when one exists (dormant, not
                                                    // dead -- keeps the guide's "complete" hint
                                                    // truthful the moment a future token produces
                                                    // one); otherwise the key falls through to the
                                                    // panel switch PanelKeyCatcher would have done
                                                    // itself, had it not stood down for this focused
                                                    // editor. Direction mirrors
                                                    // PanelKeyCatcher.tabRequested's own rule.
                                                    // Branches on plain truthiness, not the
                                                    // whitespace guard -- acceptCompletion's own
                                                    // belt-and-braces check (see its comment) is
                                                    // still the one place that actually decides
                                                    // whether to insert; duplicating it here would
                                                    // only be a second copy of the same regex.
                                                    if (root.commandParsed.completion)
                                                        root.acceptCompletion();
                                                    else if (root.scope === "day" && root.commandText.length === 0 && root.cycleBlockDescription((event.modifiers & Qt.ShiftModifier) || event.key === Qt.Key_Backtab ? -1 : 1))
                                                        event.accepted = true;
                                                    else
                                                        root.switchPanel((event.modifiers & Qt.ShiftModifier) || event.key === Qt.Key_Backtab ? -1 : 1);
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                // Arrows work in every scope. Up/Down never type,
                                                // so they move the cursor whatever is in the command
                                                // line; Left/Right move the caret when there is text
                                                // and only then act as previous/next (ruling R-AQ).
                                                if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                                                    root.moveCursor(event.key === Qt.Key_Down ? 1 : -1);
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                if ((event.key === Qt.Key_Left || event.key === Qt.Key_Right) && root.commandText === "") {
                                                    root.shiftPeriod(event.key === Qt.Key_Right ? 1 : -1);
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                // ^? and, on an empty line, a bare ? -- both reach
                                                // the same overlay.
                                                if (event.key === Qt.Key_Question && ((event.modifiers & Qt.ControlModifier) || root.commandText === "")) {
                                                    root.helpOpen = !root.helpOpen;
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                if (root.helpOpen && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                                                    root.helpOpen = false;
                                                    event.accepted = true;
                                                    return ;
                                                }
                                                if (root.scope === "cal" && root.commandText === "" && !(event.modifiers & Qt.ControlModifier)) {
                                                    // Spec 8: hjkl move, w cycles the range, a opens
                                                    // the axis settings (week only). Same rule as the
                                                    // day scope: only while the filter line is empty.
                                                    var calKeys = {
                                                    };
                                                    calKeys[Qt.Key_H] = function() {
                                                        root.moveCalendarCursor(-1, 0);
                                                    };
                                                    calKeys[Qt.Key_L] = function() {
                                                        root.moveCalendarCursor(1, 0);
                                                    };
                                                    calKeys[Qt.Key_J] = function() {
                                                        root.moveCalendarCursor(0, 1);
                                                    };
                                                    calKeys[Qt.Key_K] = function() {
                                                        root.moveCalendarCursor(0, -1);
                                                    };
                                                    calKeys[Qt.Key_T] = function() {
                                                        root.showCalendarToday();
                                                    };
                                                    calKeys[Qt.Key_W] = function() {
                                                        root.cycleCalendarRange();
                                                    };
                                                    calKeys[Qt.Key_A] = function() {
                                                        if (root.calendarRange === "week")
                                                            root.calendarAxisOpen = !root.calendarAxisOpen;

                                                    };
                                                    if (calKeys[event.key]) {
                                                        calKeys[event.key]();
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                }
                                                if (root.scope === "day") {
                                                    // Spec 7.5. With text typed the field is a
                                                    // filter and these letters must type; with
                                                    // it empty they act on the cursor row.
                                                    var empty = root.commandText === "";
                                                    var shift = !!(event.modifiers & Qt.ShiftModifier);
                                                    var ctrl = !!(event.modifiers & Qt.ControlModifier);
                                                    if (empty && !ctrl && (event.key === Qt.Key_H || event.key === Qt.Key_L)) {
                                                        root.shiftDay(event.key === Qt.Key_L ? 1 : -1);
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (empty && !ctrl && event.key === Qt.Key_T) {
                                                        root.showDay(Model.todayDate());
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (empty && !ctrl && (event.key === Qt.Key_J || event.key === Qt.Key_K)) {
                                                        // Bare j/k on an empty command line, exactly
                                                        // as the calendar scope already does it;
                                                        // ^j/^k keep working while typing a filter.
                                                        root.moveDayCursor(event.key === Qt.Key_J ? 1 : -1);
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (ctrl && event.key === Qt.Key_J) {
                                                        root.moveDayCursor(1);
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (ctrl && event.key === Qt.Key_K) {
                                                        root.moveDayCursor(-1);
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (shift && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                                                        root.applyAssigned();
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (empty && event.key === Qt.Key_Space) {
                                                        root.toggleInspect(root.dayCursorBlock());
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (empty && event.key === Qt.Key_E && !ctrl) {
                                                        root.toggleEdit(root.dayCursorBlock());
                                                        event.accepted = true;
                                                        return ;
                                                    }
                                                    if (empty && event.key === Qt.Key_Backspace) {
                                                        root.skipBlock(root.dayCursorBlock());
                                                        event.accepted = true;
                                                        return ;
                                                    }
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
                                                } else if (event.key === Qt.Key_R) {
                                                    if (root.scope === "day")
                                                        root.loadDay();
                                                    else
                                                        root.sync(true, false);
                                                } else if (event.key === Qt.Key_Comma) {
                                                    root.settingsOpen = !root.settingsOpen;
                                                } else if (event.key === Qt.Key_O) {
                                                    root.openWeb();
                                                } else if (event.key === Qt.Key_S) {
                                                    root.stop();
                                                    event.accepted = true;
                                                }
                                            }

                                            cursorDelegate: Rectangle {
                                                width: 6.6
                                                height: 13
                                                color: panelTheme.text

                                                SequentialAnimation on opacity {
                                                    loops: Animation.Infinite
                                                    running: cmdInput.cursorVisible && cmdInput.activeFocus

                                                    PauseAnimation {
                                                        duration: 530
                                                    }

                                                    PropertyAction {
                                                        value: 0
                                                    }

                                                    PauseAnimation {
                                                        duration: 530
                                                    }

                                                    PropertyAction {
                                                        value: 1
                                                    }

                                                }

                                            }

                                        }

                                        // The unscrolled x of the caret, measured in the same font
                                        // cmdInput renders with -- cmdInput.cursorRectangle.x is
                                        // already clamped into [0, width] by TextInput's own
                                        // internal auto-scroll, so the difference between the two
                                        // is exactly that scroll offset (see the overlay's x below).
                                        TextMetrics {
                                            id: cursorMetrics

                                            font: cmdInput.font
                                            text: cmdInput.text.slice(0, cmdInput.cursorPosition)
                                        }

                                        Text {
                                            // No PanelTheme/Color role exists for warn/ok --
                                            // literal per the guide, see this plan's open
                                            // questions.
                                            // Escapes everything that reaches the overlay,
                                            // segments and ghost alike. Both are project and
                                            // task names -- server data -- and concatenating
                                            // either one raw let a project called "R&D"
                                            // corrupt the markup.

                                            // &nbsp;, not a literal space: StyledText is a
                                            // QTextDocument mini-HTML subset, and plain HTML
                                            // whitespace collapses runs of spaces down to one --
                                            // the guide's .cmd .txt is "white-space: pre".
                                            function escapeSpan(raw) {
                                                return String(raw).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/ /g, "&nbsp;");
                                            }

                                            // Not anchors.fill: this must be free to sit outside
                                            // [0, parent.width] so it can track cmdInput's own
                                            // horizontal scroll (the parent Item's clip: true above
                                            // hides whatever spills past the edges either way) --
                                            // otherwise a long command's colours and caret drift
                                            // out of alignment with what cmdInput actually scrolled
                                            // to (finding 5).
                                            y: 0
                                            height: parent.height
                                            width: implicitWidth
                                            x: cmdInput.cursorRectangle.x - cursorMetrics.advanceWidth
                                            textFormat: Text.StyledText
                                            font: cmdInput.font
                                            elide: Text.ElideNone
                                            text: {
                                                // Guide 02: the empty day-scope field reads `filter blocks`.
                                                if (root.scope === "day" && root.commandText === "")
                                                    return "<font color=\"" + panelTheme.textDisabled + "\">filter blocks</font>";

                                                if (root.scope === "cal" && root.commandText === "")
                                                    return "<font color=\"" + panelTheme.textDisabled + "\">filter by project or tag</font>";

                                                var segments = Model.commandSegments(root.commandText);
                                                var colorFor = {
                                                    "plain": panelTheme.text,
                                                    "proj": panelTheme.accent,
                                                    "tag": "#f9e2af",
                                                    "bill": "#a6e3a1"
                                                };
                                                var html = segments.map(function(segment) {
                                                    return "<font color=\"" + colorFor[segment.cls] + "\">" + escapeSpan(segment.text) + "</font>";
                                                }).join("");
                                                // The ghost is --dim18 -> textDisabled, not
                                                // textFaint: stage 2's colour table is the
                                                // authoritative one (see the corrected Global
                                                // Constraints entry in this stage's plan).
                                                // This is the OTHER consumer of
                                                // commandParsed.completion (acceptCompletion,
                                                // above, is the first) -- it renders whatever
                                                // Model.parseCommand returns with no gate of
                                                // its own, so it depends on parseCommand's
                                                // guarantee (spec 6.5) that completion is ""
                                                // for every @ token: nothing here ever paints
                                                // a ghost that Tab can't actually insert.
                                                if (root.commandParsed.completion)
                                                    html += "<font color=\"" + panelTheme.textDisabled + "\">" + escapeSpan(root.commandParsed.completion) + "</font>";

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
                                                    // .scope span is --dim18 -> textDisabled, not
                                                    // textFaint -- stage 2's colour table is
                                                    // authoritative (see docs/plans/2026-09-04-
                                                    // stage-3-command-line-and-scopes.md's corrected
                                                    // Global Constraints entry).
                                                    color: chip.on ? panelTheme.text : panelTheme.textDisabled
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

                            RowLayout {
                                // One control cluster, so the icons sit tighter
                                // than the gap between them and the command box.
                                spacing: 2

                                PanelActionButton {
                                    iconText: "?"
                                    tooltipText: "Keyboard help (^?)"
                                    size: Style.spacing.controlHeight
                                    foreground: root.helpOpen ? Color.accent : panelTheme.textMuted
                                    onClicked: root.helpOpen = !root.helpOpen
                                }

                                PanelActionButton {
                                    iconText: "󰑐"
                                    tooltipText: root.scope === "day" ? "Reload day" : "Refresh"
                                    size: Style.spacing.controlHeight
                                    foreground: Color.accent
                                    onClicked: root.scope === "day" ? root.loadDay() : root.sync(true, false)
                                }

                                PanelActionButton {
                                    iconText: "󰒓"
                                    tooltipText: root.settingsOpen ? "Hide settings" : "Settings"
                                    size: Style.spacing.controlHeight
                                    foreground: root.settingsOpen ? Color.accent : panelTheme.textMuted
                                    onClicked: root.settingsOpen = !root.settingsOpen
                                }

                                PanelActionButton {
                                    iconText: "󰖟"
                                    tooltipText: "Open Toggl web"
                                    size: Style.spacing.controlHeight
                                    foreground: Color.accent
                                    onClicked: root.openWeb()
                                }

                            }

                        }

                        TimerScope {
                            id: timerScope

                            root: root
                            panelTheme: panelTheme
                        }

                        Loader {
                            id: dayScopeLoader

                            property var panelRoot: root
                            property var theme: panelTheme

                            Layout.fillWidth: true
                            active: root.scope === "day"
                            visible: active

                            sourceComponent: Component {
                                DayScope {
                                    root: dayScopeLoader.panelRoot
                                    panelTheme: dayScopeLoader.theme
                                }

                            }

                        }

                        Loader {
                            id: calendarScopeLoader

                            property var panelRoot: root
                            property var theme: panelTheme

                            Layout.fillWidth: true
                            active: root.scope === "cal"
                            visible: active

                            sourceComponent: Component {
                                CalendarScope {
                                    root: calendarScopeLoader.panelRoot
                                    panelTheme: calendarScopeLoader.theme
                                }

                            }

                        }

                    }

                }

            }

        }

    }

}
