import QtQuick

// The Library: every mod in the mods folder on the left, the chosen one in words in the middle. Its
// pictures are drawn by the window, behind this page.
Item {
    id: page
    property real reveal: 1        // 0..1: the page's entrance
    property var mods: []
    property int current: 0
    property var shown: null       // the mod whose words are on screen (it follows `current` after the swap)
    property real swap: 1          // 0..1: the words leave and come back when the chosen mod changes
    property string gameBuild: ""
    signal chose(int index)
    signal switched(string id, bool on)
    signal uninstallAsked(var mod)
    signal deleteAsked(var mod)
    signal addAsked()

    visible: reveal > 0.001

    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }
    function groupName(kind) { return kind === "CHARACTER" ? "CHARACTERS" : (kind === "CORE" ? "CORE FILES" : "MODS") }
    function kindName(kind) { return kind === "CHARACTER" ? "CHARACTER" : (kind === "CORE" ? "CORE FILE" : "MOD") }
    function where(m) {
        if (!m) return ""
        if (m.locked) return "GOES IN WITH ANY MOD"
        if (m.installed) return m.enabled ? "IN YOUR GAME" : "LEAVES WHEN YOU APPLY"
        return m.enabled ? "GOES IN WHEN YOU INSTALL" : "NOT IN YOUR GAME"
    }
    function whereTone(m) {
        if (!m || m.locked) return Theme.line
        if (m.installed && m.enabled) return Theme.cyan
        return m.installed !== m.enabled ? Theme.amber : Theme.line
    }

    // the rows keep their items while the list changes under them, so a switch is seen happening
    ListModel { id: rowsModel }
    function syncRows() {
        for (let i = 0; i < mods.length; ++i) {
            const m = mods[i]
            const row = { mid: m.id, title: m.title, version: m.version, note: m.note, kind: m.kind,
                          on: m.enabled, locked: m.locked, compatible: m.compatible,
                          opens: i === 0 || mods[i - 1].kind !== m.kind }
            if (i < rowsModel.count) rowsModel.set(i, row)
            else rowsModel.append(row)
        }
        while (rowsModel.count > mods.length) rowsModel.remove(rowsModel.count - 1)
    }
    Component.onCompleted: syncRows()
    onModsChanged: syncRows()

    // ---- the list ---------------------------------------------------------------------------------------------
    Item {
        id: list
        x: 124; y: 104
        width: 356
        height: page.height - y - 180

        Text {
            text: "YOUR MODS"
            font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 2.6
            color: Theme.dim
            opacity: page.ease(page.reveal * 3)
        }
        Text {
            anchors.right: parent.right
            text: page.mods.filter(m => m.enabled && !m.locked).length + " ON"
            font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 2.2
            color: Theme.cyan
            opacity: page.ease(page.reveal * 3)
        }
        Rule { y: 24; width: parent.width; grow: page.ease(page.reveal * 2.2) }

        Flickable {
            y: 36
            width: parent.width
            height: parent.height - 36
            contentHeight: rows.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: rows
                width: parent.width
                Repeater {
                    model: rowsModel
                    delegate: Column {
                        id: entry
                        required property int index
                        required property string mid
                        required property string title
                        required property string version
                        required property string note
                        required property string kind
                        required property bool on
                        required property bool locked
                        required property bool compatible
                        required property bool opens      // the first row of its group: the group's name goes above it
                        width: rows.width
                        readonly property real shows: page.ease(page.reveal * (1.6 + page.mods.length * 0.16) - 0.3 - index * 0.16)
                        Item {
                            visible: entry.opens
                            width: parent.width
                            height: entry.opens ? (entry.index === 0 ? 26 : 40) : 0
                            Text {
                                x: 2
                                anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                                text: page.groupName(entry.kind)
                                font.family: Theme.display; font.pixelSize: 10; font.letterSpacing: 2.4
                                color: Theme.faint
                                opacity: entry.shows
                            }
                        }
                        ModRow {
                            width: parent.width
                            title: entry.title
                            version: entry.version
                            note: entry.note
                            isOn: entry.on
                            locked: entry.locked
                            compatible: entry.compatible
                            selected: entry.index === page.current
                            reveal: entry.shows
                            onChosen: page.chose(entry.index)
                            onSwitched: (on) => page.switched(entry.mid, on)
                        }
                    }
                }
                Item {
                    width: parent.width; height: 58
                    opacity: page.ease(page.reveal * 2 - 1) * 0.9
                    Rectangle {
                        anchors.fill: parent; anchors.topMargin: 14
                        color: "transparent"
                        border.width: 1
                        border.color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.18)
                    }
                    Text {
                        anchors.centerIn: parent; anchors.verticalCenterOffset: 7
                        text: "+   DROP A MOD'S FOLDER OR ZIP HERE"
                        font.family: Theme.display; font.pixelSize: 10; font.letterSpacing: 2
                        color: Theme.faint
                    }
                }
            }
        }
    }

    // ---- the chosen mod, in words ---------------------------------------------------------------------------
    Column {
        id: detail
        x: 520; y: 122
        width: 360
        spacing: 0
        opacity: page.swap * page.ease(page.reveal * 2.2 - 0.7)
        transform: Translate { x: (1 - page.swap) * 28 + (1 - page.ease(page.reveal * 2.2 - 0.7)) * 22 }
        visible: page.shown !== null

        Row {
            spacing: 12
            Text {
                text: page.shown ? page.kindName(page.shown.kind) : ""
                font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 3
                color: page.shown && page.shown.accent ? page.shown.accent : Theme.cyan
            }
            Text {
                visible: page.shown && page.shown.note !== ""
                text: page.shown ? "/   " + page.shown.note.toUpperCase() : ""
                font.family: Theme.display; font.pixelSize: 11; font.letterSpacing: 2
                color: Theme.dim
            }
        }
        Item { width: 1; height: 10 }
        Text {
            width: parent.width
            text: page.shown ? page.shown.title.toUpperCase() : ""
            wrapMode: Text.WordWrap
            font.family: Theme.display; font.pixelSize: 38; font.letterSpacing: 1.4
            lineHeight: 1.05
            color: Theme.text
        }
        Item { width: 1; height: 16 }
        Rule {
            width: 236; grow: page.swap; strength: 0.7
            tone: page.shown && page.shown.accent ? page.shown.accent : Theme.line
        }
        Item { width: 1; height: 18 }
        Text {
            width: parent.width
            text: page.shown ? page.shown.about : ""
            wrapMode: Text.WordWrap
            maximumLineCount: 8
            elide: Text.ElideRight
            font.family: Theme.body; font.pixelSize: 15
            lineHeight: 1.36
            color: "#c6cfdc"
        }
        Item { width: 1; height: 20 }
        Flow {
            width: parent.width
            spacing: 8
            Chip { label: "VERSION"; value: page.shown ? page.shown.version : "" }
            Chip {
                label: page.shown && page.shown.compatible ? "GAME BUILD" : "CHECKED ON"
                value: page.shown ? (page.shown.compatible ? page.shown.checkedOn + "  OK" : page.shown.checkedOn + "  /  YOURS " + page.gameBuild) : ""
                tone: page.shown && page.shown.compatible ? Theme.line : Theme.amber
            }
            Chip { label: "STATE"; value: page.where(page.shown); tone: page.whereTone(page.shown) }
            Chip {
                visible: page.shown && page.shown.missing.length > 0
                label: "MISSING"
                value: page.shown ? page.shown.missing.join(", ").toUpperCase() : ""
                tone: Theme.amber
            }
        }
        Item { width: 1; height: 14 }
        Text {
            width: parent.width
            visible: text !== ""
            text: page.shown ? page.shown.credit : ""
            wrapMode: Text.WordWrap
            font.family: Theme.body; font.pixelSize: 12; font.letterSpacing: 0.3
            color: Theme.faint
        }
    }

    // a mod or a pack from a zip (a folder can be dropped on the window)
    OutlineButton {
        x: 124; y: page.height - 164
        opacity: page.ease(page.reveal * 2.2 - 1.0)
        label: "ADD A MOD"
        tone: Theme.dim
        onClicked: page.addAsked()
    }

    // what can be done with the chosen mod; it keeps its place whatever the length of the words above
    Row {
        x: 520; y: page.height - 164
        spacing: 12
        opacity: page.swap * page.ease(page.reveal * 2.2 - 1.0)
        visible: page.shown !== null && !page.shown.locked
        OutlineButton {
            label: page.shown && page.shown.enabled ? "SWITCH OFF" : "SWITCH ON"
            onClicked: page.switched(page.shown.id, !page.shown.enabled)
        }
        OutlineButton {
            visible: page.shown && page.shown.installed
            label: "UNINSTALL"
            danger: true
            onClicked: page.uninstallAsked(page.shown)
        }
        OutlineButton {
            visible: page.shown && !page.shown.installed
            label: "DELETE FILES"
            tone: Theme.dim
            onClicked: page.deleteAsked(page.shown)
        }
    }
}
