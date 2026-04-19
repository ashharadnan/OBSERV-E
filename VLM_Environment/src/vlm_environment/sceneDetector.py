
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .modelCache import load_yolo_model


@dataclass
class SceneDetection:
    bboxXyxy: tuple[float, float, float, float]
    confidence: float
    classId: int
    label: str


class SceneDetector:
    def __init__(
        self,
        modelPath: str,
        confThreshold: float = 0.25,
        iouThreshold: float = 0.45,
        imageSize: int = 224,
        device: str = 'cpu',
        allowedLabels: Optional[list[str]] = None,
        maxDetections: int = 8,
    ) -> None:
        self.modelPath = modelPath
        self.confThreshold = float(confThreshold)
        self.iouThreshold = float(iouThreshold)
        self.imageSize = int(imageSize)
        self.device = str(device)
        self.allowedLabels = None if not allowedLabels else {str(label).strip().lower() for label in allowedLabels}
        self.maxDetections = max(1, int(maxDetections))
        self.model = load_yolo_model(modelPath)

    def predict(self, frame) -> List[SceneDetection]:
        results = self.model.predict(
            source=frame,
            conf=self.confThreshold,
            iou=self.iouThreshold,
            imgsz=self.imageSize,
            device=self.device,
            verbose=False,
        )
        if not results:
            return []
        first = results[0]
        boxes = getattr(first, 'boxes', None)
        if boxes is None:
            return []
        names = getattr(first, 'names', getattr(self.model, 'names', {})) or {}
        detections: List[SceneDetection] = []
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            confidence = float(box.conf[0].item())
            class_id = int(box.cls[0].item())
            label = str(names.get(class_id, class_id))
            if self.allowedLabels is not None and label.strip().lower() not in self.allowedLabels:
                continue
            detections.append(SceneDetection(
                bboxXyxy=(float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                confidence=confidence,
                classId=class_id,
                label=label,
            ))
        detections.sort(key=lambda item: item.confidence, reverse=True)
        return detections[:self.maxDetections]
