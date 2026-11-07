#pragma once
#include <QObject>
#include <QVariantMap>
#include <QTimer>
#include <cstdint>
extern "C" {
struct NativeApp;
struct NativeFrameView {const uint8_t* data;size_t length;uint32_t width,height;uint64_t generation;void* owner;};
NativeApp* od_create(const char* directory);
void od_destroy(NativeApp* app);
void od_set_window_handle(size_t window);
void od_command(const NativeApp* app,const char* command);
char* od_poll(const NativeApp* app);
void od_string_free(char* value);
bool od_frame_acquire(const NativeApp* app,const char* key,NativeFrameView* output);
void od_frame_release(void* owner);
}
class EngineBridge final:public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap state READ state NOTIFY stateChanged)
public:
    explicit EngineBridge(QString directory,QObject* parent=nullptr);
    ~EngineBridge() override;
    QVariantMap state()const{return m_state;}
    NativeApp* native()const{return m_app;}
    Q_INVOKABLE void command(QVariantMap value);
    Q_INVOKABLE void copyText(const QString& value);
    Q_INVOKABLE void openUrl(const QString& value);
    Q_INVOKABLE void uploadFile(const QString& key,const QString& directory);
    Q_INVOKABLE void uploadFolder(const QString& key,const QString& directory);
    // Files and folders dropped from Explorer, as file URLs.
    Q_INVOKABLE void uploadPaths(const QString& key,const QString& directory,const QVariantList& urls);
    Q_INVOKABLE void chooseSharedFolder();
    Q_INVOKABLE void openSharedFolder();
    Q_INVOKABLE void downloadFile(const QString& key,const QString& path,const QString& filename);
    // Remote entries as {path,name,is_dir}: one file asks where to save it, anything more asks for a folder.
    Q_INVOKABLE void downloadItems(const QString& key,const QVariantList& items);
signals:
    void stateChanged();
private:
    void poll();
    NativeApp* m_app=nullptr;
    QVariantMap m_state;
    QTimer m_timer;
};
