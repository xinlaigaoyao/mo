import QtQuick

// A quiet action: a word, and a rule that opens under it when the pointer is over it.
Item {
    id: root
    property string label: ""
    property color tone: Theme.dim
    signal clicked()
    implicitWidth: word.implicitWidth + 8
    implicitHeight: 34

    Text {
        id: word
        anchors.centerIn: parent
        text: root.label
        font.family: Theme.display
        font.pixelSize: 12
        font.letterSpacing: 1.8
        color: hover.hovered ? Theme.text : root.tone
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - 6
        height: 1
        width: hover.hovered ? word.implicitWidth : 0
        color: Theme.text
        opacity: 0.7
        Behavior on width { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.clicked() }
}
