import QtQuick

// The column on the left: the pages of the Terminal. A lit plate and a bar slide to the chosen one.
Item {
    id: root
    property string page: "home"
    property real reveal: 1
    property string version: ""
    signal picked(string page)

    readonly property var entries: [
        { id: "home", label: "HOME" }, { id: "library", label: "LIBRARY" },
        { id: "options", label: "OPTIONS" }, { id: "support", label: "SUPPORT" }
    ]
    readonly property int at: Math.max(0, entries.findIndex(e => e.id === page))
    readonly property real first: 104
    readonly property real step: 82
    width: 96

    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }

    Rectangle { anchors.fill: parent; color: "#05070b"; opacity: 0.5 * root.reveal }
    Rectangle { x: parent.width - 1; width: 1; height: parent.height * root.reveal; color: Theme.line; opacity: 0.14 }

    Rectangle {
        x: 9; width: parent.width - 19
        y: root.first + root.at * root.step + 5
        height: root.step - 10
        color: "#ffffff"
        opacity: 0.06 * root.reveal
        Behavior on y { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
    }
    Rectangle {
        x: 0; width: 3
        y: root.first + root.at * root.step + 21
        height: root.step - 42
        color: Theme.cyan
        opacity: root.reveal
        Behavior on y { NumberAnimation { duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.1 } }
    }

    Repeater {
        model: root.entries
        delegate: Item {
            id: entry
            required property int index
            required property var modelData
            readonly property bool chosen: index === root.at
            readonly property real shows: root.ease(root.reveal * 2.2 - index * 0.24)
            y: root.first + index * root.step
            width: root.width; height: root.step
            opacity: shows
            transform: Translate { x: (1 - entry.shows) * -14 }

            NavGlyph {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 17
                width: 24; height: 24
                kind: entry.modelData.id
                tone: entry.chosen ? Theme.cyan : (over.hovered ? Theme.text : Theme.dim)
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 51
                text: entry.modelData.label
                font.family: Theme.display; font.pixelSize: 9; font.letterSpacing: 1.7
                color: entry.chosen || over.hovered ? Theme.text : Theme.dim
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
            HoverHandler { id: over; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: root.picked(entry.modelData.id) }
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 24
        text: "ALPHA\n" + root.version
        horizontalAlignment: Text.AlignHCenter
        lineHeight: 1.5
        font.family: Theme.display; font.pixelSize: 9; font.letterSpacing: 1.8
        color: Theme.faint
        opacity: root.reveal
    }
}
