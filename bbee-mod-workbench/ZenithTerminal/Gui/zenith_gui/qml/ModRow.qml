import QtQuick

// One mod in the list. A click chooses it; a click on its badge (or the ON / OFF word) switches it.
Item {
    id: root
    property string title: ""
    property string version: ""
    property string note: ""
    property bool isOn: false
    property bool locked: false
    property bool compatible: true
    property bool selected: false
    property real reveal: 1
    signal chosen()
    signal switched(bool on)

    implicitHeight: 62
    opacity: reveal
    transform: Translate { x: (1 - root.reveal) * -22 }
    onIsOnChanged: if (isOn && reveal >= 1) ping.restart()

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: 1; anchors.bottomMargin: 1
        color: "#ffffff"
        opacity: root.selected ? 0.085 : (hover.hovered ? 0.045 : 0.02)
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    // the bracket marks the game puts on its chosen row
    Rectangle {
        width: 2; height: 24
        anchors.verticalCenter: parent.verticalCenter
        x: root.selected ? 7 : -3
        opacity: root.selected ? 1 : 0
        color: Theme.text
        Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    Rectangle {
        width: 2; height: 24
        anchors.verticalCenter: parent.verticalCenter
        x: root.width - width - (root.selected ? 7 : -3)
        opacity: root.selected ? 1 : 0
        color: Theme.text
        Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }

    // switched on: a ring leaves the badge
    HexMark {
        id: ring
        x: badge.x
        anchors.verticalCenter: parent.verticalCenter
        width: 24; height: 24
        outline: Theme.cyan
        stroke: 1.2
        opacity: 0
        ParallelAnimation {
            id: ping
            NumberAnimation { target: ring; property: "scale"; from: 1; to: 2.6; duration: 560; easing.type: Easing.OutCubic }
            NumberAnimation { target: ring; property: "opacity"; from: 0.9; to: 0; duration: 560; easing.type: Easing.OutCubic }
        }
    }
    HexMark {
        id: badge
        x: 26
        anchors.verticalCenter: parent.verticalCenter
        width: 24; height: 24
        fill: root.isOn ? 1 : 0
        tone: root.locked ? Theme.dim : Theme.cyan
        outline: root.isOn ? (root.locked ? Theme.dim : Theme.cyan) : Theme.faint
        Behavior on fill { NumberAnimation { duration: 340; easing.type: Easing.OutBack } }
    }

    Column {
        x: 66
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        Text {
            text: root.title.toUpperCase()
            font.family: Theme.display
            font.pixelSize: 15
            font.letterSpacing: 1.2
            color: root.isOn ? Theme.text : Theme.dim
            Behavior on color { ColorAnimation { duration: Theme.base } }
        }
        Text {
            text: "V" + root.version + (root.note ? "   " + root.note.toUpperCase() : "")
            font.family: Theme.body
            font.pixelSize: 12
            font.letterSpacing: 0.8
            color: root.compatible ? Theme.dim : Theme.amber
            elide: Text.ElideRight
            width: root.width - 66 - 78
        }
    }

    Text {
        anchors.right: parent.right
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        text: root.locked ? "CORE" : (root.isOn ? "ON" : "OFF")
        font.family: Theme.display
        font.pixelSize: 11
        font.letterSpacing: 1.8
        color: root.locked ? Theme.faint : (root.isOn ? Theme.cyan : Theme.faint)
        Behavior on color { ColorAnimation { duration: Theme.base } }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    MouseArea {
        anchors.fill: parent
        onClicked: (mouse) => {
            const onSwitch = mouse.x < 60 || mouse.x > root.width - 70
            if (onSwitch && !root.locked) root.switched(!root.isOn)
            root.chosen()
        }
    }
}
