/** Strict binary video envelope and interoperable password proof. */
class OpenDeskWire {
  static decode(buffer) {
    const bytes=new Uint8Array(buffer);
    if(bytes.length<8 || new TextDecoder().decode(bytes.slice(0,4))!=='ODV2') throw Error('Invalid video magic');
    const size=new DataView(buffer).getUint32(4);
    if(!size || size>65536 || 8+size>bytes.length) throw Error('Invalid video header');
    const message=JSON.parse(new TextDecoder().decode(bytes.slice(8,8+size)));
    const p=message.payload;
    if(!['video_full','video_delta'].includes(message.type) || !p ||
      !Number.isInteger(p.width) || !Number.isInteger(p.height) || p.width<=0 || p.height<=0 ||
      p.width>16384 || p.height>16384 || !Array.isArray(p.tiles) || p.tiles.length>4096)
      throw Error('Invalid video metadata');
    for(const tile of p.tiles) {
      if(!Number.isInteger(tile.offset) || !Number.isInteger(tile.length) || tile.offset<0 ||
         tile.length<=0 || 8+size+tile.offset+tile.length>bytes.length) throw Error('Invalid image range');
      tile.image=bytes.slice(8+size+tile.offset,8+size+tile.offset+tile.length);
    }
    if(message.type==='video_full') {
      if(p.tiles.length!==1) throw Error('Invalid keyframe');
      p.image=p.tiles[0].image;
    }
    return message;
  }
  static async passwordProof(password, challenge) {
    const iterations=challenge.iterations;
    if(!Number.isInteger(iterations) || iterations<100000 || iterations>600000) throw Error('Invalid authentication parameters');
    const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);
    const bits=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',
      salt:Uint8Array.from(atob(challenge.salt),c=>c.charCodeAt(0)),iterations},key,256);
    const hmac=await crypto.subtle.importKey('raw',bits,{name:'HMAC',hash:'SHA-256'},false,['sign']);
    const signature=await crypto.subtle.sign('HMAC',hmac,new TextEncoder().encode(challenge.nonce));
    return Array.from(new Uint8Array(signature),b=>b.toString(16).padStart(2,'0')).join('');
  }
}
