#include "jpeg_codec.h"
#include <QByteArray>
#include <turbojpeg.h>
#include <cstdint>
#include <memory>
#include <stdexcept>
namespace {
struct NativeBuffer { const uint8_t* data; size_t length; void* owner; };
using Encode = bool (*)(const uint8_t*,size_t,uint32_t,uint32_t,uint8_t,NativeBuffer*);
using Decode = bool (*)(const uint8_t*,size_t,uint32_t,uint32_t,NativeBuffer*);
using Release = void (*)(void*);
extern "C" bool od_set_jpeg_backend(Encode,Decode,Release);
struct Codec {
    tjhandle compressor=tj3Init(TJINIT_COMPRESS), decompressor=tj3Init(TJINIT_DECOMPRESS);
    Codec(){if(!compressor||!decompressor)throw std::runtime_error("Cannot initialize the native JPEG codec");
        tj3Set(decompressor,TJPARAM_MAXMEMORY,128);tj3Set(decompressor,TJPARAM_MAXPIXELS,16*1024*1024);tj3Set(decompressor,TJPARAM_SCANLIMIT,500);
    }
    ~Codec(){tj3Destroy(compressor);tj3Destroy(decompressor);}
};
// Handles are private to each capture/decode worker and never shared with the GUI.
thread_local Codec codec;
struct Owned { unsigned char* compressed=nullptr;QByteArray decoded;~Owned(){if(compressed)tj3Free(compressed);} };
bool encode(const uint8_t* pixels,size_t length,uint32_t w,uint32_t h,uint8_t quality,NativeBuffer* out) noexcept {
    try {
        if(!pixels||!out||!w||!h||w>8192||h>8192||size_t(w)*h>16*1024*1024||length!=size_t(w)*h*4)return false;
        const auto handle=codec.compressor;
        if(tj3Set(handle,TJPARAM_QUALITY,quality)<0||tj3Set(handle,TJPARAM_SUBSAMP,quality>=80?TJSAMP_444:TJSAMP_420)<0)return false;
        auto owned=std::make_unique<Owned>();size_t size=0;
        if(tj3Compress8(handle,pixels,int(w),int(w*4),int(h),TJPF_BGRA,&owned->compressed,&size)<0)return false;
        *out={owned->compressed,size,owned.get()};owned.release();return true;
    }catch(...){return false;}
}
bool decode(const uint8_t* data,size_t length,uint32_t w,uint32_t h,NativeBuffer* out) noexcept {
    try {
        if(!data||!out||!w||!h||w>8192||h>8192||size_t(w)*h>16*1024*1024||length>32*1024*1024)return false;
        const auto handle=codec.decompressor;
        if(tj3DecompressHeader(handle,data,length)<0||tj3Get(handle,TJPARAM_JPEGWIDTH)!=int(w)||tj3Get(handle,TJPARAM_JPEGHEIGHT)!=int(h)||tj3Get(handle,TJPARAM_PRECISION)!=8)return false;
        auto owned=std::make_unique<Owned>();owned->decoded=QByteArray(qsizetype(w)*h*4,Qt::Uninitialized);
        if(tj3Decompress8(handle,data,length,reinterpret_cast<unsigned char*>(owned->decoded.data()),int(w*4),TJPF_BGRA)<0)return false;
        *out={reinterpret_cast<const uint8_t*>(owned->decoded.constData()),size_t(owned->decoded.size()),owned.get()};owned.release();return true;
    }catch(...){return false;}
}
void release(void* owner) noexcept {delete static_cast<Owned*>(owner);}
}
void installJpegCodec(){if(!od_set_jpeg_backend(encode,decode,release))throw std::runtime_error("The JPEG backend was already initialized.");}
QImage jpegSelfTestImage(){
    QImage original(128,64,QImage::Format_RGB32);original.fill(Qt::red);
    for(int y=0;y<64;++y)for(int x=64;x<128;++x)original.setPixelColor(x,y,Qt::blue);
    NativeBuffer compressed{},decoded{},invalid{};
    if(!encode(original.constBits(),size_t(original.sizeInBytes()),128,64,95,&compressed))throw std::runtime_error("JPEG encode self-test failed");
    const bool rejectsMismatch=!decode(compressed.data,compressed.length,129,64,&invalid);
    if(invalid.owner)release(invalid.owner);
    const bool okay=decode(compressed.data,compressed.length,128,64,&decoded);release(compressed.owner);
    if(!okay||!rejectsMismatch){if(decoded.owner)release(decoded.owner);throw std::runtime_error("JPEG bounds self-test failed");}
    QImage image(decoded.data,128,64,128*4,QImage::Format_ARGB32,release,decoded.owner);
    const auto red=image.pixelColor(32,32),blue=image.pixelColor(96,32);
    if(red.red()<220||red.blue()>30||blue.blue()<220||blue.red()>30||red.alpha()!=255||blue.alpha()!=255)throw std::runtime_error("JPEG pixel format self-test failed");
    return image;
}
