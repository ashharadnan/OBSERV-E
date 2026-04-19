from __future__ import annotations

from pathlib import Path
from typing import Dict

_MODEL_CACHE: Dict[str, object] = {}


def loadYoloModel(modelPath: str):
    key = str(Path(modelPath).expanduser().resolve())
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError(
            'Ultralytics is required to load YOLO models. Install dependencies from requirements.txt.'
        ) from error

    model = YOLO(key)
    _MODEL_CACHE[key] = model
    return model
