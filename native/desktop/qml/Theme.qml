pragma Singleton
import QtQuick
QtObject {
    property bool light: false
    readonly property color background: light?"#f3f5f9":"#0c0e14"
    readonly property color sidebar: light?"#ffffff":"#10131b"
    readonly property color panel: light?"#ffffff":"#151923"
    readonly property color elevated: light?"#eaf0f7":"#1b202d"
    readonly property color border: light?"#cbd4e1":"#282f3e"
    readonly property color text: light?"#1b293c":"#f2f4f8"
    readonly property color muted: light?"#495c75":"#a3adbf"
    readonly property color faint: light?"#60718a":"#8b97aa"
    readonly property color accent: light?"#d92f36":"#ef4444"
    readonly property color accentHover: light?"#bf222e":"#f25f5c"
    readonly property color success: light?"#147842":"#70d5a4"
    readonly property color warning: light?"#8a5800":"#e8bd74"
    readonly property color selected: light?"#fdebee":"#2d1c25"
    readonly property color accentText: light?"#b32230":"#ff8986"
    readonly property color hover: light?"#e4eaf3":"#242c3b"
    readonly property color pressed: light?"#d8e1ee":"#2b3446"
    readonly property color toggleOff: light?"#8d9cb0":"#47546b"
}
