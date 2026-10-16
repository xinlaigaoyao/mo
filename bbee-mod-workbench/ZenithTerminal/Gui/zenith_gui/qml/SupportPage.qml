import QtQuick

// Support: the people who make the Terminal and its mods, each with a link to their own Ko-fi page.
// The links open in the person's browser; nothing is bought or unlocked here.
Item {
    id: page
    property real reveal: 1
    property var people: []        // [{name, role, site, url}] (links.json)
    signal open(string url)
    signal copy(string url)

    visible: reveal > 0.001
    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }

    Column {
        x: 128; y: 112
        width: 660
        spacing: 0

        Row {
            spacing: 10
            opacity: page.ease(page.reveal * 3)
            NavGlyph { width: 15; height: 15; kind: "support"; tone: Theme.rose; stroke: 1.4; anchors.verticalCenter: parent.verticalCenter }
            Text {
                text: "SUPPORT"
                font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 3
                color: Theme.rose
            }
        }
        Item { width: 1; height: 14 }
        Repeater {
            model: ["THE PEOPLE", "BEHIND IT"]
            delegate: Item {
                required property int index
                required property string modelData
                readonly property real shows: page.ease(page.reveal * 2.6 - 0.25 - index * 0.28)
                width: 660; height: 56
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
            width: 560
            text: "The Terminal and every mod in it are free, and they stay free. If you want to say thanks, these are the people who make them. A tip buys nothing and unlocks nothing: it helps them keep going."
            wrapMode: Text.WordWrap
            font.family: Theme.body; font.pixelSize: 16
            lineHeight: 1.36
            color: "#c6cfdc"
            opacity: page.ease(page.reveal * 2.4 - 0.8)
        }
    }

    Item {
        id: emblem
        x: page.width - 330; y: 118
        width: 230; height: 230
        opacity: page.ease(page.reveal * 2.2 - 0.8) * 0.9
        property real turn: 0
        NumberAnimation on turn { from: 0; to: 360; duration: 80000; loops: Animation.Infinite; running: !Theme.calm }
        HexMark { anchors.fill: parent; stroke: 1.2; outline: Theme.line; opacity: 0.26; rotation: emblem.turn }
        HexMark { anchors.centerIn: parent; width: 176; height: 176; stroke: 1.2; outline: Theme.rose; opacity: 0.42; rotation: -emblem.turn * 1.6 }
        NavGlyph { anchors.centerIn: parent; width: 78; height: 78; kind: "support"; tone: Theme.text; stroke: 1.6; opacity: 0.9 }
    }

    Row {
        x: 128; y: 384
        spacing: 20
        Repeater {
            model: page.people
            delegate: Item {
                id: card
                required property int index
                required property var modelData
                readonly property real shows: page.ease(page.reveal * 2.6 - 1.0 - index * 0.26)
                width: 436; height: 184
                opacity: shows
                transform: Translate { y: (1 - card.shows) * 22 }

                Rectangle { anchors.fill: parent; color: "#ffffff"; opacity: over.hovered ? 0.06 : 0.035; Behavior on opacity { NumberAnimation { duration: Theme.fast } } }
                Rule { width: parent.width; grow: card.shows; strength: 0.45 }

                Item {
                    id: crest
                    x: 24; y: 30
                    width: 58; height: 58
                    property real turn: 0
                    NumberAnimation on turn { from: 0; to: 360; duration: 60000; loops: Animation.Infinite; running: !Theme.calm }
                    HexMark { anchors.fill: parent; stroke: 1.2; outline: Theme.line; opacity: 0.55; rotation: crest.turn }
                    HexMark { anchors.centerIn: parent; width: 44; height: 44; stroke: 1.2; outline: Theme.rose; opacity: 0.7; rotation: -crest.turn * 1.5 }
                    Text {
                        anchors.centerIn: parent
                        text: String(card.modelData.name).charAt(0).toUpperCase()
                        font.family: Theme.display; font.pixelSize: 22
                        color: Theme.text
                    }
                }
                Column {
                    x: 104; y: 26
                    width: parent.width - 128
                    spacing: 6
                    Text {
                        text: String(card.modelData.name).toUpperCase()
                        font.family: Theme.display; font.pixelSize: 21; font.letterSpacing: 1.8
                        color: Theme.text
                    }
                    Text {
                        width: parent.width
                        text: card.modelData.role
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        font.family: Theme.body; font.pixelSize: 14
                        lineHeight: 1.25
                        color: Theme.dim
                    }
                    Text {
                        text: card.modelData.site
                        font.family: Theme.mono; font.pixelSize: 13; font.letterSpacing: 0.4
                        color: Theme.cyan
                    }
                }
                Row {
                    x: 24; y: parent.height - 58
                    spacing: 20
                    PrimaryButton {
                        implicitWidth: 176; implicitHeight: 40
                        label: "OPEN KO-FI"
                        compact: true
                        onClicked: page.open(card.modelData.url)
                    }
                    GhostButton { label: "COPY LINK"; anchors.verticalCenter: parent.verticalCenter; onClicked: page.copy(card.modelData.url) }
                }
                HoverHandler { id: over }
            }
        }
    }

    Text {
        x: 128; y: 580
        width: 900
        text: "Ko-fi is a separate site that opens in your browser. This is an unofficial fan project: BlazBlue Entropy Effect belongs to 91Act and Arc System Works, and the other characters to their owners."
        wrapMode: Text.WordWrap
        font.family: Theme.body; font.pixelSize: 12
        color: Theme.faint
        opacity: page.ease(page.reveal * 2.4 - 1.3)
    }
}
