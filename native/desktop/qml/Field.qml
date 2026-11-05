import QtQuick
import QtQuick.Controls
TextField {
    id: control
    implicitHeight:46
    color:Theme.text
    placeholderTextColor:Theme.faint
    selectionColor:Theme.accent
    selectedTextColor:"white"
    font.pixelSize:14
    leftPadding:14
    rightPadding:14
    background:Rectangle{radius:Theme.radiusSmall;color:Theme.background;border.color:control.activeFocus?Theme.accent:Theme.border;border.width:control.activeFocus?2:1}
}
