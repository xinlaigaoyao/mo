import QtQuick
import Qt5Compat.GraphicalEffects

// A mod's own pictures on the right of the window. One figure is put by its face; a party stands on a
// ground line, the first in front. Each picture carries its own measurements (controller.py: _arts).
// Left of `clearFrom` nothing of a picture shows, right of `clearTo` all of it: words stay readable.
Item {
    id: root
    property var arts: []
    property real fade: 1          // 0..1: the pictures leave and come back when the mod changes
    property real lit: 1           // 1 when the mod is switched on, lower when it is off
    property real focusX: width - 300
    property real focusY: height * 0.30
    property real groundY: height - 108
    property real zoom: 1
    property real partyZoom: 1     // a party is drawn smaller where there is less room
    property real clearFrom: 700
    property real clearTo: 900

    // a party that would stand past the right edge is moved left as one
    readonly property real nudge: {
        let over = 0
        const unit = partyZoom * zoom * height
        for (let i = 0; i < arts.length; ++i) {
            const a = arts[i]
            if (!a.stand) continue
            const k = a.tall * unit / Math.max(1, (a.b - a.t) * a.h)
            over = Math.max(over, focusX + a.dx * unit + (a.r - a.ax) * a.w * k - (width - 10))
        }
        return over
    }

    Repeater {
        model: root.arts
        delegate: Item {
            id: figure
            required property int index
            required property var modelData
            readonly property var a: modelData
            readonly property real unit: (a.stand ? root.partyZoom : 1) * root.zoom * root.height
            readonly property real k: a.tall * unit / Math.max(1, (a.b - a.t) * a.h)
            readonly property real picW: a.w * k
            readonly property real picH: a.h * k
            readonly property real px: root.focusX + a.dx * unit - a.ax * picW - (a.stand ? root.nudge : 0)
                                       + (1 - root.fade) * (44 + 22 * index)
            readonly property real py: (a.stand ? root.groundY - a.dy * unit : root.focusY + a.dy * unit) - a.ay * picH
            // the veil, in the picture's own widths
            readonly property real p0: (root.clearFrom - px) / Math.max(1, picW)
            readonly property real p1: (root.clearTo - px) / Math.max(1, picW)
            readonly property real stopA: Math.max(0, Math.min(0.998, p0))
            readonly property real stopB: Math.max(stopA + 0.001, Math.min(1, p1))
            function shows(p) { return Math.max(0, Math.min(1, (p - p0) / Math.max(0.0001, p1 - p0))) }
            z: a.z

            Image {
                id: picture
                visible: false
                source: figure.a.src
                mipmap: true
                width: figure.picW; height: figure.picH
            }
            Rectangle {
                id: veil
                visible: false
                width: figure.picW; height: figure.picH
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Qt.rgba(1, 1, 1, figure.shows(0)) }
                    GradientStop { position: figure.stopA; color: Qt.rgba(1, 1, 1, figure.shows(figure.stopA)) }
                    GradientStop { position: figure.stopB; color: Qt.rgba(1, 1, 1, figure.shows(figure.stopB)) }
                    GradientStop { position: 1; color: Qt.rgba(1, 1, 1, figure.shows(1)) }
                }
            }
            OpacityMask {
                x: figure.px
                y: figure.py + bob
                width: figure.picW; height: figure.picH
                source: picture
                maskSource: veil
                visible: picture.status === Image.Ready
                opacity: root.fade * root.lit * figure.a.dim
                property real bob: 0
                SequentialAnimation on bob {
                    loops: Animation.Infinite
                    running: !Theme.calm
                    NumberAnimation { to: -7 + 2 * figure.index; duration: 4800 + 700 * figure.index; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 5 - 2 * figure.index; duration: 4800 + 700 * figure.index; easing.type: Easing.InOutSine }
                }
            }
        }
    }
}
