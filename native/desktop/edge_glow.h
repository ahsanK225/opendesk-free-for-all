#pragma once
#include <QObject>
#include <QColor>
#include <array>
// A soft glow along the edges of the primary screen while someone is connected.
// Plain layered Win32 windows in bands that fade inwards: click-through, and left out of screen capture.
class EdgeGlow final:public QObject {
    Q_OBJECT
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY activeChanged)
    Q_PROPERTY(QColor color READ color WRITE setColor NOTIFY colorChanged)
public:
    explicit EdgeGlow(QObject* parent=nullptr);
    ~EdgeGlow() override;
    bool active()const{return m_active;}
    void setActive(bool value);
    QColor color()const{return m_color;}
    void setColor(const QColor& value);
signals:
    void activeChanged();
    void colorChanged();
private:
    void paint();
    bool m_active=false;
    QColor m_color{0x4f,0xd0,0x8f};
    std::array<void*,16> m_windows{};
};
