
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
import base64
import json
import os
import queue
import threading
import cv2
import requests


@dataclass
class EnvironmentSummary:
    timestamp: float
    summary: str
    priorityHazard: str
    recommendedAction: str
    confidence: float
    rawText: str


class EnvironmentVlmClient:
    def __init__(
        self,
        enabled: bool = True,
        model: str = 'Qwen/Qwen2.5-VL-3B-Instruct',
        endpoint: str = 'http://127.0.0.1:8000/v1/chat/completions',
        apiKeyEnv: str = 'VLM_API_KEY',
        apiKey: str = '',
        intervalSec: float = 4.0,
        requestTimeoutSec: float = 8.0,
        maxImageWidth: int = 320,
        temperature: float = 0.1,
        maxCompletionTokens: int = 64,
        systemPrompt: Optional[str] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.model = str(model)
        self.endpoint = str(endpoint)
        self.apiKeyEnv = str(apiKeyEnv)
        self.explicitApiKey = str(apiKey or '').strip()
        self.intervalSec = float(intervalSec)
        self.requestTimeoutSec = float(requestTimeoutSec)
        self.maxImageWidth = int(maxImageWidth)
        self.temperature = float(temperature)
        self.maxCompletionTokens = int(maxCompletionTokens)
        self.systemPrompt = systemPrompt or (
            'You are an environment-awareness vision system. '
            'Describe the surrounding environment for safe navigation. '
            'Return valid JSON with keys short_summary, priority_hazard, recommended_action, confidence.'
        )

        self.lastSubmitTime = 0.0
        self.latestResult: Optional[EnvironmentSummary] = None
        self.latestError: Optional[str] = None
        self.lock = threading.Lock()
        self.stopEvent = threading.Event()
        self.taskQueue: 'queue.Queue[Optional[Dict[str, Any]]]' = queue.Queue(maxsize=1)
        self.workerThread = threading.Thread(target=self._workerLoop, daemon=True)
        self.workerThread.start()

    def close(self) -> None:
        self.stopEvent.set()
        try:
            self.taskQueue.put_nowait(None)
        except queue.Full:
            pass
        self.workerThread.join(timeout=2.0)

    def _resolveApiKey(self) -> str:
        if self.explicitApiKey:
            return self.explicitApiKey
        if self.apiKeyEnv.startswith('gsk_') or self.apiKeyEnv.startswith('sk-') or self.apiKeyEnv.startswith('token-'):
            return self.apiKeyEnv
        return os.environ.get(self.apiKeyEnv, '').strip()

    def _buildHeaders(self, apiKey: str) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if apiKey:
            headers['Authorization'] = f'Bearer {apiKey}'
        return headers

    def submit(self, frame, timestamp: float, detections: Optional[Iterable] = None) -> bool:
        if not self.enabled:
            return False
        if timestamp - self.lastSubmitTime < self.intervalSec:
            return False
        task = {
            'frame': frame.copy(),
            'timestamp': float(timestamp),
            'apiKey': self._resolveApiKey(),
            'detections': [
                {
                    'label': str(getattr(item, 'label', '')),
                    'confidence': float(getattr(item, 'confidence', 0.0)),
                    'bboxXyxy': [float(value) for value in getattr(item, 'bboxXyxy', (0.0, 0.0, 0.0, 0.0))],
                }
                for item in (detections or [])
            ],
        }
        try:
            if self.taskQueue.full():
                try:
                    self.taskQueue.get_nowait()
                except queue.Empty:
                    pass
            self.taskQueue.put_nowait(task)
            self.lastSubmitTime = timestamp
            return True
        except queue.Full:
            return False

    def getLatestResult(self) -> Optional[EnvironmentSummary]:
        with self.lock:
            return self.latestResult

    def getLatestError(self) -> Optional[str]:
        with self.lock:
            return self.latestError

    def _prepareFrame(self, frame) -> str:
        working = frame
        height, width = working.shape[:2]
        if width > self.maxImageWidth:
            scale = self.maxImageWidth / float(width)
            working = cv2.resize(working, (max(1, int(width * scale)), max(1, int(height * scale))))
        ok, encoded = cv2.imencode('.jpg', working, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            raise RuntimeError('Failed to encode frame')
        return base64.b64encode(encoded.tobytes()).decode('utf-8')

    def _workerLoop(self) -> None:
        while not self.stopEvent.is_set():
            try:
                task = self.taskQueue.get(timeout=0.25)
            except queue.Empty:
                continue
            if task is None:
                continue
            try:
                result = self._describe(task['frame'], task['timestamp'], task['apiKey'], task.get('detections', []))
                with self.lock:
                    self.latestResult = result
                    self.latestError = None
            except Exception as error:
                with self.lock:
                    self.latestError = str(error)

    def _describe(self, frame, timestamp: float, apiKey: str, detections: Optional[list[dict]]) -> EnvironmentSummary:
        payload = {
            'model': self.model,
            'temperature': self.temperature,
            'max_completion_tokens': self.maxCompletionTokens,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': self.systemPrompt},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Describe the scene and any immediate hazards around the user. Detector metadata: ' + json.dumps({'detections': detections or []}, separators=(',', ':'))},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + self._prepareFrame(frame)}},
                ]},
            ],
        }
        response = requests.post(
            self.endpoint,
            headers=self._buildHeaders(apiKey),
            json=payload,
            timeout=self.requestTimeoutSec,
        )
        if response.status_code >= 400:
            raise RuntimeError(f'VLM request failed with status {response.status_code}: {response.text[:240]}')
        responseJson = response.json()
        choices = responseJson.get('choices', [])
        if not choices:
            raise RuntimeError('VLM response did not include choices')
        content = choices[0].get('message', {}).get('content', '')
        if isinstance(content, list):
            content = ' '.join(str(item.get('text', '')) for item in content if isinstance(item, dict))
        text = str(content).strip()
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end >= start:
            text = text[start:end + 1]
        parsed = json.loads(text)
        return EnvironmentSummary(
            timestamp=float(timestamp),
            summary=str(parsed.get('short_summary', '')).strip(),
            priorityHazard=str(parsed.get('priority_hazard', '')).strip(),
            recommendedAction=str(parsed.get('recommended_action', '')).strip(),
            confidence=float(parsed.get('confidence', 0.0) or 0.0),
            rawText=text,
        )
