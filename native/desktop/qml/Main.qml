import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import OpenDesk.Media 1.0

ApplicationWindow {
    id: root
    visible:true
    width:1280;height:820;minimumWidth:760;minimumHeight:520
    title:lite?"OpenDesk Lite":"OpenDesk"
    color:Theme.background
    font.family:"Segoe UI"
    font.pixelSize:14
    palette.window:Theme.background;palette.windowText:Theme.text;palette.text:Theme.text;palette.buttonText:Theme.text
    palette.base:Theme.background;palette.button:Theme.elevated;palette.highlight:Theme.accent;palette.highlightedText:"white"
    property var model:backend.state
    Binding{target:Theme;property:"light";value:(root.model.settings||{}).theme==="light"}
    property string page:"home"
    property string activeKey:""
    property string serverActive:"home"
    property bool favoritesOnly:false
    readonly property bool lite:model.edition==="lite"
    readonly property string legacyRequestKey:current.needsLegacy?activeKey:""
    onLegacyRequestKeyChanged:{if(legacyRequestKey.length)legacyDialog.open();else legacyDialog.close();}
    readonly property string approvalRequestId:(model.incoming||{}).requestId||""
    onApprovalRequestIdChanged:{if(approvalRequestId.length)approval.open();else approval.close();}
    property var smokeUpdate:null
    property var smokeTransfer:null
    readonly property var updateInfo:smokeUpdate||model.update||({})
    readonly property string updateState:updateInfo.state||"idle"
    property string dismissedUpdate:""
    onUpdateStateChanged:{if(["downloading","verifying","installing","failed"].indexOf(updateState)>=0||(updateState==="available"&&updateInfo.version!==dismissedUpdate))updateDialog.open();else if(updateState==="idle"||updateState==="waiting")updateDialog.close();}
    onPageChanged:{if(page!=="files")return;if(!activeKey.length)for(let i=0;i<sessions.length;i++)if(sessions[i].state==="connected"){activeKey=sessions[i].key;break;}if(current.state==="connected"&&current.permissions&&current.permissions.file_transfer&&!current.files)send("list_files",{key:activeKey,path:"."});}
    readonly property bool sharingFiles:Boolean(model.hostSession&&model.hostSession.permissions&&model.hostSession.permissions.file_transfer)
    readonly property var transferInfo:smokeTransfer||current.transferInfo||({})
    readonly property bool transferRunning:transferInfo.state==="running"||transferInfo.state==="preparing"
    readonly property var sessions:model.connections||[]
    readonly property var current:session(activeKey)
    function session(key){for(let i=0;i<sessions.length;i++)if(sessions[i].key===key)return sessions[i];return {};}
    function send(type,data){let value=data||{};value.type=type;backend.command(value);}
    function connectTo(target){if(target.trim().length)send("connect",{target:target.trim(),password:password.text});}
    function navigate(value){page=value;}
    function formatSize(bytes){const units=["B","KB","MB","GB","TB"];let value=bytes||0,unit=0;while(value>=1024&&unit<units.length-1){value/=1024;unit++;}return (unit?value.toFixed(1):value)+" "+units[unit];}
    function focusAudio(){page="settings";Qt.callLater(function(){settingsScroll.contentItem.contentY=Math.max(0,audioPanel.y-12);});}
    function micText(s){let a=s.audio||{};if(s.permissions&&!s.permissions.audio)return "Voice off";return a.micRequested&&!a.micReady?"Mic retrying":a.micSilent&&s.micEnabled?"Mic silent":s.micEnabled?"Mic on":"Mic off";}
    function audioHelp(s){let a=s.audio||{};if(a.error)return a.error;if(a.micSilent&&s.micEnabled)return "Your microphone is on, but Windows is delivering no sound. Check the default input device and its level.";return "Voice packets sent: "+(a.txPackets||0)+" / received: "+(a.rxPackets||0);}
    function transferText(t){if(t.state==="failed"||t.state==="cancelled")return t.message||"";if(t.state==="done")return root.formatSize(t.total)+" transferred and verified";if(t.state==="preparing")return "Checking the file before sending…";let line=root.formatSize(t.done)+(t.total?" of "+root.formatSize(t.total):"")+"  ·  "+root.formatSize(t.speed||0)+"/s";if(t.total&&t.speed>0){const left=Math.ceil((t.total-t.done)/t.speed);line+="  ·  "+(left>=60?Math.ceil(left/60)+" min":left+" s")+" left";}return line;}
    Connections {target:backend;function onStateChanged(){if(root.model.exitRequested){root.close();return;}let key=root.model.activeTab||"home";if(key!==root.serverActive){root.serverActive=key;root.activeKey=key==="home"?"":key;root.page="home";}}}

    RowLayout {
        anchors.fill:parent;spacing:0
        Rectangle {
            Layout.preferredWidth:root.width<1080?76:214;Layout.fillHeight:true;color:Theme.sidebar
            Behavior on Layout.preferredWidth{NumberAnimation{duration:120}}
            Rectangle{anchors.right:parent.right;width:1;height:parent.height;color:Theme.border}
            ColumnLayout {
                anchors.fill:parent;anchors.margins:16;spacing:8
                RowLayout {
                    Layout.fillWidth:true;Layout.topMargin:8;Layout.bottomMargin:30;spacing:12
                    Image{source:"qrc:/brand/portal-o.svg";sourceSize.width:36;sourceSize.height:36;Layout.preferredWidth:36;Layout.preferredHeight:36}
                    ColumnLayout {visible:root.width>=1080;spacing:1
                        Text{text:root.title;font.pixelSize:20;font.weight:Font.DemiBold;color:Theme.text}
                        Text{text:"SILENT. DIRECT. IN CONTROL.";font.pixelSize:9;font.letterSpacing:0.8;color:Theme.faint}
                    }
                }
                Repeater {
                    model:[{key:"home",title:"Home",icon:"\ue80f"},{key:"saved",title:"Saved devices",icon:"\ue734"},{key:"files",title:"File transfer",icon:"\ue8b7"},{key:"settings",title:"Settings",icon:"\ue713"}].filter(item=>!root.lite||item.key!=="files")
                    delegate:Button {
                        required property var modelData
                        Layout.fillWidth:true;implicitHeight:46;hoverEnabled:true
                        Accessible.name:modelData.title
                        onClicked:root.navigate(modelData.key)
                        background:Rectangle{radius:Theme.radiusSmall;color:root.page===modelData.key?Theme.selected:parent.hovered?Theme.elevated:"transparent"}
                        contentItem:RowLayout{spacing:13;Glyph{text:modelData.icon;color:root.page===modelData.key?Theme.accentText:Theme.muted;Layout.alignment:Qt.AlignVCenter}Text{visible:root.width>=1080;text:modelData.title;font.pixelSize:13;font.weight:root.page===modelData.key?Font.DemiBold:Font.Normal;color:root.page===modelData.key?Theme.text:Theme.muted;Layout.fillWidth:true}}
                        ToolTip.visible:hovered&&root.width<1080;ToolTip.text:modelData.title
                    }
                }
                Item{Layout.fillHeight:true}
                Rectangle {Layout.fillWidth:true;implicitHeight:root.width>=1080?84:48;color:Theme.panel;radius:Theme.radiusSmall;border.color:Theme.border
                    ColumnLayout{anchors.fill:parent;anchors.margins:12;spacing:7
                        RowLayout{spacing:8;Rectangle{width:7;height:7;radius:4;color:root.model.statusTone==="ready"?Theme.success:root.model.statusTone==="error"?Theme.accent:Theme.warning}Text{visible:root.width>=1080;text:root.model.status||"Starting…";color:Theme.muted;font.pixelSize:11;elide:Text.ElideRight;Layout.fillWidth:true}}
                        VersionBadge{visible:root.width>=1080;version:root.model.version||"";Layout.alignment:Qt.AlignLeft|Qt.AlignVCenter}
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:0
            Rectangle {
                Layout.fillWidth:true;implicitHeight:58;color:Theme.sidebar
                Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:Theme.border}
                RowLayout {
                    anchors.fill:parent;anchors.leftMargin:24;anchors.rightMargin:24;spacing:6
                    ActionButton{text:"New connection";glyph:"\ue710";quiet:root.activeKey!=="";onClicked:{root.activeKey="";root.page="home";}}
                    Flickable{Layout.fillWidth:true;Layout.minimumWidth:60;implicitHeight:44;contentWidth:sessionTabs.implicitWidth;clip:true;flickableDirection:Flickable.HorizontalFlick
                    RowLayout{id:sessionTabs;height:parent.height;spacing:6
                    Repeater{model:root.sessions;delegate:RowLayout{required property var modelData;spacing:0
                        ActionButton{text:modelData.name||modelData.target;Layout.maximumWidth:180;glyph:"\ue7f8";quiet:root.activeKey!==modelData.key;onClicked:{root.activeKey=modelData.key;root.page="home";}}
                        ActionButton{glyph:"\ue711";quiet:true;implicitWidth:28;Accessible.name:"Close session";onClicked:root.send("close_session",{key:modelData.key})}
                    }}}
                    ScrollBar.horizontal:ScrollBar{policy:ScrollBar.AsNeeded}
                    }
                    Text{text:root.model.deviceName||"This desktop";color:Theme.faint;font.pixelSize:12;elide:Text.ElideRight;Layout.maximumWidth:180}
                }
            }
            StackLayout {
                Layout.fillWidth:true;Layout.fillHeight:true
                currentIndex:root.page==="settings"?3:root.page==="files"?2:root.page==="saved"?1:root.activeKey!==""?4:0
                ScrollView {
                    id:homeScroll;clip:true;contentWidth:availableWidth
                    ColumnLayout {
                        width:homeScroll.availableWidth;spacing:24
                        Item{implicitHeight:10}
                        ColumnLayout{Layout.leftMargin:32;Layout.rightMargin:32;Layout.fillWidth:true;spacing:7
                            Text{text:"Reach any desktop by its ID.";color:Theme.text;font.pixelSize:29;font.weight:Font.DemiBold}
                            Text{text:"Direct when the network allows it, relayed when it does not. You approve every session.";color:Theme.muted;font.pixelSize:13}
                        }
                        Panel {
                            Layout.fillWidth:true;Layout.leftMargin:32;Layout.rightMargin:32
                            ColumnLayout{anchors.fill:parent;spacing:16
                                Text{text:"CONNECT TO A DESKTOP";color:Theme.muted;font.pixelSize:10;font.weight:Font.DemiBold;font.letterSpacing:1}
                                RowLayout{Layout.fillWidth:true;spacing:12
                                    Field{id:address;Layout.fillWidth:true;placeholderText:"Enter a remote address or share link";Accessible.name:"Remote desktop address";onAccepted:root.connectTo(text)}
                                    Field{id:password;visible:root.width>=1000;Layout.preferredWidth:170;placeholderText:"Password, if required";echoMode:TextInput.Password;Accessible.name:"Remote access password";onAccepted:root.connectTo(address.text)}
                                    ActionButton{text:"Connect";glyph:"\ue72a";primary:true;implicitHeight:46;onClicked:root.connectTo(address.text);enabled:address.text.trim().length>0}
                                }
                                Text{text:"Incoming connections require your approval unless you enable unattended access.";color:Theme.faint;font.pixelSize:11;wrapMode:Text.WordWrap;Layout.fillWidth:true}
                            }
                        }
                        GridLayout {
                            Layout.fillWidth:true;Layout.leftMargin:32;Layout.rightMargin:32;columns:root.width>=1040?2:1;columnSpacing:20;rowSpacing:20
                            Panel {
                                Layout.fillWidth:true;Layout.preferredWidth:440;Layout.alignment:Qt.AlignTop;implicitHeight:239
                                ColumnLayout{anchors.fill:parent;spacing:15
                                    RowLayout{Text{text:"This desktop";font.pixelSize:16;font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true}Rectangle{width:6;height:6;radius:3;color:root.model.statusTone==="ready"?Theme.success:Theme.warning}Text{text:root.model.statusTone==="ready"?"Ready to connect":"Starting";color:Theme.muted;font.pixelSize:11}}
                                    Text{text:root.model.deviceId||"—";font.family:"Consolas";font.pixelSize:37;font.weight:Font.DemiBold;font.letterSpacing:1;color:Theme.text;Layout.topMargin:7}
                                    RowLayout{spacing:8;ActionButton{text:"Copy address";glyph:"\ue8c8";onClicked:backend.copyText(root.model.deviceId)}ActionButton{text:root.model.hasPassword?"Access settings":"Set password";glyph:"\ue72e";quiet:true;onClicked:localPassword.open()}ActionButton{text:"Copy LAN";quiet:true;visible:Boolean(root.model.lanUrl);onClicked:backend.copyText(root.model.lanUrl)}}
                                    Rectangle{Layout.fillWidth:true;height:1;color:Theme.border}
                                    RowLayout{Layout.fillWidth:true;Text{text:root.model.shareUrl?"Internet share link ready":root.model.lanUrl?"LAN: "+root.model.lanUrl:(root.model.settings||{}).lanAccess?"Local network access is on, but no local address is available":"Local network access is off";font.pixelSize:11;color:Theme.muted;elide:Text.ElideRight;Layout.fillWidth:true}ActionButton{glyph:"\ue71b";quiet:true;enabled:Boolean(root.model.shareUrl);Accessible.name:"Copy internet share link";onClicked:backend.copyText(root.model.shareUrl)}}
                                }
                            }
                            Panel {
                                Layout.fillWidth:true;Layout.preferredWidth:330;implicitHeight:239
                                ColumnLayout{anchors.fill:parent;spacing:14
                                    Text{text:"Made for focused work";font.pixelSize:16;font.weight:Font.DemiBold;color:Theme.text;Layout.bottomMargin:2}
                                    Repeater{model:[{icon:"\ue701",title:"Direct route",detail:"Goes straight to the other PC when it can."},{icon:"\ue720",title:"Clear conversations",detail:"Talk naturally while you work."},{icon:"\ue8d7",title:"You stay in control",detail:"Choose access for every session."}].filter(item=>!root.lite||item.icon!=="\ue720");delegate:RowLayout{required property var modelData;spacing:14;Glyph{text:modelData.icon;color:Theme.accentText}ColumnLayout{spacing:3;Text{text:modelData.title;color:Theme.text;font.pixelSize:12;font.weight:Font.DemiBold}Text{text:modelData.detail;color:Theme.muted;font.pixelSize:11}}}}
                                }
                            }
                        }
                        RowLayout{Layout.leftMargin:32;Layout.rightMargin:32;Layout.fillWidth:true;Text{text:"Recent desktops";font.pixelSize:18;font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true}ActionButton{text:"View all";quiet:true;onClicked:root.page="saved"}}
                        GridLayout {
                            Layout.leftMargin:32;Layout.rightMargin:32;Layout.fillWidth:true;columns:Math.max(1,Math.floor(width/270));rowSpacing:16;columnSpacing:16
                            Repeater{model:(root.model.recents||[]).slice(0,4);delegate:deviceCard}
                        }
                        Text{visible:!(root.model.recents||[]).length;text:"Your recent desktops will appear here after your first connection.";color:Theme.faint;font.pixelSize:13;Layout.leftMargin:32;Layout.rightMargin:32;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                        Item{implicitHeight:24}
                    }
                }
                ScrollView {id:savedScroll;clip:true;contentWidth:availableWidth
                    ColumnLayout{width:savedScroll.availableWidth;spacing:24
                        RowLayout{Layout.margins:32;Layout.fillWidth:true;Text{text:"Saved desktops";color:Theme.text;font.pixelSize:28;font.weight:Font.DemiBold;Layout.fillWidth:true}ActionButton{text:root.favoritesOnly?"Show all":"Favorites";glyph:"\ue734";onClicked:root.favoritesOnly=!root.favoritesOnly}}
                        GridLayout{Layout.leftMargin:32;Layout.rightMargin:32;Layout.fillWidth:true;columns:Math.max(1,Math.floor(width/270));rowSpacing:16;columnSpacing:16;Repeater{model:(root.model.recents||[]).filter(item=>!root.favoritesOnly||item.favorite);delegate:deviceCard}}
                        Text{visible:!(root.model.recents||[]).length;text:"Connect to a desktop to save it here.";color:Theme.muted;Layout.leftMargin:32}
                        Item{Layout.fillHeight:true;implicitHeight:24}
                    }
                }
                ColumnLayout {
                    spacing:18
                    RowLayout{Layout.margins:28;Layout.bottomMargin:0;Layout.fillWidth:true;ColumnLayout{spacing:5;Text{text:"File transfer";font.pixelSize:26;font.weight:Font.DemiBold;color:Theme.text}Text{text:root.current.state!=="connected"?"Connect to a desktop to browse the folder it shares.":root.current.permissions&&root.current.permissions.file_transfer?"Browse the folder shared by the remote desktop.":"The remote desktop did not allow file transfer for this session.";font.pixelSize:12;color:Theme.muted}}Item{Layout.fillWidth:true}ActionButton{text:"Send file";glyph:"\ue898";primary:true;enabled:Boolean(root.current.permissions&&root.current.permissions.file_transfer);onClicked:backend.uploadFile(root.activeKey,(root.current.files||{}).path||".")}}
                    Panel{visible:!root.lite;padding:16;Layout.fillWidth:true;Layout.leftMargin:28;Layout.rightMargin:28;Layout.topMargin:14;Layout.bottomMargin:14
                        RowLayout{anchors.fill:parent;spacing:12;Glyph{text:"\ue8b7";color:Theme.warning}
                            ColumnLayout{spacing:3;Layout.fillWidth:true
                                RowLayout{spacing:8;Text{text:"Your shared folder";color:Theme.text;font.pixelSize:13;font.weight:Font.DemiBold}Rectangle{implicitWidth:8;implicitHeight:8;radius:4;color:root.sharingFiles?Theme.success:Theme.toggleOff}Text{text:root.sharingFiles?"Shared with "+root.model.hostSession.peer+" now":"Not shared right now";color:root.sharingFiles?Theme.success:Theme.muted;font.pixelSize:11}}
                                Text{text:(root.model.settings||{}).sharedRoot||"";color:Theme.muted;font.pixelSize:11;elide:Text.ElideMiddle;Layout.fillWidth:true}
                                Text{text:((root.model.hostSession||{}).lastFile?"Received: "+root.model.hostSession.lastFile:"People you approve with file access can open and change this folder.");color:Theme.faint;font.pixelSize:11;elide:Text.ElideMiddle;Layout.fillWidth:true}
                            }
                            ActionButton{text:"Open folder";onClicked:backend.openSharedFolder()}ActionButton{text:"Change folder";onClicked:backend.chooseSharedFolder()}
                        }
                    }
                    Panel{Layout.fillWidth:true;Layout.fillHeight:true;Layout.margins:28;Layout.topMargin:0
                        ColumnLayout{anchors.fill:parent;spacing:14
                            RowLayout{Layout.fillWidth:true;ActionButton{glyph:"\ue74a";Accessible.name:"Parent directory";enabled:Boolean((root.current.files||{}).parent);onClicked:root.send("list_files",{key:root.activeKey,path:root.current.files.parent})}Field{id:remotePath;Layout.fillWidth:true;text:(root.current.files||{}).path||".";Accessible.name:"Remote folder";onAccepted:root.send("list_files",{key:root.activeKey,path:text})}ActionButton{glyph:"\ue72c";Accessible.name:"Refresh folder";enabled:root.current.state==="connected";onClicked:root.send("list_files",{key:root.activeKey,path:remotePath.text})}}
                            Text{visible:fileList.count===0;text:root.current.state!=="connected"?"No remote desktop is connected.":!(root.current.permissions&&root.current.permissions.file_transfer)?"Ask the remote desktop to tick file access when approving you.":root.current.files?"This folder is empty.":"Loading the shared folder…";color:Theme.muted;font.pixelSize:13;horizontalAlignment:Text.AlignHCenter;Layout.fillWidth:true;Layout.topMargin:24}
                            ListView{id:fileList;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:3;model:(root.current.files||{}).entries||[]
                                delegate:ItemDelegate{required property var modelData;width:ListView.view.width;height:48;hoverEnabled:true
                                    background:Rectangle{radius:7;color:parent.hovered?Theme.elevated:"transparent"}
                                    contentItem:RowLayout{spacing:12;Glyph{text:modelData.is_dir?"\ue8b7":"\ue7c3";color:modelData.is_dir?Theme.warning:Theme.muted}Text{text:modelData.name;color:Theme.text;font.pixelSize:13;Layout.fillWidth:true;elide:Text.ElideMiddle}Text{text:modelData.is_dir?"Folder":root.formatSize(modelData.size);color:Theme.faint;font.pixelSize:11}Glyph{text:modelData.is_dir?"\ue76c":"\ue896"}}
                                    onClicked:{let path=remotePath.text+"/"+modelData.name;if(modelData.is_dir)root.send("list_files",{key:root.activeKey,path:path});else backend.downloadFile(root.activeKey,path,modelData.name);}
                                }
                                ScrollBar.vertical:ScrollBar{}
                            }
                            ColumnLayout{visible:Boolean(root.transferInfo.state);spacing:6;Layout.fillWidth:true
                                RowLayout{Layout.fillWidth:true;spacing:8;Glyph{text:root.transferInfo.direction==="upload"?"\ue898":"\ue896";color:root.transferInfo.state==="failed"?Theme.warning:root.transferInfo.state==="done"?Theme.success:Theme.muted}Text{text:(root.transferInfo.direction==="upload"?"Sending ":"Receiving ")+(root.transferInfo.name||"");color:Theme.text;font.pixelSize:13;elide:Text.ElideMiddle;Layout.fillWidth:true}ActionButton{visible:root.transferRunning;text:"Cancel";quiet:true;onClicked:root.send("cancel_transfer",{key:root.activeKey})}}
                                Rectangle{visible:root.transferInfo.state!=="failed"&&root.transferInfo.state!=="cancelled";Layout.fillWidth:true;implicitHeight:8;radius:4;color:Theme.border;Rectangle{height:parent.height;radius:4;color:root.transferInfo.state==="done"?Theme.success:Theme.accent;width:parent.width*(root.transferInfo.total>0?Math.min(1,root.transferInfo.done/root.transferInfo.total):0)}}
                                Text{text:root.transferText(root.transferInfo);color:root.transferInfo.state==="failed"?Theme.warning:Theme.muted;font.pixelSize:12;elide:Text.ElideRight;Layout.fillWidth:true}
                            }
                        }
                    }
                }
                ScrollView {id:settingsScroll;clip:true;contentWidth:availableWidth
                    ColumnLayout{width:settingsScroll.availableWidth;spacing:22
                        ColumnLayout{Layout.margins:32;Layout.bottomMargin:0;spacing:7;Text{text:"Settings";font.pixelSize:28;font.weight:Font.DemiBold;color:Theme.text}Text{text:"Tune your workspace. Changes apply without restarting.";font.pixelSize:13;color:Theme.muted}}
                        Panel{Layout.fillWidth:true;Layout.leftMargin:32;Layout.rightMargin:32
                            ColumnLayout{anchors.fill:parent;spacing:18
                                Text{text:"Appearance";font.pixelSize:17;font.weight:Font.DemiBold;color:Theme.text}
                                RowLayout{Layout.fillWidth:true;Text{text:"Theme";color:Theme.text;font.pixelSize:13;Layout.fillWidth:true}ComboBox{model:["Dark","Light"];currentIndex:(root.model.settings||{}).theme==="light"?1:0;onActivated:root.send("setting",{name:"theme",value:currentIndex===1?"light":"dark"});Accessible.name:"Application theme";Layout.preferredWidth:180}}
                                Rectangle{Layout.fillWidth:true;height:1;color:Theme.border}
                                Text{text:"Connection & privacy";font.pixelSize:17;font.weight:Font.DemiBold;color:Theme.text}
                                RowLayout{Layout.fillWidth:true;ColumnLayout{spacing:4;Text{text:"Unattended access";color:Theme.text;font.pixelSize:13}Text{text:root.model.hasPassword?"A password is configured for this desktop.":"Every incoming connection needs your approval.";color:Theme.muted;font.pixelSize:11}}Item{Layout.fillWidth:true}ActionButton{text:root.model.hasPassword?"Change password":"Set password";onClicked:localPassword.open()}}
                                RowLayout{Layout.fillWidth:true;ColumnLayout{spacing:4;Text{text:"Internet access";color:Theme.text;font.pixelSize:13}Text{text:"Publish an expiring, signed directory record through the secure tunnel.";color:Theme.muted;font.pixelSize:11;wrapMode:Text.WordWrap;Layout.maximumWidth:570}}Item{Layout.fillWidth:true}Toggle{modelChecked:Boolean((root.model.settings||{}).publicAccess);Accessible.name:"Enable internet access";onEdited:(enabled)=>root.send("setting",{name:"publicAccess",value:enabled})}}
                                RowLayout{Layout.fillWidth:true;ColumnLayout{spacing:4;Text{text:"Local network access";color:Theme.text;font.pixelSize:13}Text{text:"Let devices on this network reach this desktop. Approval or a password is still required. This traffic is not encrypted, so use it only on networks you trust.";color:Theme.muted;font.pixelSize:11;wrapMode:Text.WordWrap;Layout.maximumWidth:570}}Item{Layout.fillWidth:true}Toggle{modelChecked:Boolean((root.model.settings||{}).lanAccess);Accessible.name:"Enable local network access";onEdited:(enabled)=>root.send("setting",{name:"lanAccess",value:enabled})}}
                                Rectangle{Layout.fillWidth:true;height:1;color:Theme.border}
                                Text{text:"DEVICE IDENTITY FINGERPRINT";color:Theme.faint;font.pixelSize:10;font.letterSpacing:1}
                                RowLayout{Layout.fillWidth:true;Text{text:root.model.fingerprint||"";font.family:"Consolas";font.pixelSize:12;color:Theme.muted;wrapMode:Text.WrapAnywhere;Layout.fillWidth:true}ActionButton{glyph:"\ue8c8";Accessible.name:"Copy device fingerprint";onClicked:backend.copyText(root.model.fingerprint)}}
                                Text{text:"Compare this fingerprint on the first connection to a new device.";color:Theme.faint;font.pixelSize:11}
                            }
                        }
                        Panel{id:audioPanel;Layout.fillWidth:true;Layout.leftMargin:32;Layout.rightMargin:32
                            ColumnLayout{anchors.fill:parent;spacing:18
                                Text{text:root.lite?"Streaming":"Streaming & voice";font.pixelSize:17;font.weight:Font.DemiBold;color:Theme.text}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;ColumnLayout{Layout.fillWidth:true;Text{text:"Shared folder";color:Theme.text;font.pixelSize:13}Text{text:(root.model.settings||{}).sharedRoot||"";color:Theme.muted;font.pixelSize:11;elide:Text.ElideMiddle;Layout.fillWidth:true}Text{text:"People you approve with file access can open and change this folder. Changing it ends incoming sharing.";color:Theme.faint;font.pixelSize:11;wrapMode:Text.WordWrap;Layout.fillWidth:true}}ActionButton{text:"Open folder";onClicked:backend.openSharedFolder()}ActionButton{text:"Choose folder";onClicked:backend.chooseSharedFolder()}}
                                RowLayout{Layout.fillWidth:true;Text{text:"Default quality";color:Theme.text;font.pixelSize:13;Layout.fillWidth:true}ComboBox{model:["Balanced","Performance","Sharp"];currentIndex:(root.model.settings||{}).profile==="performance"?1:(root.model.settings||{}).profile==="sharp"?2:0;onActivated:root.send("setting",{name:"profile",value:currentText.toLowerCase()});Accessible.name:"Default video quality";Layout.preferredWidth:200}}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;ColumnLayout{spacing:4;Text{text:"Microphone";color:Theme.text;font.pixelSize:13}Text{text:"Enabled only in sessions where voice is permitted.";font.pixelSize:11;color:Theme.muted}}Item{Layout.fillWidth:true}Toggle{modelChecked:Boolean((root.model.settings||{}).micEnabled);Accessible.name:"Enable microphone";onEdited:(enabled)=>root.send("setting",{name:"micEnabled",value:enabled})}}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;Text{text:"Microphone level "+Math.round(((root.model.settings||{}).micGain===undefined?1:root.model.settings.micGain)*100)+"%";color:Theme.text;font.pixelSize:13;Layout.fillWidth:true}LevelSlider{from:0;to:3;modelValue:(root.model.settings||{}).micGain===undefined?1:root.model.settings.micGain;onEdited:(newValue)=>root.send("setting",{name:"micGain",value:newValue});Accessible.name:"Microphone gain";Layout.preferredWidth:240}}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;Text{text:"Speaker";color:Theme.text;font.pixelSize:13;Layout.fillWidth:true}Toggle{modelChecked:(root.model.settings||{}).speakerEnabled!==false;Accessible.name:"Enable speaker";onEdited:(enabled)=>root.send("setting",{name:"speakerEnabled",value:enabled})}}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;Text{text:"Speaker volume "+Math.round(((root.model.settings||{}).speakerVolume||0)*100)+"%";color:Theme.text;font.pixelSize:13;Layout.fillWidth:true}LevelSlider{from:0;to:1;modelValue:(root.model.settings||{}).speakerVolume||0;onEdited:(newValue)=>root.send("setting",{name:"speakerVolume",value:newValue});Accessible.name:"Speaker volume";Layout.preferredWidth:240}}
                                RowLayout{visible:!root.lite;Layout.fillWidth:true;spacing:10;ColumnLayout{spacing:4;Layout.fillWidth:true;Text{text:"Test microphone";color:Theme.text;font.pixelSize:13}Text{text:!(root.model.micTest||{}).active?"Hear your own microphone on this PC. Use headphones to avoid feedback.":((root.model.micTest.audio||{}).error||((root.model.micTest.audio||{}).micSilent?"No sound is coming from the microphone. Check the default input device in Windows.":"Speak now, you should hear yourself. This stops after 20 seconds."));color:Theme.muted;font.pixelSize:11;wrapMode:Text.WordWrap;Layout.fillWidth:true}}LevelMeter{visible:Boolean((root.model.micTest||{}).active);level:((root.model.micTest||{}).audio||{}).micLevel||0;implicitWidth:120}ActionButton{text:(root.model.micTest||{}).active?"Stop test":"Start test";onClicked:root.send("mic_test")}}
                                Text{visible:!root.lite;text:"Headphones reduce feedback during two-way voice calls.";color:Theme.faint;font.pixelSize:11}
                            }
                        }
                        Panel{Layout.fillWidth:true;Layout.leftMargin:32;Layout.rightMargin:32;ColumnLayout{anchors.fill:parent;spacing:12;RowLayout{Layout.fillWidth:true;Text{text:"Software updates";font.pixelSize:17;font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true}ActionButton{visible:!root.lite;text:"Check for updates";enabled:!(root.model.update&&["checking","downloading","installing"].indexOf(root.model.update.state)>=0);onClicked:root.send("check_updates")}ActionButton{text:"Install & restart";primary:true;visible:Boolean(root.model.update&&root.model.update.state==="available");onClicked:root.send("install_update")}}Text{text:root.lite?"OpenDesk Lite "+(root.model.version||"")+" is updated manually by installing a newer Lite package.":(root.model.update||{}).message||"OpenDesk "+(root.model.version||"");color:Theme.muted;font.pixelSize:12;wrapMode:Text.WordWrap;Layout.fillWidth:true}}}
                        RowLayout{Layout.leftMargin:32;Layout.bottomMargin:24;spacing:12;VersionBadge{version:root.model.version||""}Text{text:"Rust engine / Qt native desktop";font.pixelSize:11;color:Theme.faint;Layout.alignment:Qt.AlignVCenter}}
                    }
                }
                ColumnLayout {
                    spacing:0
                    Rectangle{Layout.fillWidth:true;implicitHeight:62;color:Theme.panel
                        RowLayout{anchors.fill:parent;anchors.margins:12;spacing:10
                            ColumnLayout{spacing:2;Layout.maximumWidth:300;Text{text:root.current.name||root.current.target||"Remote session";color:Theme.text;font.pixelSize:13;font.weight:Font.DemiBold}Text{text:(root.current.audio||{}).error||(root.current.state==="connected"&&root.current.permissions&&!root.current.permissions.audio&&!root.lite?"Voice was not allowed for this session":root.current.message||root.current.state||"");color:(root.current.audio||{}).error?Theme.warning:Theme.muted;font.pixelSize:10;elide:Text.ElideRight;Layout.fillWidth:true}}
                            Item{Layout.fillWidth:true}
                            Rectangle{visible:root.current.state==="connected"&&!!root.current.route;implicitWidth:routeLabel.implicitWidth+16;implicitHeight:22;radius:Theme.radiusSmall;color:Theme.elevated;border.width:1;border.color:root.current.route==="Direct"?Theme.success:Theme.border;Accessible.name:"Connection route "+(root.current.route||"");Text{id:routeLabel;anchors.centerIn:parent;text:root.current.route||"";font.pixelSize:11;font.weight:Font.DemiBold;color:root.current.route==="Direct"?Theme.success:Theme.muted}}
                            Text{text:root.current.state==="connected"?((root.current.fps||0)>0?Math.round(root.current.fps)+" FPS":"Idle")+"   ·   "+Math.round(root.current.rtt||0)+" ms":"";font.family:"Consolas";font.pixelSize:11;color:Theme.muted}
                            ComboBox{model:["Balanced","Performance","Sharp"];Layout.preferredWidth:130;currentIndex:root.current.profile==="performance"?1:root.current.profile==="sharp"?2:0;onActivated:root.send("video_profile",{key:root.activeKey,profile:currentText.toLowerCase()});Accessible.name:"Session video quality"}
                            ActionButton{visible:!root.lite;text:root.micText(root.current);glyph:root.current.micEnabled?"\ue720":"\uec54";Accessible.name:"Toggle session microphone";ToolTip.visible:hovered;ToolTip.text:root.audioHelp(root.current);enabled:Boolean(root.current.permissions&&root.current.permissions.audio);onClicked:root.send("toggle_mic",{key:root.activeKey})}
                            LevelMeter{visible:!root.lite&&Boolean(root.current.micEnabled);level:(root.current.audio||{}).micLevel||0;Accessible.name:"Microphone level"}
                            ActionButton{visible:!root.lite;text:(root.model.settings||{}).speakerEnabled!==false?"Speaker on":"Speaker off";glyph:(root.model.settings||{}).speakerEnabled!==false?"\ue767":"\ue74f";Accessible.name:"Toggle speaker";enabled:Boolean(root.current.permissions&&root.current.permissions.audio);onClicked:root.send("setting",{name:"speakerEnabled",value:(root.model.settings||{}).speakerEnabled===false})}
                            LevelMeter{visible:!root.lite&&Boolean(root.current.permissions&&root.current.permissions.audio);level:(root.current.audio||{}).speakerLevel||0;Accessible.name:"Incoming voice level"}
                            ActionButton{visible:!root.lite;glyph:"\ue8b7";Accessible.name:"Remote files";enabled:Boolean(root.current.permissions&&root.current.permissions.file_transfer);onClicked:{root.page="files";root.send("list_files",{key:root.activeKey,path:"."});}}
                            ActionButton{text:"Disconnect";glyph:"\ue8bb";enabled:root.current.state!=="disconnected"&&root.current.state!=="error";onClicked:root.send("disconnect",{key:root.activeKey})}
                        }
                    }
                    Item{Layout.fillWidth:true;Layout.fillHeight:true
                        RemoteFrame{id:remoteFrame;anchors.fill:parent;engine:backend;sessionKey:root.activeKey;controlEnabled:root.current.state==="connected"&&Boolean(root.current.permissions&&root.current.permissions.input);visible:root.current.state==="connected";clip:true
                            RemoteCursor{x:remoteFrame.pointerPosition.x;y:remoteFrame.pointerPosition.y;label:"You";visible:remoteFrame.controlEnabled}
                        }
                        ColumnLayout{anchors.centerIn:parent;spacing:18;visible:root.current.state!=="connected";width:Math.min(500,parent.width-80)
                            BusyIndicator{running:root.current.state!=="error"&&root.current.state!=="disconnected";visible:running;Layout.alignment:Qt.AlignHCenter}
                            Text{text:root.current.state==="error"?"Connection needs attention":root.current.state==="disconnected"?"Session ended":"Connecting to your desktop";color:Theme.text;font.pixelSize:23;font.weight:Font.DemiBold;Layout.alignment:Qt.AlignHCenter}
                            Text{text:root.current.message||"Checking the remote device and waiting for access.";color:Theme.muted;font.pixelSize:13;wrapMode:Text.WordWrap;horizontalAlignment:Text.AlignHCenter;Layout.fillWidth:true}
                            ActionButton{text:"Reconnect";primary:true;Layout.alignment:Qt.AlignHCenter;visible:root.current.state==="error"||root.current.state==="disconnected";onClicked:{const target=root.current.target||"";root.send("close_session",{key:root.activeKey});root.connectTo(target);}}
                        }
                    }
                }
            }
            Rectangle{Layout.fillWidth:true;implicitHeight:root.model.hostSession?48:0;visible:Boolean(root.model.hostSession);color:Theme.selected
                RowLayout{anchors.fill:parent;anchors.leftMargin:24;anchors.rightMargin:24;Text{text:"Your desktop is being shared with "+((root.model.hostSession||{}).peer||"")+(root.sharingFiles?"  ·  Files: "+((root.model.settings||{}).sharedRoot||""):"");color:Theme.text;font.pixelSize:12;elide:Text.ElideMiddle;Layout.fillWidth:true}ActionButton{visible:root.sharingFiles;text:"Open folder";quiet:true;onClicked:backend.openSharedFolder()}ActionButton{visible:!root.lite;text:root.micText(root.model.hostSession||{});ToolTip.visible:hovered;ToolTip.text:root.audioHelp(root.model.hostSession||{});glyph:(root.model.hostSession||{}).micEnabled?"\ue720":"\uec54";quiet:true;enabled:Boolean(((root.model.hostSession||{}).permissions||{}).audio);onClicked:root.send("toggle_host_mic")}ActionButton{text:"End sharing";quiet:true;onClicked:root.send("end_sharing")}}
            }
        }
    }
    Component {
        id:deviceCard
        Panel {
            required property var modelData
            Layout.fillWidth:true;Layout.minimumWidth:235;implicitHeight:150;padding:18
            ColumnLayout{anchors.fill:parent;spacing:12
                RowLayout{Layout.fillWidth:true;Rectangle{width:35;height:35;radius:Theme.radiusSmall;color:Theme.selected;Glyph{anchors.centerIn:parent;text:"\ue7f8";color:Theme.accentText}}Item{Layout.fillWidth:true}ActionButton{glyph:modelData.favorite?"\ue735":"\ue734";quiet:true;Accessible.name:modelData.favorite?"Remove favorite":"Add favorite";onClicked:root.send("favorite",{id:modelData.id})}}
                Text{text:modelData.alias||modelData.id;color:Theme.text;font.pixelSize:13;font.weight:Font.DemiBold;elide:Text.ElideRight;Layout.fillWidth:true}
                RowLayout{Layout.fillWidth:true;Text{text:modelData.id;color:Theme.muted;font.family:"Consolas";font.pixelSize:12;Layout.fillWidth:true}ActionButton{glyph:"\ue72a";quiet:true;Accessible.name:"Connect to "+modelData.id;onClicked:root.connectTo(modelData.id)}}
            }
        }
    }
    Dialog{id:localPassword;title:"Unattended access";modal:true;anchors.centerIn:parent;width:430;standardButtons:Dialog.Save|Dialog.Cancel
        background:Rectangle{color:Theme.panel;radius:Theme.radiusLarge;border.color:Theme.border}
        ColumnLayout{anchors.fill:parent;spacing:16;Text{text:"Use at least 8 characters. This password grants unattended control, voice, clipboard and access to your shared folder. Leave it empty to require approval for every connection.";color:Theme.muted;wrapMode:Text.WordWrap;Layout.fillWidth:true;font.pixelSize:12}Field{id:newPassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"New password";Accessible.name:"New unattended password"}}
        onAccepted:{root.send("set_password",{password:newPassword.text});newPassword.clear();}
        onRejected:newPassword.clear()
    }
    Dialog{id:trustDialog;title:"Verify this device";modal:true;anchors.centerIn:parent;width:480;visible:Boolean(root.current.needsTrust);standardButtons:Dialog.Ok|Dialog.Cancel
        background:Rectangle{color:Theme.panel;radius:Theme.radiusLarge;border.color:Theme.border}
        ColumnLayout{anchors.fill:parent;spacing:16;Text{text:"First connection to "+(root.current.target||"")+". Compare this fingerprint with the host's Settings before trusting it.";color:Theme.muted;font.pixelSize:13;wrapMode:Text.WordWrap;Layout.fillWidth:true}Text{text:root.current.fingerprint||"";font.family:"Consolas";font.pixelSize:14;color:Theme.text;wrapMode:Text.WrapAnywhere;Layout.fillWidth:true}}
        onAccepted:root.send("trust",{key:root.activeKey,allow:true})
        onRejected:root.send("trust",{key:root.activeKey,allow:false})
    }
    Dialog{id:remotePassword;title:"Remote access password";modal:true;anchors.centerIn:parent;width:420;visible:Boolean(root.current.needsPassword);standardButtons:Dialog.Ok|Dialog.Cancel
        background:Rectangle{color:Theme.panel;radius:Theme.radiusLarge;border.color:Theme.border}
        Field{id:remoteSecret;width:parent.width;echoMode:TextInput.Password;placeholderText:"Password for this desktop";Accessible.name:"Remote desktop password"}
        onAccepted:{root.send("password",{key:root.activeKey,password:remoteSecret.text});remoteSecret.clear();}
        onRejected:root.send("disconnect",{key:root.activeKey})
    }
    Dialog{id:legacyDialog;title:"Connect to an older desktop";modal:true;anchors.centerIn:parent;width:Math.min(520,root.width-48);standardButtons:Dialog.Ok|Dialog.Cancel;closePolicy:Popup.NoAutoClose
        background:Rectangle{color:Theme.panel;radius:Theme.radiusLarge;border.color:Theme.border}
        onOpened:{legacyInput.checked=true;legacyAudio.checked=false;legacyClipboard.checked=false;standardButton(Dialog.Ok).text="Continue";}
        contentItem:ColumnLayout{spacing:12
            Text{text:"This older desktop cannot verify its identity with a fingerprint. Confirm its address with the owner before continuing.";color:Theme.warning;wrapMode:Text.WordWrap;Layout.fillWidth:true}
            Text{text:"Screen sharing, control and voice use compatibility mode. File transfer needs a newer desktop.";color:Theme.muted;wrapMode:Text.WordWrap;Layout.fillWidth:true}
            CheckBox{id:legacyInput;text:"Keyboard and mouse";checked:true}
            CheckBox{id:legacyAudio;visible:!root.lite;text:"Two-way voice"}
            CheckBox{id:legacyClipboard;text:"Text clipboard"}
        }
        onAccepted:root.send("legacy_accept",{key:root.activeKey,allow:true,permissions:{input:legacyInput.checked,audio:legacyAudio.checked,clipboard:legacyClipboard.checked,file_transfer:false}})
        onRejected:root.send("legacy_accept",{key:root.activeKey,allow:false})
    }
    Dialog{id:updateDialog;title:root.updateState==="available"?"Update available":root.updateState==="failed"?"Update did not finish":"Updating OpenDesk";modal:root.updateState==="available"||root.updateState==="failed";anchors.centerIn:parent;width:Math.min(480,root.width-48);closePolicy:Popup.NoAutoClose
        contentItem:ColumnLayout{spacing:12
            Text{text:root.updateState==="available"?"OpenDesk "+(root.updateInfo.version||"")+" is ready to download. You have "+(root.model.version||"")+".":root.updateInfo.message||"";color:Theme.text;font.pixelSize:14;wrapMode:Text.WordWrap;Layout.fillWidth:true}
            Repeater{model:root.updateState==="available"?(root.updateInfo.notes||[]):[];Text{required property var modelData;text:"•  "+modelData;color:Theme.muted;font.pixelSize:12;wrapMode:Text.WordWrap;Layout.fillWidth:true}}
            Text{visible:root.updateState==="available"&&root.sessions.concat(root.model.hostSession?[1]:[]).length>0;text:"Installing closes your open sessions.";color:Theme.warning;font.pixelSize:12;Layout.fillWidth:true}
            ColumnLayout{visible:root.updateState==="downloading"||root.updateState==="verifying"||root.updateState==="installing";spacing:6;Layout.fillWidth:true
                Rectangle{Layout.fillWidth:true;implicitHeight:8;radius:4;color:Theme.border;Rectangle{height:parent.height;radius:4;color:Theme.accent;width:parent.width*(root.updateState==="downloading"&&root.updateInfo.total>0?Math.min(1,root.updateInfo.done/root.updateInfo.total):root.updateState==="downloading"?0:1)}}
                Text{text:root.updateState==="downloading"&&root.updateInfo.total>0?root.formatSize(root.updateInfo.done)+" of "+root.formatSize(root.updateInfo.total)+"  ·  "+root.formatSize(root.updateInfo.speed||0)+"/s":root.updateState==="installing"?"OpenDesk restarts by itself when this finishes.":"";color:Theme.muted;font.pixelSize:12;Layout.fillWidth:true}
            }
            RowLayout{Layout.fillWidth:true;spacing:8;Item{Layout.fillWidth:true}
                ActionButton{visible:root.updateState==="available";text:"Later";quiet:true;onClicked:{root.dismissedUpdate=root.updateInfo.version||"";updateDialog.close();}}
                ActionButton{visible:root.updateState==="downloading";text:"Cancel";onClicked:root.send("cancel_update")}
                ActionButton{visible:root.updateState==="failed";text:"Close";quiet:true;onClicked:updateDialog.close()}
                ActionButton{visible:root.updateState==="available"||root.updateState==="failed";text:root.updateState==="failed"?"Try again":"Download and install";primary:true;onClicked:root.send("install_update")}
            }
        }
    }
    Dialog{id:approval;title:"Incoming connection";modal:true;anchors.centerIn:parent;width:460;standardButtons:Dialog.Ok|Dialog.Cancel
        closePolicy:Popup.NoAutoClose
        onOpened:{allowInput.checked=true;allowAudio.checked=true;allowClipboard.checked=false;allowFiles.checked=false;standardButton(Dialog.Ok).text="Allow connection";standardButton(Dialog.Cancel).text="Reject";forceActiveFocus();}
        background:Rectangle{color:Theme.panel;radius:Theme.radiusLarge;border.color:Theme.border}
        contentItem:ColumnLayout{spacing:12;Text{text:((root.model.incoming||{}).peer||"A remote desktop")+" wants to connect. Choose what to share.";font.pixelSize:14;color:Theme.text;wrapMode:Text.WordWrap;Layout.fillWidth:true}CheckBox{id:allowInput;text:"Keyboard and mouse";checked:true}CheckBox{id:allowAudio;visible:!root.lite;text:"Two-way voice"}CheckBox{id:allowClipboard;text:"Text clipboard"}CheckBox{id:allowFiles;visible:!root.lite;text:(root.model.incoming||{}).legacy?"Files need a newer viewer":"Files in "+((root.model.settings||{}).sharedRoot||"your shared folder");enabled:!(root.model.incoming||{}).legacy}}
        onAccepted:root.send("approve",{requestId:root.model.incoming.requestId,allow:true,permissions:{input:allowInput.checked,audio:allowAudio.checked,clipboard:allowClipboard.checked,file_transfer:allowFiles.checked}})
        onRejected:root.send("approve",{requestId:(root.model.incoming||{}).requestId||"",allow:false})
    }
    Window {
        id:remotePointerWindow
        transientParent:null
        visible:Boolean(root.model.hostSession&&root.model.remoteCursor)
        width:80;height:46;color:"transparent"
        flags:Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowTransparentForInput|Qt.WindowDoesNotAcceptFocus
        x:primaryDesktop.x+Math.round(Math.max(0,Math.min(1,(root.model.remoteCursor||{}).x||0))*(primaryDesktop.width-1))
        y:primaryDesktop.y+Math.round(Math.max(0,Math.min(1,(root.model.remoteCursor||{}).y||0))*(primaryDesktop.height-1))
        RemoteCursor{label:"Remote"}
    }
    Rectangle{anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom;anchors.bottomMargin:22;width:Math.min(660,parent.width-80);height:noticeText.implicitHeight+28;radius:Theme.radiusSmall;color:Theme.elevated;border.color:Theme.border;visible:Boolean(root.model.notice)
        Text{id:noticeText;anchors.fill:parent;anchors.margins:14;text:(root.model.notice||{}).message||"";color:(root.model.notice||{}).tone==="error"?Theme.accentText:Theme.text;wrapMode:Text.WordWrap;font.pixelSize:12}
        TapHandler{onTapped:root.send("dismiss_notice")}
    }
}
