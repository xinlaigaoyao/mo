import QtQuick

// One line of the Options table: what it is and what it does on the left, its control on the right
// (a button, a choice between words, or a plain value).
Item {
    id: root
    property string name: ""
    property string text: ""
    property string detail: ""        // a path or another long single line, cut in its middle when too long
    property string kind: "button"     // button | choice | value
    property string label: ""
    property bool danger: false
    property bool usable: true
    property var options: []
    property var value
    property real reveal: 1
    signal activated()
    signal picked(var value)

    implicitHeight: Math.max(70, words.implicitHeight + 30)
    opacity: reveal
    transform: Translate { x: (1 - root.reveal) * 18 }

    Rectangle {
        anchors.fill: parent
        color: "#ffffff"
        opacity: over.hovered ? 0.035 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 1
        color: Theme.line
        opacity: 0.10
    }
    Column {
        id: words
        x: 14
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - 320
        spacing: 5
        Text {
            text: root.name
            font.family: Theme.display; font.pixelSize: 13; font.letterSpacing: 1.6
            color: root.danger ? Theme.rose : Theme.text
        }
        Text {
            width: parent.width
            text: root.text
            wrapMode: Text.WordWrap
            font.family: Theme.body; font.pixelSize: 13
            lineHeight: 1.25
            color: Theme.dim
        }
        Text {
            width: parent.width
            visible: root.detail !== ""
            text: root.detail
            elide: Text.ElideMiddle
            font.family: Theme.mono; font.pixelSize: 12
            color: Theme.faint
        }
    }
    Item {
        anchors.right: parent.right; anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        width: 280; height: 38
        OutlineButton {
            visible: root.kind === "button"
            anchors.right: parent.right
            label: root.label
            danger: root.danger
            enabled: root.usable
            onClicked: root.activated()
        }
        Segmented {
            visible: root.kind === "choice"
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            options: root.options
            value: root.value
            onPicked: (value) => root.picked(value)
        }
        Text {
            visible: root.kind === "value"
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: root.label
            font.family: Theme.mono; font.pixelSize: 14; font.letterSpacing: 0.6
            color: Theme.line
        }
    }
    HoverHandler { id: over }
}
