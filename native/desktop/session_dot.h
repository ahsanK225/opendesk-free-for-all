#pragma once
#include <QObject>
#include <QColor>
#include <QPoint>
// A small dot, like a camera light, while someone is connected. A plain Win32 window that can be
// dragged anywhere, stays on top without taking focus, and is left out of screen capture.
class SessionDot final:public QObject {
    Q_OBJECT
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY activeChanged)
    Q_PROPERTY(QColor color READ color WRITE setColor NOTIFY colorChanged)
public:
    explicit SessionDot(QObject* parent=nullptr);
    ~SessionDot() override;
    bool active()const{return m_active;}
    void setActive(bool value);
    QColor color()const{return m_color;}
    void setColor(const QColor& value);
    // Called by the window procedure.
    void moved(QPoint position){m_position=position;m_placed=true;}
signals:
    void activeChanged();
    void colorChanged();
    // The dot was double-clicked.
    void opened();
private:
    void place();
    bool m_active=false,m_placed=false;
    QColor m_color{0xe5,0x3b,0x3b};
    QPoint m_position;
    void* m_window=nullptr;
};
