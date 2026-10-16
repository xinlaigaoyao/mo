import QtQuick
import QtQuick.Shapes

// A second-rank action: a cut-corner outline that lights when the pointer is over it. `danger` is for
// the actions that take something away.
Item {
    id: root
    property string label: ""
    property color tone: Theme.line
    property bool danger: false
    signal clicked()

    implicitWidth: Math.max(128, word.implicitWidth + 44)
    implicitHeight: 38
    readonly property color ink: danger ? Theme.rose : tone
    readonly property real cut: 9
    property real glow: hover.hovered && enabled ? 1 : 0
    Behavior on glow { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    opacity: enabled ? 1 : 0.32
    scale: press.pressed ? 0.972 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

    Shape {
        anchors.fill: parent
        layer.enabled: true; layer.samples: 4; layer.smooth: true
        ShapePath {
            strokeColor: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.46 + 0.5 * root.glow)
            strokeWidth: 1.2
            fillColor: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.04 + 0.15 * root.glow)
            joinStyle: ShapePath.MiterJoin
            startX: root.cut; startY: 0.6
            PathLine { x: root.width - 0.6; y: 0.6 }
            PathLine { x: root.width - 0.6; y: root.height - root.cut }
            PathLine { x: root.width - root.cut; y: root.height - 0.6 }
            PathLine { x: 0.6; y: root.height - 0.6 }
            PathLine { x: 0.6; y: root.cut }
            PathLine { x: root.cut; y: 0.6 }
        }
    }
    Text {
        id: word
        anchors.centerIn: parent
        text: root.label
        font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 1.8
        color: Qt.rgba(root.ink.r + (1 - root.ink.r) * root.glow, root.ink.g + (1 - root.ink.g) * root.glow,
                       root.ink.b + (1 - root.ink.b) * root.glow, 1)
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor; enabled: root.enabled }
    TapHandler { id: press; enabled: root.enabled; onTapped: root.clicked() }
}
