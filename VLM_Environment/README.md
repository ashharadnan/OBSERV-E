# VLM Environment

This module always uses a local YOLO scene detector to draw bounding boxes and class labels.
The VLM backend is configurable:

- `backend: local` -> local Gemma 4 loaded with Transformers
- `backend: http` -> OpenAI-compatible self-hosted server for later AMD deployment

## Install local Gemma
```bash
python3 -m venv .venv
source .venv/bin/activate
./scripts/installLocalGemma.sh
python scripts/checkLocalGemma.py models/gemma-4-E2B-it
```

## Boxes only (no VLM)
```bash
python scripts/runVlmEnvironment.py --camera 0 --detectorModel models/yolo11n.pt --disableVlm
```

## Boxes + local Gemma
```bash
python scripts/runVlmEnvironment.py   --camera 0   --backend local   --modelPath models/gemma-4-E2B-it   --detectorModel models/yolo11n.pt
```

## Boxes + self-hosted HTTP server
```bash
python scripts/runVlmEnvironment.py   --camera 0   --backend http   --endpoint http://127.0.0.1:8000/v1/chat/completions   --model google/gemma-4-E4B-it   --detectorModel models/yolo11n.pt
```
