import QtQuick
import Quickshell
import QtQuick.Shapes
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Bar button plus popup for Momentum 4 headphones. Every headphone call goes
// through the bundled m4.py, which runs once per action and exits, so the
// widget keeps nothing resident besides this QML. Changes are queued per
// setting: dragging the slider sends only the latest value once the previous
// command returns. While the headphones are not connected over Bluetooth a
// refresh only reads the audio output and never touches the radio.
Panel {
  id: root
  moduleName: "mohak34.momentum"
  manageIpc: false

  readonly property var helper: ["python3", "-I", decodeURIComponent(Qt.resolvedUrl("m4.py").toString().replace(/^file:\/\//, ""))]
  readonly property int refreshMs: Math.max(30, parseInt(setting("refreshIntervalSec", 120), 10) || 120) * 1000

  // Last reply from m4.py status, see State in m4.py.
  property var m4: null
  // Last state the headphones themselves reported, restored when a change fails.
  property var confirmed: null
  property string error: ""
  // Setting name -> value still to send, oldest first.
  property var queued: ({})
  property real wheelAccumulator: 0

  readonly property bool connected: !!m4 && m4.connected
  readonly property bool hasQueue: Object.keys(queued).length > 0
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.4)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  function refresh() {
    if (getProc.running || setProc.running || hasQueue) return
    getProc.command = helper.concat(["status"])
    getProc.running = true
  }

  function send(setting, value) {
    if (!connected) return
    m4 = Model.apply(m4, setting, String(value))
    var q = Model.copy(queued)
    delete q[setting]
    q[setting] = String(value)
    queued = q
    flush()
  }

  function flush() {
    var keys = Object.keys(queued)
    if (setProc.running || keys.length === 0) return
    var q = Model.copy(queued)
    setProc.command = helper.concat(["set", keys[0], q[keys[0]]])
    delete q[keys[0]]
    queued = q
    setProc.running = true
  }

  function setTransparency(v) { send("transparency", Math.max(0, Math.min(100, Math.round(v)))) }

  function cycleNoise() { if (connected) send("noise", Model.nextNoise(m4.noise)) }

  function handle(text) {
    var out = null
    try { out = JSON.parse(text) } catch (e) {}
    if (!out) return
    if (out.error) { error = out.error; m4 = confirmed || out; return }
    error = ""
    m4 = out
    confirmed = out
  }

  onOpenedChanged: if (opened) refresh()

  Process {
    id: getProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (!setProc.running && !root.hasQueue) root.handle(text)
    }
  }

  // A reply that lands while newer changes are queued is already stale, so
  // only the last command in a burst updates the panel.
  Process {
    id: setProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (!root.hasQueue) root.handle(text)
    }
    onExited: Qt.callLater(root.flush)
  }

  Timer {
    interval: root.opened ? 10000 : root.refreshMs
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Item {
        Logo {
          anchors.centerIn: parent
          size: Style.space(12)
        }
      }
    }
    dimmed: !root.connected
    tooltipText: Model.tooltip(root.m4, root.error)
    onPressed: function(b) {
      if (b === Qt.RightButton) root.cycleNoise()
      else root.toggle()
    }
    onWheelMoved: function(delta) {
      if (!root.connected || root.m4.noise !== "custom") return
      var wheel = Util.wheelSteps(root.wheelAccumulator, delta)
      root.wheelAccumulator = wheel.remainder
      if (wheel.steps !== 0) root.setTransparency(root.m4.transparency + wheel.steps * 10)
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(340))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (dx !== 0 && root.connected && root.m4.noise === "custom") root.setTransparency(root.m4.transparency + dx * 10)
      }
      onActivateRequested: root.cycleNoise()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: panelColumn
        width: parent.width
        spacing: Style.space(10)

        PanelHero {
          width: parent.width
          title: "Momentum 4"
          meta: Model.status(root.m4, root.error)
          detail: root.connected ? root.m4.battery + "%" : ""
          foreground: root.foreground
          fontFamily: root.fontFamily
          iconOpacity: root.connected ? 1.0 : 0.5
          iconComponent: Component {
            Logo { size: Style.font.display }
          }
        }

        Text {
          visible: root.error !== "" || (!!root.m4 && !root.connected)
          width: parent.width
          textFormat: Text.PlainText
          text: root.error !== "" ? root.error : "Settings need the Bluetooth connection."
          color: root.error !== "" ? (root.bar ? root.bar.urgent : Color.urgent) : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.Wrap
        }

        Column {
          visible: root.connected
          width: parent.width
          spacing: Style.space(10)

          PanelSeparator { foreground: root.foreground }

          Choices {
            label: "NOISE"
            options: Model.noiseModes
            current: root.m4 ? root.m4.noise : ""
            onPicked: function(option) { root.send("noise", option.value) }
          }

          // 0 lets no outside sound through, 100 all of it. Only Custom uses it.
          Column {
            visible: !!root.m4 && root.m4.noise === "custom"
            width: parent.width
            spacing: Style.space(2)

            Item {
              width: parent.width
              implicitHeight: transparencyHeader.implicitHeight

              PanelSectionHeader {
                id: transparencyHeader
                text: "TRANSPARENCY"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: Math.round(slider.dragging ? slider.liveValue : (root.m4 ? root.m4.transparency : 0)) + "%"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            PanelSlider {
              id: slider
              bar: root.bar
              width: parent.width - Style.space(12)
              x: Style.space(6)
              minimum: 0
              maximum: 100
              step: 5
              integer: true
              value: root.m4 ? root.m4.transparency : 0
              onMoved: function(v) { root.setTransparency(v) }
            }

            Item {
              width: parent.width
              implicitHeight: blockedLabel.implicitHeight

              Text {
                id: blockedLabel
                textFormat: Text.PlainText
                text: "Blocked"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                anchors.right: parent.right
                textFormat: Text.PlainText
                text: "Let in"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Choices {
            label: "ANTI-WIND"
            options: Model.antiWindModes
            current: root.m4 ? root.m4.antiWind : ""
            onPicked: function(option) { root.send("anti-wind", option.value) }
          }

          PanelSeparator { foreground: root.foreground }

          Switches { label: "SOUND"; items: Model.sound }

          PanelSeparator { foreground: root.foreground }

          Switches { label: "BEHAVIOUR"; items: Model.behaviour }

          Choices {
            visible: !!root.m4 && root.m4.autoOff !== null && root.m4.autoOff !== undefined
            label: "AUTO POWER OFF"
            options: Model.autoOffChoices
            current: root.m4 ? root.m4.autoOff : -1
            onPicked: function(option) { root.send("auto-off", option.arg) }
          }

          PanelSeparator {
            visible: !!root.m4 && !!root.m4.firmware
            foreground: root.foreground
          }

          PanelSectionHeader {
            visible: !!root.m4 && !!root.m4.firmware
            text: "FIRMWARE " + (root.m4 ? root.m4.firmware : "")
            foreground: root.foreground
            fontFamily: root.fontFamily
          }
        }
      }
    }
  }

  // Sennheiser's logo from Simple Icons (CC0), drawn in the theme colour.
  component Logo: Shape {
    property real size: 16
    width: size
    height: size
    preferredRendererType: Shape.CurveRenderer

    ShapePath {
      fillColor: root.foreground
      strokeWidth: -1
      scale: Qt.size(size / 24, size / 24)
      PathSvg { path: "M0 3v18h24V3zm13.209 1.659c-1.428.548-2.799 1.757-3.905 4.182-.321.703-.925 2.062-1.2 2.67-2.224 4.882-3.364 5.932-6.72 5.932V4.35H13.15c.184-.011.235.25.06.309zm9.428 1.894V19.65H10.851c-.181.005-.227-.25-.055-.309 1.427-.548 2.798-1.757 3.904-4.182.321-.703.926-2.062 1.2-2.67 2.22-4.882 3.36-5.932 6.716-5.932z" }
    }
  }

  // Section header over a row of equal buttons; the current one is active.
  component Choices: Column {
    id: choices
    property string label: ""
    property var options: []
    property var current
    signal picked(var option)

    width: parent.width
    spacing: Style.space(6)

    PanelSectionHeader {
      text: choices.label
      foreground: root.foreground
      fontFamily: root.fontFamily
    }

    Row {
      id: buttons
      width: parent.width
      spacing: Style.spacing.xs

      Repeater {
        model: choices.options

        Button {
          required property var modelData
          width: (buttons.width - buttons.spacing * (choices.options.length - 1)) / choices.options.length
          text: modelData.label
          fontSize: Style.font.caption
          foreground: root.foreground
          fontFamily: root.fontFamily
          verticalPadding: Style.spacing.controlPaddingY
          bordered: true
          active: choices.current === modelData.value
          onClicked: choices.picked(modelData)
        }
      }
    }
  }

  // Section header over one switch per setting. Settings the firmware does
  // not report (null) are left out, and the section hides when none are left.
  component Switches: Column {
    id: switches
    property string label: ""
    property var items: []

    visible: !!root.m4 && items.some(function(item) { return root.m4[item.key] !== null && root.m4[item.key] !== undefined })
    width: parent.width
    spacing: Style.space(2)

    PanelSectionHeader {
      text: switches.label
      foreground: root.foreground
      fontFamily: root.fontFamily
    }

    Repeater {
      model: switches.items

      Item {
        required property var modelData
        readonly property var value: root.m4 ? root.m4[modelData.key] : null

        visible: value !== null && value !== undefined
        width: switches.width
        // The switch's focus ring may overhang; rows only need the track.
        implicitHeight: toggle.trackHeight + Style.space(6)

        Text {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: modelData.label
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        ToggleSwitch {
          id: toggle
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          checked: !!parent.value
          foreground: root.foreground
          onToggled: root.send(modelData.setting, parent.value ? "off" : "on")
        }
      }
    }
  }
}
