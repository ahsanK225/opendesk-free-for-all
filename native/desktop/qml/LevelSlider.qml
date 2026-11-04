import QtQuick
import QtQuick.Controls

Slider {
    id:control
    property real modelValue:0
    property real requestedValue:0
    property bool awaiting:false
    property bool pending:false
    signal edited(real newValue)
    implicitWidth:240;implicitHeight:32
    locale:Qt.locale("en_US")
    LayoutMirroring.enabled:false
    Accessible.description:"Move right to increase, left to decrease"
    Binding{target:control;property:"value";value:control.modelValue;when:!control.pressed&&!control.awaiting;restoreMode:Binding.RestoreNone}
    onMoved:{requestedValue=value;awaiting=true;pending=true;if(!throttle.running)throttle.start();ackTimeout.restart();}
    onPressedChanged:{if(!pressed&&pending){throttle.stop();pending=false;edited(requestedValue);ackTimeout.restart();}}
    onModelValueChanged:{if(awaiting&&Math.abs(modelValue-requestedValue)<0.000001){awaiting=false;ackTimeout.stop();}}
    Timer{id:throttle;interval:40;onTriggered:{if(control.pending){control.pending=false;control.edited(control.requestedValue);}}}
    Timer{id:ackTimeout;interval:1500;onTriggered:control.awaiting=false}
    background:Rectangle {
        x:control.leftPadding;y:(control.height-height)/2
        width:control.availableWidth;height:5;radius:3;color:Theme.border
        Rectangle{width:parent.width*control.position;height:parent.height;radius:3;color:Theme.accent}
    }
    handle:Rectangle {
        x:control.leftPadding+control.position*(control.availableWidth-width)
        y:(control.height-height)/2;width:20;height:20;radius:10
        color:control.pressed?Theme.accentHover:Theme.accent
        border.width:2;border.color:Theme.panel
    }
}
