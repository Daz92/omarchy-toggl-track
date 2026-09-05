import QtQuick
import qs.Commons

// The panel's colour roles. Every old darkened-foreground call site in
// Panel.qml and ui/*.qml maps to one of textMuted/textFaint/textDisabled below;
// Util.alpha keeps the hue relationship to whatever the theme sets, which a
// fixed darkening factor does not. See docs/2026-09-04-panel-redesign.md §9.1.
QtObject {
    readonly property color surface: Color.popups.background
    readonly property color text: Color.popups.text
    readonly property color edge: Color.popups.border
    readonly property color textMuted: Util.alpha(Color.popups.text, 0.72)
    readonly property color textFaint: Util.alpha(Color.popups.text, 0.55)
    readonly property color textDisabled: Util.alpha(Color.popups.text, 0.38)
    readonly property color accent: Color.accent
    readonly property color urgent: Color.urgent
}
