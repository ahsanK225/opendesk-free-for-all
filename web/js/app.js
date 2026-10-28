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

  // Initialize Sub-Controllers
  const renderer = new RemoteRenderer(remoteCanvas);
  
  function sendPacket(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
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

    ws.onopen = () => {
      connectionBadge.textContent = "Online";
      connectionBadge.className = "badge badge-online";

      // Register as client
      sendPacket({
        type: "register",
        payload: { role: "client" }
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
        const msg = JSON.parse(event.data);
        handleMessage(msg);
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
  function handleMessage(msg) {
    const type = msg.type;
    const payload = msg.payload || {};

    switch (type) {
      case "register_resp":
        myClientId = payload.id;
        if (myClientIdDisplay) {
          myClientIdDisplay.textContent = myClientId;
        }
        break;

      case "connect_resp":
        if (payload.status === "ok") {
          startSession(payload.target_id);
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
          if (statLatency) statLatency.textContent = rtt + "ms";
        }
        break;

      case "video_full":
        renderer.renderFullFrame(payload.width, payload.height, payload.image);
        break;

      case "video_delta":
        renderer.renderDeltaFrame(payload.width, payload.height, payload.tiles);
        break;

      case "clipboard_text":
        if (clipboardTextarea) {
          clipboardTextarea.value = payload.text || "";
        }
        break;

      case "file_list_resp":
        fileManager.handleListResponse(payload);
        break;

      case "file_chunk":
        fileManager.handleFileChunk(payload);
        break;

      case "audio_chunk":
        if (voiceChat) {
          voiceChat.playChunk(payload.data);
        }
        break;
    }
  }

  // --- Session Lifecycle ---
  function startSession(targetId) {
    inSession = true;
    activeTargetId = targetId;
    hideError();

    connectScreen.style.display = "none";
    viewportScreen.style.display = "flex";
    sessionStats.style.display = "flex";
    sessionActions.style.display = "flex";

    remoteCanvas.focus();
    inputHandler.enabled = true;
    if (statMode) statMode.textContent = "Relay/Direct";
  }

  function endSession(reason) {
    inSession = false;
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

  // --- Event Listeners ---
  btnConnect.addEventListener("click", () => {
    const rawTarget = targetIdInput.value.trim();
    if (!rawTarget) {
      showError("Please enter a valid remote OpenDesk ID.");
      return;
    }
    hideError();
    sendPacket({
      type: "connect",
      payload: {
        target_id: rawTarget,
        password: targetPasswordInput.value
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
