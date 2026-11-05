import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property string glyph: ""
    implicitHeight:40
    implicitWidth:Math.max(40,contentItem.implicitWidth+28)
    hoverEnabled:true
    font.pixelSize:13
    font.weight:Font.DemiBold
    opacity:enabled?1:0.42
    Accessible.name:text
    background:Rectangle {
        radius:Theme.radiusSmall
        color:control.primary?(control.down?Theme.accentHover:control.hovered?Theme.accentHover:Theme.accent):(control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet?"transparent":Theme.elevated)
        border.color:control.activeFocus?Theme.accent:control.quiet?"transparent":control.primary?"transparent":Theme.border
        border.width:control.activeFocus?2:1
        Behavior on color {ColorAnimation{duration:100}}
    }
    contentItem:RowLayout {
        spacing:8
        Glyph {text:control.glyph;visible:text.length>0;color:control.primary?"white":Theme.muted;Layout.alignment:Qt.AlignVCenter}
        Text {text:control.text;visible:text.length>0;color:control.primary?"white":Theme.text;font:control.font;renderType:Text.NativeRendering;elide:Text.ElideRight;Layout.fillWidth:true;Layout.alignment:Qt.AlignVCenter}
    }
}
