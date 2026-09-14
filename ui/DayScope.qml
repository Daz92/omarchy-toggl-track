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

        TextMetrics {
            // The widest a duration ever gets; "—" and "0h04" both sit in it.
            id: durationMetrics

            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            text: "00h00"
        }

        Text {
            textFormat: Text.PlainText
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
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: root.dayLoaded && root.dayError === "" && root.dayBlocks.length === 0
            text: "No activity recorded for this day. If that looks wrong, check ActivityWatch with ./setup --check."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        Text {
            textFormat: Text.PlainText
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
                // Ruling T-B: this row's trailing column is a closed-vocabulary
                // label rather than a project name, so it is reserved instead
                // of elided.
                readonly property bool metaFixed: dayScope.at(rev, Model.blockMetaIsFixed(block))

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
                // The edit drawer's suggestion list overflows this row; without
                // this it is painted over by the block rows that follow.
                z: blockRow.editing ? 50 : 0

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
                            textFormat: Text.PlainText
                            Layout.preferredWidth: 11
                            text: Model.blockGlyph(blockRow.blockState)
                            color: dayScope.glyphColor(blockRow.blockState)
                            horizontalAlignment: Text.AlignHCenter
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            textFormat: Text.PlainText
                            text: dayScope.at(blockRow.rev, Model.clockTime(blockRow.block.start))
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Text {
                            // One width for every row. The column sized itself to
                            // its own text, which nobody noticed while every value
                            // was "0hNN" -- ruling T-I's em dash is narrower, and
                            // the descriptions on those rows started further left
                            // than the ones above and below them.
                            Layout.preferredWidth: durationMetrics.width
                            textFormat: Text.PlainText
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
                            // conflict, writing…, skipped. Applied and conflict
                            // must differ here as well as in glyph and colour.
                            // Ruling T-B, properly this time. A closed-vocabulary
                            // label takes preferredWidth and no fillWidth, so the
                            // layout hands it exactly its own text and the
                            // description is the only column that gives. Shortening
                            // the string was not enough on its own: "conflict" still
                            // came out "confli…" beside a long description, because
                            // fillWidth let this column shrink first.
                            Layout.fillWidth: !blockRow.metaFixed
                            Layout.preferredWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            Layout.minimumWidth: blockRow.metaFixed ? implicitWidth : 0
                            text: dayScope.at(blockRow.rev, Model.blockMeta(blockRow.block, root.projects, root.tasks))
                            textFormat: Text.PlainText
                            color: blockRow.blockState === "conflict" ? panelTheme.urgent : panelTheme.textDisabled
                            font.family: root.fontFamily
                            // Ruling T-D applies in the drawer, not here: at
                            // content size this column widened the row until it
                            // overflowed the panel. The row is a dense grid and
                            // already separates the two by colour.
                            font.pixelSize: Style.font.caption
                            elide: blockRow.metaFixed ? Text.ElideNone : Text.ElideRight
                        }

                        Text {
                            textFormat: Text.PlainText
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
                            // The whole description. The row above it is one
                            // line and elides, so a long entry -- and the ones
                            // that come back from Toggl are long -- could not be
                            // read anywhere in the panel. This is where it is
                            // readable in full; it wraps and never elides.
                            Layout.fillWidth: true
                            text: dayScope.at(blockRow.rev, blockRow.block.description || blockRow.block.label)
                            textFormat: Text.PlainText
                            color: panelTheme.text
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            // project · task, on its own line and wrapped, for
                            // the same reason: the row's copy is capped at its
                            // own content width and elides long client names.
                            Layout.fillWidth: true
                            text: dayScope.at(blockRow.rev, Model.blockMeta(blockRow.block, root.projects, root.tasks))
                            textFormat: Text.PlainText
                            color: blockRow.blockState === "conflict" ? panelTheme.urgent : panelTheme.textMuted
                            font.family: root.fontFamily
                            font.pixelSize: blockRow.metaFixed ? Style.font.caption : Style.font.bodySmall
                            wrapMode: Text.WordWrap
                        }

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
                                    textFormat: Text.PlainText
                                    text: barSection.modelData.title
                                    color: panelTheme.textDisabled
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                    font.letterSpacing: 1
                                }

                                Repeater {
                                    model: barSection.modelData.items.slice(0, 8)

                                    delegate: RowLayout {
                                        id: barRow

                                        required property var modelData

                                        Layout.fillWidth: true
                                        spacing: Style.spacing.rowGap

                                        Text {
                                            textFormat: Text.PlainText
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
                                            // Ruling T-H: app ids are shortened
                                            // for reading. Topics and domains
                                            // are already human names.
                                            text: barSection.modelData.title === "APPS" ? Model.appDisplayName(barRow.modelData.name) : barRow.modelData.name
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
                                        textFormat: Text.PlainText
                                        text: modelData[0]
                                        color: panelTheme.textMuted
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.caption
                                    }

                                    Text {
                                        textFormat: Text.PlainText
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
                            // Ruling T-B: drawer lines have no second home, so
                            // they wrap. This one carries an entry id, which is
                            // the kind of string a reader copies out.
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: dayScope.at(blockRow.rev, (blockRow.block.conflict ? "written as entry #" + blockRow.block.conflict.id : "") + (blockRow.block.createdWith ? "   created_with " + blockRow.block.createdWith : ""))
                            textFormat: Text.PlainText
                            color: panelTheme.textDisabled
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            wrapMode: Text.WordWrap
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

                        TextField {
                            id: tokenField

                            // Which row the keyboard is on; -1 is "none picked".
                            property int suggestionIndex: -1
                            // The text a pick left behind. The list stays shut
                            // for exactly that text, so choosing a row does not
                            // immediately re-offer the row just chosen, and one
                            // more keystroke opens it again.
                            property string pickedText: ""
                            readonly property var suggestions: activeFocus ? Model.tokenSuggestions(text, root.projects, root.tasks, 6) : []
                            // A fragment that matches nothing still opens the
                            // list, carrying one line that says so. An empty
                            // list and no list look identical, and "looks like
                            // nothing happened" is the failure this replaced.
                            readonly property bool searching: activeFocus && text.charAt(0) === "@" && text.trim().length > 1
                            readonly property bool listOpen: activeFocus && text !== pickedText && (suggestions.length > 0 || searching)

                            function choose(row) {
                                if (!row)
                                    return ;

                                tokenField.pickedText = row.token;
                                tokenField.text = row.token;
                                tokenField.suggestionIndex = -1;
                                root.pickBlockToken(blockRow.block, row);
                            }

                            function step(delta) {
                                var count = tokenField.suggestions.length;
                                if (!tokenField.listOpen || count === 0)
                                    return false;

                                var next = tokenField.suggestionIndex + delta;
                                tokenField.suggestionIndex = next < 0 ? count - 1 : (next >= count ? 0 : next);
                                return true;
                            }

                            // Full width, like the description field above it.
                            // The resolved name used to sit in a second column
                            // beside the field, which both narrowed the field
                            // and put the answer somewhere the eye was not.
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            // Above the rest of the drawer, so the suggestion
                            // list is not painted over by the APPLY row and the
                            // key hints that follow it in this column.
                            z: 10
                            text: String(blockRow.block.tokenDraft || "")
                            placeholderText: "@project/task"
                            foreground: root.foreground
                            onTextChanged: {
                                tokenField.suggestionIndex = -1;
                                if (text !== String(blockRow.block.tokenDraft || ""))
                                    root.mutateBlock(blockRow.block, function() {
                                    blockRow.block.tokenDraft = text;
                                });

                            }
                            onActiveFocusChanged: {
                                if (!activeFocus) {
                                    tokenField.suggestionIndex = -1;
                                    if (text.trim() !== "")
                                        root.resolveBlockToken(blockRow.block, text);

                                }
                            }
                            KeyNavigation.tab: descriptionField
                            KeyNavigation.backtab: descriptionField
                            Keys.onDownPressed: function(event) {
                                event.accepted = tokenField.step(1);
                            }
                            Keys.onUpPressed: function(event) {
                                event.accepted = tokenField.step(-1);
                            }
                            // ↵ takes the highlighted row when one is highlighted
                            // -- picking is not the same act as writing the entry,
                            // and one key must not do both. With nothing
                            // highlighted it resolves and applies, as before.
                            Keys.onReturnPressed: function(event) {
                                if (tokenField.suggestionIndex >= 0 && tokenField.listOpen) {
                                    tokenField.choose(tokenField.suggestions[tokenField.suggestionIndex]);
                                } else {
                                    root.resolveBlockToken(blockRow.block, text);
                                    root.applyBlock(blockRow.block);
                                }
                                event.accepted = true;
                            }
                            Keys.onEscapePressed: function(event) {
                                root.closeEdit(blockRow.block);
                                event.accepted = true;
                            }

                            Rectangle {
                                // Overlaid beneath the field rather than laid
                                // out under it: a list that pushed the rest of
                                // the day down by six rows on every keystroke
                                // moved the row the user was reading.
                                id: tokenList

                                visible: tokenField.listOpen
                                anchors.top: parent.bottom
                                anchors.topMargin: 2
                                anchors.left: parent.left
                                width: parent.width
                                height: tokenColumn.implicitHeight + 4
                                z: 200
                                color: panelTheme.surface
                                border.width: 1
                                border.color: Util.alpha(panelTheme.text, 0.22)

                                Column {
                                    id: tokenColumn

                                    y: 2
                                    width: parent.width

                                    Repeater {
                                        // Gated on the model: a Repeater is not
                                        // an Item, so `visible` would not hide
                                        // these rows.
                                        model: tokenField.listOpen ? tokenField.suggestions : []

                                        delegate: Rectangle {
                                            id: tokenRow

                                            required property var modelData
                                            required property int index

                                            width: tokenColumn.width
                                            height: Style.space(20)
                                            color: tokenRow.index === tokenField.suggestionIndex ? Util.alpha(panelTheme.accent, 0.2) : (tokenRowMouse.containsMouse ? Util.alpha(panelTheme.text, 0.08) : "transparent")

                                            MouseArea {
                                                id: tokenRowMouse

                                                anchors.fill: parent
                                                hoverEnabled: true
                                                onClicked: tokenField.choose(tokenRow.modelData)
                                            }

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: Style.spacing.controlPaddingX
                                                anchors.rightMargin: Style.spacing.controlPaddingX
                                                spacing: Style.spacing.rowGap

                                                Text {
                                                    Layout.fillWidth: true
                                                    Layout.minimumWidth: 0
                                                    text: tokenRow.modelData.label
                                                    textFormat: Text.PlainText
                                                    color: tokenRow.index === tokenField.suggestionIndex ? panelTheme.accent : panelTheme.text
                                                    elide: Text.ElideRight
                                                    font.family: root.fontFamily
                                                    font.pixelSize: Style.font.bodySmall
                                                }

                                                Text {
                                                    Layout.maximumWidth: implicitWidth
                                                    Layout.minimumWidth: 0
                                                    text: tokenRow.modelData.detail
                                                    textFormat: Text.PlainText
                                                    color: panelTheme.textDisabled
                                                    elide: Text.ElideRight
                                                    font.family: root.fontFamily
                                                    font.pixelSize: Style.font.caption
                                                }

                                            }

                                        }

                                    }

                                    Text {
                                        // Column leaves an invisible child out
                                        // of the layout, so this costs nothing
                                        // when there are rows to show.
                                        visible: tokenField.listOpen && tokenField.suggestions.length === 0
                                        width: tokenColumn.width
                                        height: Style.space(20)
                                        leftPadding: Style.spacing.controlPaddingX
                                        verticalAlignment: Text.AlignVCenter
                                        text: Model.tokenHint(tokenField.text, root.projects, root.tasks, root.tags)
                                        textFormat: Text.PlainText
                                        color: panelTheme.urgent
                                        elide: Text.ElideRight
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.caption
                                    }

                                }

                            }

                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            Text {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: "writes a completed entry · never touches the running timer"
                                color: panelTheme.textDisabled
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Button {
                                // The mouse path to apply. Keyboard is Enter on the row.
                                text: "Apply"
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
                                        textFormat: Text.PlainText
                                        text: modelData[0]
                                        color: panelTheme.textMuted
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.caption
                                    }

                                    Text {
                                        textFormat: Text.PlainText
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
        // clip, because this row has no give: a hint one word too long used to
        // push the whole column past the panel and clip every block row's
        // trailing column mid-glyph, with no ellipsis to show it had happened.
        RowLayout {
            visible: root.dayVisibleBlocks.length > 0
            Layout.fillWidth: true
            Layout.maximumWidth: parent.width
            clip: true
            spacing: 14

            Repeater {
                // ↵ and ⇧↵ say what they will actually do to THIS cursor row
                // and THIS day. Both used to be fixed strings, so the bar
                // offered "apply" on rows where the key does nothing.
                model: root.dayVisibleBlocks.length > 0 ? [["space", "inspect"], ["e", "edit"], ["⇥", "wording"], ["↵", dayScope.at(root.dayRevision, Model.enterHint(root.dayVisibleBlocks[root.dayCursorIndex]))], ["⇧↵", dayScope.at(root.dayRevision, Model.applyAllHint(root.daySummary))], ["⌫", "skip"]] : []

                delegate: Row {
                    required property var modelData

                    spacing: 4

                    Text {
                        textFormat: Text.PlainText
                        text: modelData[0]
                        color: panelTheme.textMuted
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                    Text {
                        textFormat: Text.PlainText
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
