from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .geometry import xyxyToXywhCenter


STATE_VECTOR_ORDER = ['x', 'y', 'xv', 'yv', 'w', 'h']


def _flattenStateMatrix(stateMatrix: Any) -> Optional[list]:
    if stateMatrix is None:
        return None

    flattened = []
    try:
        for value in stateMatrix:
            if isinstance(value, (list, tuple)):
                if not value:
                    return None
                flattened.append(float(value[0]))
            else:
                flattened.append(float(value))
    except Exception:
        return None

    if len(flattened) != 6:
        return None
    return flattened


def stateMatrixToNamedState(stateMatrix: Any) -> Optional[Dict[str, float]]:
    flattened = _flattenStateMatrix(stateMatrix)
    if flattened is None:
        return None
    return {
        'x': float(flattened[0]),
        'y': float(flattened[1]),
        'xv': float(flattened[2]),
        'yv': float(flattened[3]),
        'w': max(1.0, float(flattened[4])),
        'h': max(1.0, float(flattened[5])),
    }


def namedStateToVector(namedState: Optional[Dict[str, float]]) -> Optional[list]:
    if namedState is None:
        return None
    return [float(namedState[key]) for key in STATE_VECTOR_ORDER]


def measurementBoxToState(
    bboxXyxy: Optional[Tuple[float, float, float, float]],
    timestamp: float,
    previousState: Optional[Dict[str, float]] = None,
    previousTimestamp: Optional[float] = None,
) -> Optional[Dict[str, float]]:
    if bboxXyxy is None:
        return None

    centerX, centerY, width, height = xyxyToXywhCenter(tuple(float(value) for value in bboxXyxy))
    state = {
        'x': float(centerX),
        'y': float(centerY),
        'xv': 0.0,
        'yv': 0.0,
        'w': max(1.0, float(width)),
        'h': max(1.0, float(height)),
    }

    if previousState is None or previousTimestamp is None:
        return state

    dt = max(1e-3, float(timestamp) - float(previousTimestamp))
    state['xv'] = (state['x'] - float(previousState['x'])) / dt
    state['yv'] = (state['y'] - float(previousState['y'])) / dt
    return state


def stateToRoundedDict(namedState: Optional[Dict[str, float]], digits: int = 3) -> Optional[Dict[str, float]]:
    if namedState is None:
        return None
    return {key: round(float(value), digits) for key, value in namedState.items()}
