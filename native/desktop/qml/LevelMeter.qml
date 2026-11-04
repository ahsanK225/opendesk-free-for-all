import QtQuick
// Square root makes quiet speech visible on a short bar.
Rectangle {
    property real level:0
    implicitWidth:48;implicitHeight:6;radius:3;color:Theme.border
    Rectangle{height:parent.height;radius:3;color:Theme.success;width:parent.width*Math.min(1,Math.sqrt(Math.max(0,parent.level)))}
}
