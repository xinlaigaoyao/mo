import QtQuick
import QtQuick.Shapes

// The one big action. A cut-corner plate in the accent colour; a band of light crosses it now and then.
Item {
    id: root
    property string label: "INSTALL"
    property color tone: Theme.rose
    property bool lively: true
    property bool compact: false
    signal clicked()

    implicitWidth: 312; implicitHeight: 58
    readonly property real cut: compact ? 11 : 15
    opacity: enabled ? 1 : 0.4
    property real sheen: -0.4
    scale: !enabled ? 1 : (press.pressed ? 0.972 : (hover.hovered ? 1.018 : 1))
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

    SequentialAnimation on sheen {
        loops: Animation.Infinite
        running: root.lively && root.enabled && !Theme.calm
        PauseAnimation { duration: 2400 }
        NumberAnimation { from: -0.4; to: 1.4; duration: 1000; easing.type: Easing.InOutCubic }
    }

    Shape {
        anchors.fill: parent
        layer.enabled: true; layer.samples: 4; layer.smooth: true
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * (root.sheen - 0.22); y1: 0
                x2: root.width * (root.sheen + 0.22); y2: root.height
                GradientStop { position: 0.0; color: Qt.darker(root.tone, hover.hovered ? 1.0 : 1.08) }
                GradientStop { position: 0.5; color: Qt.lighter(root.tone, 1.45) }
                GradientStop { position: 1.0; color: Qt.darker(root.tone, hover.hovered ? 1.0 : 1.08) }
            }
            startX: root.cut; startY: 0
            PathLine { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.height - root.cut }
            PathLine { x: root.width - root.cut; y: root.height }
            PathLine { x: 0; y: root.height }
            PathLine { x: 0; y: root.cut }
            PathLine { x: root.cut; y: 0 }
        }
    }
    // a hairline inside the plate, as a machined edge
    Shape {
        anchors.fill: parent
        layer.enabled: true; layer.samples: 4; layer.smooth: true
        opacity: 0.35
        ShapePath {
            strokeColor: "#ffffff"; strokeWidth: 1; fillColor: "transparent"
            startX: root.cut + 3; startY: 4
            PathLine { x: root.width - 4; y: 4 }
            PathLine { x: root.width - 4; y: root.height - root.cut - 2 }
            PathLine { x: root.width - root.cut - 2; y: root.height - 4 }
            PathLine { x: 4; y: root.height - 4 }
            PathLine { x: 4; y: root.cut + 2 }
            PathLine { x: root.cut + 3; y: 4 }
        }
    }
    Text {
        anchors.centerIn: parent
        text: root.label
        font.family: Theme.display
        font.pixelSize: root.compact ? 13 : 17
        font.letterSpacing: root.compact ? 2 : 2.6
        color: "#ffffff"
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor; enabled: root.enabled }
    TapHandler { id: press; enabled: root.enabled; onTapped: root.clicked() }
}
