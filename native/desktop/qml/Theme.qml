pragma Singleton
import QtQuick
QtObject {
    property bool light: false
    readonly property int radiusLarge: 8
    readonly property int radiusSmall: 4
    readonly property color background: light?"#f3f5f9":"#08090c"
    readonly property color sidebar: light?"#ffffff":"#0b0c10"
    readonly property color panel: light?"#ffffff":"#101116"
    readonly property color elevated: light?"#eaf0f7":"#16181f"
    readonly property color border: light?"#cbd4e1":"#262832"
    readonly property color text: light?"#1b293c":"#eceef2"
    readonly property color muted: light?"#495c75":"#a0a5b1"
    readonly property color faint: light?"#60718a":"#858a97"
    readonly property color accent: light?"#d92f36":"#e3172f"
    readonly property color accentHover: light?"#bf222e":"#ff2e45"
    readonly property color success: light?"#147842":"#4fd08f"
    readonly property color warning: light?"#8a5800":"#e0b35a"
    readonly property color selected: light?"#fdebee":"#2a0d13"
    readonly property color accentText: light?"#b32230":"#ff6072"
    readonly property color hover: light?"#e4eaf3":"#1c1e26"
    readonly property color pressed: light?"#d8e1ee":"#24262f"
    readonly property color toggleOff: light?"#8d9cb0":"#3f424e"
}
