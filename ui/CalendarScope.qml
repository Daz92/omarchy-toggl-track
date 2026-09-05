// Calendar scope (spec 8, design-guide.html §04): three ranges that are not
// one grid at three sizes. Week draws a real time axis; fortnight a density
// strip per day; month a total and a project-colour stack. Project colours
// come from Toggl (project_color, meta=true) and are the one palette a theme
// must not override (spec 8.5).

import "../Model.js" as Model
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

// Presentation only. All state and requests live in Panel.qml.
Item {
    id: calendarScope

    required property var root
    required property var panelTheme
    // The guide's --warn (#f9e2af) for the ◌ unapplied flag; no theme role
    // exists for warn, same literal the day scope uses.
    readonly property color warn: "#f9e2af"
    readonly property color cellEdge: Util.alpha(panelTheme.text, 0.1)
    readonly property color weekendFill: Qt.rgba(0, 0, 0, 0.22)
    readonly property var entries: root.calendarFilteredEntries
    readonly property var dayTotals: Model.calendarDayTotals(entries)
    readonly property var conflictDates: Model.calendarConflictDates(entries)
    readonly property int rangeTotal: Model.calendarRangeTotal(entries)
    readonly property var dates: root.calendarGridDates
    readonly property var axis: root.calendarAxis
    readonly property string today: Model.todayDate()
    // Entries the axis clips -- only possible under an override (spec 8.1).
    readonly property int overflowCount: entries.filter(function(e) {
        var s = Model.hourOfDay(e.start), t = Model.hourOfDay(e.stop);
        return (s !== null && s < axis.start) || (t !== null && t > axis.end);
    }).length

    function entriesOn(date) {
        return entries.filter(function(e) {
            var d = new Date(e.start);
            return isFinite(d.getTime()) && Model.isoDate(d) === date;
        });
    }

    function blocksOn(date) {
        var perDay = root.calendarBlocksByDate[date];
        return perDay ? perDay.prepared : [];
    }

    function hasUnapplied(date) {
        return blocksOn(date).some(function(b) {
            return b.state === "pending";
        });
    }

    function projectColor(entry) {
        var c = String((entry && (entry.project_color || entry.projectColor)) || "");
        return /^#[0-9a-f]{6}$/i.test(c) ? c : panelTheme.accent;
    }

    function pad2(n) {
        return (n < 10 ? "0" : "") + n;
    }

    function axisLabel() {
        return pad2(axis.start) + ":00–" + pad2(axis.end) + ":00";
    }

    function axisModeLabel() {
        return axis.derived ? "automatic, from your tracked hours" : ("fixed, " + pad2(axis.start) + ":00 – " + pad2(axis.end) + ":00");
    }

    visible: root.scope === "cal"
    Layout.fillWidth: true
    implicitHeight: column.implicitHeight

    ColumnLayout {
        id: column

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.rowGap

        // ---- header: ‹ range › · W 2W M · total --------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            PanelActionButton {
                iconText: "‹"
                tooltipText: root.calendarCanPageBackward ? "Earlier" : Model.calendarFloorHint(calendarScope.today)
                size: Style.spacing.controlHeight
                enabled: root.calendarCanPageBackward
                foreground: root.calendarCanPageBackward ? root.foreground : Util.alpha(panelTheme.text, 0.18)
                onClicked: root.shiftCalendarRange(-1)
            }

            Text {
                text: Model.calendarHeaderLabel(root.calendarRange, root.calendarAnchorDate)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
            }

            PanelActionButton {
                iconText: "›"
                tooltipText: "Later"
                size: Style.spacing.controlHeight
                foreground: root.foreground
                onClicked: root.shiftCalendarRange(1)
            }

            Row {
                // .rangechips: W · 2W · M, the active one on the selected fill.
                spacing: 2

                Repeater {
                    model: [{
                        "id": "week",
                        "label": "W"
                    }, {
                        "id": "fortnight",
                        "label": "2W"
                    }, {
                        "id": "month",
                        "label": "M"
                    }]

                    delegate: Rectangle {
                        id: chip

                        required property var modelData
                        readonly property bool on: root.calendarRange === modelData.id

                        width: chipLabel.implicitWidth + 12
                        height: chipLabel.implicitHeight + 2
                        color: on ? Style.selectedFillFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : "transparent"
                        border.width: 1
                        border.color: on ? Style.normalBorderFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : "transparent"

                        Text {
                            id: chipLabel

                            anchors.centerIn: parent
                            text: chip.modelData.label
                            color: chip.on ? panelTheme.text : panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: root.setCalendarRange(chip.modelData.id)
                        }

                    }

                }

            }

            Item {
                Layout.fillWidth: true
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 0

                Text {
                    Layout.alignment: Qt.AlignRight
                    text: Model.clockDuration(calendarScope.rangeTotal)
                    color: panelTheme.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.title
                    font.bold: true
                }

                Text {
                    // month: `18 TRACKED DAYS · 4 WITH UNAPPLIED BLOCKS`
                    // week:  `axis 08:00–19:00 · automatic, from your tracked hours`
                    Layout.alignment: Qt.AlignRight
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    visible: root.calendarRange !== "fortnight"
                    text: root.calendarRange === "month" ? (Object.keys(calendarScope.dayTotals).length + " TRACKED DAYS" + (calendarScope.dates.filter(function(d) {
                        return calendarScope.hasUnapplied(d.date);
                    }).length ? " · " + calendarScope.dates.filter(function(d) {
                        return calendarScope.hasUnapplied(d.date);
                    }).length + " WITH UNAPPLIED BLOCKS" : "")) : ("axis " + calendarScope.axisLabel() + " · " + calendarScope.axisModeLabel())
                    color: panelTheme.textDisabled
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: root.calendarRange === "month" ? 0.8 : 0
                }

            }

        }

        Text {
            // Backward navigation disables at the 91-day floor and says why (spec 8.4).
            Layout.fillWidth: true
            visible: !root.calendarCanPageBackward
            text: "‹  " + Model.calendarFloorHint(calendarScope.today)
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            visible: root.calendarClamped
            text: "Range shortened to " + root.calendarStartDate + " – Toggl answers 91 days back at most."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.calendarError !== ""
            text: root.calendarError
            color: panelTheme.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            visible: root.status === "loading" && (root.pendingAction === "range_entries" || root.pendingAction === "day_activity") && root.scope === "cal"
            text: "Loading entries…"
            color: panelTheme.textMuted
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        // ---- fortnight / month grid: 7 day columns + Σ ----------------------
        GridLayout {
            id: cellGrid

            visible: root.calendarRange !== "week"
            Layout.fillWidth: true
            columns: 8
            columnSpacing: 4
            rowSpacing: 4

            // Day-of-week header row.
            Repeater {
                model: root.calendarRange === "week" ? [] : ["M", "T", "W", "T", "F", "S", "S", "Σ"]

                delegate: Text {
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData
                    color: panelTheme.textDisabled
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                }

            }

            // Cells, with a week-total cell after every seventh day.
            Repeater {
                model: root.calendarRange === "week" ? [] : calendarScope.dates.reduce(function(acc, d, i) {
                    acc.push({
                        "kind": "day",
                        "date": d.date,
                        "inRange": d.inRange
                    });
                    if (i % 7 === 6)
                        acc.push({
                        "kind": "week",
                        "date": d.date,
                        "from": calendarScope.dates[i - 6].date
                    });

                    return acc;
                }, [])

                delegate: Rectangle {
                    id: cell

                    required property var modelData
                    readonly property bool isWeek: modelData.kind === "week"
                    readonly property bool isToday: !isWeek && modelData.date === calendarScope.today
                    readonly property bool onCursor: !isWeek && modelData.date === root.calendarCursorDate
                    readonly property bool weekend: !isWeek && (new Date(modelData.date + "T12:00:00").getDay() % 6 === 0)
                    readonly property int total: isWeek ? calendarScope.dates.filter(function(d) {
                        return d.date >= modelData.from && d.date <= modelData.date;
                    }).reduce(function(sum, d) {
                        return sum + (calendarScope.dayTotals[d.date] || 0);
                    }, 0) : (calendarScope.dayTotals[modelData.date] || 0)
                    readonly property var dayEntries: isWeek ? [] : calendarScope.entriesOn(modelData.date)

                    // h/j/k/l must not walk the selection off screen.
                    onOnCursorChanged: {
                        if (onCursor) {
                            root.ensureVisible(this);
                        }
                    }
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: root.calendarRange === "fortnight" ? 66 : 50
                    opacity: !isWeek && !modelData.inRange ? 0.32 : 1
                    color: onCursor ? Style.selectedFillFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : (isWeek ? Qt.rgba(0, 0, 0, 0.18) : (weekend ? calendarScope.weekendFill : "transparent"))
                    border.width: 1
                    border.color: (isToday || onCursor) ? panelTheme.accent : (isWeek ? Util.alpha(panelTheme.text, 0.06) : calendarScope.cellEdge)

                    MouseArea {
                        anchors.fill: parent
                        enabled: !cell.isWeek
                        onClicked: {
                            root.calendarCursorDate = cell.modelData.date;
                        }
                        onDoubleClicked: root.openCalendarCursorDay()
                    }

                    // Week total: `32h00` over `W36`.
                    ColumnLayout {
                        anchors.centerIn: parent
                        visible: cell.isWeek
                        spacing: 0

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: Model.clockDuration(cell.total)
                            color: panelTheme.accent
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: Model.isoWeekLabel(cell.modelData.from || cell.modelData.date)
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: 9
                            font.letterSpacing: 0.7
                        }

                    }

                    // Day cell: number + flag, total, then strip or stack.
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 4
                        visible: !cell.isWeek
                        spacing: 2

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: String(Number(String(cell.modelData.date).split("-")[2]))
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            Text {
                                // ▲ conflict beats ◌ unapplied; nothing else is flagged (spec 8.4).
                                visible: !!cell.modelData.inRange && !!(calendarScope.conflictDates[cell.modelData.date] || calendarScope.hasUnapplied(cell.modelData.date))
                                text: calendarScope.conflictDates[cell.modelData.date] ? "▲" : "◌"
                                color: calendarScope.conflictDates[cell.modelData.date] ? panelTheme.urgent : calendarScope.warn
                                font.family: root.fontFamily
                                font.pixelSize: 9
                            }

                        }

                        Text {
                            text: cell.total > 0 ? Model.clockDuration(cell.total) : "—"
                            color: cell.total > 0 ? panelTheme.text : panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        // Fortnight: 9px wall-time-ordered density strip. Month: 4px
                        // project-colour stack. An Item with precomputed offsets, not a
                        // Row -- children sized from the parent's width inside a Row is a
                        // polish loop.
                        Item {
                            id: strip

                            readonly property var segments: {
                                var sorted = cell.dayEntries.slice().sort(function(a, b) {
                                    return new Date(a.start) - new Date(b.start);
                                });
                                var total = cell.total > 0 ? cell.total : 1;
                                var gaps = Math.max(0, sorted.length - 1);
                                var usable = Math.max(0, strip.width - gaps);
                                var out = [];
                                var x = 0;
                                for (var i = 0; i < sorted.length; i++) {
                                    var w = Math.max(1, usable * Math.max(0, Model.durationSecondsOf(sorted[i])) / total);
                                    out.push({
                                        "x": x,
                                        "w": w,
                                        "color": calendarScope.projectColor(sorted[i])
                                    });
                                    x += w + 1;
                                }
                                return out;
                            }

                            Layout.fillWidth: true
                            Layout.preferredHeight: root.calendarRange === "fortnight" ? 9 : 4
                            visible: !!cell.modelData.inRange && cell.dayEntries.length > 0

                            Repeater {
                                model: strip.segments

                                delegate: Rectangle {
                                    required property var modelData

                                    x: modelData.x
                                    width: modelData.w
                                    height: strip.height
                                    color: modelData.color
                                }

                            }

                        }

                    }

                }

            }

        }

        // ---- week: 26px hour gutter + 7 columns, 156px, real time axis ------
        ColumnLayout {
            readonly property var hourMarks: {
                var marks = [];
                for (var h = calendarScope.axis.start; h <= calendarScope.axis.end; h += 2) marks.push(h)
                return marks;
            }

            visible: root.calendarRange === "week"
            Layout.fillWidth: true
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                Item {
                    Layout.preferredWidth: 26
                }

                Repeater {
                    model: root.calendarRange === "week" ? calendarScope.dates : []

                    delegate: Text {
                        required property var modelData
                        readonly property bool isToday: modelData.date === calendarScope.today

                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        text: Model.dayLabel(modelData.date).split(" ")[0].toUpperCase() + " " + Number(modelData.date.split("-")[2])
                        color: isToday ? panelTheme.accent : panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        font.letterSpacing: 0.8
                    }

                }

            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                Item {
                    // Hour gutter: labels every two hours at their own y.
                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 156

                    Repeater {
                        model: parent.parent.parent.hourMarks

                        delegate: Text {
                            required property var modelData

                            x: 0
                            y: (modelData - calendarScope.axis.start) * calendarScope.axis.rowHeight - 4
                            width: 22
                            horizontalAlignment: Text.AlignRight
                            text: calendarScope.pad2(modelData)
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: 9
                        }

                    }

                }

                Repeater {
                    model: root.calendarRange === "week" ? calendarScope.dates : []

                    delegate: Rectangle {
                        id: col

                        required property var modelData
                        readonly property bool isToday: modelData.date === calendarScope.today
                        readonly property bool onCursor: modelData.date === root.calendarCursorDate
                        readonly property var dayEntries: calendarScope.entriesOn(modelData.date)
                        readonly property var dayBlocks: calendarScope.blocksOn(modelData.date).filter(function(b) {
                            return b.state !== "applied";
                        })

                        // h/j/k/l must not walk the selection off screen.
                        onOnCursorChanged: {
                            if (onCursor) {
                                root.ensureVisible(this);
                            }
                        }
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        Layout.preferredHeight: 156
                        clip: true
                        color: onCursor ? Style.selectedFillFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : (isToday ? Util.alpha(panelTheme.accent, 0.06) : (dayEntries.length ? Qt.rgba(0, 0, 0, 0.2) : Qt.rgba(0, 0, 0, 0.28)))
                        border.width: onCursor ? 1 : 0
                        border.color: panelTheme.accent

                        MouseArea {
                            anchors.fill: parent
                            z: -1
                            onClicked: root.calendarCursorDate = col.modelData.date
                            onDoubleClicked: root.openCalendarCursorDay()
                        }

                        // Hour gridlines.
                        Repeater {
                            model: Math.max(0, calendarScope.axis.end - calendarScope.axis.start)

                            delegate: Rectangle {
                                required property int index

                                x: 0
                                y: index * calendarScope.axis.rowHeight
                                width: col.width
                                height: 1
                                color: Util.alpha(panelTheme.text, 0.05)
                            }

                        }

                        // Entries: top = (startHour - axisStart) * rowHeight, project colour.
                        Repeater {
                            model: col.dayEntries

                            delegate: Rectangle {
                                id: ev

                                required property var modelData
                                readonly property real startHour: Math.max(calendarScope.axis.start, Model.hourOfDay(modelData.start) === null ? calendarScope.axis.start : Model.hourOfDay(modelData.start))
                                readonly property real endHour: Math.min(calendarScope.axis.end, Model.hourOfDay(modelData.stop) === null ? startHour + 0.25 : Model.hourOfDay(modelData.stop))
                                readonly property bool clippedTop: Model.hourOfDay(modelData.start) !== null && Model.hourOfDay(modelData.start) < calendarScope.axis.start
                                readonly property bool clippedBottom: Model.hourOfDay(modelData.stop) !== null && Model.hourOfDay(modelData.stop) > calendarScope.axis.end

                                x: 0
                                y: (startHour - calendarScope.axis.start) * calendarScope.axis.rowHeight
                                width: col.width
                                height: Math.max(2, (endHour - startHour) * calendarScope.axis.rowHeight)
                                color: Util.alpha(calendarScope.projectColor(modelData), 0.85)

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 2
                                    anchors.top: parent.top
                                    width: parent.width - 4
                                    visible: parent.height >= 11
                                    text: String(ev.modelData.description || "")
                                    textFormat: Text.PlainText
                                    color: Color.background
                                    font.family: root.fontFamily
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }

                                // 2px edge marker where the axis clipped the entry (spec 8.1 Overflow).
                                Rectangle {
                                    visible: ev.clippedTop
                                    anchors.top: parent.top
                                    width: parent.width
                                    height: 2
                                    color: panelTheme.urgent
                                }

                                Rectangle {
                                    visible: ev.clippedBottom
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 2
                                    color: panelTheme.urgent
                                }

                            }

                        }

                        // Unapplied blocks: dashed outline, no fill. Conflict: urgent border.
                        Repeater {
                            model: col.dayBlocks

                            delegate: Item {
                                id: blk

                                required property var modelData
                                readonly property bool isConflict: modelData.state === "conflict"
                                readonly property real startHour: Math.max(calendarScope.axis.start, Model.hourOfDay(modelData.start) || calendarScope.axis.start)
                                readonly property real endHour: Math.min(calendarScope.axis.end, Model.hourOfDay(modelData.end) || startHour + 0.25)

                                x: 0
                                y: (startHour - calendarScope.axis.start) * calendarScope.axis.rowHeight
                                width: col.width
                                height: Math.max(2, (endHour - startHour) * calendarScope.axis.rowHeight)

                                Canvas {
                                    anchors.fill: parent
                                    onPaint: {
                                        var ctx = getContext("2d");
                                        ctx.clearRect(0, 0, width, height);
                                        ctx.strokeStyle = blk.isConflict ? String(panelTheme.urgent) : String(Util.alpha(panelTheme.text, 0.35));
                                        ctx.lineWidth = 1;
                                        if (!blk.isConflict)
                                            ctx.setLineDash([2, 2]);

                                        ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
                                        if (blk.isConflict) {
                                            ctx.setLineDash([]);
                                            ctx.strokeStyle = String(Util.alpha(panelTheme.urgent, 0.45));
                                            for (var d = -height; d < width; d += 5) {
                                                ctx.beginPath();
                                                ctx.moveTo(d, height);
                                                ctx.lineTo(d + height, 0);
                                                ctx.stroke();
                                            }
                                        }
                                    }
                                }

                                Text {
                                    anchors.centerIn: parent
                                    visible: parent.height >= 11
                                    text: blk.isConflict ? String(blk.modelData.label || "") : (parent.height >= 20 ? String(blk.modelData.label || "") : "◌")
                                    textFormat: Text.PlainText
                                    color: blk.isConflict ? panelTheme.urgent : panelTheme.textMuted
                                    font.family: root.fontFamily
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                    width: parent.width - 4
                                    horizontalAlignment: Text.AlignHCenter
                                }

                            }

                        }

                    }

                }

            }

            // Per-day totals under the columns.
            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                Item {
                    Layout.preferredWidth: 26
                }

                Repeater {
                    model: root.calendarRange === "week" ? calendarScope.dates : []

                    delegate: Text {
                        required property var modelData
                        readonly property int total: calendarScope.dayTotals[modelData.date] || 0

                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        horizontalAlignment: Text.AlignHCenter
                        text: total > 0 ? Model.clockDuration(total) : "—"
                        color: total > 0 ? panelTheme.textMuted : panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                }

            }

            Text {
                // ▸ 3 entries fall outside 07:00 – 21:00  (ruling R-L, exact copy)
                visible: calendarScope.overflowCount > 0
                text: "▸ " + calendarScope.overflowCount + (calendarScope.overflowCount === 1 ? " entry falls" : " entries fall") + " outside " + calendarScope.pad2(calendarScope.axis.start) + ":00 – " + calendarScope.pad2(calendarScope.axis.end) + ":00"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

        }

        // ---- axis settings (week, toggled by `a`) -----------------------------
        // One row (ruling R-AI): caption, status, then the two hour fields and
        // Reset -- the stacked version spent three lines on two numbers.
        RowLayout {
            visible: root.calendarRange === "week" && root.calendarAxisOpen
            Layout.fillWidth: true
            Layout.topMargin: Style.spacing.rowGap
            spacing: Style.spacing.rowGap

            Text {
                text: "AXIS"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: calendarScope.axis.derived ? "automatic, from your tracked hours" : ("fixed, " + calendarScope.pad2(calendarScope.axis.start) + ":00 – " + calendarScope.pad2(calendarScope.axis.end) + ":00")
                color: panelTheme.textMuted
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
            }

            Text {
                text: "STARTS"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            NumberField {
                fieldWidth: 64
                fontSize: Style.font.bodySmall
                from: 0
                to: 24
                stepSize: 1
                value: root.calendarDayStart === "auto" ? calendarScope.axis.start : root.calendarDayStart
                onModified: function(value) {
                    root.setCalendarAxisOverride("start", value);
                }
            }

            Text {
                Layout.leftMargin: 4
                text: "ENDS"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
            }

            NumberField {
                fieldWidth: 64
                fontSize: Style.font.bodySmall
                from: 0
                to: 24
                stepSize: 1
                value: root.calendarDayEnd === "auto" ? calendarScope.axis.end : root.calendarDayEnd
                onModified: function(value) {
                    root.setCalendarAxisOverride("end", value);
                }
            }

            Button {
                Layout.leftMargin: 4
                text: "Reset"
                enabled: !calendarScope.axis.derived
                focusable: true
                bordered: true
                fontSize: Style.font.caption
                foreground: panelTheme.accent
                onClicked: root.resetCalendarAxis()
            }

        }

        PanelSeparator {
            Layout.fillWidth: true
            Layout.topMargin: Style.spacing.rowGap
            foreground: root.foreground
        }

        // ---- hints + legend --------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            Repeater {
                model: [["↵", "open day"], [root.calendarRange === "week" ? "hl" : "hjkl", root.calendarRange === "week" ? "day" : "move"], ["w", "cycle range"]].concat(root.calendarRange === "week" ? [["a", "axis"]] : [])

                delegate: Row {
                    required property var modelData

                    spacing: 4

                    Text {
                        text: modelData[0]
                        color: panelTheme.textMuted
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                    Text {
                        text: modelData[1]
                        color: panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                }

            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text: "◌"
                color: calendarScope.warn
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                text: "unapplied"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                text: "▲"
                color: panelTheme.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                text: "conflict"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

        }

    }

}
