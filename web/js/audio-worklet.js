class VoiceCapture extends AudioWorkletProcessor {
  constructor() { super(); this.block = new Int16Array(Math.round(sampleRate*.02)); this.offset=0; }
  process(inputs, outputs) {
    const input=inputs[0]?.[0];
    if(input) for(const value of input) {
      this.block[this.offset++]=Math.round(Math.max(-1,Math.min(1,value))*32767);
      if(this.offset===this.block.length) {
        this.port.postMessage(this.block.buffer,[this.block.buffer]);
        this.block=new Int16Array(Math.round(sampleRate*.02)); this.offset=0;
      }
    }
    return true;
  }
}
registerProcessor('voice-capture',VoiceCapture);
