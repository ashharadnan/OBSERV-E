const ROBOT_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const ROBOT_SPEECH_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214";
const ROBOT_COMMAND_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214";
const ROBOT_STATUS_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214";

const els = {
  browserStatus: document.getElementById("browserStatus"),
  transportStatus: document.getElementById("transportStatus"),
  connectionStatus: document.getElementById("connectionStatus"),
  audioStatus: document.getElementById("audioStatus"),
  supportBanner: document.getElementById("supportBanner"),
  diagnosticText: document.getElementById("diagnosticText"),
  connectBluetoothButton: document.getElementById("connectBluetoothButton"),
  connectSerialButton: document.getElementById("connectSerialButton"),
  connectBridgeButton: document.getElementById("connectBridgeButton"),
  reconnectButton: document.getElementById("reconnectButton"),
  disconnectButton: document.getElementById("disconnectButton"),
  stopAudioButton: document.getElementById("stopAudioButton"),
  speakAgainButton: document.getElementById("speakAgainButton"),
  liveSpeech: document.getElementById("liveSpeech"),
  queueList: document.getElementById("queueList"),
  queueCount: document.getElementById("queueCount"),
  transcriptList: document.getElementById("transcriptList"),
  clearTranscriptButton: document.getElementById("clearTranscriptButton"),
  copyTranscriptButton: document.getElementById("copyTranscriptButton"),
  manualTextInput: document.getElementById("manualTextInput"),
  manualNormalButton: document.getElementById("manualNormalButton"),
  manualUrgentButton: document.getElementById("manualUrgentButton"),
  sendRobotAckButton: document.getElementById("sendRobotAckButton"),
  voiceIdInput: document.getElementById("voiceIdInput"),
  modelIdInput: document.getElementById("modelIdInput"),
  devicePrefixInput: document.getElementById("devicePrefixInput"),
  cooldownInput: document.getElementById("cooldownInput"),
  serialBaudInput: document.getElementById("serialBaudInput"),
  bridgeUrlInput: document.getElementById("bridgeUrlInput")
};

const state = {
  config: null,
  device: null,
  server: null,
  speechChar: null,
  commandChar: null,
  statusChar: null,
  serialPort: null,
  serialReader: null,
  serialWriter: null,
  serialKeepReading: false,
  eventSource: null,
  queue: [],
  audio: null,
  speaking: false,
  resolvePlayback: null,
  lastSpokenText: "",
  transcript: [],
  seenTextAt: new Map(),
  wakeLock: null,
  audioUnlocked: false,
  bluetoothAvailability: null,
  transport: null,
  serialReadBuffer: "",
  supports: {
    bluetooth: false,
    serial: false,
    secure: false
  }
};

function setPill(el, text, mode) {
  el.textContent = text;
  el.className = `pill ${mode}`;
}

function setSupportBanner(text, mode = "muted") {
  els.supportBanner.textContent = text;
  els.supportBanner.className = `support-banner ${mode}`;
}

function setDiagnostic(text) {
  els.diagnosticText.textContent = text;
}

