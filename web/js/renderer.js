/** Sequential JPEG presentation: a delta is never painted ahead of its base frame. */
class RemoteRenderer {
  constructor(canvas) {
    this.canvas=canvas; this.ctx=canvas.getContext('2d',{alpha:false});
    this.framesCount=0; this.lastFpsTimestamp=performance.now(); this.generation=0;
    this.lastFrame=0;
  }
  reset() { this.generation++; this.lastFrame=0; }
  async renderPacket(message) {
    const generation=this.generation, p=message.payload;
    if(p.frame_id<=this.lastFrame) return;
    if(message.type==='video_delta' && (!this.lastFrame || this.canvas.width!==p.width || this.canvas.height!==p.height))
      throw new Error('Missing video base frame');
    const tiles=message.type==='video_full'?[{image:p.image,x:0,y:0}]:p.tiles;
    const images=await Promise.all(tiles.map(async tile=>{
      const data=typeof tile.image==='string'?Uint8Array.from(atob(tile.image),c=>c.charCodeAt(0)):tile.image;
      return {tile,image:await createImageBitmap(new Blob([data],{type:'image/jpeg'}))};
    }));
    try {
      if(generation!==this.generation) return;
      if(this.canvas.width!==p.width || this.canvas.height!==p.height) {
        this.canvas.width=p.width; this.canvas.height=p.height;
      }
      this.ctx.imageSmoothingEnabled=false;
      for(const {tile,image} of images) this.ctx.drawImage(image,tile.x,tile.y);
      this.lastFrame=p.frame_id;
      this.framesCount++;
      const now=performance.now();
      if(now-this.lastFpsTimestamp>=1000) {
        document.getElementById('statFps').textContent=Math.round(this.framesCount*1000/(now-this.lastFpsTimestamp));
        this.framesCount=0; this.lastFpsTimestamp=now;
      }
    } finally { for(const {image} of images) image.close(); }
  }
}
