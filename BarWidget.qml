import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "daz.toggl-track"
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened : false
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function inject() {
    if (!panelLoader.item) return
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
    panelLoader.item.bar = root.bar
    panelLoader.item.settings = root.settings
  }
  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
  function switchPanel(direction) { return panelLoader.item && panelLoader.item.switchPanel ? panelLoader.item.switchPanel(direction) : false }
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  Loader { id: panelLoader; active: true; source: Qt.resolvedUrl("Panel.qml"); visible: false; onLoaded: { root.inject(); Qt.callLater(root.inject) } }
  onBarChanged: inject()
  onSettingsChanged: inject()

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    property string currentLabel: panelLoader.item && panelLoader.item.current ? panelLoader.item.barLabel : ""
    fixedWidth: root.vertical ? -1 : (timerRunning ? contentRow.implicitWidth + scaledHorizontalMargin * 2 : Style.bar.iconSlot)
    fixedHeight: root.vertical ? Style.bar.iconSlot : -1
    hasVisualContent: true
    horizontalMargin: 8.75
    verticalPadding: 8.75
    property bool timerRunning: panelLoader.item ? !!panelLoader.item.current : false

    Image {
      anchors.centerIn: parent
      visible: root.vertical
      width: Style.bar.iconFont
      height: Style.bar.iconFont
      source: Qt.resolvedUrl("assets/toggl-track.svg")
      fillMode: Image.PreserveAspectFit
      sourceSize: Qt.size(width, height)
    }

    Row {
      id: contentRow
      anchors.centerIn: parent
      visible: !root.vertical
      spacing: Style.space(6)

      Image {
        width: Style.bar.iconFont
        height: Style.bar.iconFont
        source: Qt.resolvedUrl("assets/toggl-track.svg")
        fillMode: Image.PreserveAspectFit
        sourceSize: Qt.size(width, height)
      }

      Text {
        text: button.timerRunning ? button.currentLabel : ""
        visible: button.timerRunning
        color: button.foreground
        font.family: button.fontFamily
        font.pixelSize: button.fontSize
        renderType: Text.NativeRendering
        verticalAlignment: Text.AlignVCenter
      }
    }

    onPressed: function(button) { if (button === Qt.RightButton && panelLoader.item) panelLoader.item.openWeb(); else root.togglePanel() }
  }
  IpcHandler {
    target: root.moduleName
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }
}
