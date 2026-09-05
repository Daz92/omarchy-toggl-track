import "../Model.js" as Model
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

// The day header: `‹ Wed 3 Sep ›`, the day total and the count line
// (design-guide.html §02). It is a separate component from DayScope because
// the guide orders day scope as dayhead, sep, cmd, rows -- the command line
// sits BELOW the header -- while the timer scope puts the command line first.
// One fixed cmdBox in Panel.qml cannot satisfy both, so the header is placed
// above it and gated on scope (ruling R-V).
Item {
    id: dayHeader

    required property var root
    required property var panelTheme

    // See DayScope.at(): a real function argument, not a comma tap, so the
    // dayRevision read is a captured dependency.
    function at(rev, value) {
        return value;
    }

    visible: root.scope === "day"
    Layout.fillWidth: true
    implicitHeight: headerRow.implicitHeight

    RowLayout {
        id: headerRow

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.rowGap

        PanelActionButton {
            iconText: "‹"
            tooltipText: "Previous day"
            size: Style.spacing.controlHeight
            foreground: root.foreground
            onClicked: root.shiftDay(-1)
        }

        Text {
            // The guide shows `Wed 3 Sep`, no year; dayLabel carries the year
            // for the BLOCK rows' "today / Fri 4 Sep 2026" meta.
            text: Model.dayLabel(root.dayDate).replace(/ \d{4}$/, "")
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
            foreground: panelTheme.accent
            onClicked: root.showDay(Model.todayDate())
        }

        Item {
            Layout.fillWidth: true
        }

        Text {
            // `2 APPLIED · 2 READY · 1 UNASSIGNED · 1 CONFLICT` -- .dayhead .cnt is
            // --dim18 with letter-spacing 0.08em, caption size. One row with the
            // total (ruling R-AI): the count sits left of it, total on the far right.
            visible: root.dayBlocks.length > 0
            text: at(root.dayRevision, Model.countLine(root.daySummary))
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 0.8
            elide: Text.ElideLeft
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            horizontalAlignment: Text.AlignRight
        }

        Text {
            // Model.blockSummary() · Style.font.title 14 · Color.accent (guide §02)
            Layout.leftMargin: 4
            text: Model.clockDuration(root.daySummary.totalSeconds)
            color: panelTheme.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
        }

    }

}
