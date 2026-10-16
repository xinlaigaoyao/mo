import QtQuick

// Home: where things stand, in a few large words, and the characters in the Library as cards. The
// window draws the featured character's pictures behind this page and moves on to the next one by
// itself; a card under the pointer is shown at once, and a press opens it in the Library.
Item {
    id: page
    property real reveal: 1
    property var heroes: []        // the mods with a face to show
    property int featured: 0
    property real cycle: 0         // 0..1: how far the wait for the next one has got
    property string state: ""
    property int wanted: 0         // how many mods are switched on
    property string gameBuild: ""
    property string installedAt: ""
    signal picked(int index)
    signal hovered(int index)      // -1: the pointer left the cards

    visible: reveal > 0.001
    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }

    readonly property string count: wanted + (wanted === 1 ? " MOD" : " MODS")
    readonly property var lines: state === "installed" ? ["YOU ARE SET"]
                               : state === "changes" ? ["CHANGES", "WAITING"]
                               : state === "ready" ? (wanted > 0 ? [count + " READY", "TO INSTALL"] : ["NOTHING", "SWITCHED ON"])
                               : state === "setup" ? ["ONE SETUP", "STEP FIRST"]
                               : ["FIRST,", "YOUR GAME"]
    readonly property string advice: state === "installed" ? wanted + (wanted === 1 ? " mod is" : " mods are") + " in your game. Press Play, or start it from Steam. New characters are at the end of the Prototype list."
                                   : state === "changes" ? "You switched something. Press Apply changes and your game is rebuilt to match. Your save is backed up first."
                                   : state === "ready" ? (wanted > 0 ? "Press Install and they are built into your game. Your save is backed up first." : "Open the Library and switch a mod on.")
                                   : state === "setup" ? "The game's data has to be read for this build of the game. Press Set up and install; it takes a few minutes."
                                   : "Press Set up and install. The Terminal finds Entropy Effect on this PC and reads its data once, which takes a few minutes."
    readonly property string tag: state === "installed" ? "INSTALLED" : (state === "changes" ? "NOT APPLIED YET" : (state === "ready" && wanted > 0 ? "READY" : "TO DO"))
    readonly property color tagTone: state === "changes" || tag === "TO DO" ? Theme.amber : Theme.cyan

    Column {
        x: 128; y: 112
        width: 520
        spacing: 0

        Row {
            spacing: 10
            opacity: page.ease(page.reveal * 3)
            HexMark {
                width: 14; height: 14
                anchors.verticalCenter: parent.verticalCenter
                fill: page.state === "installed" ? 1 : 0.55
                tone: page.tagTone; outline: page.tagTone
                stroke: 1.2
            }
            Text {
                text: page.tag
                font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 3
                color: page.tagTone
            }
        }
        Item { width: 1; height: 14 }
        // each line of the headline rises into place behind its own edge
        Repeater {
            model: page.lines
            delegate: Item {
                required property int index
                required property string modelData
                readonly property real shows: page.ease(page.reveal * 2.6 - 0.25 - index * 0.28)
                width: 520; height: 56
                clip: true
                Text {
                    y: (1 - parent.shows) * 58
                    text: parent.modelData
                    font.family: Theme.display; font.pixelSize: 50; font.letterSpacing: 1.6
                    color: Theme.text
                }
            }
        }
        Item { width: 1; height: 14 }
        Rule { width: 250; grow: page.ease(page.reveal * 2.4 - 0.7); strength: 0.6 }
        Item { width: 1; height: 16 }
        Text {
            width: 452
            text: page.advice.charAt(0).toUpperCase() + page.advice.slice(1)
            wrapMode: Text.WordWrap
            font.family: Theme.body; font.pixelSize: 16
            lineHeight: 1.36
            color: "#c6cfdc"
            opacity: page.ease(page.reveal * 2.4 - 0.8)
        }
        Item { width: 1; height: 12 }
        Text {
            text: (page.gameBuild ? "GAME BUILD " + page.gameBuild : "GAME NOT FOUND YET")
                  + (page.installedAt ? "    /    LAST INSTALL " + page.installedAt.slice(0, 16) : "")
            font.family: Theme.mono; font.pixelSize: 12; font.letterSpacing: 0.6
            color: Theme.faint
            opacity: page.ease(page.reveal * 2.4 - 1.0)
        }
    }

    // ---- the characters ---------------------------------------------------------------------------------------
    Item {
        x: 128; y: 388
        width: 520; height: 224
        visible: page.heroes.length > 0

        Text {
            text: "IN YOUR LIBRARY"
            font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 2.6
            color: Theme.dim
            opacity: page.ease(page.reveal * 2.4 - 0.9)
        }
        ListView {
            id: cards
            y: 24
            width: parent.width; height: 196
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: page.heroes
            delegate: Item {
                id: card
                required property int index
                required property var modelData
                readonly property var art: modelData.arts.length > 0 ? modelData.arts[0] : null
                readonly property bool chosen: index === page.featured
                readonly property real shows: page.ease(page.reveal * 2.6 - 1.0 - index * 0.2)
                width: 152; height: 196
                opacity: shows
                transform: Translate { y: (1 - card.shows) * 20 }

                Rectangle {
                    anchors.fill: parent
                    color: "#ffffff"
                    opacity: card.chosen ? 0.09 : (over.hovered ? 0.055 : 0.028)
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                // the face, cut from the mod's own picture
                Item {
                    x: 1; y: 1
                    width: parent.width - 2; height: 136
                    clip: true
                    Rectangle { anchors.fill: parent; color: Theme.panel }
                    Image {
                        visible: card.art !== null
                        source: card.art ? card.art.src : ""
                        mipmap: true
                        readonly property real k: card.art ? card.art.card / Math.max(1, (card.art.b - card.art.t) * card.art.h) : 1
                        width: card.art ? card.art.w * k : 0
                        height: card.art ? card.art.h * k : 0
                        x: parent.width / 2 - (card.art ? card.art.fx : 0.5) * width
                        y: parent.height * 0.48 - (card.art ? card.art.fy : 0.2) * height
                        opacity: card.modelData.enabled ? 1 : 0.38
                        transformOrigin: Item.Center
                        scale: over.hovered || card.chosen ? 1.06 : 1
                        Behavior on scale { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                    }
                    Text {
                        visible: card.art === null
                        anchors.centerIn: parent
                        text: card.modelData.monogram
                        font.family: Theme.display; font.pixelSize: 54
                        color: Theme.dim
                    }
                    Rectangle {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 54
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#0005070b" }
                            GradientStop { position: 1; color: "#f005070b" }
                        }
                    }
                }
                Text {
                    x: 14; y: 146
                    width: parent.width - 28
                    text: card.modelData.title.toUpperCase()
                    elide: Text.ElideRight
                    font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 1
                    color: card.modelData.enabled ? Theme.text : Theme.dim
                }
                Row {
                    x: 14; y: 168
                    spacing: 7
                    HexMark {
                        width: 11; height: 11
                        anchors.verticalCenter: parent.verticalCenter
                        fill: card.modelData.enabled ? 1 : 0
                        outline: card.modelData.enabled ? Theme.cyan : Theme.faint
                        stroke: 1.1
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: (card.modelData.installed ? "IN GAME" : (card.modelData.enabled ? "ON" : "OFF")) + "   V" + card.modelData.version
                        font.family: Theme.body; font.pixelSize: 11; font.letterSpacing: 0.8
                        color: Theme.dim
                    }
                }
                // the chosen card: the game's bracket marks, and a hairline that fills until the next one
                Rectangle {
                    width: 2; height: 30; y: 150
                    x: card.chosen ? 4 : -4
                    opacity: card.chosen ? 1 : 0
                    color: Theme.text
                    Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Rectangle {
                    width: 2; height: 30; y: 150
                    x: parent.width - width - (card.chosen ? 4 : -4)
                    opacity: card.chosen ? 1 : 0
                    color: Theme.text
                    Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    height: 2
                    width: card.chosen ? parent.width * (page.heroes.length > 1 ? page.cycle : 1) : 0
                    color: card.modelData.accent ? card.modelData.accent : Theme.cyan
                    opacity: 0.9
                }
                HoverHandler {
                    id: over
                    cursorShape: Qt.PointingHandCursor
                    onHoveredChanged: page.hovered(hovered ? card.index : -1)
                }
                TapHandler { onTapped: page.picked(card.index) }
            }
        }
    }
}
