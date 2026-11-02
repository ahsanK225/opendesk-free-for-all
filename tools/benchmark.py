"""Reproducible synthetic codec timing; optional local GDI capture (no images saved)."""
import argparse
import base64
import json
import statistics
import time
import numpy as np
from PIL import Image, ImageDraw
from common.codec import DeskRTCodec
from common.protocol import encode_video_packet


def measure(function, count):
    samples=[]
    for _ in range(count):
        start=time.perf_counter()
        function()
        samples.append((time.perf_counter()-start)*1000)
    return {'mean_ms':round(statistics.mean(samples),2),
            'p95_ms':round(sorted(samples)[int(.95*(len(samples)-1))],2)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--output')
    args=parser.parse_args()
    codec=DeskRTCodec(quality=65)
    image=Image.new('RGB',(1600,900),'#202534')
    draw=ImageDraw.Draw(image)
    for y in range(0,900,24): draw.text((24,y),'OpenDesk synthetic desktop text and window regions '*4,fill='white')
    pixels=np.asarray(image.convert('RGBA')).view(np.uint32).reshape((900,1600))
    codec.encode(image,raw_u32=pixels,force_keyframe=True)
    idle=measure(lambda:codec.encode(image,raw_u32=pixels),60)
    position=[0]
    def delta():
        position[0]=(position[0]+1)%120
        x=position[0]*8
        image.paste((position[0]*2,60,150),(x,300,x+64,364))
        data=np.asarray(image.convert('RGBA')).view(np.uint32).reshape((900,1600))
        return codec.encode(image,raw_u32=data)
    motion=measure(delta,60)
    keyframe=codec.encode(image,raw_u32=pixels,force_keyframe=True)
    legacy=json.dumps({'type':'video_full','payload':{'width':1600,'height':900,'frame_id':1,
                      'image':base64.b64encode(keyframe['data']).decode()}}).encode()
    binary=encode_video_packet(keyframe,'benchmark-session')
    report={'scope':'Local synthetic codec timings; excludes network RTT and viewer rendering',
            'resolution':[1600,900],'idle':idle,'small_changes':motion,
            'legacy_json_bytes':len(legacy),'binary_bytes':len(binary),
            'wire_reduction_pct':round(100*(1-len(binary)/len(legacy)),1)}
    if args.capture:
        from host.capture import WindowsScreenCapturer, AdaptiveScreenCapturer
        capturer=WindowsScreenCapturer()
        try:
            report['capture_resolution']=[capturer.width,capturer.height]
            report['gdi_capture']=measure(capturer.grab_frame,60)
        finally: capturer.close()
        capturer=AdaptiveScreenCapturer()
        try:
            report['preferred_capture_backend']=capturer.backend
            report['adaptive_capture']=measure(capturer.grab_frame,60)
        finally: capturer.close()
    text=json.dumps(report,indent=2)
    print(text)
    if args.output:
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(text,encoding='utf-8')


if __name__=='__main__': main()
