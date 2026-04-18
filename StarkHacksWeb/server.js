const express = require("express");
const path = require("path");
const dotenv = require("dotenv");
const crypto = require("crypto");
const { Readable } = require("stream");

dotenv.config();

const app = express();
const port = Number(process.env.PORT || 3000);
const ttsSessions = new Map();
const bridgeClients = new Set();
const robotCommandQueue = [];
const sessionTtlMs = 60 * 1000;

app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public"), {
  setHeaders: (res) => {
    res.setHeader("Cache-Control", "no-store");
  }
}));

function cleanupExpiredSessions() {
  const now = Date.now();
  for (const [token, session] of ttsSessions.entries()) {
    if ((now - session.createdAt) > sessionTtlMs) {
      ttsSessions.delete(token);
    }
  }
}

function broadcastSse(eventName, payload) {
  const data = `event: ${eventName}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const client of bridgeClients) {
    client.write(data);
  }
}

function nextCommand() {
  if (!robotCommandQueue.length) {
    return null;
  }
  return robotCommandQueue.shift();
}

setInterval(cleanupExpiredSessions, 15 * 1000).unref();
setInterval(() => {
  broadcastSse("robot_status", { text: "Bridge heartbeat ok", source: "Bridge", priority: "low", ts: Date.now() });
}, 15000).unref();

app.get("/api/health", (req, res) => {
  res.json({
    ok: true,
    secureContextRecommended: true,
    elevenLabsKeyPresent: Boolean(process.env.ELEVENLABS_API_KEY),
    bridgeClients: bridgeClients.size,
    queuedCommands: robotCommandQueue.length,
    ts: Date.now()
  });
});

app.get("/api/config", (req, res) => {
  res.json({
    defaultVoiceId: process.env.ELEVENLABS_VOICE_ID || "JBFqnCBsd6RMkjVDRZzb",
    defaultModelId: process.env.ELEVENLABS_MODEL_ID || "eleven_flash_v2_5",
    defaultBridgeUrl: process.env.BRIDGE_EVENT_PATH || "/api/events"
  });
});

app.get("/api/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders?.();
  bridgeClients.add(res);
  res.write(`event: hello\ndata: ${JSON.stringify({ text: "Bridge connected", ts: Date.now() })}\n\n`);

  req.on("close", () => {
    bridgeClients.delete(res);
  });
});

app.post("/api/robot-message", (req, res) => {
  const payload = {
    text: String(req.body?.text || "").trim(),
    priority: String(req.body?.priority || "normal"),
    eventType: String(req.body?.eventType || "robot_update"),
    source: String(req.body?.source || "robot"),
    ts: Number(req.body?.ts || Date.now())
  };

  if (!payload.text) {
    return res.status(400).json({ error: "Missing text." });
  }

  broadcastSse("robot_message", payload);
  return res.json({ ok: true, deliveredTo: bridgeClients.size });
});

app.post("/api/robot-status", (req, res) => {
  const payload = {
    text: String(req.body?.text || "").trim(),
    priority: String(req.body?.priority || "low"),
    source: String(req.body?.source || "robot_status"),
    ts: Number(req.body?.ts || Date.now())
  };

  if (!payload.text) {
    return res.status(400).json({ error: "Missing text." });
  }

  broadcastSse("robot_status", payload);
  return res.json({ ok: true, deliveredTo: bridgeClients.size });
});

app.post("/api/robot-command", (req, res) => {
  const payload = {
    id: crypto.randomUUID(),
    type: String(req.body?.type || "command"),
    text: req.body?.text ? String(req.body.text) : "",
    ts: Number(req.body?.ts || Date.now())
  };
  robotCommandQueue.push(payload);
  return res.json({ ok: true, queued: robotCommandQueue.length, command: payload });
});

app.get("/api/robot-command/next", (req, res) => {
  const command = nextCommand();
  res.json({ ok: true, command });
});

app.post("/api/tts-token", (req, res) => {
  const apiKeyPresent = Boolean(process.env.ELEVENLABS_API_KEY);
  if (!apiKeyPresent) {
    return res.status(500).json({ error: "Missing ELEVENLABS_API_KEY on the server." });
  }

  const text = String(req.body?.text || "").trim();
  const voiceId = String(req.body?.voiceId || process.env.ELEVENLABS_VOICE_ID || "JBFqnCBsd6RMkjVDRZzb").trim();
  const modelId = String(req.body?.modelId || process.env.ELEVENLABS_MODEL_ID || "eleven_flash_v2_5").trim();
  const priority = String(req.body?.priority || "normal").trim();

  if (!text) {
    return res.status(400).json({ error: "Missing text." });
  }

  const token = crypto.randomUUID();
  ttsSessions.set(token, { text, voiceId, modelId, priority, createdAt: Date.now() });

  return res.json({ ok: true, token, url: `/api/tts-stream/${encodeURIComponent(token)}` });
});

app.get("/api/tts-stream/:token", async (req, res) => {
  try {
    const session = ttsSessions.get(req.params.token);
    if (!session) {
      return res.status(404).json({ error: "TTS session not found or expired." });
    }
    ttsSessions.delete(req.params.token);

    const apiKey = process.env.ELEVENLABS_API_KEY;
    const voiceSettings = session.priority === "urgent"
      ? { stability: 0.35, similarity_boost: 0.75, style: 0.15, use_speaker_boost: true }
      : { stability: 0.5, similarity_boost: 0.8, style: 0.35, use_speaker_boost: true };

    const url = `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(session.voiceId)}/stream?output_format=mp3_44100_128`;
    const upstream = await fetch(url, {
      method: "POST",
      headers: {
        "xi-api-key": apiKey,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
      },
      body: JSON.stringify({
        text: session.text,
        model_id: session.modelId,
        voice_settings: voiceSettings
      })
    });

    if (!upstream.ok || !upstream.body) {
      const fallbackText = await upstream.text().catch(() => "");
      return res.status(upstream.status || 502).json({
        error: "ElevenLabs request failed.",
        details: fallbackText.slice(0, 500)
      });
    }

    res.setHeader("Content-Type", "audio/mpeg");
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Transfer-Encoding", "chunked");
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: "Unexpected TTS server error.", details: String(error?.message || error) });
  }
});

app.listen(port, () => {
  console.log(`OBSERV-E web app running on http://localhost:${port}`);
});
