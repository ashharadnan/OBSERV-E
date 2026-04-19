from __future__ import annotations

import struct
from typing import Dict, Optional

GIMBAL_CONTROL_MAGIC = 0x47494D42
# magic, frame_index, timestamp, target_locked, measurement_source, reserved0, 50 floats
GIMBAL_CONTROL_STRUCT = struct.Struct('<II f B B H 51f')
MEASUREMENT_SOURCE_TO_ID = {
    'none': 0,
    'detector': 1,
    'tracker': 2,
    'predictionOnly': 3,
    'highRateProjector': 4,
    'staleProjection': 5,
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _vector4(values) -> list[float]:
    values = values or [0.0, 0.0, 0.0, 0.0]
    return [
        _safe_float(values[0] if len(values) > 0 else 0.0),
        _safe_float(values[1] if len(values) > 1 else 0.0),
        _safe_float(values[2] if len(values) > 2 else 0.0),
        _safe_float(values[3] if len(values) > 3 else 0.0),
    ]


def pack_gimbal_control_packet(payload: Dict) -> bytes:
    current_state = payload.get('kalmanState') or {}
    predicted_state = payload.get('predictedKalmanState') or {}
    covariance_diag = payload.get('covarianceDiag') or {}
    next_center = payload.get('nextCenter') or [0.0, 0.0]
    predicted_bbox = _vector4(payload.get('bboxXyxy'))
    measured_bbox = _vector4(payload.get('measuredBoxXyxy'))
    pixel_error = payload.get('pixelError') or [0.0, 0.0]
    normalized_error = payload.get('normalizedError') or [0.0, 0.0]
    angles = payload.get('angles') or {}
    kalman_params = payload.get('kalmanParams') or {}

    return GIMBAL_CONTROL_STRUCT.pack(
        int(GIMBAL_CONTROL_MAGIC),
        int(payload.get('frameIndex', 0) or 0),
        _safe_float(payload.get('timestamp')),
        1 if payload.get('targetLocked') else 0,
        int(MEASUREMENT_SOURCE_TO_ID.get(str(payload.get('measurementSource', 'none')), 0)),
        0,
        _safe_float(payload.get('confidence')),
        _safe_float(current_state.get('x')),
        _safe_float(current_state.get('y')),
        _safe_float(current_state.get('xv')),
        _safe_float(current_state.get('yv')),
        _safe_float(current_state.get('w')),
        _safe_float(current_state.get('h')),
        _safe_float(predicted_state.get('x')),
        _safe_float(predicted_state.get('y')),
        _safe_float(predicted_state.get('xv')),
        _safe_float(predicted_state.get('yv')),
        _safe_float(predicted_state.get('w')),
        _safe_float(predicted_state.get('h')),
        measured_bbox[0], measured_bbox[1], measured_bbox[2], measured_bbox[3],
        predicted_bbox[0], predicted_bbox[1], predicted_bbox[2], predicted_bbox[3],
        _safe_float(next_center[0] if len(next_center) > 0 else 0.0),
        _safe_float(next_center[1] if len(next_center) > 1 else 0.0),
        _safe_float(pixel_error[0] if len(pixel_error) > 0 else 0.0),
        _safe_float(pixel_error[1] if len(pixel_error) > 1 else 0.0),
        _safe_float(normalized_error[0] if len(normalized_error) > 0 else 0.0),
        _safe_float(normalized_error[1] if len(normalized_error) > 1 else 0.0),
        _safe_float(angles.get('yawErrorDeg')),
        _safe_float(angles.get('pitchErrorDeg')),
        _safe_float(angles.get('yawRateDegPerSec')),
        _safe_float(angles.get('pitchRateDegPerSec')),
        _safe_float(angles.get('boxWidthDeg')),
        _safe_float(angles.get('boxHeightDeg')),
        _safe_float(payload.get('visionDt')),
        _safe_float(payload.get('projectionDt')),
        _safe_float(payload.get('visionAgeSec')),
        _safe_float(covariance_diag.get('x')),
        _safe_float(covariance_diag.get('y')),
        _safe_float(covariance_diag.get('xv')),
        _safe_float(covariance_diag.get('yv')),
        _safe_float(covariance_diag.get('w')),
        _safe_float(covariance_diag.get('h')),
        _safe_float(kalman_params.get('dt')),
        _safe_float(kalman_params.get('processNoisePosition')),
        _safe_float(kalman_params.get('processNoiseVelocity')),
        _safe_float(kalman_params.get('processNoiseSize')),
        _safe_float(kalman_params.get('measurementNoisePosition')),
        _safe_float(kalman_params.get('measurementNoiseSize')),
        _safe_float(kalman_params.get('initialCovariance')),
        _safe_float(kalman_params.get('horizontalFovDeg')),
        _safe_float(kalman_params.get('verticalFovDeg')),
    )
