#include "engine_bridge.h"
#include "frame_item.h"
#include "jpeg_codec.h"
extern "C" char* od_diagnostics(bool capture);
#include <QApplication>
#include <QCommandLineParser>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QCryptographicHash>
#include <QIcon>
#include <QJsonDocument>
#include <QMessageBox>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QScreen>
#include <QTimer>
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
int main(int argc,char** argv){
    QApplication application(argc,argv);application.setApplicationName(QStringLiteral("OpenDesk"));application.setApplicationVersion(QStringLiteral("3.0.0-alpha.1"));application.setWindowIcon(QIcon(QStringLiteral(":/brand/portal-o.svg")));
    QQuickStyle::setStyle(QStringLiteral("Basic"));QCommandLineParser parser;parser.addHelpOption();parser.addVersionOption();
    parser.addOption({QStringLiteral("config-dir"),QStringLiteral("Isolated configuration directory"),QStringLiteral("path")});
    parser.addOption({QStringLiteral("smoke-test"),QStringLiteral("Save startup evidence and exit")});
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
        qmlRegisterType<FrameItem>("OpenDesk.Media",1,0,"RemoteFrame");
        QQmlApplicationEngine engine;engine.rootContext()->setContextProperty(QStringLiteral("backend"),&bridge);
        QObject::connect(&engine,&QQmlApplicationEngine::objectCreationFailed,&application,[]{QCoreApplication::exit(1);},Qt::QueuedConnection);
        engine.loadFromModule(QStringLiteral("OpenDesk.Native"),QStringLiteral("Main"));
        if(engine.rootObjects().isEmpty())return 1;
        auto* window=qobject_cast<QQuickWindow*>(engine.rootObjects().first());if(!window)return 1;
        const auto available=window->screen()->availableGeometry();
        window->resize(qMin(1280,qMax(760,available.width()-24)),qMin(820,qMax(520,available.height()-48)));
        window->setPosition(available.center()-QPoint(window->width()/2,window->height()/2));
        if(parser.isSet(QStringLiteral("smoke-test"))&&parser.isSet(QStringLiteral("smoke-page"))){const auto page=parser.value(QStringLiteral("smoke-page"));if(!QStringList{QStringLiteral("home"),QStringLiteral("settings"),QStringLiteral("saved"),QStringLiteral("files")}.contains(page))return 2;window->setProperty("page",page);}
        od_set_window_handle(size_t(window->winId()));
        BOOL dark=TRUE;DwmSetWindowAttribute(HWND(window->winId()),20,&dark,sizeof(dark));
        QTimer launcher;QObject::connect(&launcher,&QTimer::timeout,&application,[&]{if(WaitForSingleObject(instance.shutdown,0)==WAIT_OBJECT_0){window->close();return;}if(WaitForSingleObject(instance.activate,0)==WAIT_OBJECT_0){window->showNormal();window->raise();window->requestActivate();}});launcher.start(100);
        if(parser.isSet(QStringLiteral("smoke-test")))QTimer::singleShot(2500,&application,[&]{
            bool okay=true;const auto imagePath=parser.value(QStringLiteral("screenshot"));if(!imagePath.isEmpty())okay=window->grabWindow().save(imagePath);
            const auto outputPath=parser.value(QStringLiteral("smoke-output"));if(!outputPath.isEmpty()){QFile file(outputPath);okay=file.open(QIODevice::WriteOnly)&&okay;if(file.isOpen())file.write(QJsonDocument::fromVariant(bridge.state()).toJson());}
            application.exit(okay?0:2);
        });
        return application.exec();
    }catch(const std::exception& error){QMessageBox::critical(nullptr,QStringLiteral("OpenDesk could not start"),QString::fromUtf8(error.what()));return 1;}
}
