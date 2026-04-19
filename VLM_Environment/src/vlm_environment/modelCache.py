
from __future__ import annotations

from pathlib import Path
from typing import Dict

_MODEL_CACHE: Dict[str, object] = {}


def load_yolo_model(model_path: str):
    key = str(Path(model_path).expanduser().resolve())
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError('Ultralytics is required for VLM environment box overlays. Install requirements.txt.') from error
    model = YOLO(key)
    _MODEL_CACHE[key] = model
    return model
