// Native integration probe: request approval without injecting desktop input.
// Run alongside an isolated --smoke-test --smoke-minimized host.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const [url, target, evidence, mode = 'pending'] = process.argv.slice(2);
if (!url || !target || !evidence) throw Error('Usage: node tests/test_incoming.cjs ws://127.0.0.1:PORT/ws HOST_ID evidence.json [pending|cancel]');
const deadline = Date.now() + 30000;
let socket;
let requests=0;
function connect() {
  socket = new WebSocket(url);
  socket.onopen = () => socket.send(JSON.stringify({type:'register',payload:{role:'client',protocol:2}}));
  socket.onerror = () => { if (Date.now() < deadline) setTimeout(connect, 100); else process.exitCode = 1; };
  socket.onmessage = ({data}) => {
    if (typeof data !== 'string') return;
    const p = JSON.parse(data);
    if (p.type === 'register_resp' && p.payload.status === 'ok') socket.send(JSON.stringify({type:'connect',payload:{target_id:target}}));
    if (p.type === 'connect_resp' && p.payload.status === 'waiting_approval') {
      requests++;
      if(mode === 'cancel' || requests === 1){
        setTimeout(() => socket.send(JSON.stringify({type:'session_end',payload:{}})), 250);
        if(mode !== 'cancel') setTimeout(() => socket.send(JSON.stringify({type:'connect',payload:{target_id:target}})), 650);
      }
    }
  };
}
connect();
const check = setInterval(() => {
  if (fs.existsSync(evidence)) {
    clearInterval(check);
    const state = JSON.parse(fs.readFileSync(evidence, 'utf8'));
    assert.equal(state.nativeWindow.minimized, false, 'incoming request must restore the host');
    assert.equal(state.nativeWindow.topmost, mode !== 'cancel', 'topmost state must follow pending approval');
    assert.equal(Boolean(state.incoming), mode !== 'cancel');
    assert.ok(requests >= (mode === 'cancel' ? 1 : 2), 'exercise fresh request after cancellation');
    console.log(JSON.stringify({passed:true,mode,requests,window:state.nativeWindow}));
    socket.close();
    // The evidence is complete. Bound teardown even if the native host exits
    // before the WebSocket close handshake finishes.
    setTimeout(() => process.exit(0), 200);
  } else if (Date.now() > deadline) { clearInterval(check);socket.close();throw Error('No native evidence'); }
}, 100);
