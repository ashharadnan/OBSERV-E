
from __future__ import annotations

import struct
from typing import Iterable, Optional

ENV_PACKET_MAGIC = 0x564C4D45
MAX_OBJECTS = 8
OBJECT_STRUCT = struct.Struct('<H H f f f f f 24s')
PACKET_HEADER_STRUCT = struct.Struct('<II f f B 3x 160s 64s 64s')


def _safe_text(value: Optional[str], size: int) -> bytes:
    text = '' if value is None else str(value)
    encoded = text.encode('utf-8', errors='ignore')[: max(0, size - 1)]
    return encoded + b'\x00' * (size - len(encoded))


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def pack_environment_packet(frame_index: int, timestamp: float, summary, detections: Iterable) -> bytes:
    summary_text = getattr(summary, 'summary', '') if summary is not None else ''
    hazard_text = getattr(summary, 'priorityHazard', '') if summary is not None else ''
    action_text = getattr(summary, 'recommendedAction', '') if summary is not None else ''
    confidence = _safe_float(getattr(summary, 'confidence', 0.0) if summary is not None else 0.0)
    detections = list(detections)[:MAX_OBJECTS]
    header = PACKET_HEADER_STRUCT.pack(
        int(ENV_PACKET_MAGIC),
        int(frame_index),
        _safe_float(timestamp),
        confidence,
        int(len(detections)),
        _safe_text(summary_text, 160),
        _safe_text(hazard_text, 64),
        _safe_text(action_text, 64),
    )
    body = bytearray()
    for detection in detections:
        bbox = getattr(detection, 'bboxXyxy', (0.0, 0.0, 0.0, 0.0))
        body.extend(OBJECT_STRUCT.pack(
            int(getattr(detection, 'classId', 0)),
            0,
            _safe_float(getattr(detection, 'confidence', 0.0)),
            _safe_float(bbox[0] if len(bbox) > 0 else 0.0),
            _safe_float(bbox[1] if len(bbox) > 1 else 0.0),
            _safe_float(bbox[2] if len(bbox) > 2 else 0.0),
            _safe_float(bbox[3] if len(bbox) > 3 else 0.0),
            _safe_text(getattr(detection, 'label', ''), 24),
        ))
    while len(detections) < MAX_OBJECTS:
        body.extend(OBJECT_STRUCT.pack(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, _safe_text('', 24)))
        detections.append(None)
    return header + bytes(body)
