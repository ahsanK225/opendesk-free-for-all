#include "frame_item.h"
#include <QKeyEvent>
#include <QQuickWindow>
#include <QSGSimpleTextureNode>
#include <QSGTexture>
#include <QWheelEvent>
namespace {struct TextureNode final:QSGSimpleTextureNode{QSGTexture* owned=nullptr;~TextureNode()override{delete owned;}void replace(QSGTexture* texture){delete owned;owned=texture;setTexture(texture);}};}
FrameItem::FrameItem(QQuickItem* parent):QQuickItem(parent){setFlag(ItemHasContents,true);setAcceptedMouseButtons(Qt::AllButtons);setAcceptHoverEvents(true);setActiveFocusOnTab(true);connect(&m_timer,&QTimer::timeout,this,&FrameItem::poll);m_timer.start(8);m_fps.start();}
void FrameItem::setEngine(EngineBridge* value){if(m_engine!=value){m_engine=value;emit engineChanged();}}
void FrameItem::setDiagnosticFrame(const QImage& image){m_image=image;m_generation++;update();}
void FrameItem::setSessionKey(const QString& value){if(m_key!=value){if(m_control)input(QStringLiteral("input_reset"),{});m_key=value;m_generation=m_painted=0;m_image={};update();emit sessionKeyChanged();}}
void FrameItem::setControlEnabled(bool value){if(m_control!=value){if(!value)input(QStringLiteral("input_reset"),{});m_control=value;emit controlEnabledChanged();}}
void FrameItem::poll(){if(!m_engine||m_key.isEmpty()||!isVisible())return;if(m_fps.elapsed()>=1000){m_engine->command({{QStringLiteral("type"),QStringLiteral("render_metrics")},{QStringLiteral("key"),m_key},{QStringLiteral("fps"),m_rendered.exchange(0)*1000.0/m_fps.elapsed()}});m_fps.restart();}NativeFrameView view{};const auto key=m_key.toUtf8();if(!od_frame_acquire(m_engine->native(),key.constData(),&view))return;if(view.generation==m_generation){od_frame_release(view.owner);return;}m_generation=view.generation;m_image=QImage(view.data,int(view.width),int(view.height),int(view.width*4),QImage::Format_ARGB32,od_frame_release,view.owner);update();}
QRectF FrameItem::imageRect()const{if(m_image.isNull())return {};const auto size=m_image.size().scaled(QSize(int(width()),int(height())),Qt::KeepAspectRatio);return QRectF((width()-size.width())/2,(height()-size.height())/2,size.width(),size.height());}
QSGNode* FrameItem::updatePaintNode(QSGNode* old,UpdatePaintNodeData*){if(m_image.isNull()||!window()){delete old;return nullptr;}auto* node=static_cast<TextureNode*>(old);if(!node)node=new TextureNode;if(m_painted!=m_generation||!node->owned){node->replace(window()->createTextureFromImage(m_image));node->setFiltering(QSGTexture::Linear);m_painted=m_generation;m_rendered.fetch_add(1);}node->setRect(imageRect());return node;}
void FrameItem::input(const QString& type,QVariantMap payload){if(!m_engine||m_key.isEmpty())return;payload.insert(QStringLiteral("type"),type);m_engine->command({{QStringLiteral("type"),QStringLiteral("input")},{QStringLiteral("key"),m_key},{QStringLiteral("payload"),payload}});}
void FrameItem::pointer(QMouseEvent* event,const QString& type){if(!m_control)return;const auto rect=imageRect();if(rect.isEmpty()||(!rect.contains(event->position())&&type!=QStringLiteral("mouse_up")))return;const int button=event->button()==Qt::MiddleButton?1:event->button()==Qt::RightButton?2:0;input(type,{{QStringLiteral("x"),qBound(0.0,(event->position().x()-rect.x())/rect.width(),1.0)},{QStringLiteral("y"),qBound(0.0,(event->position().y()-rect.y())/rect.height(),1.0)},{QStringLiteral("button"),button}});event->accept();}
void FrameItem::mouseMoveEvent(QMouseEvent* event){pointer(event,QStringLiteral("mouse_move"));}
void FrameItem::hoverMoveEvent(QHoverEvent* event){if(!m_control)return;const auto rect=imageRect();if(!rect.isEmpty()&&rect.contains(event->position()))input(QStringLiteral("mouse_move"),{{QStringLiteral("x"),(event->position().x()-rect.x())/rect.width()},{QStringLiteral("y"),(event->position().y()-rect.y())/rect.height()}});}
void FrameItem::mousePressEvent(QMouseEvent* event){forceActiveFocus();pointer(event,QStringLiteral("mouse_down"));}
void FrameItem::mouseReleaseEvent(QMouseEvent* event){pointer(event,QStringLiteral("mouse_up"));}
void FrameItem::wheelEvent(QWheelEvent* event){if(m_control){input(QStringLiteral("mouse_scroll"),{{QStringLiteral("delta_y"),-event->angleDelta().y()/120.0},{QStringLiteral("delta_x"),event->angleDelta().x()/120.0}});event->accept();}}
void FrameItem::keyPressEvent(QKeyEvent* event){if(m_control){input(QStringLiteral("key_down"),{{QStringLiteral("vk"),event->nativeVirtualKey()},{QStringLiteral("key"),event->text()}});event->accept();}}
void FrameItem::keyReleaseEvent(QKeyEvent* event){if(m_control&&!event->isAutoRepeat()){input(QStringLiteral("key_up"),{{QStringLiteral("vk"),event->nativeVirtualKey()},{QStringLiteral("key"),event->text()}});event->accept();}}
void FrameItem::focusOutEvent(QFocusEvent* event){input(QStringLiteral("input_reset"),{});QQuickItem::focusOutEvent(event);}
