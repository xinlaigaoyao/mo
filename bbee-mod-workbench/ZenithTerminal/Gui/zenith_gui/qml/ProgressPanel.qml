import QtQuick

// What is on screen while the loader works: the steps, a bar that moves, the loader's own last lines,
// and at the end either the way into the game or what went wrong, in the loader's words.
Item {
    id: root
    property bool open: false
    property bool running: false
    property string title: ""
    property var steps: []
    property int step: -1
    property string result: ""
    property string resultText: ""
    property var lines: []
    property string resultAction: ""     // play | backups | feedback | nothing
    signal play()
    signal folder(string which)
    signal closed()

    visible: shade.opacity > 0.01
    property real appear: open ? 1 : 0
    Behavior on appear { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }

    Rectangle { id: shade; anchors.fill: parent; color: "#05070b"; opacity: 0.86 * root.appear }
    MouseArea { anchors.fill: parent; enabled: root.open; hoverEnabled: true; onWheel: (wheel) => wheel.accepted = true }

    Item {
        id: card
        width: 660; height: 404
        anchors.centerIn: parent
        opacity: root.appear
        scale: 0.97 + 0.03 * root.appear

        Rule { id: top; width: parent.width; grow: root.appear }
        Rule { width: parent.width; anchors.bottom: parent.bottom; grow: root.appear }
        Rectangle { anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: 3; color: "#0a0d14"; opacity: 0.92 }

        Text {
            id: heading
            x: 36; y: 30
            text: root.result === "ok" ? "DONE" : (root.result === "error" ? "STOPPED" : root.title)
            font.family: Theme.display; font.pixelSize: 22; font.letterSpacing: 3
            color: root.result === "error" ? Theme.amber : Theme.text
        }
        HexMark {
            anchors.right: parent.right; anchors.rightMargin: 36; y: 30
            width: 26; height: 26
            fill: root.result === "ok" ? 1 : pulse
            tone: root.result === "error" ? Theme.amber : Theme.cyan
            outline: tone
            property real pulse: 0.3
            SequentialAnimation on pulse {
                loops: Animation.Infinite; running: root.running
                NumberAnimation { to: 1; duration: 620; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.3; duration: 620; easing.type: Easing.InOutSine }
            }
        }

        // the steps
        Column {
            x: 36; y: 84
            spacing: 9
            Repeater {
                model: root.steps
                delegate: Row {
                    required property int index
                    required property string modelData
                    spacing: 14
                    readonly property bool done: index < root.step || root.result === "ok"
                    readonly property bool now: index === root.step && root.running
                    HexMark {
                        width: 16; height: 16
                        anchors.verticalCenter: parent.verticalCenter
                        fill: parent.done ? 1 : (parent.now ? 0.55 : 0)
                        outline: parent.done || parent.now ? Theme.cyan : Theme.faint
                        stroke: 1.2
                        Behavior on fill { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
                    }
                    Text {
                        text: modelData.toUpperCase()
                        font.family: Theme.display; font.pixelSize: 13; font.letterSpacing: 1.5
                        color: parent.done ? Theme.dim : (parent.now ? Theme.text : Theme.faint)
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: Theme.base } }
                    }
                }
            }
        }

        // the bar: 28 cells, lit up to the current step, with a light running over the lit part
        Row {
            id: bar
            x: 36; y: 232
            spacing: 4
            readonly property int cells: 28
            readonly property real share: root.result === "ok" ? 1 : Math.max(0, Math.min(1, (root.step + 0.5) / Math.max(1, root.steps.length)))
            // the lit length follows the step smoothly: one animation per step, none per cell (a cell that started
            // its own animation on every frame also made a slow recording run at double speed)
            property real shown: share
            Behavior on shown { NumberAnimation { duration: 520; easing.type: Easing.OutCubic } }
            property real travel: 0
            NumberAnimation on travel { from: 0; to: 1; duration: 1300; loops: Animation.Infinite; running: root.running }
            Repeater {
                model: bar.cells
                delegate: Rectangle {
                    required property int index
                    width: (card.width - 72 - (bar.cells - 1) * 4) / bar.cells; height: 7
                    readonly property real lit: Math.max(0, Math.min(1, bar.shown * bar.cells - index))
                    readonly property real wave: Math.max(0, 1 - Math.abs(index / bar.cells - bar.travel * bar.shown) * 9)
                    color: root.result === "error" ? Theme.amber : Theme.cyan
                    opacity: 0.12 + lit * (root.running ? 0.43 + 0.45 * wave : 0.83)
                }
            }
        }

        // the loader's own words
        Column {
            x: 36; y: 258
            width: parent.width - 72
            spacing: 3
            visible: root.result === ""
            Repeater {
                model: root.lines
                delegate: Text {
                    required property int index
                    required property string modelData
                    width: parent.width
                    text: modelData
                    elide: Text.ElideRight
                    font.family: Theme.mono; font.pixelSize: 12
                    color: Theme.dim
                    opacity: 0.35 + 0.65 * (index + 1) / Math.max(1, root.lines.length)
                }
            }
        }
        Text {
            x: 36; y: 262
            width: parent.width - 72
            visible: root.result !== ""
            text: root.resultText
            wrapMode: Text.WordWrap
            maximumLineCount: 5
            elide: Text.ElideRight
            font.family: Theme.body; font.pixelSize: 15; lineHeight: 1.3
            color: Theme.text
        }

        Row {
            anchors.right: parent.right; anchors.rightMargin: 36
            anchors.bottom: parent.bottom; anchors.bottomMargin: 26
            spacing: 26
            visible: root.result !== ""
            GhostButton { label: "CLOSE"; anchors.verticalCenter: parent.verticalCenter; onClicked: root.closed() }
            OutlineButton {
                visible: root.resultAction === "backups" || root.resultAction === "feedback"
                anchors.verticalCenter: parent.verticalCenter
                label: "OPEN FOLDER"
                onClicked: root.folder(root.resultAction)
            }
            PrimaryButton {
                visible: root.resultAction === "play"
                implicitWidth: 200; implicitHeight: 48
                label: "PLAY"
                onClicked: root.play()
            }
        }
    }
}
