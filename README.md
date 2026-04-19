# OBSERV-E Gemma Local Build

This build has two independent modules:

- `CNN_Follower/`: single-person YOLO + tracker + Kalman + upsampled projector + packed C struct output
- `VLM_Environment/`: local YOLO scene detector for bounding boxes/classes + local Gemma 4 narration by default + packed C struct output

## Important note

The Gemma **code** is fully implemented in this build, but the Gemma **weights are not embedded in the zip**.
You must download the model once on your machine because the weights are large and require a Hugging Face download/auth flow.

## Quick run

### CNN follower
```bash
cd CNN_Follower
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/runCnnFollower.py --model models/yolo11n.pt --camera 0 --printEvery 10
```

### Install local Gemma 4 E2B
```bash
cd ../VLM_Environment
python3 -m venv .venv
source .venv/bin/activate
./scripts/installLocalGemma.sh
python scripts/checkLocalGemma.py models/gemma-4-E2B-it
```

### VLM environment with boxes + local Gemma
```bash
python scripts/runVlmEnvironment.py   --camera 0   --backend local   --modelPath models/gemma-4-E2B-it   --detectorModel models/yolo11n.pt   --printEvery 10
```

### VLM environment with boxes only
```bash
python scripts/runVlmEnvironment.py --camera 0 --detectorModel models/yolo11n.pt --disableVlm --printEvery 10
```

### Future self-hosted server mode
```bash
python scripts/runVlmEnvironment.py   --camera 0   --backend http   --endpoint http://YOUR_SERVER:8000/v1/chat/completions   --model google/gemma-4-E4B-it   --detectorModel models/yolo11n.pt   --printEvery 10
```

The packed C packet layout is in `include/gimbal_packets.h`.
