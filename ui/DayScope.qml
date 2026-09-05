// Day scope body: the block rows, their two drawers and the hint bar
// (design-guide.html §02, §03, §05). The day header lives in DayHeader.qml,
// above the command line, per ruling R-V.

import "../Model.js" as Model
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

// Presentation and interaction only: every mutation goes back through
// root.mutateBlock() and friends in Panel.qml so dayRevision keeps bumping.
Item {
    id: dayScope

    required property var root
    required property var panelTheme
    // The guide's --warn (#f9e2af) marks a guessed row's `~`. No PanelTheme or
    // Color role exists for warn, so it is a literal per the guide -- the same
    // call stage 3 made for the overlay's tag/billable colours.
    readonly property color warn: "#f9e2af"
    // Eight hues walked from the theme's accent, so the palette follows the
    // theme instead of fighting it. The same name is the same colour in the
    // timeline and in every bar list -- that correlation is the point.
    readonly property int paletteSize: 8

    function colorFor(name) {
        var base = panelTheme.accent.hslHue;
        var slot = Model.paletteIndex(name, paletteSize);
        return Qt.hsla((base + slot / paletteSize) % 1, 0.55, 0.64, 1);
    }

    // Re-evaluation tap. dayBlocks are mutated in place so the edit drawer's
    // field keeps focus, and QML cannot observe a JS mutation -- so every
    // binding that reads a block also reads dayRevision. The bare comma form
    // `(rev, expr)` looked right but did NOT re-evaluate: the compiler drops a
    // side-effect-free left operand, so no dependency is captured. A function
    // argument is always evaluated, so this form is.
    function at(rev, value) {
        return value;
    }

    // Which state tiers use which colour role (guide §05 + R-R). Applied is
    // dimmed but readable; unassigned and skipped are the dimmest tier.
    function glyphColor(state) {
        if (state === "applied")
            return panelTheme.textMuted;

        if (state === "ready" || state === "guessed" || state === "inflight")
            return panelTheme.accent;

        if (state === "conflict")
            return panelTheme.urgent;

        return panelTheme.textFaint;
    }

    function labelColor(state) {
        if (state === "applied")
            return panelTheme.textMuted;

        if (state === "unassigned" || state === "skipped")
            return panelTheme.textFaint;

        return panelTheme.text;
    }

    function durationColor(state) {
        if (state === "applied")
            return panelTheme.textMuted;

        if (state === "skipped")
            return panelTheme.textFaint;

        return panelTheme.accent;
    }

    visible: root.scope === "day"
    Layout.fillWidth: true
    implicitHeight: dayContent.implicitHeight

    ColumnLayout {
        id: dayContent

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.spacing.rowGap

        Text {
            visible: root.status === "loading" && root.pendingAction === "day_activity"
            text: "Reading local activity…"
            color: panelTheme.textMuted
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.italic: true
        }

        Text {
            Layout.fillWidth: true
            visible: root.dayError !== ""
            text: root.dayError
            color: panelTheme.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            Layout.fillWidth: true
            visible: root.dayLoaded && root.dayError === "" && root.dayBlocks.length === 0
            text: "No tracked activity for this day. Omalog records activity through ActivityWatch on 127.0.0.1:5600."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.dayLoaded && root.dayBlocks.length > 0 && root.dayVisibleBlocks.length === 0
            text: "No blocks match the filter."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
        }

        Repeater {
            model: root.dayVisibleBlocks

            delegate: ColumnLayout {
                id: blockRow

                required property var modelData
                required property int index
                readonly property int rev: root.dayRevision
                // THE live block. A JS-array model reaches the delegate as a
                // QVariantList, so `modelData` is a COPY made when the row was
                // created and never sees an in-place mutation. Indexing the
                // source array on every dayRevision bump does. Every state read
                // and every mutation below goes through this, never modelData.
                readonly property var block: dayScope.at(rev, root.dayVisibleBlocks[index] || modelData)
                readonly property string blockState: dayScope.at(rev, Model.blockState(block))
                readonly property bool inspecting: dayScope.at(rev, !!block.inspecting)
                readonly property bool editing: dayScope.at(rev, !!block.editing)
                readonly property bool guessed: dayScope.at(rev, !!block.guessed)
                readonly property bool onCursor: index === root.dayCursorIndex
                readonly property int blockProjectId: dayScope.at(rev, Number(block.projectId) || 0)
                readonly property int blockTaskId: dayScope.at(rev, Number(block.taskId) || 0)
                readonly property string failure: dayScope.at(rev, String(block.failure || ""))

                // Keep the cursor row on screen when j/k walks past the fold.
                onOnCursorChanged: {
                    if (onCursor)
                        root.ensureVisible(blockRow);

                }
                // `e` is a door, not a toggle switch: opening the edit drawer puts
                // the keyboard in it (guide 03's EDIT hints assume focus is inside).
                onEditingChanged: {
                    if (editing)
                        descriptionField.forceActiveFocus();

                }
                Layout.fillWidth: true
                spacing: 0

                // ---- the one-line row -------------------------------------
                Rectangle {
                    id: blockHead

                    Layout.fillWidth: true
                    implicitHeight: Style.space(22)
                    color: blockRow.onCursor ? Style.selectedFillFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : (blockMouse.containsMouse ? Style.hoverFillFor(panelTheme.text, panelTheme.accent, panelTheme.urgent) : "transparent")

                    MouseArea {
                        id: blockMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            root.setDayCursor(blockRow.index);
                            root.toggleInspect(blockRow.block);
                        }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 2
                        anchors.rightMargin: 2
                        spacing: Style.spacing.rowGap

                        Text {
                            Layout.preferredWidth: 11
                            text: Model.blockGlyph(blockRow.blockState)
                            color: dayScope.glyphColor(blockRow.blockState)
                            horizontalAlignment: Text.AlignHCenter
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            text: dayScope.at(blockRow.rev, Model.clockTime(blockRow.block.start))
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            text: dayScope.at(blockRow.rev, Model.clockDuration(blockRow.block.seconds))
                            color: dayScope.durationColor(blockRow.blockState)
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: dayScope.at(blockRow.rev, blockRow.block.description || blockRow.block.label)
                            textFormat: Text.PlainText
                            color: dayScope.labelColor(blockRow.blockState)
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            elide: Text.ElideRight
                        }

                        Text {
                            // Trailing text per state: project · task, — unassigned —,
                            // conflict · manual, writing…, skipped. Applied and conflict
                            // must differ here as well as in glyph and colour.
                            Layout.fillWidth: true
                            Layout.maximumWidth: implicitWidth
                            Layout.minimumWidth: 0
                            text: dayScope.at(blockRow.rev, Model.blockMeta(blockRow.block, root.projects, root.tasks))
                            textFormat: Text.PlainText
                            color: blockRow.blockState === "conflict" ? panelTheme.urgent : panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            elide: Text.ElideRight
                        }

                        Text {
                            // `~` -- named or assigned by the classifier, unconfirmed.
                            // Disappears the moment the row is touched.
                            visible: blockRow.guessed
                            text: "~"
                            color: dayScope.warn
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                    }

                }

                // ---- inspect drawer: dim rule, nothing here writes --------
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 19
                    Layout.topMargin: 4
                    Layout.bottomMargin: 6
                    visible: blockRow.inspecting
                    spacing: 12

                    Rectangle {
                        // .drawer.inspect { border-left: 1px solid rgba(fg, 0.22) }
                        Layout.fillHeight: true
                        Layout.preferredWidth: 1
                        color: Util.alpha(panelTheme.text, 0.22)
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            // 2h25 active · 2h41 wall · 16m idle removed · 63 switches · longest run 11m
                            Layout.fillWidth: true
                            text: dayScope.at(blockRow.rev, Model.blockFacts(blockRow.block).join("   "))
                            textFormat: Text.PlainText
                            color: panelTheme.textMuted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            wrapMode: Text.WordWrap
                        }

                        // Fragment timeline across the wall span. Active ticks in
                        // accent, idle gaps in the track colour -- the guide hatches
                        // idle; a dimmer fill is the closest a plain Rectangle gets.
                        Row {
                            id: timelineRow

                            Layout.fillWidth: true
                            height: 7
                            spacing: 0

                            Repeater {
                                model: blockRow.inspecting ? dayScope.at(blockRow.rev, blockRow.block.timeline) : []

                                delegate: Rectangle {
                                    required property var modelData

                                    width: blockRow.block.spanSeconds > 0 ? Math.max(1, timelineRow.width * modelData.seconds / blockRow.block.spanSeconds) : 0
                                    height: 7
                                    color: modelData.idle ? Util.alpha(panelTheme.text, 0.07) : dayScope.colorFor(modelData.topic)
                                }

                            }

                        }

                        // TOPICS / APPS / DOMAINS bars: 34px seconds column, a track,
                        // the name. Gated on the model, never on `visible` -- a
                        // Repeater is not an Item.
                        Repeater {
                            model: blockRow.inspecting ? [{
                                "title": "TOPICS",
                                "items": blockRow.block.topics
                            }, {
                                "title": "APPS",
                                "items": blockRow.block.apps
                            }, {
                                "title": "DOMAINS",
                                "items": blockRow.block.domains
                            }].filter(function(section) {
                                return section.items.length > 0;
                            }) : []

                            delegate: ColumnLayout {
                                id: barSection

                                required property var modelData
                                readonly property int maxSeconds: modelData.items.reduce(function(m, item) {
                                    return Math.max(m, Number(item.seconds) || 0);
                                }, 0)

                                Layout.fillWidth: true
                                spacing: 3

                                Text {
                                    text: barSection.modelData.title
                                    color: panelTheme.textDisabled
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                    font.letterSpacing: 0.8
                                }

                                Repeater {
                                    model: barSection.modelData.items.slice(0, 8)

                                    delegate: RowLayout {
                                        id: barRow

                                        required property var modelData

                                        Layout.fillWidth: true
                                        spacing: Style.spacing.rowGap

                                        Text {
                                            Layout.preferredWidth: 34
                                            text: barRow.modelData.seconds ? Model.clockDuration(barRow.modelData.seconds) : ""
                                            color: panelTheme.textMuted
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.caption
                                        }

                                        Rectangle {
                                            id: track

                                            // A third of the row, not half: the user wants the
                                            // names readable, so the track gives up 30% of the
                                            // width it had and the name column takes it.
                                            Layout.preferredWidth: Math.round(dayContent.width * 0.33)
                                            Layout.preferredHeight: 7
                                            color: Util.alpha(panelTheme.text, 0.07)

                                            Rectangle {
                                                width: barSection.maxSeconds > 0 ? track.width * (Number(barRow.modelData.seconds) || 0) / barSection.maxSeconds : 0
                                                height: track.height
                                                color: dayScope.colorFor(barRow.modelData.name)
                                            }

                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: barRow.modelData.name
                                            textFormat: Text.PlainText
                                            color: panelTheme.textMuted
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.caption
                                            elide: Text.ElideRight
                                        }

                                    }

                                }

                            }

                        }

                        Row {
                            // INSPECT · e switch to edit · space close · ^j/^k next block
                            spacing: 12

                            Repeater {
                                model: [["e", "switch to edit"], ["space", "close"], ["^j/^k", "next block"]]

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

                        }

                        Text {
                            // written as entry #3901284471 · created_with omarchy-toggl-track/day
                            visible: blockRow.blockState === "applied" || blockRow.blockState === "conflict"
                            text: dayScope.at(blockRow.rev, (blockRow.block.conflict ? "written as entry #" + blockRow.block.conflict.id : "") + (blockRow.block.createdWith ? "   created_with " + blockRow.block.createdWith : ""))
                            textFormat: Text.PlainText
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            elide: Text.ElideRight
                        }

                    }

                }

                // ---- edit drawer: accent rule, these fields reach Toggl ---
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 19
                    Layout.topMargin: 4
                    Layout.bottomMargin: 6
                    visible: blockRow.editing
                    spacing: 12

                    Rectangle {
                        // .drawer.edit { border-left: 1px solid var(--accent) }
                        Layout.fillHeight: true
                        Layout.preferredWidth: 1
                        color: panelTheme.accent
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        TextField {
                            id: descriptionField

                            Layout.fillWidth: true
                            // Bound without the rev tap, and guarded below, so the
                            // model write cannot re-enter this binding -- the loop
                            // the previous drawer logged on every keystroke.
                            text: blockRow.block.description
                            placeholderText: "Describe this block"
                            foreground: root.foreground
                            onTextChanged: {
                                if (text === blockRow.block.description)
                                    return ;

                                root.setBlockDescription(blockRow.block, text);
                            }
                            KeyNavigation.tab: tokenField
                            KeyNavigation.backtab: tokenField
                            // ↵ save + apply · esc close (guide 03). PanelKeyCatcher stands
                            // down while an editor has focus, so Escape reaches us here and
                            // must close the DRAWER, not the panel.
                            Keys.onReturnPressed: function(event) {
                                root.applyBlock(blockRow.block);
                                event.accepted = true;
                            }
                            Keys.onEscapePressed: function(event) {
                                root.closeEdit(blockRow.block);
                                event.accepted = true;
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            TextField {
                                id: tokenField

                                // The same token grammar as the command line:
                                // @project or @project/task, resolved on Enter or
                                // when focus leaves. Fuzzy, like the command line.
                                Layout.fillWidth: true
                                text: String(blockRow.block.tokenDraft || "")
                                onTextChanged: {
                                    if (text !== String(blockRow.block.tokenDraft || ""))
                                        root.mutateBlock(blockRow.block, function() {
                                        blockRow.block.tokenDraft = text;
                                    });

                                }
                                placeholderText: "@project/task"
                                foreground: root.foreground
                                onActiveFocusChanged: {
                                    if (!activeFocus && text.trim() !== "")
                                        root.resolveBlockToken(blockRow.block, text);

                                }
                                KeyNavigation.tab: descriptionField
                                KeyNavigation.backtab: descriptionField
                                // ↵ here resolves the token, then applies when that made
                                // the row ready -- one key from "@acme/backend" to written.
                                Keys.onReturnPressed: function(event) {
                                    root.resolveBlockToken(blockRow.block, text);
                                    root.applyBlock(blockRow.block);
                                    event.accepted = true;
                                }
                                Keys.onEscapePressed: function(event) {
                                    root.closeEdit(blockRow.block);
                                    event.accepted = true;
                                }
                            }

                            Text {
                                text: dayScope.at(blockRow.rev, Model.projectMeta(root.projects, root.tasks, blockRow.blockProjectId, blockRow.blockTaskId))
                                textFormat: Text.PlainText
                                color: blockRow.blockProjectId ? panelTheme.textMuted : panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            Text {
                                Layout.fillWidth: true
                                text: "writes a completed entry · never touches the running timer"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Button {
                                // The mouse path to apply. Keyboard is Enter on the row.
                                text: "APPLY"
                                enabled: !root.requestPending && dayScope.at(blockRow.rev, Model.blockReady(blockRow.block))
                                focusable: true
                                bordered: true
                                fontSize: Style.font.caption
                                foreground: panelTheme.accent
                                onClicked: root.applyBlock(blockRow.block)
                            }

                        }

                        Row {
                            // EDIT · ↵ save + apply · ⇥ next field · esc close. The guide
                            // also lists "space back to inspect"; inside a text field Space
                            // must type a space, so that one is not offered here.
                            spacing: 12

                            Repeater {
                                model: [["↵", "save + apply"], ["⇥", "next field"], ["esc", "close"]]

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

                        }

                        Text {
                            Layout.fillWidth: true
                            visible: blockRow.failure !== ""
                            text: blockRow.failure
                            color: panelTheme.urgent
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }

                    }

                }

            }

        }

        PanelSeparator {
            visible: root.dayVisibleBlocks.length > 0
            Layout.fillWidth: true
            Layout.topMargin: Style.spacing.rowGap
            foreground: root.foreground
        }

        // Hint bar: two tiers like the timer scope's -- keycap --dim15, word --dim18.
        RowLayout {
            visible: root.dayVisibleBlocks.length > 0
            Layout.fillWidth: true
            spacing: 14

            Repeater {
                model: root.dayVisibleBlocks.length > 0 ? [["space", "inspect"], ["e", "edit"], ["⇥", "wording"], ["↵", "apply"], ["⇧↵", dayScope.at(root.dayRevision, "apply ready · " + root.daySummary.applicable)], ["⌫", "skip"]] : []

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

        }

    }

}
