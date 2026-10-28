/**
 * OpenDesk Input Handler
 * Captures browser mouse, wheel, and keyboard events,
 * normalizes coordinates, and serializes them to OpenDesk input packets.
 */

class InputHandler {
  constructor(canvasElement, sendCallback) {
    this.canvas = canvasElement;
    this.send = sendCallback;
    this.enabled = true;
    
    this.lastMoveTime = 0;
    this.moveThrottleMs = 15; // ~60 Hz mouse sampling

    this._bindEvents();
  }

  _getNormalizedCoords(e) {
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    return {
      x: Math.max(0, Math.min(1.0, x)),
      y: Math.max(0, Math.min(1.0, y))
    };
  }

  _bindEvents() {
    // Mouse Move
    this.canvas.addEventListener("mousemove", (e) => {
      if (!this.enabled) return;
      const now = performance.now();
      if (now - this.lastMoveTime < this.moveThrottleMs) return;
      this.lastMoveTime = now;

      const { x, y } = this._getNormalizedCoords(e);
      this.send({
        type: "mouse_move",
        payload: { x, y }
      });
    });

    // Mouse Down
    this.canvas.addEventListener("mousedown", (e) => {
      if (!this.enabled) return;
      this.canvas.focus();
      const { x, y } = this._getNormalizedCoords(e);
      this.send({
        type: "mouse_down",
        payload: { button: e.button, x, y }
      });
    });

    // Mouse Up
    this.canvas.addEventListener("mouseup", (e) => {
      if (!this.enabled) return;
      const { x, y } = this._getNormalizedCoords(e);
      this.send({
        type: "mouse_up",
        payload: { button: e.button, x, y }
      });
    });

    // Mouse Wheel
    this.canvas.addEventListener("wheel", (e) => {
      if (!this.enabled) return;
      e.preventDefault();
      // Normalize wheel delta
      const deltaX = Math.sign(e.deltaX);
      const deltaY = Math.sign(e.deltaY);
      this.send({
        type: "mouse_scroll",
        payload: { delta_x: deltaX, delta_y: deltaY }
      });
    }, { passive: false });

    // Suppress local browser context menu on right click
    this.canvas.addEventListener("contextmenu", (e) => {
      e.preventDefault();
    });

    // Keyboard Down
    window.addEventListener("keydown", (e) => {
      if (!this.enabled || document.activeElement !== this.canvas) return;
      // Prevent browser default actions on key bindings like Tab, F5, etc.
      if (["Tab", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"].includes(e.code)) {
        e.preventDefault();
      }
      this.send({
        type: "key_down",
        payload: { code: e.code, key: e.key }
      });
    });

    // Keyboard Up
    window.addEventListener("keyup", (e) => {
      if (!this.enabled || document.activeElement !== this.canvas) return;
      this.send({
        type: "key_up",
        payload: { code: e.code, key: e.key }
      });
    });
  }

  sendShortcut(name) {
    this.send({
      type: "shortcut",
      payload: { name }
    });
  }
}
