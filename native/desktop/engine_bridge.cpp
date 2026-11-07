#include "engine_bridge.h"
#include <QApplication>
#include <QClipboard>
#include <QDir>
#include <QDesktopServices>
#include <QFileDialog>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>
#include <QUrl>
#include <stdexcept>
EngineBridge::EngineBridge(QString directory,QObject* parent):QObject(parent){
    const auto bytes=directory.toUtf8();m_app=od_create(directory.isEmpty()?nullptr:bytes.constData());
    if(!m_app)throw std::runtime_error("Unable to initialize the native engine. Existing configuration was preserved.");
    poll();connect(&m_timer,&QTimer::timeout,this,&EngineBridge::poll);m_timer.start(16);
}
EngineBridge::~EngineBridge(){m_timer.stop();od_destroy(m_app);}
void EngineBridge::poll(){if(char* raw=od_poll(m_app)){const auto document=QJsonDocument::fromJson(QByteArray(raw));od_string_free(raw);if(document.isObject()){m_state=document.object().toVariantMap();emit stateChanged();}}}
void EngineBridge::command(QVariantMap value){const auto bytes=QJsonDocument::fromVariant(value).toJson(QJsonDocument::Compact);od_command(m_app,bytes.constData());}
void EngineBridge::copyText(const QString& value){QApplication::clipboard()->setText(value);}
void EngineBridge::chooseSharedFolder(){const auto folder=QFileDialog::getExistingDirectory(nullptr,QStringLiteral("Choose the folder available to approved remote sessions"),m_state.value(QStringLiteral("settings")).toMap().value(QStringLiteral("sharedRoot")).toString());if(!folder.isEmpty())command({{QStringLiteral("type"),QStringLiteral("setting")},{QStringLiteral("name"),QStringLiteral("sharedRoot")},{QStringLiteral("value"),folder}});}
void EngineBridge::openSharedFolder(){const auto folder=m_state.value(QStringLiteral("settings")).toMap().value(QStringLiteral("sharedRoot")).toString();if(!folder.isEmpty())QDesktopServices::openUrl(QUrl::fromLocalFile(folder));}
void EngineBridge::openUrl(const QString& value){const QUrl url(value);if(url.scheme()==QStringLiteral("https")||(url.scheme()==QStringLiteral("http")&&url.host()==QStringLiteral("127.0.0.1")))QDesktopServices::openUrl(url);}
void EngineBridge::uploadFile(const QString& key,const QString& directory){const auto paths=QFileDialog::getOpenFileNames(nullptr,QStringLiteral("Send files"));if(!paths.isEmpty())command({{QStringLiteral("type"),QStringLiteral("upload")},{QStringLiteral("key"),key},{QStringLiteral("sources"),paths},{QStringLiteral("directory"),directory}});}
void EngineBridge::uploadFolder(const QString& key,const QString& directory){const auto folder=QFileDialog::getExistingDirectory(nullptr,QStringLiteral("Send a folder"));if(!folder.isEmpty())command({{QStringLiteral("type"),QStringLiteral("upload")},{QStringLiteral("key"),key},{QStringLiteral("sources"),QStringList{folder}},{QStringLiteral("directory"),directory}});}
void EngineBridge::uploadPaths(const QString& key,const QString& directory,const QVariantList& urls){QStringList paths;for(const auto& url:urls){const auto local=url.toUrl().toLocalFile();if(!local.isEmpty())paths<<QDir::toNativeSeparators(local);}if(!paths.isEmpty())command({{QStringLiteral("type"),QStringLiteral("upload")},{QStringLiteral("key"),key},{QStringLiteral("sources"),paths},{QStringLiteral("directory"),directory}});}
void EngineBridge::downloadFile(const QString& key,const QString& path,const QString& filename){const auto destination=QFileDialog::getSaveFileName(nullptr,QStringLiteral("Save remote file"),QStandardPaths::writableLocation(QStandardPaths::DownloadLocation)+QLatin1Char('/')+filename);if(!destination.isEmpty())command({{QStringLiteral("type"),QStringLiteral("download")},{QStringLiteral("key"),key},{QStringLiteral("path"),path},{QStringLiteral("destination"),destination}});}
void EngineBridge::downloadItems(const QString& key,const QVariantList& items){if(items.isEmpty())return;const auto first=items.first().toMap();if(items.size()==1&&!first.value(QStringLiteral("is_dir")).toBool()){downloadFile(key,first.value(QStringLiteral("path")).toString(),first.value(QStringLiteral("name")).toString());return;}const auto folder=QFileDialog::getExistingDirectory(nullptr,QStringLiteral("Save to folder"),QStandardPaths::writableLocation(QStandardPaths::DownloadLocation));if(!folder.isEmpty())command({{QStringLiteral("type"),QStringLiteral("download")},{QStringLiteral("key"),key},{QStringLiteral("items"),items},{QStringLiteral("directory"),QDir::toNativeSeparators(folder)}});}
