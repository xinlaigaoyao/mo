import QtQuick

// The moving field behind everything: the shader, and a few dozen small squares drifting up through it.
Item {
    id: root
    property real reveal: 0

    ShaderEffect {
        anchors.fill: parent
        property real time: 0
        property real intro: root.reveal
        property vector2d res: Qt.vector2d(Math.max(1, width), Math.max(1, height))
        property color glowA: Theme.cyan
        property color glowB: Theme.rose
        fragmentShader: "shaders/backdrop.frag.qsb"
        NumberAnimation on time { from: 0; to: 36000; duration: 36000000; loops: Animation.Infinite }
    }

    Repeater {
        model: 44
        delegate: Rectangle {
            id: mote
            required property int index
            readonly property real a: (index * 0.6180339887) % 1
            readonly property real b: (index * 0.7548776662) % 1
            property real rise: 0
            property real drift: 0
            property real flick: 1
            width: 2 + Math.round(b * 2)
            height: width
            color: index % 6 === 0 ? Theme.rose : (index % 2 ? Theme.cyan : "#ffffff")
            x: root.width * (0.03 + 0.94 * a) + drift
            y: root.height * (1.06 - 1.16 * ((rise + b) % 1))
            opacity: root.reveal * (0.08 + 0.30 * b) * flick

            NumberAnimation on rise { from: 0; to: 1; duration: 24000 + 30000 * mote.a; loops: Animation.Infinite }
            SequentialAnimation on drift {
                loops: Animation.Infinite
                NumberAnimation { to: 16; duration: 5200 + 3400 * mote.b; easing.type: Easing.InOutSine }
                NumberAnimation { to: -16; duration: 5200 + 3400 * mote.b; easing.type: Easing.InOutSine }
            }
            SequentialAnimation on flick {
                loops: Animation.Infinite
                PauseAnimation { duration: 1200 + 5200 * mote.a }
                NumberAnimation { to: 0.15; duration: 80 }
                NumberAnimation { to: 1; duration: 260 }
            }
        }
    }
}
