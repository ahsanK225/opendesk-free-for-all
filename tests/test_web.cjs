const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
global.crypto=crypto.webcrypto;
vm.runInThisContext(fs.readFileSync('web/js/protocol.js','utf8'));
vm.runInThisContext(fs.readFileSync('web/js/audio.js','utf8'));

async function main() {
  const challenge={salt:Buffer.from('0123456789abcdef').toString('base64'),iterations:210000,nonce:'test-nonce'};
  const proof=await OpenDeskWire.passwordProof('test password',challenge);
  const key=crypto.pbkdf2Sync('test password',Buffer.from(challenge.salt,'base64'),210000,32,'sha256');
  assert.equal(proof,crypto.createHmac('sha256',key).update(challenge.nonce).digest('hex'));
  await assert.rejects(OpenDeskWire.passwordProof('test',{...challenge,iterations:999999999}));
  const header=Buffer.from(JSON.stringify({type:'video_full',payload:{width:2,height:2,frame_id:1,
    tiles:[{offset:0,length:4}],session_id:'test'}}));
  const length=Buffer.alloc(4); length.writeUInt32BE(header.length);
  const packet=Buffer.concat([Buffer.from('ODV2'),length,header,Buffer.from('jpeg')]);
  const decoded=OpenDeskWire.decode(packet.buffer.slice(packet.byteOffset,packet.byteOffset+packet.length));
  assert.equal(Buffer.from(decoded.payload.image).toString(),'jpeg');
  assert.throws(()=>OpenDeskWire.decode(new ArrayBuffer(3)));
  const voice=new WebAudioVoiceChat(()=>{});
  let scheduled;
  voice.audioCtx={currentTime:0,state:'running',destination:{},
    createBuffer(channels,count,rate) { scheduled={count,rate,duration:count/rate};
      return {duration:count/rate,getChannelData:()=>new Float32Array(count)}; },
    createBufferSource(){return {connect(){},start(){},stop(){}}}};
  voice.playChunk(Buffer.alloc(960*2).toString('base64'),48000);
  assert.equal(scheduled.rate,48000);
  assert.equal(scheduled.duration,.02);
  voice.stop();
  assert.equal(voice.sources.size,0);
  console.log('Web protocol/password/audio regression checks passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
