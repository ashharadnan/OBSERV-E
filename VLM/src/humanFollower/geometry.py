from typing import Tuple
import math


def clampBox(bboxXyxy: Tuple[float, float, float, float], frameWidth: int, frameHeight: int) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = bboxXyxy
    x1 = max(0.0, min(float(frameWidth - 1), x1))
    y1 = max(0.0, min(float(frameHeight - 1), y1))
    x2 = max(0.0, min(float(frameWidth - 1), x2))
    y2 = max(0.0, min(float(frameHeight - 1), y2))
    return x1, y1, x2, y2


def xyxyToXywhCenter(bboxXyxy: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = bboxXyxy
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    centerX = x1 + width / 2.0
    centerY = y1 + height / 2.0
    return centerX, centerY, width, height


def xywhCenterToXyxy(centerX: float, centerY: float, width: float, height: float) -> Tuple[float, float, float, float]:
    x1 = centerX - width / 2.0
    y1 = centerY - height / 2.0
    x2 = centerX + width / 2.0
    y2 = centerY + height / 2.0
    return x1, y1, x2, y2


def computeIou(boxA: Tuple[float, float, float, float], boxB: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = boxA
    bx1, by1, bx2, by2 = boxB

    interX1 = max(ax1, bx1)
    interY1 = max(ay1, by1)
    interX2 = min(ax2, bx2)
    interY2 = min(ay2, by2)

    interWidth = max(0.0, interX2 - interX1)
    interHeight = max(0.0, interY2 - interY1)
    interArea = interWidth * interHeight

    areaA = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    areaB = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    unionArea = max(1e-6, areaA + areaB - interArea)
    return interArea / unionArea


def centerDistance(pointA: Tuple[float, float], pointB: Tuple[float, float]) -> float:
    dx = pointA[0] - pointB[0]
    dy = pointA[1] - pointB[1]
    return math.sqrt(dx * dx + dy * dy)
