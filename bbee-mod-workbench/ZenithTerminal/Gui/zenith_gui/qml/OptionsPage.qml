import QtQuick

// Options: the kinds on the left, a table of OPTION and STATUS on the right. Anything that takes
// something away asks first (the window shows the question).
Item {
    id: page
    property real reveal: 1
    property string cat: "general"
    property real catIn: 1         // 0..1: the rows' entrance after the kind is changed
    signal ask(string title, string body, string label, string then)
    signal goSupport()

    visible: reveal > 0.001
    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }
    onCatChanged: catSwap.restart()
    NumberAnimation { id: catSwap; target: page; property: "catIn"; from: 0; to: 1; duration: 520 }

    readonly property var cats: [
        { id: "general", label: "GENERAL" }, { id: "saves", label: "SAVES AND REPORTS" },
        { id: "interface", label: "INTERFACE" }, { id: "about", label: "ABOUT" }
    ]
    readonly property int at: Math.max(0, cats.findIndex(c => c.id === cat))

    function perform(act) {
        if (act === "mods") controller.openModsFolder()
        else if (act === "game") controller.openGameFolder()
        else if (act === "setup") controller.runSetup()
        else if (act === "backup") controller.backupSave()
        else if (act === "backups") controller.openBackups()
        else if (act === "report") controller.makeReport()
        else if (act === "log") controller.openLog()
        else if (act === "notices") controller.openNotices()
        else if (act === "support") page.goSupport()
        else if (act === "uninstall")
            page.ask("UNINSTALL EVERY MOD?", "Every mod is taken out of your game, and the mod characters' Evotypes and records are taken out of your save so the normal game can load it. A full copy of your save is made first. Your mods stay in the Library, ready to install again.", "UNINSTALL", "uninstall")
        else if (act === "repair")
            page.ask("REPAIR YOUR SAVE?", "Every mod character's data is taken out of your save: their Evotypes, their records, and a run in progress with one of them. Everything else stays as it is, and a full copy of your save is made first. Use this when the normal game will not load your save.", "REPAIR", "repair")
    }

    // the rows of the chosen kind; read again whenever what they show changes
    readonly property var rows: {
        if (cat === "general") return [
            { name: "MODS FOLDER", text: "Where your mods live. You can also drop a mod's folder or zip on the window.",
              kind: "button", label: "OPEN", act: "mods" },
            { name: "GAME", text: controller.gamePath !== "" ? "BlazBlue Entropy Effect" + (controller.gameBuild ? ", build " + controller.gameBuild + "." : ".")
                                  : "Not found yet. Press Set up and install and the Terminal looks for it.",
              detail: controller.gamePath,
              kind: "button", label: "OPEN", usable: controller.gamePath !== "", act: "game" },
            { name: "READ THE GAME'S DATA AGAIN", text: "Done once, and again after a game update. It takes a few minutes, and the game must be closed.",
              kind: "button", label: "READ AGAIN", act: "setup" },
            { name: "UNINSTALL EVERY MOD", text: "Takes every mod out of the game and cleans your save so the normal game loads it. Your save is backed up first, and your mods stay in the Library.",
              kind: "button", label: "UNINSTALL", danger: true,
              act: "uninstall" }
        ]
        if (cat === "saves") return [
            { name: "BACK UP MY SAVE", text: "A full copy of your save, kept in the Terminal's save_backups folder. The game must be closed.",
              kind: "button", label: "BACK UP", act: "backup" },
            { name: "SAVE BACKUPS", text: controller.backups + (controller.backups === 1 ? " copy" : " copies") + " so far. The Terminal makes one before every install and uninstall.",
              kind: "button", label: "OPEN", usable: controller.backups > 0, act: "backups" },
            { name: "REPAIR MY SAVE", text: "For a save the normal game will not load because it still holds a mod character. A backup is made first.",
              kind: "button", label: "REPAIR", danger: true,
              act: "repair" },
            { name: "FEEDBACK REPORT", text: "Zips your latest F9 reports and your mod versions into the feedback folder, to send with your notes. Nothing is uploaded.",
              kind: "button", label: "MAKE REPORT", act: "report" },
            { name: "LAST LOG", text: "What the loader printed the last time it ran. Useful in a bug report.",
              kind: "button", label: "OPEN", act: "log" }
        ]
        if (cat === "interface") return [
            { name: "MOTION", text: "Full: the backdrop and the pictures move. Calm: they hold still.",
              kind: "choice", key: "motion", options: [{ value: "full", label: "FULL" }, { value: "calm", label: "CALM" }] },
            { name: "OPEN ON", text: "The page the Terminal shows first.",
              kind: "choice", key: "startPage", options: [{ value: "home", label: "HOME" }, { value: "library", label: "LIBRARY" }] },
            { name: "CORE FILES", text: "Show the shared files the other mods run on in the Library. They go into the game by themselves.",
              kind: "choice", key: "showCore", options: [{ value: false, label: "HIDE" }, { value: true, label: "SHOW" }] }
        ]
        return [
            { name: "THE ZENITH TERMINAL", text: "A mod loader for BlazBlue Entropy Effect. Unofficial: not made or endorsed by 91Act or Arc System Works.",
              kind: "value", label: "V" + controller.version + "  ALPHA" },
            { name: "THE PEOPLE", text: "Redux, its characters and this window: Soulve. The mod loader: KittySkin.",
              kind: "button", label: "SUPPORT", act: "support" },
            { name: "OPEN-SOURCE PARTS", text: "Qt for Python (LGPL v3), and the typefaces Aldrich, Chakra Petch and Share Tech Mono (SIL Open Font License).",
              kind: "button", label: "NOTICES", act: "notices" }
        ]
    }

    // ---- the kinds --------------------------------------------------------------------------------------------
    Item {
        x: 124; y: 104
        width: 250

        Text {
            text: "OPTIONS"
            font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 2.6
            color: Theme.dim
            opacity: page.ease(page.reveal * 3)
        }
        Rule { y: 24; width: parent.width; grow: page.ease(page.reveal * 2.2) }
        Repeater {
            model: page.cats
            delegate: Item {
                id: kind
                required property int index
                required property var modelData
                readonly property bool chosen: index === page.at
                readonly property real shows: page.ease(page.reveal * 2.4 - 0.3 - index * 0.2)
                y: 44 + index * 52
                width: 250; height: 48
                opacity: shows
                transform: Translate { x: (1 - kind.shows) * -18 }
                Rectangle {
                    anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: 1
                    color: "#ffffff"
                    opacity: kind.chosen ? 0.085 : (over.hovered ? 0.045 : 0.02)
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Rectangle {
                    width: 2; height: 20
                    anchors.verticalCenter: parent.verticalCenter
                    x: kind.chosen ? 7 : -3
                    opacity: kind.chosen ? 1 : 0
                    color: Theme.text
                    Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Rectangle {
                    width: 2; height: 20
                    anchors.verticalCenter: parent.verticalCenter
                    x: parent.width - width - (kind.chosen ? 7 : -3)
                    opacity: kind.chosen ? 1 : 0
                    color: Theme.text
                    Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Text {
                    x: 24
                    anchors.verticalCenter: parent.verticalCenter
                    text: kind.modelData.label
                    font.family: Theme.display; font.pixelSize: 13; font.letterSpacing: 1.6
                    color: kind.chosen ? Theme.text : Theme.dim
                    Behavior on color { ColorAnimation { duration: Theme.base } }
                }
                HoverHandler { id: over; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: page.cat = kind.modelData.id }
            }
        }
    }

    // ---- the table --------------------------------------------------------------------------------------------
    Item {
        x: 420; y: 104
        width: page.width - x - 40

        Text {
            x: 14
            text: "OPTION"
            font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 2.6
            color: Theme.dim
            opacity: page.ease(page.reveal * 3)
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 14
            text: "STATUS"
            font.family: Theme.display; font.pixelSize: 12; font.letterSpacing: 2.6
            color: Theme.dim
            opacity: page.ease(page.reveal * 3)
        }
        Rule { y: 24; width: parent.width; grow: page.ease(page.reveal * 2.2) }
        Column {
            y: 34
            width: parent.width
            Repeater {
                model: page.rows
                delegate: OptionRow {
                    required property int index
                    required property var modelData
                    width: parent.width
                    name: modelData.name
                    text: modelData.text
                    detail: modelData.detail || ""
                    kind: modelData.kind
                    label: modelData.label || ""
                    danger: modelData.danger === true
                    usable: modelData.usable !== false
                    options: modelData.options || []
                    value: modelData.key ? controller.settings[modelData.key] : undefined
                    reveal: page.ease(Math.min(page.reveal, page.catIn) * 2.6 - 0.4 - index * 0.22)
                    onActivated: page.perform(modelData.act)
                    onPicked: (value) => controller.setSetting(modelData.key, value)
                }
            }
        }
    }
}