function nowString(ts = Date.now()) {
  return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeText(text) {
  return String(text || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function appendTranscript(item) {
  state.transcript.unshift(item);
  if (state.transcript.length > 150) {
    state.transcript.length = 150;
  }
  renderTranscript();
}

function renderTranscript() {
  els.transcriptList.innerHTML = "";
  for (const item of state.transcript) {
    const li = document.createElement("li");
    li.className = `priority-${item.priority || "normal"}`;
    li.innerHTML = `
      <div class="transcript-meta">
        <span>${escapeHtml(item.source || "System")}</span>
        <span>${nowString(item.ts)}</span>
      </div>
      <div class="transcript-text">${escapeHtml(item.text)}</div>
    `;
    els.transcriptList.appendChild(li);
  }
}

function renderQueue() {
  els.queueList.innerHTML = "";
  for (const item of state.queue) {
    const li = document.createElement("li");
    li.className = `priority-${item.priority || "normal"}`;
    li.innerHTML = `
      <div class="transcript-meta">
        <span>${escapeHtml(item.eventType || "robot update")}</span>
        <span>${escapeHtml(item.priority || "normal")}</span>
      </div>
      <div class="transcript-text">${escapeHtml(item.text)}</div>
    `;
    els.queueList.appendChild(li);
  }
  els.queueCount.textContent = `${state.queue.length} item${state.queue.length === 1 ? "" : "s"}`;
}

function updateLiveSpeech(text) {
  els.liveSpeech.textContent = text || "Waiting for robot speech…";
}

function setTransport(mode, text, pillMode = "muted") {
  state.transport = mode;
  setPill(els.transportStatus, text, pillMode);
}

function shouldSpeakMessage(message) {
  const normalized = normalizeText(message.text);
  if (!normalized) {
    return false;
  }
  const cooldownMs = Number(els.cooldownInput.value || 7000);
  const seenAt = state.seenTextAt.get(normalized) || 0;
  if ((Date.now() - seenAt) < cooldownMs) {
    return false;
  }
  state.seenTextAt.set(normalized, Date.now());
  return true;
}

function isUrgent(message) {
  return (message.priority || "normal") === "urgent";
}

function pruneQueueForFreshness() {
  const now = Date.now();
  state.queue = state.queue.filter((item) => {
    if (isUrgent(item)) {
      return true;
    }
    return (now - (item.ts || now)) < 8000;
  });
}

function enqueueMessage(message) {
  if (!shouldSpeakMessage(message)) {
    appendTranscript({
      text: `Skipped repeat: ${message.text}`,
      source: "Queue manager",
      priority: "low",
      ts: Date.now()
    });
    return;
  }

  if (isUrgent(message)) {
    state.queue = state.queue.filter((item) => isUrgent(item));
    state.queue.unshift(message);
    if (state.audio && !state.audio.paused) {
      state.audio.pause();
      state.speaking = false;
      setPill(els.audioStatus, "Urgent update interrupted the previous line", "warn");
      if (state.resolvePlayback) {
        state.resolvePlayback();
        state.resolvePlayback = null;
      }
    }
  } else {
    pruneQueueForFreshness();
    state.queue.push(message);
  }

  updateLiveSpeech(message.text);
  appendTranscript({
    text: message.text,
    source: `Queued from ${message.source || "robot"}`,
    priority: message.priority || "normal",
    ts: Date.now()
  });
  renderQueue();
  processQueue().catch((error) => {
    console.error(error);
  });
}

async function loadConfig() {
  const res = await fetch("/api/config", { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Could not load server config.");
  }
  state.config = await res.json();
  els.voiceIdInput.value = state.config.defaultVoiceId;
  els.modelIdInput.value = state.config.defaultModelId;
  els.bridgeUrlInput.value = state.config.defaultBridgeUrl || "/api/events";
  setSupportBanner("Ready. Choose Bluetooth, USB, or bridge mode.", "ok");
}

async function requestTtsStreamUrl(message) {
  const res = await fetch("/api/tts-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: message.text,
      priority: message.priority || "normal",
      voiceId: els.voiceIdInput.value.trim(),
      modelId: els.modelIdInput.value.trim()
    })
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.url) {
    throw new Error(data.error || "Could not create TTS session.");
  }
  return data.url;
}

async function unlockAudio() {
  if (state.audioUnlocked) {
    return;
  }

  const audio = new Audio();
  audio.muted = true;
  audio.playsInline = true;
  try {
    await audio.play().catch(() => {});
  } catch {
  }
  audio.pause();
  state.audioUnlocked = true;
  appendTranscript({
    text: "Audio output unlocked for this session.",
    source: "System",
    priority: "low",
    ts: Date.now()
  });
}

async function playAudioFromUrl(url) {
  if (state.audio) {
    state.audio.pause();
  }

  state.audio = new Audio(url);
  state.audio.preload = "auto";
  state.audio.playsInline = true;

  await new Promise((resolve, reject) => {
    state.resolvePlayback = resolve;
    state.audio.addEventListener("ended", () => {
      state.resolvePlayback = null;
      resolve();
    }, { once: true });
    state.audio.addEventListener("error", () => {
      state.resolvePlayback = null;
      reject(new Error("Could not play audio."));
    }, { once: true });
    state.audio.play().catch((error) => {
      state.resolvePlayback = null;
      reject(error);
    });
  });
}

async function processQueue() {
  if (state.speaking || !state.queue.length) {
    return;
  }

  const message = state.queue.shift();
  renderQueue();
  state.speaking = true;
  state.lastSpokenText = message.text;
  els.speakAgainButton.disabled = false;
  els.stopAudioButton.disabled = false;
  setPill(els.audioStatus, `Speaking ${message.priority || "normal"} line`, isUrgent(message) ? "warn" : "ok");

  appendTranscript({
    text: message.text,
    source: "Will be spoken",
    priority: message.priority || "normal",
    ts: Date.now()
  });

  try {
    await unlockAudio();
    const url = await requestTtsStreamUrl(message);
    await playAudioFromUrl(url);
    appendTranscript({
      text: message.text,
      source: "Spoken",
      priority: message.priority || "normal",
      ts: Date.now()
    });
  } catch (error) {
    console.error(error);
    appendTranscript({
      text: `TTS failed: ${String(error.message || error)}`,
      source: "System",
      priority: "urgent",
      ts: Date.now()
    });
    setPill(els.audioStatus, "Audio error", "error");
  } finally {
    state.speaking = false;
    els.stopAudioButton.disabled = true;
    if (!state.queue.length) {
      setPill(els.audioStatus, "Audio idle", "muted");
    }
    if (state.queue.length) {
      processQueue().catch((error) => console.error(error));
    }
  }
}

function decodeTextPayload(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return null;
  }

  if (trimmed.startsWith("WEB_COMMAND:")) {
    return {
      text: trimmed,
      priority: "low",
      eventType: "robot_status",
      ts: Date.now(),
      source: "robot"
    };
  }

  try {
    const parsed = JSON.parse(trimmed);
    return {
      text: String(parsed.text || "").trim(),
      priority: parsed.priority || "normal",
      eventType: parsed.eventType || "robot_update",
      ts: parsed.ts || Date.now(),
      source: parsed.source || "robot"
    };
  } catch {
    return {
      text: trimmed,
      priority: "normal",
      eventType: "robot_update",
      ts: Date.now(),
      source: "robot"
    };
  }
}

function decodeBleMessage(view) {
  const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
  const text = new TextDecoder().decode(bytes).trim();
  return decodeTextPayload(text);
}

function handleIncomingMessage(message) {
  if (!message || !message.text) {
    return;
  }
  enqueueMessage(message);
}

function handleIncomingStatus(message) {
  if (!message || !message.text) {
    return;
  }
  appendTranscript({
    text: message.text,
    source: message.source || "Robot status",
    priority: message.priority || "low",
    ts: message.ts || Date.now()
  });
}

function getSupportSummary() {
  const parts = [];
  if (state.supports.secure) {
    parts.push("Secure context: yes.");
  } else {
    parts.push("Secure context: no.");
  }
  parts.push(`Bluetooth API: ${state.supports.bluetooth ? "present" : "missing"}.`);
  parts.push(`Web Serial API: ${state.supports.serial ? "present" : "missing"}.`);
  if (state.bluetoothAvailability === false) {
    parts.push("Bluetooth radio appears off or unavailable.");
  }
  parts.push("Bridge mode works as long as this page can reach the Node server.");
  return parts.join(" ");
}

async function refreshTransportSupport() {
  state.supports.bluetooth = Boolean(navigator.bluetooth);
  state.supports.serial = Boolean(navigator.serial);
  state.supports.secure = window.isSecureContext;

  if (state.supports.bluetooth && navigator.bluetooth.getAvailability) {
    try {
      state.bluetoothAvailability = await navigator.bluetooth.getAvailability();
    } catch {
      state.bluetoothAvailability = null;
    }
  } else {
    state.bluetoothAvailability = null;
  }

  if (!state.supports.secure) {
    setPill(els.browserStatus, "Needs localhost or HTTPS", "error");
    setSupportBanner("Open this app on localhost or HTTPS. Bridge mode is still the most compatible option.", "warn");
  } else if (state.supports.bluetooth) {
    setPill(els.browserStatus, "Bluetooth API detected", state.bluetoothAvailability === false ? "warn" : "ok");
    setSupportBanner("Bluetooth is available here. USB and bridge fallback are also ready.", "ok");
  } else if (state.supports.serial) {
    const isLinuxChrome = /Linux/i.test(navigator.userAgent) && /Chrome/i.test(navigator.userAgent) && !/Edg/i.test(navigator.userAgent);
    setPill(els.browserStatus, "Bluetooth missing, USB available", "warn");
    if (isLinuxChrome) {
      setSupportBanner("Chrome on Linux is running without Web Bluetooth. Enable chrome://flags/#enable-experimental-web-platform-features, relaunch Chrome, then reload this page.", "warn");
    } else {
      setSupportBanner("This browser instance does not expose Bluetooth. Use USB or bridge mode.", "warn");
    }
  } else {
    setPill(els.browserStatus, "Use bridge mode in this browser", "warn");
    setSupportBanner("This browser does not expose Bluetooth or USB. Connect through the bridge instead.", "warn");
  }

  els.connectBluetoothButton.disabled = !(state.supports.secure && state.supports.bluetooth);
  els.reconnectButton.disabled = !(state.supports.secure && state.supports.bluetooth && navigator.bluetooth?.getDevices);
  els.connectSerialButton.disabled = !state.supports.serial;
  els.connectBridgeButton.disabled = false;
  setDiagnostic(getSupportSummary());
}

async function getKnownDevice() {
  if (!navigator.bluetooth?.getDevices) {
    return null;
  }
  const devices = await navigator.bluetooth.getDevices();
  const prefix = (els.devicePrefixInput.value.trim() || "OBSERVE").toLowerCase();
  return devices.find((device) => String(device.name || "").toLowerCase().startsWith(prefix)) || null;
}

function clearBleListeners() {
  if (state.speechChar) {
    state.speechChar.removeEventListener("characteristicvaluechanged", onSpeechNotification);
  }
  if (state.statusChar) {
    state.statusChar.removeEventListener("characteristicvaluechanged", onStatusNotification);
  }
}

async function setupBleDevice(device) {
  clearBleListeners();
  if (state.device) {
    state.device.removeEventListener("gattserverdisconnected", handleBleDisconnect);
  }

  device.addEventListener("gattserverdisconnected", handleBleDisconnect);

  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(ROBOT_SERVICE_UUID);
  const speechChar = await service.getCharacteristic(ROBOT_SPEECH_UUID);
  const commandChar = await service.getCharacteristic(ROBOT_COMMAND_UUID);
  const statusChar = await service.getCharacteristic(ROBOT_STATUS_UUID);

  await speechChar.startNotifications();
  speechChar.addEventListener("characteristicvaluechanged", onSpeechNotification);

  await statusChar.startNotifications();
  statusChar.addEventListener("characteristicvaluechanged", onStatusNotification);

  state.device = device;
  state.server = server;
  state.speechChar = speechChar;
  state.commandChar = commandChar;
  state.statusChar = statusChar;

  setTransport("bluetooth", "Bluetooth direct", "ok");
  els.disconnectButton.disabled = false;
  els.sendRobotAckButton.disabled = false;
  setPill(els.connectionStatus, `Connected to ${device.name || "robot"}`, "ok");
  appendTranscript({ text: `Connected to ${device.name || "robot"} over Bluetooth.`, source: "System", priority: "normal", ts: Date.now() });
}

async function connectBluetooth() {
  const namePrefix = els.devicePrefixInput.value.trim() || "OBSERVE";
  const device = await navigator.bluetooth.requestDevice({
    filters: [{ namePrefix, services: [ROBOT_SERVICE_UUID] }],
    optionalServices: [ROBOT_SERVICE_UUID]
  });
  await disconnectTransport(false);
  await setupBleDevice(device);
}

async function reconnectKnownRobot() {
  const device = await getKnownDevice();
  if (!device) {
    throw new Error("No previously granted OBSERVE robot was found for this browser. Use Connect with Bluetooth first.");
  }
  await disconnectTransport(false);
  await setupBleDevice(device);
}

function handleBleDisconnect() {
  appendTranscript({ text: "Bluetooth robot disconnected.", source: "System", priority: "urgent", ts: Date.now() });
  state.device = null;
  state.server = null;
  state.speechChar = null;
  state.commandChar = null;
  state.statusChar = null;
  els.sendRobotAckButton.disabled = true;
  els.disconnectButton.disabled = true;
  setPill(els.connectionStatus, "Robot disconnected", "warn");
  if (state.transport === "bluetooth") {
    setTransport(null, "No transport selected", "muted");
  }
}

function onSpeechNotification(event) {
  handleIncomingMessage(decodeBleMessage(event.target.value));
}

function onStatusNotification(event) {
  handleIncomingStatus(decodeBleMessage(event.target.value));
}

async function connectSerial() {
  if (!navigator.serial) {
    throw new Error("Web Serial is not available in this browser.");
  }
  await disconnectTransport(false);
  const port = await navigator.serial.requestPort();
  const baudRate = Number(els.serialBaudInput.value || 115200);
  await port.open({ baudRate, bufferSize: 4096 });
  state.serialPort = port;
  state.serialKeepReading = true;
  setTransport("serial", "USB serial direct", "ok");
  els.disconnectButton.disabled = false;
  els.sendRobotAckButton.disabled = false;
  setPill(els.connectionStatus, "Connected over USB serial", "ok");
  appendTranscript({ text: `Connected over USB serial at ${baudRate} baud.`, source: "System", priority: "normal", ts: Date.now() });
  startSerialReadLoop().catch((error) => {
    console.error(error);
    appendTranscript({ text: `USB serial error: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
  });
}

async function startSerialReadLoop() {
  if (!state.serialPort?.readable) {
    return;
  }
  const decoder = new TextDecoder();
  state.serialReader = state.serialPort.readable.getReader();
  state.serialReadBuffer = "";
  try {
    while (state.serialKeepReading) {
      const { value, done } = await state.serialReader.read();
      if (done) {
        break;
      }
      state.serialReadBuffer += decoder.decode(value, { stream: true });
      let newlineIndex = state.serialReadBuffer.indexOf("\n");
      while (newlineIndex >= 0) {
        const line = state.serialReadBuffer.slice(0, newlineIndex).replace(/\r/g, "").trim();
        state.serialReadBuffer = state.serialReadBuffer.slice(newlineIndex + 1);
        if (line) {
          const parsed = decodeTextPayload(line);
          if (parsed?.eventType === "robot_status" || /^OBSERVE-|BLE ready|Central /.test(line)) {
            handleIncomingStatus(parsed || { text: line, source: "Robot status", priority: "low", ts: Date.now() });
          } else {
            handleIncomingMessage(parsed);
          }
        }
        newlineIndex = state.serialReadBuffer.indexOf("\n");
      }
    }
  } finally {
    if (state.serialReader) {
      await state.serialReader.cancel().catch(() => {});
      state.serialReader.releaseLock();
      state.serialReader = null;
    }
  }
}

async function connectBridge() {
  await disconnectTransport(false);
  const url = els.bridgeUrlInput.value.trim() || "/api/events";
  const eventSource = new EventSource(url);
  state.eventSource = eventSource;
  setTransport("bridge", "Bridge stream", "ok");
  els.disconnectButton.disabled = false;
  els.sendRobotAckButton.disabled = false;
  setPill(els.connectionStatus, "Connecting to bridge…", "warn");

  eventSource.addEventListener("open", () => {
    setPill(els.connectionStatus, "Connected to bridge", "ok");
    appendTranscript({ text: "Connected to the live bridge.", source: "System", priority: "normal", ts: Date.now() });
  });

  eventSource.addEventListener("robot_message", (event) => {
    const message = JSON.parse(event.data);
    handleIncomingMessage(message);
  });

  eventSource.addEventListener("robot_status", (event) => {
    const message = JSON.parse(event.data);
    handleIncomingStatus(message);
  });

  eventSource.addEventListener("hello", (event) => {
    const message = JSON.parse(event.data);
    handleIncomingStatus({ text: message.text || "Bridge connected.", source: "Bridge", priority: "low", ts: Date.now() });
  });

  eventSource.onerror = () => {
    setPill(els.connectionStatus, "Bridge connection lost", "warn");
  };
}

async function disconnectTransport(updateTranscript = true) {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }

  if (state.serialWriter) {
    state.serialWriter.releaseLock();
    state.serialWriter = null;
  }

  if (state.serialReader) {
    state.serialKeepReading = false;
    await state.serialReader.cancel().catch(() => {});
    state.serialReader.releaseLock();
    state.serialReader = null;
  }

  if (state.serialPort) {
    await state.serialPort.close().catch(() => {});
    state.serialPort = null;
  }

  clearBleListeners();
  if (state.device?.gatt?.connected) {
    try {
      state.device.gatt.disconnect();
    } catch {
    }
  }
  state.device = null;
  state.server = null;
  state.speechChar = null;
  state.commandChar = null;
  state.statusChar = null;

  setTransport(null, "No transport selected", "muted");
  setPill(els.connectionStatus, "Robot not connected", "muted");
  els.disconnectButton.disabled = true;
  els.sendRobotAckButton.disabled = true;

  if (updateTranscript) {
    appendTranscript({ text: "Disconnected from the current transport.", source: "System", priority: "low", ts: Date.now() });
  }
}

async function sendRobotCommand(payload) {
  if (state.transport === "bluetooth") {
    if (!state.commandChar) {
      throw new Error("Robot is not connected over Bluetooth.");
    }
    const data = new TextEncoder().encode(JSON.stringify(payload));
    await state.commandChar.writeValue(data);
    return;
  }

  if (state.transport === "serial") {
    if (!state.serialPort?.writable) {
      throw new Error("Robot is not connected over USB serial.");
    }
    const writer = state.serialPort.writable.getWriter();
    await writer.write(new TextEncoder().encode(`${JSON.stringify(payload)}\n`));
    writer.releaseLock();
    return;
  }

  if (state.transport === "bridge") {
    const res = await fetch("/api/robot-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || "Could not send command to bridge.");
    }
    return;
  }

  throw new Error("No robot transport is connected.");
}

function manualSpeak(priority) {
  const text = els.manualTextInput.value.trim();
  if (!text) {
    return;
  }
  enqueueMessage({
    text,
    priority,
    eventType: "manual_test",
    ts: Date.now(),
    source: "manual"
  });
}

function copyTranscript() {
  const text = state.transcript
    .slice()
    .reverse()
    .map((item) => `[${nowString(item.ts)}] ${item.source}: ${item.text}`)
    .join("\n");
  navigator.clipboard.writeText(text).then(() => {
    appendTranscript({ text: "Transcript copied.", source: "System", priority: "low", ts: Date.now() });
  }).catch((error) => {
    appendTranscript({ text: `Copy failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
  });
}

function stopAudio() {
  if (state.audio) {
    state.audio.pause();
    if (state.resolvePlayback) {
      state.resolvePlayback();
      state.resolvePlayback = null;
    }
    state.speaking = false;
    setPill(els.audioStatus, "Audio stopped", "warn");
    els.stopAudioButton.disabled = true;
    if (state.queue.length) {
      processQueue().catch((error) => console.error(error));
    }
  }
}

async function requestWakeLock() {
  if (!("wakeLock" in navigator)) {
    return;
  }
  try {
    state.wakeLock = await navigator.wakeLock.request("screen");
  } catch {
  }
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  const host = window.location.hostname;
  const isLocal = host === "localhost" || host === "127.0.0.1" || host === "::1";

  if (isLocal) {
    const regs = await navigator.serviceWorker.getRegistrations().catch(() => []);
    await Promise.all(regs.map((reg) => reg.unregister().catch(() => {})));
    return;
  }

  await navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}

function wireUi() {
  const unlockHandler = () => unlockAudio().catch(() => {});
  document.addEventListener("pointerdown", unlockHandler, { once: true });
  document.addEventListener("keydown", unlockHandler, { once: true });

  els.connectBluetoothButton.addEventListener("click", async () => {
    try {
      await unlockAudio();
      await requestWakeLock();
      await connectBluetooth();
    } catch (error) {
      console.error(error);
      appendTranscript({ text: `Bluetooth connection failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
    }
  });

  els.connectSerialButton.addEventListener("click", async () => {
    try {
      await unlockAudio();
      await requestWakeLock();
      await connectSerial();
    } catch (error) {
      console.error(error);
      appendTranscript({ text: `USB connection failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
    }
  });

  els.connectBridgeButton.addEventListener("click", async () => {
    try {
      await unlockAudio();
      await requestWakeLock();
      await connectBridge();
    } catch (error) {
      console.error(error);
      appendTranscript({ text: `Bridge connection failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
    }
  });

  els.reconnectButton.addEventListener("click", async () => {
    try {
      await unlockAudio();
      await requestWakeLock();
      await reconnectKnownRobot();
    } catch (error) {
      console.error(error);
      appendTranscript({ text: `Reconnect failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
    }
  });

  els.disconnectButton.addEventListener("click", () => disconnectTransport().catch((error) => console.error(error)));
  els.manualNormalButton.addEventListener("click", () => manualSpeak("normal"));
  els.manualUrgentButton.addEventListener("click", () => manualSpeak("urgent"));
  els.clearTranscriptButton.addEventListener("click", () => {
    state.transcript = [];
    renderTranscript();
  });
  els.copyTranscriptButton.addEventListener("click", copyTranscript);
  els.stopAudioButton.addEventListener("click", stopAudio);
  els.speakAgainButton.addEventListener("click", () => {
    if (!state.lastSpokenText) {
      return;
    }
    enqueueMessage({ text: state.lastSpokenText, priority: "normal", eventType: "replay", ts: Date.now(), source: "replay" });
  });
  els.sendRobotAckButton.addEventListener("click", async () => {
    try {
      await sendRobotCommand({ type: "ack", ts: Date.now() });
      appendTranscript({ text: "Sent ack to robot.", source: "Web app", priority: "low", ts: Date.now() });
    } catch (error) {
      appendTranscript({ text: `Ack failed: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
    }
  });
}

async function boot() {
  registerServiceWorker();
  wireUi();
  await loadConfig().catch((error) => {
    appendTranscript({ text: `Could not load server config: ${String(error.message || error)}`, source: "System", priority: "urgent", ts: Date.now() });
  });
  await refreshTransportSupport();

  if (navigator.bluetooth?.addEventListener) {
    navigator.bluetooth.addEventListener("availabilitychanged", (event) => {
      state.bluetoothAvailability = Boolean(event.value);
      refreshTransportSupport().catch(() => {});
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshTransportSupport().catch(() => {});
      requestWakeLock().catch(() => {});
    }
  });
}

boot().catch((error) => console.error(error));
