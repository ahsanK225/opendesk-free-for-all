import QtQuick
Rectangle {
    property string version: ""
    implicitWidth: label.implicitWidth+16
    implicitHeight: 24
    radius: 5;color: Theme.elevated;border.color: Theme.border
    Text{id:label;anchors.centerIn:parent;text:"v"+parent.version;color:Theme.muted;font.family:"Consolas";font.pixelSize:11;verticalAlignment:Text.AlignVCenter}
}
