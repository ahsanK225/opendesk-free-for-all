/**
 * OpenDesk Canvas Renderer
 * Handles full-frame rasterization and DeskRT-style dirty tile blitting.
 */

class RemoteRenderer {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d', { alpha: false });
    this.ctx.imageSmoothingEnabled = false;

    this.width = 0;
    this.height = 0;
    this.framesCount = 0;
    this.lastFpsTimestamp = performance.now();
    this.currentFps = 0;
  }

  setDimensions(w, h) {
    if (this.width !== w || this.height !== h) {
      this.width = w;
      this.height = h;
      this.canvas.width = w;
      this.canvas.height = h;
      this.ctx.imageSmoothingEnabled = false;
    }
  }

  renderFullFrame(width, height, b64Image, onComplete) {
    this.setDimensions(width, height);
    const img = new Image();
    img.onload = () => {
      this.ctx.drawImage(img, 0, 0);
      this._updateFps();
      if (onComplete) onComplete();
    };
    img.src = "data:image/jpeg;base64," + b64Image;
  }

  renderDeltaFrame(width, height, tiles, onComplete) {
    this.setDimensions(width, height);
    if (!tiles || tiles.length === 0) {
      this._updateFps();
      if (onComplete) onComplete();
      return;
    }

    let loaded = 0;
    const total = tiles.length;

    for (const tile of tiles) {
      const img = new Image();
      img.onload = () => {
        this.ctx.drawImage(img, tile.x, tile.y, tile.w, tile.h);
        loaded++;
        if (loaded >= total) {
          this._updateFps();
          if (onComplete) onComplete();
        }
      };
      img.src = "data:image/jpeg;base64," + tile.image;
    }
  }

  _updateFps() {
    this.framesCount++;
    const now = performance.now();
    const elapsed = now - this.lastFpsTimestamp;
    if (elapsed >= 1000) {
      this.currentFps = Math.round((this.framesCount * 1000) / elapsed);
      this.framesCount = 0;
      this.lastFpsTimestamp = now;
      
      const fpsElem = document.getElementById("statFps");
      if (fpsElem) {
        fpsElem.textContent = this.currentFps;
      }
    }
  }
}
