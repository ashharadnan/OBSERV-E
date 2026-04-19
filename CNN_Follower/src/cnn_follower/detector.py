from typing import List

from .dataTypes import Detection
from .modelCache import loadYoloModel


class PersonDetector:
    def __init__(
        self,
        modelPath: str,
        confThreshold: float = 0.4,
        iouThreshold: float = 0.5,
        imageSize: int = 640,
        device: str = 'cpu',
        personClassId: int = 0,
    ) -> None:
        self.modelPath = modelPath
        self.confThreshold = float(confThreshold)
        self.iouThreshold = float(iouThreshold)
        self.imageSize = int(imageSize)
        self.device = device
        self.personClassId = int(personClassId)

        self.model = loadYoloModel(self.modelPath)

    def predict(self, frame) -> List[Detection]:
        results = self.model.predict(
            source=frame,
            conf=self.confThreshold,
            iou=self.iouThreshold,
            imgsz=self.imageSize,
            device=self.device,
            classes=[self.personClassId],
            verbose=False,
        )

        detections: List[Detection] = []
        if not results:
            return detections

        firstResult = results[0]
        boxes = getattr(firstResult, 'boxes', None)
        if boxes is None:
            return detections

        for box in boxes:
            xyxyTensor = box.xyxy[0].tolist()
            confidence = float(box.conf[0].item())
            classId = int(box.cls[0].item())
            detections.append(
                Detection(
                    bboxXyxy=(float(xyxyTensor[0]), float(xyxyTensor[1]), float(xyxyTensor[2]), float(xyxyTensor[3])),
                    confidence=confidence,
                    classId=classId,
                )
            )

        return detections
