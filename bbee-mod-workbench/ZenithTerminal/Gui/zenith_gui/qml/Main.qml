import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import Qt5Compat.GraphicalEffects

// The Zenith Terminal's window: a column of pages on the left (Home, Library, Options, Support), the
// chosen page in the middle, the featured or chosen mod's own pictures on the right, and one big
// action at the bottom.
ApplicationWindow {
    id: win
    width: 1280; height: 720
    minimumWidth: 1280; minimumHeight: 720
    maximumWidth: 1280; maximumHeight: 720
    x: shell.capture ? -6000 : (Screen.width - width) / 2
    y: shell.capture ? 60 : (Screen.height - height) / 2
    visible: true
    color: Theme.bg
    title: "The Zenith Terminal"
    flags: shell.capture ? (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus) : (Qt.Window | Qt.FramelessWindowHint)

    // ---- what is chosen ---------------------------------------------------------------------------------------
    property string page: "home"
    property string pageShown: "home"      // follows `page` once the old page has left
    property real pageIn: 0                // 0..1: the shown page's entrance
    readonly property var mods: controller.mods.filter(m => m.kind !== "CORE" || controller.settings.showCore)
    property int current: 0                // the Library's chosen mod
    readonly property var mod: mods.length > 0 ? mods[Math.min(current, mods.length - 1)] : null
    readonly property var heroes: {
        const faces = mods.filter(m => m.kind === "CHARACTER" && m.arts.length > 0)
        return faces.length > 0 ? faces : mods.filter(m => m.arts.length > 0)
    }
    property int featured: 0               // Home's featured character; it moves on by itself
    property int hoverHero: -1             // a card under the pointer is shown at once
    property real cycle: 0
    readonly property int heroAt: hoverHero >= 0 && hoverHero < heroes.length ? hoverHero : Math.min(featured, Math.max(0, heroes.length - 1))
    readonly property var hero: heroes.length > 0 ? heroes[heroAt] : null
    readonly property var stageWant: page === "home" ? hero : (page === "library" ? mod : null)
    readonly property string stageId: stageWant ? stageWant.id : ""
    property var shown: null               // the mod whose pictures and words are on screen
    property real swapIn: 0                // 0..1: they leave and come back when it changes
    property bool opened: false            // set once the window has put its first mod on show
    property string notice: ""

    // the opening: each part of the screen has its own 0..1
    property real bgIn: 0
    property real headIn: 0
    property real railIn: 0
    property real footIn: 0

    // animation time in milliseconds since the window opened (a recording reads it to space its frames evenly)
    property real clock: 0
    property real demoWait: 0      // what the hand-played install screen waits on between its steps
    NumberAnimation on clock { from: 0; to: 36000000; duration: 36000000; loops: Animation.Infinite }

    function ease(t) { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c) }
    function go(name) { if (name !== page) page = name }

    Binding { target: Theme; property: "calm"; value: controller.settings.motion === "calm" }
    Component.onCompleted: {
        if (controller.settings.startPage === "library") { page = "library"; pageShown = "library" }
        shown = stageWant
        opened = true
    }

    onPageChanged: { pageSwap.restart(); sweep.restart() }
    onStageIdChanged: if (opened && stageId !== "" && (!shown || shown.id !== stageId)) swap.restart()
    onModsChanged: {
        if (current >= mods.length) current = Math.max(0, mods.length - 1)
        if (shown) { const now = mods.find(m => m.id === shown.id); if (now) shown = now }
    }
    onHeroesChanged: if (featured >= heroes.length) featured = 0
    onNoticeChanged: if (notice !== "") noticeTimer.restart()

    ParallelAnimation {
        running: true
        NumberAnimation { target: win; property: "bgIn"; from: 0; to: 1; duration: 1200; easing.type: Easing.OutCubic }
        SequentialAnimation {
            PauseAnimation { duration: 160 }
            NumberAnimation { target: win; property: "headIn"; from: 0; to: 1; duration: 700; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            PauseAnimation { duration: 260 }
            NumberAnimation { target: win; property: "railIn"; from: 0; to: 1; duration: 900 }
        }
        SequentialAnimation {
            PauseAnimation { duration: 460 }
            NumberAnimation { target: win; property: "pageIn"; from: 0; to: 1; duration: 1100 }
        }
        SequentialAnimation {
            PauseAnimation { duration: 640 }
            NumberAnimation { target: win; property: "swapIn"; from: 0; to: 1; duration: 760; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            PauseAnimation { duration: 900 }
            NumberAnimation { target: win; property: "footIn"; from: 0; to: 1; duration: 600; easing.type: Easing.OutCubic }
        }
    }

    // a page is left quickly and the next one builds itself in
    SequentialAnimation {
        id: pageSwap
        NumberAnimation { target: win; property: "pageIn"; to: 0; duration: 130; easing.type: Easing.InCubic }
        ScriptAction { script: win.pageShown = win.page }
        NumberAnimation { target: win; property: "pageIn"; from: 0; to: 1; duration: 900 }
    }
    // the chosen mod changes: what is shown leaves, is replaced, and comes back in
    SequentialAnimation {
        id: swap
        NumberAnimation { target: win; property: "swapIn"; to: 0; duration: 120; easing.type: Easing.InCubic }
        ScriptAction { script: win.shown = win.stageWant }
        NumberAnimation { target: win; property: "swapIn"; to: 1; duration: 460; easing.type: Easing.OutCubic }
    }
    // Home moves on to the next character by itself, unless a card is under the pointer or something is open
    SequentialAnimation {
        id: cycler
        running: win.page === "home" && win.heroes.length > 1 && win.hoverHero < 0 && !controller.busy && !win.askOpen && !Theme.calm
        loops: Animation.Infinite
        NumberAnimation { target: win; property: "cycle"; from: 0; to: 1; duration: 7000 }
        ScriptAction { script: win.featured = (win.featured + 1) % Math.max(1, win.heroes.length) }
        onRunningChanged: if (!running) win.cycle = 0
    }

    Backdrop { anchors.fill: parent; reveal: win.bgIn }

    // ---- the pictures -----------------------------------------------------------------------------------------
    RadialGradient {
        id: aura
        property color tone: win.shown && win.shown.accent ? win.shown.accent : Theme.cyan
        Behavior on tone { ColorAnimation { duration: 520 } }
        width: 980; height: 980
        x: stage.focusX - width / 2
        y: win.height * 0.44 - height / 2
        opacity: stage.on * win.swapIn * win.bgIn * (win.shown && win.shown.enabled ? 1 : 0.4)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(aura.tone.r, aura.tone.g, aura.tone.b, 0.24) }
            GradientStop { position: 0.25; color: Qt.rgba(aura.tone.r, aura.tone.g, aura.tone.b, 0.09) }
            GradientStop { position: 0.5; color: Qt.rgba(aura.tone.r, aura.tone.g, aura.tone.b, 0.0) }
        }
    }
    Item {
        id: slash
        anchors.fill: parent
        clip: true
        visible: win.swapIn < 0.999 && stage.on > 0.5 && !Theme.calm
        Repeater {
            model: 2
            delegate: Rectangle {
                required property int index
                width: index === 0 ? 120 : 26
                height: win.height * 1.7
                x: stage.focusX - 620 + win.swapIn * (760 + 150 * index) - width / 2
                y: -win.height * 0.35
                rotation: 20
                color: aura.tone
                opacity: Math.sin(Math.PI * win.swapIn) * (index === 0 ? 0.16 : 0.34)
            }
        }
    }
    ArtStage {
        id: stage
        anchors.fill: parent
        readonly property bool home: win.page === "home"
        property real on: win.page === "home" || win.page === "library" ? 1 : 0
        Behavior on on { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        arts: win.shown ? win.shown.arts : []
        fade: win.swapIn
        lit: (win.shown && win.shown.enabled ? 1 : 0.4) * on * win.bgIn
        focusX: home ? win.width - 318 : win.width - 216
        focusY: win.height * 0.30
        groundY: win.height - 106
        zoom: home ? 1.06 : 1.0
        partyZoom: home ? 1.057 : 0.84
        clearFrom: home ? 610 : 850
        clearTo: home ? 800 : 975
        Behavior on focusX { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
        Behavior on zoom { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
        Behavior on partyZoom { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
        Behavior on clearFrom { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
        Behavior on clearTo { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
    }
    // a mod without a picture: its initial in a crest
    Item {
        id: crest
        visible: win.shown !== null && win.shown.arts.length === 0 && stage.on > 0.01
        width: 300; height: 300
        x: win.width - 418 + (1 - win.swapIn) * 44
        y: (win.height - height) / 2 - 40
        opacity: win.swapIn * stage.on * (win.shown && win.shown.enabled ? 1 : 0.45)
        property real turn: 0
        NumberAnimation on turn { from: 0; to: 360; duration: 90000; loops: Animation.Infinite; running: !Theme.calm }
        HexMark { anchors.fill: parent; stroke: 1.2; outline: Theme.line; opacity: 0.30; rotation: crest.turn }
        HexMark { anchors.centerIn: parent; width: 230; height: 230; stroke: 1.2; outline: Theme.cyan; opacity: 0.45; rotation: -crest.turn * 1.6 }
        Text {
            anchors.centerIn: parent
            text: win.shown ? win.shown.monogram : ""
            font.family: Theme.display; font.pixelSize: 120
            color: Theme.text
        }
    }

    // the foot of the window stays dark across its whole width, so the action reads over any picture
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 150
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0005070b" }
            GradientStop { position: 0.34; color: "#e605070b" }
            GradientStop { position: 1.0; color: "#fa05070b" }
        }
    }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right
        height: 104
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#f005070b" }
            GradientStop { position: 0.55; color: "#b005070b" }
            GradientStop { position: 1.0; color: "#0005070b" }
        }
    }

    // ---- the pages --------------------------------------------------------------------------------------------
    HomePage {
        anchors.fill: parent
        reveal: win.pageShown === "home" ? win.pageIn : 0
        heroes: win.heroes
        featured: win.heroAt
        cycle: win.hoverHero >= 0 ? 1 : win.cycle
        state: controller.state
        wanted: controller.mods.filter(m => m.enabled && !m.locked).length
        gameBuild: controller.gameBuild
        installedAt: controller.installedAt
        onHovered: (index) => { win.hoverHero = index; if (index >= 0) win.featured = index }
        onPicked: (index) => {
            const at = win.mods.findIndex(m => m.id === win.heroes[index].id)
            if (at >= 0) win.current = at
            win.hoverHero = -1
            win.go("library")
        }
    }
    LibraryPage {
        anchors.fill: parent
        reveal: win.pageShown === "library" ? win.pageIn : 0
        mods: win.mods
        current: win.current
        shown: win.shown
        swap: win.swapIn
        gameBuild: controller.gameBuild
        onChose: (index) => win.current = index
        onSwitched: (id, on) => controller.setEnabled(id, on)
        onAddAsked: addDialog.open()
        onUninstallAsked: (mod) => win.ask("UNINSTALL " + mod.title.toUpperCase() + "?",
            mod.title + " is taken out of your game" + (mod.kind === "CHARACTER" ? ", and the character's Evotypes and records are taken out of your save" : "")
            + ". A full copy of your save is made first. The mod's files stay in the Library, so it can be installed again.",
            "UNINSTALL", "uninstallMod:" + mod.id)
        onDeleteAsked: (mod) => win.ask("DELETE " + mod.title.toUpperCase() + "?",
            "The mod's folder is moved to the Recycle Bin. It is not in your game, so nothing else changes.",
            "DELETE FILES", "deleteMod:" + mod.id)
    }
    OptionsPage {
        id: options
        anchors.fill: parent
        reveal: win.pageShown === "options" ? win.pageIn : 0
        onAsk: (title, body, label, then) => win.ask(title, body, label, then)
        onGoSupport: win.go("support")
    }
    SupportPage {
        anchors.fill: parent
        reveal: win.pageShown === "support" ? win.pageIn : 0
        people: controller.supporters
        onOpen: (url) => controller.openLink(url)
        onCopy: (url) => controller.copyLink(url)
    }

    // a line of light crosses the page when it changes
    Item {
        id: sweep
        property real t: 1
        function restart() { run.restart() }
        NumberAnimation { id: run; target: sweep; property: "t"; from: 0; to: 1; duration: 620; easing.type: Easing.InOutCubic }
        x: 96 + t * (win.width - 96)
        y: 76; width: 2; height: win.height - 176
        visible: t < 1 && !Theme.calm
        opacity: Math.sin(Math.PI * t) * 0.8
        Rectangle { anchors.fill: parent; color: Theme.cyan }
        Rectangle {
            x: -220; width: 220; height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(Theme.cyan.r, Theme.cyan.g, Theme.cyan.b, 0) }
                GradientStop { position: 1; color: Qt.rgba(Theme.cyan.r, Theme.cyan.g, Theme.cyan.b, 0.14) }
            }
        }
    }

    // ---- the column of pages ----------------------------------------------------------------------------------
    NavRail {
        height: win.height
        page: win.page
        reveal: win.railIn
        version: "V" + controller.version
        onPicked: (name) => win.go(name)
    }
    Item {
        id: mark
        x: 25; y: 14; width: 46; height: 46
        opacity: win.headIn
        scale: 0.6 + 0.4 * win.ease(win.headIn * 1.4)
        rotation: (1 - win.ease(win.headIn * 1.4)) * -40
        Image {
            anchors.fill: parent
            source: Qt.resolvedUrl("../../art/logo/zenith_logo.png")
            sourceSize: Qt.size(184, 184)
            mipmap: true
        }
        Rectangle {
            id: glint
            width: 7; height: 7
            x: parent.width / 2 - width / 2; y: 2
            rotation: 45
            color: "#ffffff"
            opacity: 0
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                running: !Theme.calm
                PauseAnimation { duration: 3600 }
                NumberAnimation { to: 0.85; duration: 160; easing.type: Easing.OutCubic }
                NumberAnimation { to: 0; duration: 620; easing.type: Easing.InCubic }
            }
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: win.go("home") }
    }

    // ---- the top: the name, and the window's own buttons ------------------------------------------------------
    Item {
        id: head
        x: 96
        width: win.width - 96; height: 76
        DragHandler { target: null; onActiveChanged: if (active) win.startSystemMove() }

        Column {
            x: 30; y: 21
            spacing: 4
            opacity: win.headIn
            Text {
                text: "THE ZENITH TERMINAL"
                font.family: Theme.display; font.pixelSize: 17
                font.letterSpacing: 3.4 + (1 - win.headIn) * 7
                color: Theme.text
            }
            Text {
                text: "MOD LOADER FOR BLAZBLUE ENTROPY EFFECT   /   UNOFFICIAL"
                font.family: Theme.display; font.pixelSize: 10; font.letterSpacing: 2
                color: Theme.dim
            }
        }
        Text {
            visible: controller.preview
            anchors.right: parent.right; anchors.rightMargin: 118
            y: 31
            text: "PREVIEW  /  TEST COPY"
            font.family: Theme.display; font.pixelSize: 10; font.letterSpacing: 2.2
            color: Theme.amber
            opacity: win.headIn * 0.9
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 20
            y: 18
            spacing: 2
            opacity: win.headIn
            Item {
                width: 40; height: 36
                Rectangle { anchors.fill: parent; color: "#ffffff"; opacity: minHover.hovered ? 0.08 : 0 }
                Rectangle { anchors.centerIn: parent; width: 13; height: 1.4; color: Theme.dim }
                HoverHandler { id: minHover }
                TapHandler { onTapped: win.showMinimized() }
            }
            Item {
                width: 40; height: 36
                Rectangle { anchors.fill: parent; color: Theme.rose; opacity: closeHover.hovered ? 0.85 : 0 }
                Rectangle { anchors.centerIn: parent; width: 15; height: 1.4; rotation: 45; color: closeHover.hovered ? "#ffffff" : Theme.dim }
                Rectangle { anchors.centerIn: parent; width: 15; height: 1.4; rotation: -45; color: closeHover.hovered ? "#ffffff" : Theme.dim }
                HoverHandler { id: closeHover }
                TapHandler { onTapped: win.close() }
            }
        }
    }

    // ---- the foot: where things stand, the quiet action, the one big action ----------------------------------
    Rule { x: 124; y: win.height - 100; width: win.width - 158; grow: win.footIn; strength: 0.4 }
    Row {
        x: 126; y: win.height - 70
        spacing: 14
        opacity: win.footIn
        HexMark {
            width: 22; height: 22
            anchors.verticalCenter: parent.verticalCenter
            fill: controller.state === "installed" ? 1 : (controller.state === "changes" ? 0.6 : 0)
            tone: controller.state === "changes" ? Theme.amber : Theme.cyan
            outline: controller.state === "installed" ? Theme.cyan : (controller.state === "changes" ? Theme.amber : Theme.dim)
            Behavior on fill { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Text {
                text: controller.stateText.toUpperCase()
                font.family: Theme.display; font.pixelSize: 13; font.letterSpacing: 1.8
                color: Theme.text
            }
            Text {
                text: controller.gameBuild ? "GAME BUILD " + controller.gameBuild : "PRESS THE BUTTON AND THE GAME IS LOOKED FOR"
                font.family: Theme.body; font.pixelSize: 12; font.letterSpacing: 1
                color: Theme.dim
            }
        }
    }
    GhostButton {
        anchors.right: action.left; anchors.rightMargin: 34
        y: win.height - 66
        opacity: win.footIn
        visible: controller.state === "installed" || controller.state === "changes"
        label: "UNINSTALL EVERY MOD"
        onClicked: options.perform("uninstall")
    }
    PrimaryButton {
        id: action
        x: win.width - width - 34
        y: win.height - 79
        label: controller.actionLabel
        enabled: controller.canAct
        opacity: win.footIn * (enabled ? 1 : 0.4)
        transform: Translate { y: (1 - win.footIn) * 14 }
        onClicked: controller.primary()
    }

    Text {
        id: noticeLine
        anchors.right: parent.right; anchors.rightMargin: 34
        y: win.height - 130
        text: win.notice
        font.family: Theme.body; font.pixelSize: 14
        color: Theme.text
        opacity: win.notice !== "" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }
    Timer { id: noticeTimer; interval: 5000; onTriggered: win.notice = "" }
    Connections { target: controller; function onSaid(text) { win.notice = text } }

    // ---- a mod or a pack chosen from a zip ----------------------------------------------------------------------
    FileDialog {
        id: addDialog
        title: "Add a mod"
        nameFilters: ["Mods and packs (*.zip)"]
        onAccepted: { win.notice = controller.addMod(selectedFile.toString()); win.go("library") }
    }

    // ---- a mod dropped on the window --------------------------------------------------------------------------
    DropArea {
        id: drop
        anchors.fill: parent
        onDropped: (event) => {
            for (const url of event.urls) win.notice = controller.addMod(url.toString())
            win.go("library")
        }
    }
    Rectangle {
        anchors.fill: parent
        color: "#05070b"
        opacity: drop.containsDrag ? 0.84 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Text {
            anchors.centerIn: parent
            text: "LET GO TO ADD IT"
            font.family: Theme.display; font.pixelSize: 26; font.letterSpacing: 5
            color: Theme.text
        }
    }

    ProgressPanel {
        anchors.fill: parent
        open: controller.busy
        running: controller.running
        title: controller.title
        steps: controller.steps
        step: controller.step
        result: controller.result
        resultText: controller.resultText
        resultAction: controller.resultAction
        lines: controller.logTail
        onPlay: { controller.dismiss(); controller.play() }
        onFolder: (which) => { if (which === "feedback") controller.openFeedback(); else controller.openBackups() }
        onClosed: controller.dismiss()
    }

    // ---- asked before anything is taken away ------------------------------------------------------------------
    property bool askOpen: false
    property var asked: ({ title: "", body: "", label: "", then: "" })
    function ask(title, body, label, then) { asked = { title: title, body: body, label: label, then: then }; askOpen = true }
    function proceed(then) {
        if (then === "uninstall") controller.uninstall()
        else if (then === "repair") controller.repairSave()
        else if (then.startsWith("uninstallMod:")) controller.uninstallMod(then.slice(13))
        else if (then.startsWith("deleteMod:")) win.notice = controller.deleteMod(then.slice(10))
    }
    ConfirmPanel {
        anchors.fill: parent
        open: win.askOpen
        title: win.asked.title
        body: win.asked.body
        label: win.asked.label
        onConfirmed: { win.askOpen = false; win.proceed(win.asked.then) }
        onCancelled: win.askOpen = false
    }

    Shortcut { sequence: "Down"; enabled: win.page === "library"; onActivated: if (win.current < win.mods.length - 1) win.current += 1 }
    Shortcut { sequence: "Up"; enabled: win.page === "library"; onActivated: if (win.current > 0) win.current -= 1 }
    Shortcut {
        sequence: "Space"
        enabled: win.page === "library"
        onActivated: if (win.mod && !win.mod.locked) controller.setEnabled(win.mod.id, !win.mod.enabled)
    }
    Shortcut { sequence: "Escape"; onActivated: { if (win.askOpen) win.askOpen = false; else controller.dismiss() } }
    Shortcut { sequence: "Ctrl+1"; onActivated: win.go("home") }
    Shortcut { sequence: "Ctrl+2"; onActivated: win.go("library") }
    Shortcut { sequence: "Ctrl+3"; onActivated: win.go("options") }
    Shortcut { sequence: "Ctrl+4"; onActivated: win.go("support") }

    // ---- a recording drives the window with cues ("7|page=library"): nothing real is started by them ---------
    property string cue: ""
    onCueChanged: {
        const what = cue.slice(cue.indexOf("|") + 1)
        const eq = what.indexOf("=")
        const name = eq < 0 ? what : what.slice(0, eq), value = eq < 0 ? "" : what.slice(eq + 1)
        if (name === "page") go(value)
        else if (name === "select") current = parseInt(value)
        else if (name === "feature") { featured = parseInt(value); if (cycler.running) cycler.restart() }
        else if (name === "cat") options.cat = value
        else if (name === "install") demo.restart()
        else if (name === "ask" && mod) ask("UNINSTALL " + mod.title.toUpperCase() + "?",
            mod.title + " is taken out of your game, and the character's Evotypes and records are taken out of your save. A full copy of your save is made first. The mod's files stay in the Library, so it can be installed again.",
            "UNINSTALL", "")
        else if (name === "cancel") askOpen = false
    }
    // the install screen played by hand: nothing is installed
    SequentialAnimation {
        id: demo
        ScriptAction { script: controller.demoBegin("INSTALLING") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 520 }
        ScriptAction { script: controller.demoStep(0, "Game folder link  ok -> D:\\SteamLibrary\\steamapps\\common\\BlazblueEntropyEffect") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 620 }
        ScriptAction { script: controller.demoStep(1, "Reading the game data (takes a few minutes, only needed once and after each game update)...") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 900 }
        ScriptAction { script: controller.demoStep(1, "tables decoded: 188, failed: 1") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 520 }
        ScriptAction { script: controller.demoStep(2, "Save backed up to: save_backups\\20261009_162554_before_install") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 700 }
        ScriptAction { script: controller.demoStep(3, "game build 25627491; load order: ['bbee-sdk', 'bbee-actors', 'char-nine', 'char-ruby']") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 900 }
        ScriptAction { script: controller.demoStep(4, "NEW bundle entry: ui/texture/iconpotential/potential_rubytalent.ab") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 620 }
        ScriptAction { script: controller.demoStep(4, "installed 887 bundles into m_mod.m; merge.json updated (backup: merge.json.orig)") }
        NumberAnimation { target: win; property: "demoWait"; from: 0; to: 1; duration: 600 }
        ScriptAction { script: controller.demoFinish() }
    }
}
