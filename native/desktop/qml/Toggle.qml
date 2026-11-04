import QtQuick
import QtQuick.Controls

Switch {
    id: control
    property bool modelChecked:false
    property bool requestedChecked:false
    property bool awaiting:false
    signal edited(bool enabled)
    implicitWidth: 94; implicitHeight: 34
    leftPadding: 58; rightPadding: 0
    locale: Qt.locale("en_US")
    LayoutMirroring.enabled: false
    Binding{target:control;property:"checked";value:control.modelChecked;when:!control.awaiting;restoreMode:Binding.RestoreNone}
    onToggled:{requestedChecked=checked;awaiting=true;edited(checked);ackTimeout.restart();}
    onModelCheckedChanged:{if(awaiting&&modelChecked===requestedChecked){awaiting=false;ackTimeout.stop();}}
    Timer{id:ackTimeout;interval:1500;onTriggered:control.awaiting=false}
    indicator: Rectangle {
        x:0;y:(control.height-height)/2;width:48;height:26;radius:13
        color:control.checked?Theme.accent:Theme.toggleOff
        Rectangle{x:control.checked?25:3;y:3;width:20;height:20;radius:10;color:"white";Behavior on x{NumberAnimation{duration:100}}}
    }
    contentItem: Text {
        text:control.checked?"On":"Off";color:Theme.text;font.pixelSize:12
        verticalAlignment:Text.AlignVCenter
    }
}
