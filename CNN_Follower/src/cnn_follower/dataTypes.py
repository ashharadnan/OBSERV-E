from dataclasses import dataclass
from typing import Optional, Tuple, List


@dataclass
class Detection:
    bboxXyxy: Tuple[float, float, float, float]
    confidence: float
    classId: int = 0


@dataclass
class TargetState:
    bboxXyxy: Tuple[float, float, float, float]
    confidence: float
    measurementSource: str
    targetLocked: bool
    nextCenter: Optional[Tuple[float, float]]
    stateMatrix: Optional[List[List[float]]]
    pixelError: Optional[Tuple[float, float]]
    normalizedError: Optional[Tuple[float, float]]
