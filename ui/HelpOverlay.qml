import "../Model.js" as Model
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

// The keyboard reference (ruling R-AQ). Its content is Model.helpSections(),
// the same list the README is written from, so a key cannot exist in the panel
// and be missing here. Opened with ^? or a bare ? on an empty command line, or
// the header's ? button; dismissed with the same keys, Escape, Return, or a
// click anywhere.
Rectangle {
    id: helpOverlay

    required property var root
    required property var panelTheme
    readonly property var sections: Model.helpSections(root.scope)

    visible: root.helpOpen
    anchors.fill: parent
    // Fully opaque: at 0.97 the rows behind stayed legible through it and the
    // reference became unreadable.
    color: panelTheme.surface
    clip: true
    z: 100

    // Swallow clicks so a stray press lands on the overlay, not on a row behind it.
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.helpOpen = false
    }

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Style.spacing.rowGap
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.rowGap

            Text {
                text: "KEYBOARD"
                color: panelTheme.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1.2
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text: "esc to close"
                color: panelTheme.textDisabled
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
            }

        }

        PanelSeparator {
            Layout.fillWidth: true
            foreground: root.foreground
        }

        // Two columns, because one runs past the bottom of the panel: the
        // current scope's keys on the left, the shared ones on the right.
        RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.panelGap

            Repeater {
                model: helpOverlay.sections

                delegate: ColumnLayout {
                    id: keyColumn

                    required property var modelData
                    // The widest key label decides the gutter for this column.
                    readonly property real gutter: {
                        var widest = 0;
                        for (var i = 0; i < modelData.keys.length; i++) {
                            keyMetrics.text = modelData.keys[i][0];
                            widest = Math.max(widest, keyMetrics.implicitWidth);
                        }
                        return Math.ceil(widest) + 6;
                    }

                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignTop
                    spacing: 1

                    TextMetrics {
                        id: keyMetrics

                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                    }

                    Text {
                        text: modelData.title
                        color: panelTheme.textDisabled
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        font.letterSpacing: 1
                    }

                    Repeater {
                        model: modelData.keys

                        delegate: RowLayout {
                            required property var modelData

                            Layout.fillWidth: true
                            spacing: Style.spacing.rowGap

                            Text {
                                // Gutter sized to the widest key in this column,
                                // so nothing is clipped and nothing is padded.
                                Layout.preferredWidth: keyColumn.gutter
                                text: modelData[0]
                                color: panelTheme.text
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Text {
                                // Wrap, never elide: a keyboard reference that
                                // hides half a key's meaning is not a reference.
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: modelData[1]
                                color: panelTheme.textMuted
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                wrapMode: Text.WordWrap
                            }

                        }

                    }

                }

            }

        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: "Letters act on the cursor row only while the command line is empty; with text typed they type."
            color: panelTheme.textDisabled
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
        }

    }

}
