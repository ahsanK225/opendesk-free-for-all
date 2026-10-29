/**
 * OpenDesk Web Audio Engine
 * Real-time bidirectional voice communication (WhatsApp-style voice call)
 * Uses Web Audio API & MediaDevices getUserMedia with 16kHz 16-bit PCM streaming.
 */

class WebAudioVoiceChat {
  constructor(sendPacketFn) {
    this.sendPacket = sendPacketFn;
    this.audioCtx = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.processorNode = null;
    
    this.isActive = false;
    this.isMuted = false;
    this.nextPlayTime = 0;
    this.onStateChange = null; // Callback for UI updates
  }

  /**
   * Initializes the AudioContext safely on user interaction.
   */
  _ensureAudioContext() {
    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      try {
        this.audioCtx = new AudioContextClass({ sampleRate: 16000 });
      } catch (e) {
        this.audioCtx = new AudioContextClass();
      }
    }
    this.resumeContext();
  }

  /**
   * Resumes AudioContext if suspended by browser autoplay policy.
   */
  resumeContext() {
    if (this.audioCtx && this.audioCtx.state === "suspended") {
      this.audioCtx.resume().catch(() => {});
    }
  }

  /**
   * Pre-initializes audio context on session start so incoming host audio plays immediately.
   */
  initSpeaker() {
    this._ensureAudioContext();
  }

  /**
   * Starts bidirectional voice communication.
   */
  async start() {
    if (this.isActive) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Microphone Access Notice:\nBrowsers require a Secure Context (HTTPS or localhost) for microphone access.\nPlease use the Cloudflare Worldwide HTTPS link or open via localhost.");
      return;
    }
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
      
      // Buffer size: 2048 frames (~128ms per chunk at 16kHz)
      this.processorNode = this.audioCtx.createScriptProcessor(2048, 1, 1);

      this.processorNode.onaudioprocess = (e) => {
        if (!this.isActive || this.isMuted) return;

        const inputData = e.inputBuffer.getChannelData(0);
        // Convert Float32Array (-1.0 to +1.0) to 16-bit signed PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Convert to Base64 binary string
        const bytes = new Uint8Array(pcm16.buffer);
        let binary = "";
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        const b64Data = btoa(binary);

        this.sendPacket({
          type: "audio_chunk",
          payload: { data: b64Data }
        });
      };

      this.sourceNode.connect(this.processorNode);
      // Connect to dummy destination to keep processor node running
      const dummyGain = this.audioCtx.createGain();
      dummyGain.gain.value = 0;
      this.processorNode.connect(dummyGain);
      dummyGain.connect(this.audioCtx.destination);

      this.isActive = true;
      this.isMuted = false;
      this.nextPlayTime = this.audioCtx.currentTime;

      if (this.onStateChange) this.onStateChange("active");
      console.log("[Audio] Voice communication started successfully.");
    } catch (err) {
      console.error("[Audio] Failed to access microphone:", err);
      alert("Microphone access error: " + (err.message || err.name) + "\nPlease allow microphone permissions in your browser.");
      if (this.onStateChange) this.onStateChange("off");
    }
  }

  /**
   * Toggles microphone mute state.
   */
  toggleMute() {
    if (!this.isActive) return;
    this.isMuted = !this.isMuted;
    if (this.onStateChange) {
      this.onStateChange(this.isMuted ? "muted" : "active");
    }
  }

  /**
   * Stops voice communication and releases microphone.
   */
  stop() {
    this.isActive = false;
    this.isMuted = false;

    if (this.processorNode) {
      try { this.processorNode.disconnect(); } catch (e) {}
      this.processorNode = null;
    }

    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (e) {}
      this.sourceNode = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    if (this.onStateChange) this.onStateChange("off");
    console.log("[Audio] Voice communication stopped.");
  }

  /**
   * Plays an incoming 16kHz 16-bit PCM chunk from the remote host.
   */
  playChunk(b64Data) {
    try {
      this._ensureAudioContext();

      // Decode base64 to Uint8Array
      const binaryString = atob(b64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Read as Int16 PCM
      const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
      const float32 = new Float32Array(int16.length);

      // Convert Int16 (-32768 to 32767) to Float32 (-1.0 to 1.0)
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
      }

      // Schedule into Web Audio queue
      const audioBuffer = this.audioCtx.createBuffer(1, float32.length, 16000);
      audioBuffer.getChannelData(0).set(float32);

      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioCtx.destination);

      const currentTime = this.audioCtx.currentTime;
      if (this.nextPlayTime < currentTime) {
        this.nextPlayTime = currentTime + 0.02; // Small 20ms jitter cushion
      }

      source.start(this.nextPlayTime);
      this.nextPlayTime += audioBuffer.duration;
    } catch (err) {
      console.warn("[Audio] Error playing audio chunk:", err);
    }
  }
}
