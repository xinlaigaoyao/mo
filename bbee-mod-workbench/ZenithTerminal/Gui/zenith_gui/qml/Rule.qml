import QtQuick

// A thin rule with a small tick at each end, as the game's own panels are closed off. `grow` opens it
// from its middle.
Item {
    id: root
    property real grow: 1
    property color tone: Theme.line
    property real strength: 0.5
    implicitHeight: 7

    Rectangle {
        anchors.centerIn: parent
        width: root.width * root.grow
        height: 1
        color: root.tone
        opacity: root.strength
    }
    Rectangle {
        x: root.width * (1 - root.grow) / 2
        width: 1; height: root.height
        color: root.tone
        opacity: root.strength * root.grow
    }
    Rectangle {
        x: root.width - root.width * (1 - root.grow) / 2 - 1
        width: 1; height: root.height
        color: root.tone
        opacity: root.strength * root.grow
    }
}
