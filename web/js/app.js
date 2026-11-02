/**
 * OpenDesk Web Client Main Application
 * Connects to Relay Server, manages P2P/Relay sessions, UI state, and coordinates sub-controllers.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const connectionBadge = document.getElementById("connectionBadge");
  const myClientIdDisplay = document.getElementById("myClientIdDisplay");
  const targetIdInput = document.getElementById("targetIdInput");
  const targetPasswordInput = document.getElementById("targetPasswordInput");
  const btnConnect = document.getElementById("btnConnect");
  const connectError = document.getElementById("connectError");
  
  const connectScreen = document.getElementById("connectScreen");
  const viewportScreen = document.getElementById("viewportScreen");
  const sessionStats = document.getElementById("sessionStats");
  const sessionActions = document.getElementById("sessionActions");
  const remoteCanvas = document.getElementById("remoteCanvas");
  
  const btnDisconnect = document.getElementById("btnDisconnect");
  const btnFullscreen = document.getElementById("btnFullscreen");
  const btnVoiceToggle = document.getElementById("btnVoiceToggle");
  const btnFiles = document.getElementById("btnFiles");
  const btnClipboard = document.getElementById("btnClipboard");
  
  const fileModal = document.getElementById("fileModal");
  const btnCloseFileModal = document.getElementById("btnCloseFileModal");
  const btnFileUp = document.getElementById("btnFileUp");
  const btnFileRefresh = document.getElementById("btnFileRefresh");
  const fileUploadZone = document.getElementById("fileUploadZone");
  const filePickerInput = document.getElementById("filePickerInput");
  const btnTriggerUpload = document.getElementById("btnTriggerUpload");

  const clipboardModal = document.getElementById("clipboardModal");
  const btnCloseClipModal = document.getElementById("btnCloseClipModal");
  const clipboardTextarea = document.getElementById("clipboardTextarea");
  const btnSendClipboard = document.getElementById("btnSendClipboard");
  const btnCopyLocal = document.getElementById("btnCopyLocal");
  
  const statLatency = document.getElementById("statLatency");
  const statMode = document.getElementById("statMode");

  // State
  let ws = null;
  let myClientId = null;
  let activeTargetId = null;
  let inSession = false;
  let pingInterval = null;
  let lastPingTime = 0;
  let rttMs = 0;
  let sessionId = null;
  let videoChain = Promise.resolve();

  // Initialize Sub-Controllers
  const renderer = new RemoteRenderer(remoteCanvas);
  
  function sendPacket(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (data.type === 'audio_chunk' && ws.bufferedAmount > 128*1024) return;
      if (typeof data === "object") {
        data.timestamp = Date.now();
        ws.send(JSON.stringify(data));
      } else {
        ws.send(data);
      }
    }
  }

  const inputHandler = new InputHandler(remoteCanvas, sendPacket);
  const fileManager = new FileTransferManager(sendPacket);
  const voiceChat = new WebAudioVoiceChat(sendPacket);

  voiceChat.onStateChange = (state) => {
    if (!btnVoiceToggle) return;
    if (state === "active") {
      btnVoiceToggle.textContent = "🎙️ Voice: ON";
      btnVoiceToggle.className = "btn-icon btn-voice-active";
      btnVoiceToggle.title = "Microphone is Active. Click to Mute, Right-Click to Turn Off.";
    } else if (state === "muted") {
      btnVoiceToggle.textContent = "🔇 Mic: Muted";
      btnVoiceToggle.className = "btn-icon btn-voice-muted";
      btnVoiceToggle.title = "Microphone is Muted. Click to Unmute, Right-Click to Turn Off.";
    } else {
      btnVoiceToggle.textContent = "🎙️ Voice: Off";
      btnVoiceToggle.className = "btn-icon";
      btnVoiceToggle.title = "Click to Start Voice Call (WhatsApp Style)";
    }
  };

  // --- WebSocket Connection to Relay Server ---
  function connectToRelay() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${location.host}/ws`;

    ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      connectionBadge.textContent = "Online";
      connectionBadge.className = "badge badge-online";

      // Register as client
      sendPacket({
        type: "register",
        payload: { role: "client", protocol: 2 }
      });

      // Start ping loop for RTT measurement
      if (pingInterval) clearInterval(pingInterval);
      pingInterval = setInterval(() => {
        if (inSession && ws && ws.readyState === WebSocket.OPEN) {
          lastPingTime = performance.now();
          sendPacket({ type: "heartbeat", payload: {} });
        }
      }, 2000);
    };

    ws.onmessage = (event) => {
      try {
        let msg;
        if(event.data instanceof ArrayBuffer) {
          msg=OpenDeskWire.decode(event.data);
        } else msg=JSON.parse(event.data);
        handleMessage(msg).catch(console.error);
      } catch (err) {
        console.error("Message parse error:", err);
      }
    };

    ws.onclose = () => {
      connectionBadge.textContent = "Offline";
      connectionBadge.className = "badge badge-offline";
      if (myClientIdDisplay) myClientIdDisplay.textContent = "Disconnected";
      if (inSession) endSession("Connection to relay lost.");
      setTimeout(connectToRelay, 3000);
    };

    ws.onerror = (err) => {
      console.warn("Relay connection error:", err);
    };
  }

  // --- Packet Handling ---
  async function handleMessage(msg) {
    const type = msg.type;
    const payload = msg.payload || {};

    if (['video_full','video_delta','audio_chunk','clipboard_text'].includes(type) &&
        (!inSession || payload.session_id !== sessionId)) return;
    switch (type) {
      case 'auth_challenge': {
        try {
          const proof=await OpenDeskWire.passwordProof(targetPasswordInput.value,payload);
          sendPacket({type:'connect',payload:{target_id:payload.target_id,proof}});
        } catch(error) { showError('Secure password authentication requires HTTPS or localhost. '+error.message); }
        break;
      }
      case "register_resp":
        myClientId = payload.id;
        if (myClientIdDisplay) {
          myClientIdDisplay.textContent = myClientId;
        }
        break;

      case "connect_resp":
        if (payload.status === "ok") {
          sessionId = payload.session_id;
          startSession(payload.target_id, payload.permissions);
        } else if (payload.status === 'waiting_approval') {
          showError('Waiting for the host to approve this connection...');
        } else {
          showError(payload.message || "Failed to connect to remote desk.");
        }
        break;

      case "session_end":
        endSession(payload.message || "Remote host closed the session.");
        break;

      case "heartbeat":
        if (lastPingTime > 0) {
          const rtt = Math.round(performance.now() - lastPingTime);
          rttMs = rtt;
          if (statLatency) statLatency.textContent = rtt + "ms";
        }
        break;

      case 'video_full':
      case 'video_delta': {
        const expected=sessionId;
        videoChain=videoChain.then(async()=>{
          if(expected!==sessionId || !inSession) return;
          await renderer.renderPacket(msg);
          sendPacket({type:'video_ack',payload:{frame_id:payload.frame_id,rtt_ms:rttMs}});
        }).catch(error=>{
          console.warn(error);
          if(expected===sessionId) sendPacket({type:'video_refresh',payload:{}});
        });
        break;
      }

      case "clipboard_text":
        const clipText = payload.text || "";
        if (clipboardTextarea) {
          clipboardTextarea.value = clipText;
        }
        if (clipText && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(clipText).catch(() => {});
        }
        break;

      case "file_list_resp":
        fileManager.handleListResponse(payload);
        break;

      case 'file_error':
        showError(payload.message || 'File transfer failed.');
        fileManager.activeUpload = fileManager.activeDownload = null;
        fileManager._hideProgress();
        break;
      case "file_chunk":
        fileManager.handleFileChunk(payload);
        break;

      case "audio_chunk":
        if (voiceChat) {
          voiceChat.playChunk(payload.data, payload.sample_rate);
        }
        break;
    }
  }

  // --- Session Lifecycle ---
  function startSession(targetId, permissions = {}) {
    renderer.reset();
    document.getElementById('streamProfile').value='Balanced';
    sendPacket({type:'video_config',payload:{fps:30,max_width:1600,quality:65}});
    btnFiles.disabled = !permissions.file_transfer;
    btnClipboard.disabled = !permissions.clipboard;
    btnVoiceToggle.disabled = !permissions.audio;
    inSession = true;
    activeTargetId = targetId;
    hideError();

    // Prepare audio playback
    if (voiceChat) {
      voiceChat.initSpeaker();
    }

    connectScreen.style.display = "none";
    viewportScreen.style.display = "flex";
    sessionStats.style.display = "flex";
    sessionActions.style.display = "flex";

    remoteCanvas.focus();
    inputHandler.enabled = permissions.input === true;
    if (statMode) statMode.textContent = "Relay/Direct";
  }

  function endSession(reason) {
    inSession = false;
    sessionId = null;
    renderer.reset();
    activeTargetId = null;
    inputHandler.enabled = false;
    if (voiceChat) {
      voiceChat.stop();
    }

    connectScreen.style.display = "flex";
    viewportScreen.style.display = "none";
    sessionStats.style.display = "none";
    sessionActions.style.display = "none";

    fileModal.style.display = "none";
    clipboardModal.style.display = "none";

    if (reason) {
      showError(reason);
    }
  }

  function showError(msg) {
    if (connectError) {
      connectError.textContent = msg;
      connectError.style.display = "block";
    }
  }

  function hideError() {
    if (connectError) {
      connectError.style.display = "none";
    }
  }

  // User gesture listener to automatically unlock Web Audio API playback
  const unlockAudio = () => {
    if (voiceChat) voiceChat.resumeContext();
  };
  window.addEventListener("click", unlockAudio, { passive: true });
  window.addEventListener("keydown", unlockAudio, { passive: true });
  window.addEventListener("touchstart", unlockAudio, { passive: true });

  // --- Event Listeners ---
  btnConnect.addEventListener("click", async () => {
    unlockAudio();
    const rawTarget = targetIdInput.value.replace(/[\s-]/g, "").trim();
    if (!rawTarget) {
      showError("Please enter a valid remote OpenDesk ID.");
      return;
    }
    hideError();

    sendPacket({
      type: "connect",
      payload: {
        target_id: rawTarget
      }
    });
  });

  targetIdInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") btnConnect.click();
  });

  btnDisconnect.addEventListener("click", () => {
    sendPacket({ type: "session_end", payload: {} });
    endSession("Session disconnected by user.");
  });

  btnFullscreen.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      viewportScreen.requestFullscreen().catch(err => console.warn(err));
    } else {
      document.exitFullscreen().catch(err => console.warn(err));
    }
  });

  // Real-Time Voice Communication Toggle (WhatsApp-style call)
  if (btnVoiceToggle) {
    btnVoiceToggle.addEventListener("click", () => {
      if (!voiceChat.isActive) {
        voiceChat.start();
      } else {
        voiceChat.toggleMute();
      }
    });

    btnVoiceToggle.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (voiceChat.isActive) {
        voiceChat.stop();
      }
    });
  }

  // System Shortcuts Dropdown
  document.querySelectorAll("[data-shortcut]").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const shortcut = link.dataset.shortcut;
      inputHandler.sendShortcut(shortcut);
    });
  });

  // File Manager Modal
  btnFiles.addEventListener("click", () => {
    fileModal.style.display = "flex";
    fileManager.requestList();
  });

  btnCloseFileModal.addEventListener("click", () => {
    fileModal.style.display = "none";
  });

  btnFileUp.addEventListener("click", () => {
    if (fileManager.parentPath) {
      fileManager.requestList(fileManager.parentPath);
    }
  });

  btnFileRefresh.addEventListener("click", () => {
    fileManager.requestList();
  });

  btnTriggerUpload.addEventListener("click", () => {
    filePickerInput.click();
  });

  filePickerInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      fileManager.startUpload(e.target.files[0]);
    }
  });

  // Drag and Drop Upload Zone
  fileUploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    fileUploadZone.style.borderColor = "var(--accent-color)";
  });

  fileUploadZone.addEventListener("dragleave", () => {
    fileUploadZone.style.borderColor = "var(--border-color)";
  });

  fileUploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    fileUploadZone.style.borderColor = "var(--border-color)";
    if (e.dataTransfer.files.length > 0) {
      fileManager.startUpload(e.dataTransfer.files[0]);
    }
  });

  // Clipboard Modal
  btnClipboard.addEventListener("click", () => {
    clipboardModal.style.display = "flex";
  });

  btnCloseClipModal.addEventListener("click", () => {
    clipboardModal.style.display = "none";
  });

  btnSendClipboard.addEventListener("click", () => {
    const text = clipboardTextarea.value;
    sendPacket({
      type: "clipboard_text",
      payload: { text }
    });
    alert("Clipboard pushed to host!");
  });

  btnCopyLocal.addEventListener("click", () => {
    const text = clipboardTextarea.value;
    navigator.clipboard.writeText(text).then(() => {
      alert("Copied to local clipboard!");
    }).catch(err => {
      clipboardTextarea.select();
      document.execCommand("copy");
    });
  });

  document.getElementById('streamProfile').addEventListener('change',event=>{
    const profiles={Balanced:{fps:30,max_width:1600,quality:65},
      Performance:{fps:60,max_width:1280,quality:55},Sharp:{fps:30,max_width:2560,quality:85}};
    sendPacket({type:'video_config',payload:profiles[event.target.value]});
  });

  // Start connection
  connectToRelay();

  // Auto-connect if ?connect=... URL query parameter is supplied
  const urlParams = new URLSearchParams(window.location.search);
  const autoConnectId = urlParams.get("connect");
  if (autoConnectId) {
    targetIdInput.value = autoConnectId;
    setTimeout(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        btnConnect.click();
      } else {
        setTimeout(() => btnConnect.click(), 1000);
      }
    }, 600);
  }
});
