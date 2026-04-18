from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .geometry import clampBox, xyxyToXywhCenter


@dataclass
class HazardDetection:
    label: str
    bboxXyxy: Tuple[float, float, float, float]
    confidence: float
    distanceScore: float
    side: str
    inPathCorridor: bool
    dangerScore: float


class HazardDetector:
    def __init__(
        self,
        modelPath: str,
        confThreshold: float = 0.25,
        iouThreshold: float = 0.45,
        imageSize: int = 640,
        device: str = 'cpu',
        pathCorridorRatio: float = 0.34,
        minDangerConfidence: float = 0.20,
    ) -> None:
        self.modelPath = modelPath
        self.confThreshold = float(confThreshold)
        self.iouThreshold = float(iouThreshold)
        self.imageSize = int(imageSize)
        self.device = device
        self.pathCorridorRatio = float(pathCorridorRatio)
        self.minDangerConfidence = float(minDangerConfidence)
        self.names: Dict[int, str] = {}

        try:
            from ultralytics import YOLO
        except Exception as error:
            raise RuntimeError(
                'Ultralytics is required for HazardDetector. Install dependencies from requirements.txt.'
            ) from error

        self.model = YOLO(self.modelPath)

        modelNames = getattr(self.model, 'names', None)
        if isinstance(modelNames, dict):
            self.names = {int(key): str(value) for key, value in modelNames.items()}
        elif isinstance(modelNames, list):
            self.names = {index: str(value) for index, value in enumerate(modelNames)}

        self.vehicleLabels = {
            'car', 'truck', 'bus', 'motorcycle', 'bicycle', 'scooter', 'train'
        }
        self.barrierLabels = {
            'chair', 'bench', 'potted plant', 'fire hydrant', 'stop sign', 'parking meter',
            'traffic cone', 'cone', 'barrier', 'bollard', 'suitcase', 'backpack', 'stroller'
        }

    def _normalizeLabel(self, classId: int) -> str:
        return self.names.get(int(classId), str(classId)).lower().strip()

    def _labelBaseDanger(self, label: str) -> float:
        if label in self.vehicleLabels:
            return 0.92
        if label in self.barrierLabels:
            return 0.62
        if label in {'person'}:
            return 0.38
        return 0.48

    def _sideFromCenter(self, centerX: float, frameWidth: int) -> str:
        leftBand = frameWidth * 0.42
        rightBand = frameWidth * 0.58
        if centerX < leftBand:
            return 'left'
        if centerX > rightBand:
            return 'right'
        return 'center'

    def predict(self, frame) -> List[HazardDetection]:
        results = self.model.predict(
            source=frame,
            conf=self.confThreshold,
            iou=self.iouThreshold,
            imgsz=self.imageSize,
            device=self.device,
            verbose=False,
        )

        detections: List[HazardDetection] = []
        if not results:
            return detections

        firstResult = results[0]
        boxes = getattr(firstResult, 'boxes', None)
        if boxes is None:
            return detections

        frameHeight, frameWidth = frame.shape[:2]
        corridorHalfWidth = max(1.0, frameWidth * self.pathCorridorRatio / 2.0)
        frameCenterX = frameWidth / 2.0
        frameArea = max(1.0, float(frameWidth * frameHeight))

        for box in boxes:
            xyxyTensor = box.xyxy[0].tolist()
            confidence = float(box.conf[0].item())
            classId = int(box.cls[0].item())
            if confidence < self.minDangerConfidence:
                continue

            bboxXyxy = clampBox(
                (float(xyxyTensor[0]), float(xyxyTensor[1]), float(xyxyTensor[2]), float(xyxyTensor[3])),
                frameWidth,
                frameHeight,
            )
            centerX, centerY, width, height = xyxyToXywhCenter(bboxXyxy)
            label = self._normalizeLabel(classId)
            relativeArea = max(0.0, min(1.0, (width * height) / frameArea * 9.0))
            nearBottomBoost = max(0.0, min(1.0, centerY / max(1.0, frameHeight)))
            inPathCorridor = abs(centerX - frameCenterX) <= corridorHalfWidth
            corridorBoost = 0.15 if inPathCorridor else 0.0
            distanceScore = max(0.0, min(1.0, 0.60 * relativeArea + 0.40 * nearBottomBoost))
            dangerScore = max(
                0.0,
                min(
                    1.0,
                    self._labelBaseDanger(label) * 0.55
                    + confidence * 0.15
                    + distanceScore * 0.15
                    + corridorBoost
                ),
            )
            detections.append(
                HazardDetection(
                    label=label,
                    bboxXyxy=bboxXyxy,
                    confidence=confidence,
                    distanceScore=distanceScore,
                    side=self._sideFromCenter(centerX, frameWidth),
                    inPathCorridor=inPathCorridor,
                    dangerScore=dangerScore,
                )
            )

        detections.sort(key=lambda item: item.dangerScore, reverse=True)
        return detections

    @staticmethod
    def summarizeHazards(detections: List[HazardDetection]) -> Dict[str, Any]:
        if not detections:
            return {
                'hazards': [],
                'topHazard': None,
                'vehicleThreat': 0.0,
                'pathDanger': 0.0,
                'hazardProximity': 0.0,
            }

        topHazard = detections[0]
        vehicleThreat = 0.0
        pathDanger = 0.0
        hazardProximity = 0.0

        for detection in detections:
            hazardProximity = max(hazardProximity, detection.distanceScore)
            if detection.inPathCorridor:
                pathDanger = max(pathDanger, detection.dangerScore)
            if detection.label in {'car', 'truck', 'bus', 'motorcycle', 'bicycle', 'scooter'}:
                lateralBoost = 0.08 if detection.side in ('left', 'right') else 0.0
                vehicleThreat = max(vehicleThreat, min(1.0, detection.dangerScore + lateralBoost))

        return {
            'hazards': detections,
            'topHazard': topHazard,
            'vehicleThreat': float(vehicleThreat),
            'pathDanger': float(pathDanger),
            'hazardProximity': float(hazardProximity),
        }
