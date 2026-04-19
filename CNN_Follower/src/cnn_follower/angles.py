
from __future__ import annotations

from typing import Dict, Optional, Tuple


def computeAngleState(
    frameWidth: int,
    frameHeight: int,
    nextCenter: Optional[Tuple[float, float]],
    predictedKalmanState: Optional[Dict[str, float]],
    horizontalFovDeg: float,
    verticalFovDeg: float,
) -> Optional[Dict[str, float]]:
    if nextCenter is None or frameWidth <= 0 or frameHeight <= 0:
        return None

    frameCenterX = frameWidth / 2.0
    frameCenterY = frameHeight / 2.0
    dxPixels = float(nextCenter[0]) - frameCenterX
    dyPixels = float(nextCenter[1]) - frameCenterY

    yawErrorDeg = (dxPixels / max(1.0, frameWidth / 2.0)) * (float(horizontalFovDeg) / 2.0)
    pitchErrorDeg = -(dyPixels / max(1.0, frameHeight / 2.0)) * (float(verticalFovDeg) / 2.0)

    yawRateDegPerSec = 0.0
    pitchRateDegPerSec = 0.0
    boxWidthDeg = 0.0
    boxHeightDeg = 0.0

    if predictedKalmanState is not None:
        yawRateDegPerSec = float(predictedKalmanState.get('xv', 0.0)) * float(horizontalFovDeg) / max(1.0, frameWidth)
        pitchRateDegPerSec = -float(predictedKalmanState.get('yv', 0.0)) * float(verticalFovDeg) / max(1.0, frameHeight)
        boxWidthDeg = max(0.0, float(predictedKalmanState.get('w', 0.0)) * float(horizontalFovDeg) / max(1.0, frameWidth))
        boxHeightDeg = max(0.0, float(predictedKalmanState.get('h', 0.0)) * float(verticalFovDeg) / max(1.0, frameHeight))

    return {
        'yawErrorDeg': float(yawErrorDeg),
        'pitchErrorDeg': float(pitchErrorDeg),
        'yawRateDegPerSec': float(yawRateDegPerSec),
        'pitchRateDegPerSec': float(pitchRateDegPerSec),
        'boxWidthDeg': float(boxWidthDeg),
        'boxHeightDeg': float(boxHeightDeg),
        'horizontalFovDeg': float(horizontalFovDeg),
        'verticalFovDeg': float(verticalFovDeg),
    }
