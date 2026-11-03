import QtQuick

Item {
    id: cursor
    width: 76; height: 44
    property string label: "Remote"
    Canvas {
        width: 22; height: 28
        onPaint: {
            let ctx=getContext("2d");ctx.clearRect(0,0,width,height);
            ctx.beginPath();ctx.moveTo(2,2);ctx.lineTo(2,22);ctx.lineTo(7,17);
            ctx.lineTo(12,26);ctx.lineTo(16,24);ctx.lineTo(11,15);ctx.lineTo(20,15);ctx.closePath();
            ctx.fillStyle="#52e0db";ctx.fill();ctx.strokeStyle="#102c35";ctx.lineWidth=1.5;ctx.stroke();
        }
    }
    Rectangle {
        x:18;y:25;width:caption.implicitWidth+12;height:19;radius:5;color:"#133f48"
        Text{id:caption;anchors.centerIn:parent;text:cursor.label;color:"#bafdfa";font.pixelSize:10;font.family:"Segoe UI"}
    }
}
