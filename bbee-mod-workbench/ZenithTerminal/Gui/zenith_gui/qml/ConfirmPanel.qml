import QtQuick

// Asked before anything is taken away: what will happen, in plain words, and two answers.
Item {
    id: root
    property bool open: false
    property string title: ""
    property string body: ""
    property string label: "CONFIRM"
    property bool danger: true
    signal confirmed()
    signal cancelled()

    visible: appear > 0.01
    property real appear: open ? 1 : 0
    Behavior on appear { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }

    Rectangle { anchors.fill: parent; color: "#05070b"; opacity: 0.84 * root.appear }
    MouseArea { anchors.fill: parent; enabled: root.open; hoverEnabled: true; onWheel: (wheel) => wheel.accepted = true; onClicked: root.cancelled() }

    Item {
        id: card
        width: 600
        height: words.implicitHeight + 150
        anchors.centerIn: parent
        opacity: root.appear
        scale: 0.97 + 0.03 * root.appear
        MouseArea { anchors.fill: parent }

        Rule { width: parent.width; grow: root.appear; tone: root.danger ? Theme.rose : Theme.line; strength: 0.7 }
        Rule { width: parent.width; anchors.bottom: parent.bottom; grow: root.appear }
        Rectangle { anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: 3; color: Theme.panel; opacity: 0.95 }

        Text {
            x: 36; y: 30
            width: parent.width - 72
            text: root.title
            wrapMode: Text.WordWrap
            font.family: Theme.display; font.pixelSize: 20; font.letterSpacing: 2.4
            color: Theme.text
        }
        Text {
            id: words
            x: 36; y: 72
            width: parent.width - 72
            text: root.body
            wrapMode: Text.WordWrap
            font.family: Theme.body; font.pixelSize: 15; lineHeight: 1.34
            color: "#c6cfdc"
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 36
            anchors.bottom: parent.bottom; anchors.bottomMargin: 24
            spacing: 22
            GhostButton { label: "CANCEL"; anchors.verticalCenter: parent.verticalCenter; onClicked: root.cancelled() }
            OutlineButton { label: root.label; danger: root.danger; onClicked: root.confirmed() }
        }
    }
}
