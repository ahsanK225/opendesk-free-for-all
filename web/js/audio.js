/** Explicit-rate 20ms PCM voice with browser AEC and bounded playback latency. */
class WebAudioVoiceChat {
  constructor(sendPacket) {
    this.sendPacket = sendPacket;
    this.audioCtx = null;
    this.isActive = false;
    this.isMuted = false;
    this.nextPlayTime = 0;
    this.sources = new Set();
  }
  _ensureAudioContext() {
    if (!this.audioCtx) this.audioCtx = new AudioContext({sampleRate:48000, latencyHint:"interactive"});
    this.resumeContext();
  }
  resumeContext() {
    if (this.audioCtx?.state === "suspended") this.audioCtx.resume().catch(()=>{});
  }
  initSpeaker() { this._ensureAudioContext(); }
  async start() {
    if (this.isActive || this.starting) return;
    this.starting = true;
    try {
      this._ensureAudioContext();
      this.mediaStream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,
        echoCancellation:true, noiseSuppression:true, autoGainControl:true}, video:false});
      if (!this.starting) { this.mediaStream.getTracks().forEach(t=>t.stop()); return; }
      if (!this.workletLoaded) {
        await this.audioCtx.audioWorklet.addModule('/js/audio-worklet.js');
        this.workletLoaded = true;
      }
      this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
      this.processorNode = new AudioWorkletNode(this.audioCtx, 'voice-capture');
      this.processorNode.port.onmessage = ({data}) => {
        if (!this.isActive || this.isMuted) return;
        const bytes = new Uint8Array(data);
        let text = '';
        for (const byte of bytes) text += String.fromCharCode(byte);
        this.sendPacket({type:'audio_chunk',payload:{data:btoa(text),
          sample_rate:this.audioCtx.sampleRate,channels:1,format:'pcm_s16le'}});
      };
      this.sourceNode.connect(this.processorNode);
      this.processorNode.connect(this.audioCtx.destination); // worklet outputs silence
      this.isActive = true;
      this.isMuted = false;
      this.onStateChange?.('active');
    } catch(error) {
      this.stop();
      alert('Microphone could not start: '+error.message);
    } finally { this.starting = false; }
  }
  toggleMute() {
    this.isMuted = !this.isMuted;
    this.onStateChange?.(this.isMuted?'muted':'active');
  }
  stop() {
    this.starting = false;
    this.isActive = false;
    this.isMuted = false;
    if (this.processorNode) { this.processorNode.port.onmessage=null; this.processorNode.disconnect(); }
    this.sourceNode?.disconnect();
    this.mediaStream?.getTracks().forEach(t=>t.stop());
    this.processorNode=this.sourceNode=this.mediaStream=null;
    for (const source of this.sources) { try { source.stop(); } catch {} }
    this.sources.clear();
    this.nextPlayTime=0;
    this.onStateChange?.('off');
  }
  playChunk(data, rate=48000) {
    if (![8000,16000,24000,44100,48000].includes(rate)) return;
    try {
      this._ensureAudioContext();
      const binary=atob(data);
      if (binary.length%2 || binary.length>rate*2/5) return;
      const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
      const pcm=new DataView(bytes.buffer);
      const buffer=this.audioCtx.createBuffer(1,bytes.length/2,rate);
      const samples=buffer.getChannelData(0);
      for(let i=0;i<samples.length;i++) samples[i]=pcm.getInt16(i*2,true)/32768;
      const now=this.audioCtx.currentTime;
      if(this.nextPlayTime>now+.12) return; // discard stale audio, never overlap it
      if(this.nextPlayTime<now) this.nextPlayTime=now+.035;
      const source=this.audioCtx.createBufferSource();
      source.buffer=buffer;
      source.connect(this.audioCtx.destination);
      this.sources.add(source);
      source.onended=()=>this.sources.delete(source);
      source.start(this.nextPlayTime);
      this.nextPlayTime+=buffer.duration;
    } catch(error) { console.warn('Invalid voice block',error); }
  }
}
