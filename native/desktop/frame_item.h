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
public:
    explicit FrameItem(QQuickItem* parent=nullptr);
    EngineBridge* engine()const{return m_engine;}
    void setEngine(EngineBridge* value);
    QString sessionKey()const{return m_key;}
    void setSessionKey(const QString& value);
    bool controlEnabled()const{return m_control;}
    void setControlEnabled(bool value);
    void setDiagnosticFrame(const QImage& image);
signals:void engineChanged();void sessionKeyChanged();void controlEnabledChanged();
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
private:
    void poll();void pointer(QMouseEvent*,const QString&);void input(const QString&,QVariantMap);
    QRectF imageRect()const;
    EngineBridge* m_engine=nullptr;QString m_key;bool m_control=false;
    QImage m_image;uint64_t m_generation=0,m_painted=0;QTimer m_timer;
    std::atomic<int> m_rendered{0};QElapsedTimer m_fps;
};
