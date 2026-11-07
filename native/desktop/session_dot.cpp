#include "session_dot.h"
#include <QGuiApplication>
#include <QScreen>
#include <algorithm>
#include <cmath>
#define NOMINMAX
#include <windows.h>
#ifndef WDA_EXCLUDEFROMCAPTURE
#define WDA_EXCLUDEFROMCAPTURE 0x11
#endif
namespace {
const wchar_t* dotClass=L"OpenDeskSessionDot";
// Diameter in pixels at 100% scaling.
constexpr int dotSize=14;
SessionDot* owner(HWND window){return reinterpret_cast<SessionDot*>(GetWindowLongPtrW(window,GWLP_USERDATA));}
LRESULT CALLBACK dotProc(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
    switch(message){
    // The whole dot is a title bar, so Windows drags it without any code here.
    case WM_NCHITTEST:return HTCAPTION;
    case WM_SETCURSOR:SetCursor(LoadCursorW(nullptr,IDC_SIZEALL));return TRUE;
    case WM_NCLBUTTONDBLCLK:if(auto* dot=owner(window))QMetaObject::invokeMethod(dot,&SessionDot::opened,Qt::QueuedConnection);return 0;
    case WM_EXITSIZEMOVE:{RECT area;if(GetWindowRect(window,&area))if(auto* dot=owner(window))dot->moved(QPoint(area.left,area.top));return 0;}
    case WM_ERASEBKGND:return 1;
    case WM_PAINT:{
        PAINTSTRUCT paint;const HDC dc=BeginPaint(window,&paint);RECT area;GetClientRect(window,&area);
        const COLORREF color=COLORREF(GetPropW(window,L"OpenDeskColor"));
        const HBRUSH fill=CreateSolidBrush(color);FillRect(dc,&area,fill);DeleteObject(fill);
        // A darker rim keeps the dot visible on red and on white.
        const HPEN rim=CreatePen(PS_SOLID,1,RGB(GetRValue(color)*3/5,GetGValue(color)*3/5,GetBValue(color)*3/5));
        const HGDIOBJ oldPen=SelectObject(dc,rim),oldBrush=SelectObject(dc,GetStockObject(NULL_BRUSH));
        Ellipse(dc,area.left,area.top,area.right,area.bottom);
        SelectObject(dc,oldPen);SelectObject(dc,oldBrush);DeleteObject(rim);
        EndPaint(window,&paint);return 0;}
    }
    return DefWindowProcW(window,message,wparam,lparam);
}
}
SessionDot::SessionDot(QObject* parent):QObject(parent){
    connect(qGuiApp,&QGuiApplication::screenRemoved,this,[this]{if(m_active)place();});
    connect(qGuiApp,&QGuiApplication::primaryScreenChanged,this,[this]{if(m_active)place();});
}
SessionDot::~SessionDot(){if(m_window)DestroyWindow(HWND(m_window));}
void SessionDot::setActive(bool value){
    if(value==m_active)return;
    m_active=value;
    if(m_active)place();else if(m_window)ShowWindow(HWND(m_window),SW_HIDE);
    emit activeChanged();
}
void SessionDot::setColor(const QColor& value){
    if(value==m_color)return;
    m_color=value;
    if(m_window){SetPropW(HWND(m_window),L"OpenDeskColor",HANDLE(INT_PTR(RGB(m_color.red(),m_color.green(),m_color.blue()))));InvalidateRect(HWND(m_window),nullptr,TRUE);}
    emit colorChanged();
}
void SessionDot::place(){
    if(!m_window){
        static const bool registered=[]{WNDCLASSW type{};type.lpfnWndProc=dotProc;type.hInstance=GetModuleHandleW(nullptr);type.lpszClassName=dotClass;type.style=CS_DBLCLKS;return RegisterClassW(&type)!=0;}();
        if(!registered)return;
        m_window=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_TOPMOST|WS_EX_NOACTIVATE,dotClass,L"OpenDesk session",WS_POPUP,0,0,1,1,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        if(!m_window)return;
        SetWindowLongPtrW(HWND(m_window),GWLP_USERDATA,LONG_PTR(this));
        SetPropW(HWND(m_window),L"OpenDeskColor",HANDLE(INT_PTR(RGB(m_color.red(),m_color.green(),m_color.blue()))));
    }
    const HWND window=HWND(m_window);
    const qreal scale=QGuiApplication::primaryScreen()?QGuiApplication::primaryScreen()->devicePixelRatio():1;
    const int size=std::max(8,int(std::lround(dotSize*scale)));
    MONITORINFO monitor{sizeof(MONITORINFO)};
    // A dot the person has not moved sits at the top centre of the main screen, like a camera light.
    if(!m_placed&&GetMonitorInfoW(MonitorFromPoint(POINT{0,0},MONITOR_DEFAULTTOPRIMARY),&monitor))
        m_position=QPoint((monitor.rcMonitor.left+monitor.rcMonitor.right-size)/2,monitor.rcMonitor.top+std::lround(6*scale));
    // Keep it on a screen that still exists.
    const int left=GetSystemMetrics(SM_XVIRTUALSCREEN),top=GetSystemMetrics(SM_YVIRTUALSCREEN);
    m_position=QPoint(std::clamp(m_position.x(),left,left+GetSystemMetrics(SM_CXVIRTUALSCREEN)-size),std::clamp(m_position.y(),top,top+GetSystemMetrics(SM_CYVIRTUALSCREEN)-size));
    SetWindowRgn(window,CreateEllipticRgn(0,0,size+1,size+1),FALSE);
    // The viewer must not see the dot in the remote picture. Windows before 10 2004 ignores this.
    SetWindowDisplayAffinity(window,WDA_EXCLUDEFROMCAPTURE);
    SetWindowPos(window,HWND_TOPMOST,m_position.x(),m_position.y(),size,size,SWP_NOACTIVATE|SWP_SHOWWINDOW);
    InvalidateRect(window,nullptr,TRUE);
}
