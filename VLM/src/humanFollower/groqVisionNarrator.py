from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import base64
import json
import os
import queue
import threading

import cv2
import requests


@dataclass
class VlmNarrationResult:
    timestamp: float
    summary: str
    priorityHazard: str
    recommendedAction: str
    confidence: float
    rawText: str
    source: str


class GroqVisionNarrator:
    def __init__(
        self,
        enabled: bool = False,
        model: str = 'meta-llama/llama-4-scout-17b-16e-instruct',
        endpoint: str = 'https://api.groq.com/openai/v1/chat/completions',
        apiKeyEnv: str = 'GROQ_API_KEY',
        apiKey: str = '',
        intervalSec: float = 2.0,
        requestTimeoutSec: float = 8.0,
        maxImageWidth: int = 640,
        temperature: float = 0.2,
        maxCompletionTokens: int = 180,
        systemPrompt: Optional[str] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.model = str(model)
        self.endpoint = str(endpoint)
        self.apiKeyEnv = str(apiKeyEnv).strip() if apiKeyEnv else 'GROQ_API_KEY'
        self.explicitApiKey = str(apiKey or '').strip()
        self.intervalSec = float(intervalSec)
        self.requestTimeoutSec = float(requestTimeoutSec)
        self.maxImageWidth = int(maxImageWidth)
        self.temperature = float(temperature)
        self.maxCompletionTokens = int(maxCompletionTokens)
        self.systemPrompt = systemPrompt or (
            'You are a mobility-assistance vision system. '
            'Describe the external environment for a blind or low-vision user. '
            'Be concise, practical, and safety-first. '
            'Return valid JSON with keys short_summary, priority_hazard, recommended_action, confidence. '
            'Keep short_summary to one sentence under 20 words. '
            'Use only direct visual observations and provided detector metadata. '
            'Do not speculate beyond the visible scene.'
        )

        self.taskQueue: 'queue.Queue[Optional[Dict[str, Any]]]' = queue.Queue(maxsize=1)
        self.lastSubmitTime = 0.0
        self.latestResult: Optional[VlmNarrationResult] = None
        self.latestError: Optional[str] = None
        self.lock = threading.Lock()
        self.stopEvent = threading.Event()
        self.workerThread: Optional[threading.Thread] = None

        if self.enabled:
            self.workerThread = threading.Thread(target=self._workerLoop, daemon=True)
            self.workerThread.start()

    def close(self) -> None:
        if not self.enabled:
            return
        self.stopEvent.set()
        try:
            self.taskQueue.put_nowait(None)
        except queue.Full:
            pass
        if self.workerThread is not None:
            self.workerThread.join(timeout=2.0)

    def getLatestResult(self) -> Optional[VlmNarrationResult]:
        with self.lock:
            return self.latestResult

    def getLatestError(self) -> Optional[str]:
        with self.lock:
            return self.latestError

    def _resolveApiKey(self) -> str:
        if self.explicitApiKey:
            return self.explicitApiKey

        # Support accidental config mistakes where the real key was placed in apiKeyEnv.
        if self.apiKeyEnv.startswith('gsk_'):
            return self.apiKeyEnv

        return os.environ.get(self.apiKeyEnv, '').strip()

    def submit(self, frame, state: Dict[str, Any], currentTime: float) -> bool:
        if not self.enabled:
            return False

        apiKey = self._resolveApiKey()
        if not apiKey:
            with self.lock:
                self.latestError = f'Missing Groq API key. Set {self.apiKeyEnv} or pass --groqApiKey.'
            return False

        if currentTime - self.lastSubmitTime < self.intervalSec:
            return False

        task = {
            'frame': frame.copy(),
            'state': self._compactState(state),
            'timestamp': float(currentTime),
            'apiKey': apiKey,
        }

        try:
            if self.taskQueue.full():
                try:
                    self.taskQueue.get_nowait()
                except queue.Empty:
                    pass
            self.taskQueue.put_nowait(task)
            self.lastSubmitTime = currentTime
            return True
        except queue.Full:
            return False

    def _workerLoop(self) -> None:
        while not self.stopEvent.is_set():
            try:
                task = self.taskQueue.get(timeout=0.25)
            except queue.Empty:
                continue

            if task is None:
                continue

            try:
                result = self._describe(task['frame'], task['state'], task['timestamp'], task['apiKey'])
                with self.lock:
                    self.latestResult = result
                    self.latestError = None
            except Exception as error:
                with self.lock:
                    self.latestError = str(error)

    def _compactState(self, state: Dict[str, Any]) -> Dict[str, Any]:
        hazards: List[Dict[str, Any]] = []
        for hazard in state.get('hazards', [])[:6]:
            hazards.append(
                {
                    'label': hazard.label,
                    'side': hazard.side,
                    'inPathCorridor': bool(hazard.inPathCorridor),
                    'dangerScore': round(float(hazard.dangerScore), 3),
                    'distanceScore': round(float(hazard.distanceScore), 3),
                }
            )

        payload = state.get('trackingPayload', {})
        return {
            'eventLevel': int(state.get('eventLevel', 0)),
            'riskScore': round(float(state.get('riskScore', 0.0)), 3),
            'pathDanger': round(float(state.get('pathDanger', 0.0)), 3),
            'trafficThreat': round(float(state.get('trafficThreat', 0.0)), 3),
            'targetLocked': bool(payload.get('targetLocked', False)),
            'targetConfidence': round(float(payload.get('confidence', 0.0)), 3),
            'kalmanState': payload.get('kalmanState'),
            'actualBoxState': payload.get('actualBoxState'),
            'topHazardLabel': None if state.get('topHazard') is None else state['topHazard'].label,
            'topHazardSide': None if state.get('topHazard') is None else state['topHazard'].side,
            'hazards': hazards,
        }

    def _prepareFrame(self, frame) -> str:
        working = frame
        height, width = working.shape[:2]
        if width > self.maxImageWidth:
            scale = self.maxImageWidth / float(width)
            newWidth = max(1, int(width * scale))
            newHeight = max(1, int(height * scale))
            working = cv2.resize(working, (newWidth, newHeight))
        ok, encoded = cv2.imencode('.jpg', working, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise RuntimeError('Failed to encode frame for VLM request')
        return base64.b64encode(encoded.tobytes()).decode('utf-8')

    def _buildUserText(self, compactState: Dict[str, Any]) -> str:
        return (
            'Describe the environment for safe walking. '
            'Prefer lane or sidewalk obstacles, cars, bikes, cones, barriers, stairs, and blocked paths. '
            'Prioritize immediate hazards and directional cues. '
            'Detector metadata: ' + json.dumps(compactState, separators=(',', ':'))
        )

    def _extractText(self, responseJson: Dict[str, Any]) -> str:
        choices = responseJson.get('choices', [])
        if not choices:
            raise RuntimeError('Groq response did not include choices')
        message = choices[0].get('message', {})
        content = message.get('content', '')
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    parts.append(item.get('text', ''))
            content = ' '.join(part for part in parts if part)
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError('Groq response content was empty')
        return content.strip()

    def _parseJsonText(self, text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start >= 0 and end >= start:
            cleaned = cleaned[start:end + 1]
        return json.loads(cleaned)

    def _describe(self, frame, compactState: Dict[str, Any], timestamp: float, apiKey: str) -> VlmNarrationResult:
        base64Image = self._prepareFrame(frame)
        payload = {
            'model': self.model,
            'temperature': self.temperature,
            'max_completion_tokens': self.maxCompletionTokens,
            'response_format': {'type': 'json_object'},
            'messages': [
                {
                    'role': 'system',
                    'content': self.systemPrompt,
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': self._buildUserText(compactState),
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:image/jpeg;base64,{base64Image}',
                            },
                        },
                    ],
                },
            ],
        }
        headers = {
            'Authorization': f'Bearer {apiKey}',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.requestTimeoutSec,
        )
        if response.status_code >= 400:
            raise RuntimeError(f'Groq request failed with status {response.status_code}: {response.text[:300]}')
        responseJson = response.json()
        rawText = self._extractText(responseJson)
        parsed = self._parseJsonText(rawText)
        summary = str(parsed.get('short_summary', '')).strip()
        priorityHazard = str(parsed.get('priority_hazard', '')).strip()
        recommendedAction = str(parsed.get('recommended_action', '')).strip()
        try:
            confidence = float(parsed.get('confidence', 0.0))
        except Exception:
            confidence = 0.0

        if not summary:
            raise RuntimeError('VLM returned no short_summary')

        return VlmNarrationResult(
            timestamp=float(timestamp),
            summary=summary,
            priorityHazard=priorityHazard,
            recommendedAction=recommendedAction,
            confidence=max(0.0, min(1.0, confidence)),
            rawText=rawText,
            source='groq_vision',
        )
