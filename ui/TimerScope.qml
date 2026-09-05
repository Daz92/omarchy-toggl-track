import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

// The command-line result rows and the timer-scope hint bar. The running
// strip that used to open this file now lives in Panel.qml itself, right
// before the command line -- design-guide.html:426-448's order is .running,
// .sep, .cmd, .rows, .sep, .hints, and .running has to sit above .cmd while
// .rows and .hints stay below it, so one Item couldn't hold all three
// (finding 2). Stage 3 replaces the old elapsed-time hero and the whole
// entry composer (description field, START/STOP, project/task dropdowns,
// tags, billable toggle, search) with the single command line Panel.qml owns
// -- see docs/2026-09-04-panel-redesign.md and
// docs/2026-09-04-stage-2-6-rulings.md §7 (R-Q, the Ctrl+S stop binding this
// file's hint entry documents).
Item {
    id: timerScope

    required property var root
    required property var panelTheme

    visible: root.scope === "timer"
    Layout.fillWidth: true
    implicitHeight: timerContent.implicitHeight

    ColumnLayout {
        id: timerContent

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.panelGap

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            Repeater {
                model: root.commandRows

                delegate: Item {
                    id: rowItem

                    required property var modelData
                    required property int index
                    readonly property bool onCursor: index === root.resultCursorIndex

                    Layout.fillWidth: true
                    implicitHeight: Style.space(22)
                    // Ten recent entries outgrow the panel, so ^j/^k has to
                    // bring its row with it.
                    onOnCursorChanged: {
                        if (onCursor) {
                            root.ensureVisible(rowItem);
                        }
                    }

                    Rectangle {
                        anchors.fill: parent
                        color: rowItem.index === root.resultCursorIndex ? Style.selectedFill : (rowMouse.containsMouse ? Style.hoverFill : "transparent")
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 2
                        anchors.rightMargin: 2
                        spacing: Style.spacing.rowGap

                        Text {
                            Layout.preferredWidth: 11
                            text: rowItem.modelData.glyph
                            // --dim18 -> textDisabled (stage 2's colour table
                            // is authoritative; see docs/plans/2026-09-04-
                            // stage-3-command-line-and-scopes.md's corrected
                            // Global Constraints entry).
                            color: rowItem.index === root.resultCursorIndex ? panelTheme.accent : panelTheme.textDisabled
                            horizontalAlignment: Text.AlignHCenter
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            Layout.preferredWidth: 52
                            text: rowItem.modelData.verb
                            color: rowItem.index === root.resultCursorIndex ? panelTheme.accent : panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            font.letterSpacing: 0.6
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: rowItem.modelData.label
                            color: panelTheme.text
                            elide: Text.ElideRight
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            // The guide's row grid is "11px 52px 1fr auto".
                            // An `auto` track takes max-content as its max
                            // sizing function and `auto` as its min, and that
                            // min is floored by the item's automatic minimum
                            // size, which `.row .lbl`'s overflow:hidden puts
                            // at 0 -- so `auto` grows to content and is NOT
                            // rigid. Both halves are needed here:
                            // Layout.fillWidth lets it shrink and elide;
                            // maximumWidth caps it at its own content so it
                            // never claims free space the label should have.
                            // Together these are QML's equivalent of the
                            // guide's `auto` grid track, which sizes to
                            // content but still shrinks when the row is
                            // too narrow. fillWidth alone gave meta half the
                            // row; neither alone is correct.
                            Layout.fillWidth: true
                            Layout.maximumWidth: implicitWidth
                            Layout.minimumWidth: 0
                            text: rowItem.modelData.meta
                            // --dim18 -> textDisabled, not textFaint -- see
                            // the glyph/verb comment above.
                            color: panelTheme.textDisabled
                            elide: Text.ElideRight
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        Text {
                            // Never elided, unlike label/meta above -- a
                            // CONT row's duration lives here (see
                            // Model.js's continueRow), and clipping it was
                            // the whole bug this column exists to fix.
                            // Layout.minimumWidth pinned to its own natural
                            // width so the layout can never shrink it to
                            // make room for label or meta -- the one
                            // constraint that must survive finding 6.
                            Layout.minimumWidth: implicitWidth
                            visible: !!rowItem.modelData.num
                            text: rowItem.modelData.num
                            // One tier brighter than meta (finding 7): the
                            // guide gives .row .meta .num its own --dim15
                            // against meta's --dim18.
                            color: panelTheme.textMuted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                    }

                    MouseArea {
                        id: rowMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            root.resultCursorIndex = rowItem.index;
                            root.activateSelectedRow();
                        }
                    }

                }

            }

        }

        // Restored from master:ui/TimerScope.qml:265-313 (F2, final review):
        // Task 5's rewrite of this file dropped every error/loading/stale-
        // cache indicator while root.errorMessage/errorStatus/cacheInfo/
        // setupCommand kept being written from Panel.qml -- an expired
        // token, a helper crash or any Toggl 4xx went completely silent.
        // Sits below the rows and above the hint bar, as design-guide.html
        // §01 implies and master had it.
        Text {
            visible: root.status === "loading"
            text: root.manualRefresh ? "Refreshing metadata…" : (root.pendingAction ? "Updating Toggl…" : "Loading Toggl…")
            color: panelTheme.textMuted
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        Text {
            visible: root.cacheInfo && root.cacheInfo.stale === true
            text: "Using cached project data — Refresh to retry."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        RowLayout {
            visible: root.status === "error"
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            Text {
                Layout.fillWidth: true
                text: root.errorMessage
                // PlainText, never StyledText: this can carry Toggl's raw
                // HTTP body, and the command line's own escapeSpan (below)
                // exists for the identical reason -- unescaped server text
                // reaching a StyledText Text is markup, not a message.
                // Colour follows DayScope's dayError (Color.urgent), not
                // master's Color.accent -- this branch already established
                // urgent-red for surfaced errors and the two should agree.
                color: Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }

            Button {
                text: "RETRY"
                focusable: true
                bordered: true
                foreground: Color.accent
                onClicked: root.bootstrap()
            }

        }

        TextField {
            // Gate unchanged from master: 401 means "run setup, then retry"
            // outright; errorStatus 0 covers the local, non-HTTP failures
            // (helper missing/crashed, token/setup misconfigured) where the
            // message itself names the cause. Never widened to match
            // server-supplied text -- that would send half the panel's
            // Toggl-side error vocabulary to a setup hint that means nothing
            // there.
            visible: root.status === "error" && (root.errorStatus === 401 || (root.errorStatus === 0 && /helper|token|setup/i.test(root.errorMessage)))
            Layout.fillWidth: true
            text: "Run setup, then retry: " + root.setupCommand
            readOnly: true
            foreground: panelTheme.textMuted
        }

        PanelSeparator {
            // PanelSeparator sets width: parent.width, which a
            // ColumnLayout overrides -- without this it falls back
            // to implicitWidth 100 and renders as a stub.
            Layout.fillWidth: true
            // Guide's second .sep, between .rows and .hints.
            foreground: root.foreground
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // Each hint is one keycap plus one word, and the guide draws a
            // deliberate contrast between them (finding 7): ".hints" itself
            // is --dim18 (textDisabled) but ".hints b" is --dim15
            // (textMuted) -- one tier brighter. --dim18 maps to textDisabled,
            // not textFaint -- stage 2's colour table is authoritative (see
            // docs/plans/2026-09-04-stage-3-command-line-and-scopes.md's
            // corrected Global Constraints entry). Static strings, no user
            // data, so no escaping is needed for the StyledText markup below.
            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">↵</font> act"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">⇥</font> complete"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">^j/^k</font> move"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                // R-Q: stopping the running timer is a keyboard binding
                // (Ctrl+S on the command-line field, see Panel.qml), not a
                // visible control -- this hint is its only trace, and it must
                // disappear when idle so the hint bar stays byte-identical
                // to the guide with nothing running.
                visible: !!root.current
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">^s</font> stop"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">^d</font> day"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">^l</font> calendar"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

            Text {
                textFormat: Text.StyledText
                text: "<font color=\"" + panelTheme.textMuted + "\">esc</font> close"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

        }

    }

}
