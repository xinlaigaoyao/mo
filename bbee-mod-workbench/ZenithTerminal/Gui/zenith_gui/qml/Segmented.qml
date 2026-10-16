import QtQuick

// A choice between two or three words. The lit cell slides to the one that is chosen.
Item {
    id: root
    property var options: []       // [{value, label}]
    property var value
    signal picked(var value)

    readonly property real cell: 92
    implicitWidth: cell * options.length
    implicitHeight: 34
    readonly property int at: {
        for (let i = 0; i < options.length; ++i) if (options[i].value === value) return i
        return 0
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.26)
    }
    Rectangle {
        x: root.at * root.cell + 3; y: 3
        width: root.cell - 6; height: parent.height - 6
        color: Qt.rgba(Theme.cyan.r, Theme.cyan.g, Theme.cyan.b, 0.16)
        border.width: 1
        border.color: Qt.rgba(Theme.cyan.r, Theme.cyan.g, Theme.cyan.b, 0.7)
        Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
    }
    Repeater {
        model: root.options
        delegate: Item {
            required property int index
            required property var modelData
            x: index * root.cell
            width: root.cell; height: root.height
            Text {
                anchors.centerIn: parent
                text: modelData.label
                font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 1.6
                color: index === root.at ? Theme.cyan : (over.hovered ? Theme.text : Theme.dim)
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
            HoverHandler { id: over; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: if (index !== root.at) root.picked(modelData.value) }
        }
    }
}
