from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import json
import queue
import threading

import cv2
from PIL import Image
import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

from .narrator import EnvironmentSummary


class LocalGemmaClient:
    def __init__(
        self,
        enabled: bool = True,
        modelPath: str = 'models/gemma-4-E2B-it',
        intervalSec: float = 4.0,
        maxImageWidth: int = 320,
        temperature: float = 0.1,
        maxCompletionTokens: int = 64,
        deviceMap: str = 'auto',
        torchDtype: str = 'auto',
        enableThinking: bool = False,
        systemPrompt: Optional[str] = None,
        **_: Any,
    ) -> None:
        self.enabled = bool(enabled)
        self.modelPath = str(modelPath)
        self.intervalSec = float(intervalSec)
        self.maxImageWidth = int(maxImageWidth)
        self.temperature = float(temperature)
        self.maxCompletionTokens = int(maxCompletionTokens)
        self.deviceMap = str(deviceMap)
        self.torchDtype = str(torchDtype)
        self.enableThinking = bool(enableThinking)
        self.systemPrompt = systemPrompt or (
            'You are an environment-awareness vision system. '
            'Describe what is around the user. '
            'Focus on obstacles, paths, cars, bikes, stairs, doors, signs, people, and blocked routes. '
            'Use the provided detector metadata as additional context. '
            'Return valid JSON with keys short_summary, priority_hazard, recommended_action, confidence. '
            'Keep short_summary to one sentence under 24 words.'
        )

        self.lastSubmitTime = 0.0
        self.latestResult: Optional[EnvironmentSummary] = None
        self.latestError: Optional[str] = None
        self.lock = threading.Lock()
        self.stopEvent = threading.Event()
        self.taskQueue: 'queue.Queue[Optional[Dict[str, Any]]]' = queue.Queue(maxsize=1)
        self.workerThread = threading.Thread(target=self._workerLoop, daemon=True)

        self.processor = None
        self.model = None
        if self.enabled:
            model_dir = Path(self.modelPath)
            if not model_dir.exists():
                raise FileNotFoundError(
                    'Local Gemma model directory was not found at '
                    f"{model_dir}. Run scripts/installLocalGemma.sh first."
                )
            self.processor = AutoProcessor.from_pretrained(self.modelPath)
            load_kwargs: Dict[str, Any] = {
                'device_map': self.deviceMap,
            }
            if self.torchDtype == 'auto':
                load_kwargs['torch_dtype'] = 'auto'
            else:
                load_kwargs['torch_dtype'] = getattr(torch, self.torchDtype)
            self.model = AutoModelForMultimodalLM.from_pretrained(self.modelPath, **load_kwargs)
            self.model.eval()
            self.workerThread.start()

    def close(self) -> None:
        if not self.enabled:
            return
        self.stopEvent.set()
        try:
            self.taskQueue.put_nowait(None)
        except queue.Full:
            pass
        self.workerThread.join(timeout=2.0)

    def submit(self, frame, timestamp: float, detections: Optional[Iterable] = None) -> bool:
        if not self.enabled:
            return False
        if timestamp - self.lastSubmitTime < self.intervalSec:
            return False
        task = {
            'frame': frame.copy(),
            'timestamp': float(timestamp),
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

    def _prepareImage(self, frame) -> Image.Image:
        working = frame
        height, width = working.shape[:2]
        if width > self.maxImageWidth:
            scale = self.maxImageWidth / float(width)
            working = cv2.resize(working, (max(1, int(width * scale)), max(1, int(height * scale))))
        rgb = cv2.cvtColor(working, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _workerLoop(self) -> None:
        while not self.stopEvent.is_set():
            try:
                task = self.taskQueue.get(timeout=0.25)
            except queue.Empty:
                continue
            if task is None:
                continue
            try:
                result = self._describe(task['frame'], task['timestamp'], task.get('detections', []))
                with self.lock:
                    self.latestResult = result
                    self.latestError = None
            except Exception as error:
                with self.lock:
                    self.latestError = str(error)

    def _describe(self, frame, timestamp: float, detections: list[dict]) -> EnvironmentSummary:
        assert self.processor is not None and self.model is not None

        prompt_text = (
            'Detector metadata: '
            + json.dumps({'detections': detections}, separators=(',', ':'))
            + '\nReturn only JSON with keys short_summary, priority_hazard, recommended_action, confidence.'
        )
        messages = [
            {'role': 'system', 'content': self.systemPrompt},
            {
                'role': 'user',
                'content': [
                    {'type': 'image'},
                    {'type': 'text', 'text': prompt_text},
                ],
            },
        ]

        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            return_dict=True,
            return_tensors='pt',
            add_generation_prompt=True,
            enable_thinking=self.enableThinking,
        )
        image_inputs = self.processor(images=[self._prepareImage(frame)], return_tensors='pt')
        for key, value in image_inputs.items():
            if key not in inputs:
                inputs[key] = value

        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) if hasattr(v, 'to') else v for k, v in inputs.items()}
        input_len = inputs['input_ids'].shape[-1]

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.maxCompletionTokens,
                do_sample=self.temperature > 0,
                temperature=max(self.temperature, 1e-5),
                top_p=0.95,
                top_k=64,
                cache_implementation='static',
            )

        response = self.processor.decode(outputs[0][input_len:], skip_special_tokens=False)
        if hasattr(self.processor, 'parse_response'):
            try:
                parsed_response = self.processor.parse_response(response)
                if isinstance(parsed_response, dict) and 'response' in parsed_response:
                    response = parsed_response['response']
            except Exception:
                pass

        text = str(response).strip()
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
