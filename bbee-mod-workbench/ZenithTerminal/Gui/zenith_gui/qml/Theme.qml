pragma Singleton
import QtQuick

// The one place colours, type and timing are written down. Measured against the game's own menus:
// near-black cool panels, thin light rules with end ticks, bracket marks on the chosen row, hexagon
// badges, and its two typefaces (Aldrich for labels, Chakra Petch for reading text).
QtObject {
    readonly property color bg: "#05070b"
    readonly property color panel: "#0a0d14"
    readonly property color line: "#c9d3e0"
    readonly property color text: "#e9eef6"
    readonly property color dim: "#8d97a9"
    readonly property color faint: "#4d5666"
    readonly property color cyan: "#4fdcf0"
    readonly property color rose: "#ff3f6c"
    readonly property color amber: "#ffb657"

    readonly property string display: "Aldrich"
    readonly property string body: "Chakra Petch"
    readonly property string mono: "Share Tech Mono"

    readonly property int fast: 140
    readonly property int base: 280
    readonly property int slow: 560

    // the person asked for a calm window (Options): nothing drifts or idles; things still answer a click
    property bool calm: false
}
