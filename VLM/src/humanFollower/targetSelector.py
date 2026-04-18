from typing import List, Optional, Tuple
import math

from .dataTypes import Detection
from .geometry import computeIou, xyxyToXywhCenter, centerDistance


class TargetSelector:
    def __init__(
        self,
        selectionMode: str = 'closestToCenter',
        maxAssociationDistanceRatio: float = 0.28,
        minAssociationIou: float = 0.05,
    ) -> None:
        self.selectionMode = selectionMode
        self.maxAssociationDistanceRatio = float(maxAssociationDistanceRatio)
        self.minAssociationIou = float(minAssociationIou)

    def _scoreInitialSelection(
        self,
        detection: Detection,
        frameWidth: int,
        frameHeight: int,
    ) -> float:
        centerX, centerY, width, height = xyxyToXywhCenter(detection.bboxXyxy)
        frameCenter = (frameWidth / 2.0, frameHeight / 2.0)
        distanceToCenter = centerDistance((centerX, centerY), frameCenter)
        maxDistance = math.sqrt(frameCenter[0] ** 2 + frameCenter[1] ** 2)
        normalizedDistance = distanceToCenter / max(1e-6, maxDistance)
        area = width * height

        if self.selectionMode == 'highestConfidence':
            return detection.confidence
        if self.selectionMode == 'largest':
            return area + detection.confidence * 1000.0

        return (1.0 - normalizedDistance) * 0.65 + detection.confidence * 0.35

    def select(
        self,
        detections: List[Detection],
        frameWidth: int,
        frameHeight: int,
        predictedCenter: Optional[Tuple[float, float]] = None,
        previousBox: Optional[Tuple[float, float, float, float]] = None,
    ) -> Optional[Detection]:
        if not detections:
            return None

        if predictedCenter is None or previousBox is None:
            scored = sorted(
                detections,
                key=lambda detection: self._scoreInitialSelection(detection, frameWidth, frameHeight),
                reverse=True,
            )
            return scored[0]

        maxAssociationDistance = math.sqrt(frameWidth ** 2 + frameHeight ** 2) * self.maxAssociationDistanceRatio
        scoredCandidates = []

        for detection in detections:
            centerX, centerY, _, _ = xyxyToXywhCenter(detection.bboxXyxy)
            detectionCenter = (centerX, centerY)
            distanceValue = centerDistance(detectionCenter, predictedCenter)
            iouValue = computeIou(detection.bboxXyxy, previousBox)

            passesGate = distanceValue <= maxAssociationDistance or iouValue >= self.minAssociationIou
            if not passesGate:
                continue

            distanceScore = max(0.0, 1.0 - (distanceValue / max(1e-6, maxAssociationDistance)))
            totalScore = distanceScore * 0.55 + iouValue * 0.25 + detection.confidence * 0.20
            scoredCandidates.append((totalScore, detection))

        if scoredCandidates:
            scoredCandidates.sort(key=lambda item: item[0], reverse=True)
            return scoredCandidates[0][1]

        fallbackScored = sorted(detections, key=lambda detection: detection.confidence, reverse=True)
        return fallbackScored[0]
