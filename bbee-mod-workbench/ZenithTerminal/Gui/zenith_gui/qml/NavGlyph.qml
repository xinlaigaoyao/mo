import QtQuick
import QtQuick.Shapes

// The four signs on the left column, drawn on a 24-unit grid in the same thin angular line as the rest
// of the window: a house, book spines, sliders, a faceted heart.
Item {
    id: root
    property string kind: "home"
    property color tone: Theme.dim
    property real stroke: 1.5
    implicitWidth: 24; implicitHeight: 24

    readonly property var paths: ({
        "home": "M 3 11.5 L 12 3.5 L 21 11.5 M 5.5 10 L 5.5 20.5 L 18.5 20.5 L 18.5 10 M 10 20.5 L 10 14.5 L 14 14.5 L 14 20.5",
        "library": "M 4 4 L 8.5 4 L 8.5 20 L 4 20 Z M 10.5 4 L 15 4 L 15 20 L 10.5 20 Z M 16.7 6.7 L 19.6 5.7 L 22.3 19.3 L 19.4 20.3 Z",
        "options": "M 3 6 L 12 6 M 17 6 L 21 6 M 12.5 4 L 16.5 4 L 16.5 8 L 12.5 8 Z M 3 12 L 6 12 M 11 12 L 21 12 M 6.5 10 L 10.5 10 L 10.5 14 L 6.5 14 Z M 3 18 L 14 18 M 19 18 L 21 18 M 14.5 16 L 18.5 16 L 18.5 20 L 14.5 20 Z",
        "support": "M 12 20.5 L 3 11.5 L 3 7 L 6.5 3.8 L 9.5 3.8 L 12 6.6 L 14.5 3.8 L 17.5 3.8 L 21 7 L 21 11.5 Z"
    })

    Shape {
        anchors.fill: parent
        layer.enabled: true; layer.samples: 4; layer.smooth: true
        ShapePath {
            strokeColor: root.tone
            strokeWidth: root.stroke
            fillColor: "transparent"
            joinStyle: ShapePath.MiterJoin
            capStyle: ShapePath.FlatCap
            scale: Qt.size(root.width / 24, root.height / 24)
            PathSvg { path: root.paths[root.kind] || "" }
        }
    }
}
