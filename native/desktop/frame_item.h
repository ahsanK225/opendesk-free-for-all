#pragma once
#include "engine_bridge.h"
#include <QImage>
#include <QElapsedTimer>
#include <QQuickItem>
#include <atomic>
class FrameItem:public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(EngineBridge* engine READ engine WRITE setEngine NOTIFY engineChanged)
    Q_PROPERTY(QString sessionKey READ sessionKey WRITE setSessionKey NOTIFY sessionKeyChanged)
    Q_PROPERTY(bool controlEnabled READ controlEnabled WRITE setControlEnabled NOTIFY controlEnabledChanged)
    Q_PROPERTY(QPointF pointerPosition READ pointerPosition NOTIFY pointerChanged)
    // Zoom 0 fits the picture to the item; otherwise it is remote pixels per screen pixel, counted at the
    // widest picture this session has sent, so the size on screen holds when the host lowers the resolution.
    Q_PROPERTY(qreal zoom READ zoom WRITE setZoom NOTIFY viewChanged)
    Q_PROPERTY(qreal zoomLevel READ zoomLevel NOTIFY viewChanged)
    // The visible part of a zoomed picture, as scroll bar positions and sizes.
    Q_PROPERTY(qreal viewX READ viewX WRITE setViewX NOTIFY viewChanged)
    Q_PROPERTY(qreal viewY READ viewY WRITE setViewY NOTIFY viewChanged)
    Q_PROPERTY(qreal viewWidth READ viewWidth NOTIFY viewChanged)
    Q_PROPERTY(qreal viewHeight READ viewHeight NOTIFY viewChanged)
    // In full screen, Esc leaves it instead of going to the remote desktop.
    Q_PROPERTY(bool escapeLeaves MEMBER m_escapeLeaves NOTIFY escapeLeavesChanged)
public:
    explicit FrameItem(QQuickItem* parent=nullptr);
    EngineBridge* engine()const{return m_engine;}
    void setEngine(EngineBridge* value);
    QString sessionKey()const{return m_key;}
    void setSessionKey(const QString& value);
    bool controlEnabled()const{return m_control;}
    void setControlEnabled(bool value);
    void setDiagnosticFrame(const QImage& image);
    QPointF pointerPosition()const{return m_pointer;}
    qreal zoom()const{return m_zoom;}
    void setZoom(qreal value);
    qreal zoomLevel()const;
    qreal viewX()const{return m_viewX;}
    void setViewX(qreal value);
    qreal viewY()const{return m_viewY;}
    void setViewY(qreal value);
    qreal viewWidth()const;
    qreal viewHeight()const;
    Q_INVOKABLE void zoomIn();
    Q_INVOKABLE void zoomOut();
signals:void escapeLeavesChanged();void escapePressed();void engineChanged();void sessionKeyChanged();void controlEnabledChanged();void pointerChanged();void viewChanged();
protected:
    QSGNode* updatePaintNode(QSGNode* old,UpdatePaintNodeData*)override;
    void mouseMoveEvent(QMouseEvent*)override;
    void hoverMoveEvent(QHoverEvent*)override;
    void mousePressEvent(QMouseEvent*)override;
    void mouseReleaseEvent(QMouseEvent*)override;
    void wheelEvent(QWheelEvent*)override;
    void keyPressEvent(QKeyEvent*)override;
    void keyReleaseEvent(QKeyEvent*)override;
    void focusOutEvent(QFocusEvent*)override;
    void geometryChange(const QRectF& next,const QRectF& previous)override;
private:
    void poll();void pointer(QMouseEvent*,const QString&);void input(const QString&,QVariantMap);
    QRectF imageRect()const;
    qreal fitScale()const;QSizeF zoomedSize()const;void zoomAround(qreal value,QPointF anchor);void zoomStep(bool in,QPointF anchor);void clampView();
    qreal m_zoom=0,m_viewX=0,m_viewY=0;QSize m_frameSize;int m_refWidth=0;bool m_escapeLeaves=false;
    // Touchpads send many small wheel steps; zoom moves one step per notch of 120.
    int m_zoomWheel=0;
    qreal refWidth()const{return qMax(m_refWidth,m_image.width());}
    EngineBridge* m_engine=nullptr;QString m_key;bool m_control=false;
    QImage m_image;uint64_t m_generation=0,m_painted=0;QTimer m_timer;
    std::atomic<int> m_rendered{0};QElapsedTimer m_fps;
    QPointF m_pointer{-100,-100};
    QVariantMap m_pendingMove;
    void flushPointer();
};
