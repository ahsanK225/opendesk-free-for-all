#include "engine_bridge.h"
#include "version.h"
#include "frame_item.h"
#include "jpeg_codec.h"
#include "session_dot.h"
extern "C" char* od_diagnostics(bool capture);
#include <QApplication>
#include <QCommandLineParser>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QCryptographicHash>
#include <QIcon>
#include <QJsonDocument>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QSGRendererInterface>
#define NOMINMAX
#include <dxgi.h>
#include <QMessageBox>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QScreen>
#include <QTimer>
#include <QDateTime>
#include <QLocale>
#include <QVariantMap>
#include <thread>
#include <windows.h>
#include <dwmapi.h>
class NativeInstance {
public:
    HANDLE mutex=nullptr,shutdown=nullptr,activate=nullptr;bool primary=false;
    explicit NativeInstance(const QString& directory){
        QString user=QDir::toNativeSeparators(QDir::homePath()).toLower();
        if(!directory.isEmpty())user+=QLatin1Char('|')+QDir::toNativeSeparators(QFileInfo(directory).absoluteFilePath()).toLower();
        const auto digest=QCryptographicHash::hash(user.toUtf8(),QCryptographicHash::Sha256).toHex().left(24);
        const auto name=QStringLiteral("Local\\OpenDesk.")+QString::fromLatin1(digest);
        SetLastError(0);mutex=CreateMutexW(nullptr,FALSE,name.toStdWString().c_str());primary=GetLastError()!=ERROR_ALREADY_EXISTS;
        shutdown=CreateEventW(nullptr,FALSE,FALSE,(name+QStringLiteral(".shutdown")).toStdWString().c_str());
        activate=CreateEventW(nullptr,FALSE,FALSE,(name+QStringLiteral(".activate")).toStdWString().c_str());
        if(!mutex||!shutdown||!activate)throw std::runtime_error("Unable to initialize the Windows launcher.");
        if(!primary)SetEvent(activate);
    }
    ~NativeInstance(){if(activate)CloseHandle(activate);if(shutdown)CloseHandle(shutdown);if(mutex)CloseHandle(mutex);}
};
namespace {
// Display drivers made for Windows 8.1 and older (WDDM 1.x, versions below 20.x) can make the whole
// screen blink while a flip-model Direct3D window redraws. Returns the adapter name when that is the case.
QString oldDisplayDriver(){
    IDXGIFactory1* factory=nullptr;if(FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1),reinterpret_cast<void**>(&factory))))return {};
    QString name;IDXGIAdapter1* adapter=nullptr;
    if(SUCCEEDED(factory->EnumAdapters1(0,&adapter))){
        DXGI_ADAPTER_DESC1 desc{};LARGE_INTEGER version{};
        if(SUCCEEDED(adapter->GetDesc1(&desc))&&!(desc.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)&&desc.VendorId!=0x1414&&SUCCEEDED(adapter->CheckInterfaceSupport(__uuidof(IDXGIDevice),&version))&&HIWORD(version.HighPart)<20)name=QString::fromWCharArray(desc.Description);
        adapter->Release();
    }
    factory->Release();return name;
}
bool openGlWorks(){QOffscreenSurface surface;surface.create();QOpenGLContext context;return context.create()&&context.format().majorVersion()>=2&&context.makeCurrent(&surface)&&(context.doneCurrent(),true);}
// Picks how Qt Quick draws, before the first window exists, and says what it picked.
QString chooseGraphics(const QString& choice){
    if(qEnvironmentVariableIsSet("QSG_RHI_BACKEND")||qEnvironmentVariableIsSet("QT_QUICK_BACKEND"))return QStringLiteral("set by environment variable");
    if(choice==QStringLiteral("software")){QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);return QStringLiteral("Software");}
    if(choice==QStringLiteral("opengl")){if(openGlWorks()){QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);return QStringLiteral("OpenGL");}return QStringLiteral("Direct3D 11, because OpenGL is not available");}
    if(choice==QStringLiteral("direct3d"))return QStringLiteral("Direct3D 11");
    const auto adapter=oldDisplayDriver();
    if(!adapter.isEmpty()&&openGlWorks()){QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);return QStringLiteral("OpenGL, chosen automatically for the older display driver of ")+adapter;}
    return QStringLiteral("Direct3D 11, chosen automatically");
}
}
int main(int argc,char** argv){
    QApplication application(argc,argv);QLocale::setDefault(QLocale(QLocale::English,QLocale::UnitedStates));application.setLayoutDirection(Qt::LeftToRight);application.setApplicationName(QStringLiteral("OpenDesk"));application.setApplicationVersion(QStringLiteral(OPENDESK_VERSION));application.setWindowIcon(QIcon(QStringLiteral(":/brand/portal-o.svg")));
    QQuickStyle::setStyle(QStringLiteral("Basic"));QCommandLineParser parser;parser.addHelpOption();parser.addVersionOption();
    parser.addOption({QStringLiteral("config-dir"),QStringLiteral("Isolated configuration directory"),QStringLiteral("path")});
    parser.addOption({QStringLiteral("smoke-test"),QStringLiteral("Save startup evidence and exit")});
    parser.addOption({QStringLiteral("smoke-delay-ms"),QStringLiteral("Bounded evidence delay for connection checks"),QStringLiteral("milliseconds"),QStringLiteral("2500")});
    parser.addOption({QStringLiteral("smoke-minimized"),QStringLiteral("Start a smoke test minimized")});
    parser.addOption({QStringLiteral("smoke-page"),QStringLiteral("Select the native page for a smoke screenshot"),QStringLiteral("page")});
    parser.addOption({QStringLiteral("render-self-test"),QStringLiteral("Verify JPEG pixel formats and GPU texture presentation"),QStringLiteral("image")});
    parser.addOption({QStringLiteral("screenshot"),QStringLiteral("Native startup image destination"),QStringLiteral("path")});
    parser.addOption({QStringLiteral("smoke-output"),QStringLiteral("Startup state destination"),QStringLiteral("path")});
    parser.addOption({QStringLiteral("benchmark-output"),QStringLiteral("Run native codec diagnostics and save JSON"),QStringLiteral("path")});parser.process(application);
    try{
        installJpegCodec();
        if(parser.isSet(QStringLiteral("render-self-test"))){
            const auto pixels=jpegSelfTestImage();QQuickWindow window;window.setTitle(QStringLiteral("OpenDesk renderer verification"));window.resize(640,320);window.setColor(Qt::black);
            auto* item=new FrameItem(window.contentItem());item->setSize(QSizeF(640,320));item->setDiagnosticFrame(pixels);window.show();
            QTimer::singleShot(1200,&application,[&]{const auto image=window.grabWindow();const auto red=image.pixelColor(image.width()/4,image.height()/2),blue=image.pixelColor(image.width()*3/4,image.height()/2);const bool hardware=window.rendererInterface()->graphicsApi()!=QSGRendererInterface::Software;const bool okay=hardware&&red.red()>220&&red.blue()<30&&blue.blue()>220&&blue.red()<30&&image.save(parser.value(QStringLiteral("render-self-test")));application.exit(okay?0:2);});
            return application.exec();
        }
        if(parser.isSet(QStringLiteral("benchmark-output"))){char* report=od_diagnostics(true);if(!report)return 2;QByteArray bytes(report);od_string_free(report);QFile output(parser.value(QStringLiteral("benchmark-output")));if(!output.open(QIODevice::WriteOnly))return 2;return output.write(bytes)==bytes.size()&&!bytes.contains("\"error\"")?0:2;}
        NativeInstance instance(parser.value(QStringLiteral("config-dir")));if(!instance.primary)return 0;
        EngineBridge bridge(parser.value(QStringLiteral("config-dir")));
        const QString graphicsInfo=chooseGraphics(bridge.state().value(QStringLiteral("settings")).toMap().value(QStringLiteral("graphics")).toString());
        qmlRegisterType<FrameItem>("OpenDesk.Media",1,0,"RemoteFrame");
        SessionDot dot;
        QQmlApplicationEngine engine;engine.rootContext()->setContextProperty(QStringLiteral("backend"),&bridge);engine.rootContext()->setContextProperty(QStringLiteral("sessionDot"),&dot);engine.rootContext()->setContextProperty(QStringLiteral("graphicsInfo"),graphicsInfo);
        const auto desktop=QGuiApplication::primaryScreen()->geometry();
        engine.rootContext()->setContextProperty(QStringLiteral("primaryDesktop"),QVariantMap{{QStringLiteral("x"),desktop.x()},{QStringLiteral("y"),desktop.y()},{QStringLiteral("width"),desktop.width()},{QStringLiteral("height"),desktop.height()}});
        QObject::connect(&engine,&QQmlApplicationEngine::objectCreationFailed,&application,[]{QCoreApplication::exit(1);},Qt::QueuedConnection);
        engine.loadFromModule(QStringLiteral("OpenDesk.Native"),QStringLiteral("Main"));
        if(engine.rootObjects().isEmpty())return 1;
        auto* window=qobject_cast<QQuickWindow*>(engine.rootObjects().first());if(!window)return 1;
        const auto available=window->screen()->availableGeometry();
        window->resize(qMin(1280,qMax(760,available.width()-24)),qMin(820,qMax(520,available.height()-48)));
        window->setPosition(available.center()-QPoint(window->width()/2,window->height()/2));
        if(parser.isSet(QStringLiteral("smoke-test"))&&parser.isSet(QStringLiteral("smoke-page"))){const auto page=parser.value(QStringLiteral("smoke-page"));if(!QStringList{QStringLiteral("home"),QStringLiteral("settings"),QStringLiteral("saved"),QStringLiteral("files"),QStringLiteral("audio"),QStringLiteral("update"),QStringLiteral("transfer"),QStringLiteral("pointer"),QStringLiteral("session"),QStringLiteral("sharing"),QStringLiteral("thumbnails"),QStringLiteral("fullscreen")}.contains(page))return 2;if(page==QStringLiteral("pointer"))window->setProperty("smokePointer",true);if(page==QStringLiteral("fullscreen"))window->setProperty("fullView",true);if(page==QStringLiteral("session")||page==QStringLiteral("fullscreen")){window->setProperty("smokeSession",QVariantMap{{QStringLiteral("key"),QStringLiteral("smoke")},{QStringLiteral("state"),QStringLiteral("connected")},{QStringLiteral("name"),QStringLiteral("Office PC")},{QStringLiteral("route"),QStringLiteral("Direct")},{QStringLiteral("fps"),30},{QStringLiteral("rtt"),42},{QStringLiteral("profile"),QStringLiteral("balanced")},{QStringLiteral("maxWidth"),1920},{QStringLiteral("message"),QStringLiteral("Connected")},{QStringLiteral("permissions"),QVariantMap{{QStringLiteral("input"),true},{QStringLiteral("audio"),true},{QStringLiteral("file_transfer"),true}}}});window->setProperty("activeKey",QStringLiteral("smoke"));}if(page==QStringLiteral("sharing"))window->setProperty("smokeHost",QVariantMap{{QStringLiteral("peer"),QStringLiteral("100200300")},{QStringLiteral("since"),QDateTime::currentSecsSinceEpoch()-420},{QStringLiteral("from"),QVariantMap{{QStringLiteral("id"),QStringLiteral("111 222 333")},{QStringLiteral("name"),QStringLiteral("OFFICE-PC")}}},{QStringLiteral("permissions"),QVariantMap{{QStringLiteral("input"),true},{QStringLiteral("audio"),true},{QStringLiteral("file_transfer"),true}}}});window->setProperty("page",page==QStringLiteral("audio")?QStringLiteral("settings"):page==QStringLiteral("update")||page==QStringLiteral("pointer")||page==QStringLiteral("session")||page==QStringLiteral("fullscreen")||page==QStringLiteral("sharing")?QStringLiteral("home"):page==QStringLiteral("transfer")||page==QStringLiteral("thumbnails")?QStringLiteral("files"):page);if(page==QStringLiteral("update"))window->setProperty("smokeUpdate",QVariantMap{{QStringLiteral("state"),QStringLiteral("downloading")},{QStringLiteral("version"),QStringLiteral("9.9")},{QStringLiteral("done"),26214400},{QStringLiteral("total"),52428800},{QStringLiteral("speed"),2097152},{QStringLiteral("message"),QStringLiteral("Downloading the update…")}});// A remote folder with a few entries and one picture preview, in list (transfer) or grid (thumbnails) view.
if(page==QStringLiteral("transfer")||page==QStringLiteral("thumbnails")){window->setProperty("smokeSession",QJsonDocument::fromJson(R"({"key":"smoke","state":"connected","name":"Office PC","permissions":{"file_transfer":true},"fileFeatures":["folders","thumbnails"],"files":{"path":"C:\\Users\\Office\\Shared","parent":"C:\\Users\\Office","entries":[{"name":"Holiday","is_dir":true,"size":0,"modified":1793900000},{"name":"Invoices","is_dir":true,"size":0,"modified":1793800000},{"name":"Logo.png","is_dir":false,"size":48211,"modified":1793700000},{"name":"Quarterly report.pdf","is_dir":false,"size":2411520,"modified":1793600000},{"name":"Setup.exe","is_dir":false,"size":39331752,"modified":1793500000},{"name":"song.mp3","is_dir":false,"size":5242880,"modified":1793400000}]},"previews":{"Logo.png":"qrc:/brand/portal-o.svg"}})").toVariant());window->setProperty("picked",QVariantMap{{QStringLiteral("Quarterly report.pdf"),true}});if(page==QStringLiteral("thumbnails"))window->setProperty("fileView",QStringLiteral("grid"));}
if(page==QStringLiteral("transfer"))window->setProperty("smokeTransfer",QVariantMap{{QStringLiteral("state"),QStringLiteral("running")},{QStringLiteral("direction"),QStringLiteral("upload")},{QStringLiteral("name"),QStringLiteral("example.zip")},{QStringLiteral("done"),13107200},{QStringLiteral("total"),52428800},{QStringLiteral("speed"),3145728}});if(page==QStringLiteral("audio"))QTimer::singleShot(800,window,[window]{QMetaObject::invokeMethod(window,"focusAudio");});}
        od_set_window_handle(size_t(window->winId()));
        // The remote pointer window would otherwise keep the app alive after the main window closes.
        QObject::connect(window,&QWindow::visibleChanged,&application,[](bool visible){if(!visible)QCoreApplication::exit(0);});
        // Keep an unanswered request above other apps, including when minimized.
        // Windows may refuse foreground activation; flashing remains a fallback.
        QString pendingRequest;
        bool wasTopmost=false;
        const auto presentIncoming=[&]{
            const auto incoming=bridge.state().value(QStringLiteral("incoming")).toMap();
            const auto request=incoming.value(QStringLiteral("requestId")).toString();
            const auto handle=HWND(window->winId());
            if(request==pendingRequest&&(request.isEmpty()||(!IsIconic(handle)&&window->visibility()!=QWindow::Minimized)))return;
            if(!request.isEmpty()){
                if(pendingRequest.isEmpty())wasTopmost=(GetWindowLongPtrW(handle,GWL_EXSTYLE)&WS_EX_TOPMOST)!=0;
                if(IsIconic(handle)||window->visibility()==QWindow::Minimized){window->showNormal();ShowWindow(handle,SW_RESTORE);}
                window->show();
                SetWindowPos(handle,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW);
                window->raise();window->requestActivate();SetForegroundWindow(handle);
                FLASHWINFO flash{sizeof(FLASHWINFO),handle,FLASHW_TRAY|FLASHW_TIMERNOFG,3,0};FlashWindowEx(&flash);
            }else{
                SetWindowPos(handle,wasTopmost?HWND_TOPMOST:HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
                FLASHWINFO flash{sizeof(FLASHWINFO),handle,FLASHW_STOP,0,0};FlashWindowEx(&flash);
            }
            pendingRequest=request;
        };
        QObject::connect(&bridge,&EngineBridge::stateChanged,window,presentIncoming);
        BOOL dark=bridge.state().value(QStringLiteral("settings")).toMap().value(QStringLiteral("theme")).toString()!=QStringLiteral("light");DwmSetWindowAttribute(HWND(window->winId()),20,&dark,sizeof(dark));
        QObject::connect(&bridge,&EngineBridge::stateChanged,window,[&]{const BOOL next=bridge.state().value(QStringLiteral("settings")).toMap().value(QStringLiteral("theme")).toString()!=QStringLiteral("light");if(next!=dark){dark=next;DwmSetWindowAttribute(HWND(window->winId()),20,&dark,sizeof(dark));}});
        QTimer launcher;QObject::connect(&launcher,&QTimer::timeout,&application,[&]{if(WaitForSingleObject(instance.shutdown,0)==WAIT_OBJECT_0){window->close();return;}if(WaitForSingleObject(instance.activate,0)==WAIT_OBJECT_0){window->showNormal();window->raise();window->requestActivate();}presentIncoming();});launcher.start(100);
        if(parser.isSet(QStringLiteral("smoke-test"))&&parser.isSet(QStringLiteral("smoke-minimized")))window->showMinimized();
        // The engine can receive a request while QML is still loading, before
        // the signal connection above exists. Inspect that initial state too.
        QTimer::singleShot(0,window,presentIncoming);
        if(parser.isSet(QStringLiteral("smoke-test")))QTimer::singleShot(qBound(2500,parser.value(QStringLiteral("smoke-delay-ms")).toInt(),30000),&application,[&]{
            bool okay=true;const auto imagePath=parser.value(QStringLiteral("screenshot"));if(!imagePath.isEmpty())okay=window->grabWindow().save(imagePath);
            const auto outputPath=parser.value(QStringLiteral("smoke-output"));if(!outputPath.isEmpty()){QFile file(outputPath);okay=file.open(QIODevice::WriteOnly)&&okay;if(file.isOpen()){auto evidence=bridge.state();evidence.insert(QStringLiteral("nativeWindow"),QVariantMap{{QStringLiteral("minimized"),window->visibility()==QWindow::Minimized},{QStringLiteral("topmost"),(GetWindowLongPtrW(HWND(window->winId()),GWL_EXSTYLE)&WS_EX_TOPMOST)!=0},{QStringLiteral("foreground"),GetForegroundWindow()==HWND(window->winId())}});file.write(QJsonDocument::fromVariant(evidence).toJson());}}
            application.exit(okay?0:2);
        });
        const int code=application.exec();
        // Exit is final: a stuck engine task must not leave a process behind.
        std::thread([code]{Sleep(5000);TerminateProcess(GetCurrentProcess(),UINT(code));}).detach();
        return code;
    }catch(const std::exception& error){QMessageBox::critical(nullptr,QStringLiteral("OpenDesk could not start"),QString::fromUtf8(error.what()));return 1;}
}
