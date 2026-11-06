#include "edge_glow.h"
#include <QGuiApplication>
#include <QScreen>
#include <algorithm>
#include <cmath>
#include <utility>
#define NOMINMAX
#include <windows.h>
#ifndef WDA_EXCLUDEFROMCAPTURE
#define WDA_EXCLUDEFROMCAPTURE 0x11
#endif
namespace {
const wchar_t* glowClass=L"OpenDeskEdgeGlow";
// Bands from the screen edge inwards, in pixels at 100% scaling, with their opacity. Each band is
// a solid window with one opacity, because Windows keeps windows with per-pixel opacity in screen capture.
constexpr std::array<std::pair<int,double>,4> glowBands{{{3,0.6},{4,0.38},{5,0.2},{6,0.08}}};
LRESULT CALLBACK paintStrip(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
    if(message==WM_ERASEBKGND){RECT area;GetClientRect(window,&area);const HBRUSH brush=CreateSolidBrush(COLORREF(GetWindowLongPtrW(window,GWLP_USERDATA)));FillRect(HDC(wparam),&area,brush);DeleteObject(brush);return 1;}
    return DefWindowProcW(window,message,wparam,lparam);
}
HWND createStrip(){
    static const bool registered=[]{WNDCLASSW type{};type.lpfnWndProc=paintStrip;type.hInstance=GetModuleHandleW(nullptr);type.lpszClassName=glowClass;return RegisterClassW(&type)!=0;}();
    if(!registered)return nullptr;
    return CreateWindowExW(WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOOLWINDOW|WS_EX_TOPMOST|WS_EX_NOACTIVATE,glowClass,L"",WS_POPUP,0,0,1,1,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
}
}
EdgeGlow::EdgeGlow(QObject* parent):QObject(parent){
    const auto watch=[this](QScreen* screen){if(screen)connect(screen,&QScreen::geometryChanged,this,[this]{if(m_active)paint();});};
    watch(QGuiApplication::primaryScreen());
    connect(qGuiApp,&QGuiApplication::primaryScreenChanged,this,[this,watch](QScreen* screen){watch(screen);if(m_active)paint();});
}
EdgeGlow::~EdgeGlow(){for(auto* window:m_windows)if(window)DestroyWindow(HWND(window));}
void EdgeGlow::setActive(bool value){
    if(value==m_active)return;
    m_active=value;
    if(m_active)paint();else for(auto* window:m_windows)if(window)ShowWindow(HWND(window),SW_HIDE);
    emit activeChanged();
}
void EdgeGlow::setColor(const QColor& value){
    if(value==m_color)return;
    m_color=value;
    if(m_active)paint();
    emit colorChanged();
}
void EdgeGlow::paint(){
    MONITORINFO monitor{sizeof(MONITORINFO)};
    if(!GetMonitorInfoW(MonitorFromPoint(POINT{0,0},MONITOR_DEFAULTTOPRIMARY),&monitor))return;
    const RECT screen=monitor.rcMonitor;
    const int width=screen.right-screen.left,height=screen.bottom-screen.top;
    const qreal scale=QGuiApplication::primaryScreen()?QGuiApplication::primaryScreen()->devicePixelRatio():1;
    const COLORREF color=RGB(m_color.red(),m_color.green(),m_color.blue());
    size_t index=0;int outer=0;
    for(const auto& [size,opacity]:glowBands){
        const int inner=outer+std::max(1,int(std::lround(size*scale)));
        if(width<=2*inner||height<=2*inner)break;
        // Top and bottom take the corners of each ring, so that no two windows overlap.
        const std::array<RECT,4> strips{RECT{outer,outer,width-outer,inner},RECT{outer,height-inner,width-outer,height-outer},RECT{outer,inner,inner,height-inner},RECT{width-inner,inner,width-outer,height-inner}};
        for(const RECT& strip:strips){
            if(!m_windows[index])m_windows[index]=createStrip();
            const HWND window=HWND(m_windows[index++]);
            if(!window)continue;
            SetWindowLongPtrW(window,GWLP_USERDATA,LONG_PTR(color));
            SetLayeredWindowAttributes(window,0,BYTE(std::lround(opacity*255)),LWA_ALPHA);
            // The viewer must not see the glow in the remote picture. Windows before 10 2004 ignores this.
            SetWindowDisplayAffinity(window,WDA_EXCLUDEFROMCAPTURE);
            SetWindowPos(window,HWND_TOPMOST,screen.left+strip.left,screen.top+strip.top,strip.right-strip.left,strip.bottom-strip.top,SWP_NOACTIVATE|SWP_SHOWWINDOW);
            InvalidateRect(window,nullptr,TRUE);
        }
        outer=inner;
    }
    for(;index<m_windows.size();++index)if(m_windows[index])ShowWindow(HWND(m_windows[index]),SW_HIDE);
}
