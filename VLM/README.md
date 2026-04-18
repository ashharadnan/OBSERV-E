# Human Follower + High-Rate Gimbal Predictor Package

This package is built for a hackathon workflow where a camera feed follows one human, draws a live measured and predicted bounding box, and continuously emits a predicted next-state matrix that a gimbal controller can consume.

## What changed in this revision

- Fixed the OpenCV tracker initialization crash by sanitizing the box and falling back safely when an OpenCV tracker backend rejects it.
- Added a robust tracker path that tries OpenCV trackers first and falls back to Lucas-Kanade optical flow plus local template matching.
- Added a high-rate projector loop so you can publish predicted states at **100 to 300 Hz** even if the detector is only running at camera / CPU speed.
- Added explicit training-data preparation scripts for a **human-only robust detector** using COCO and optional CrowdHuman / WiderPerson merges.
- Added both `currentStateMatrix` and `stateMatrix` to the payload. `stateMatrix` is the projected next-state matrix that the gimbal should follow.

## What is included

- Human detector wrapper around Ultralytics YOLO weights
- Single-target lock and reacquisition logic for humans only
- Robust single-object tracker with OpenCV tracker backends and LK optical-flow fallback
- Separate NumPy Kalman filter that predicts the next human state
- High-rate output publisher for control loops running faster than inference
- Optional dataset download and fine-tuning scripts
- Benchmark script to compare models on your AMD mini PC

## Recommended default

Start with `yolo11n.pt` for the hackathon baseline.

If your AMD mini PC likes the newer model better, benchmark `yolo26n.pt` on the same video and keep whichever gives you the best balance of FPS and lock quality.


## OBSERV-E mode: human tracking + VLM environment description

This revision also includes an OBSERV-E demo pipeline that combines:
- a local human-tracking pipeline for following one person
- a local hazard detector for immediate warnings
- an optional Groq vision-language model path for richer scene descriptions

The local tracking and hazard detection stay on-device. The VLM path is optional and runs asynchronously so the camera loop does not stop while the model describes the environment.

### Run OBSERV-E with local narration only

```bash
python scripts/runObserveDemo.py \
  --trackModel models/yolo11n.pt \
  --hazardModel models/yolo11n.pt \
  --trackingCamera 0 \
  --userName Danish \
  --locationLabel "Hackathon demo zone"
```

### Run OBSERV-E with Groq vision enabled

Set your API key first, or pass it directly on the command line:

```bash
export GROQ_API_KEY=your_key_here
```

Then run:

```bash
python scripts/runObserveDemo.py \
  --trackModel models/yolo11n.pt \
  --hazardModel models/yolo11n.pt \
  --trackingCamera 0 \
  --enableVlm \
  --groqModel meta-llama/llama-4-scout-17b-16e-instruct \
  --groqApiKeyEnv GROQ_API_KEY \
  --userName Danish \
  --locationLabel "Hackathon demo zone"
```

Or pass the key directly without relying on shell environment setup:

```bash
python scripts/runObserveDemo.py \
  --trackModel models/yolo11n.pt \
  --hazardModel models/yolo11n.pt \
  --trackingCamera 0 \
  --enableVlm \
  --groqModel meta-llama/llama-4-scout-17b-16e-instruct \
  --groqApiKey your_key_here \
  --userName Danish \
  --locationLabel "Hackathon demo zone"
```

The VLM uses a sampled image frame plus detector metadata and returns a short environment summary in JSON.

## Conversational TTS planning and printed speech output

This revision adds a **conversation-style speech planner** on top of the local hazard logic and VLM summaries.

It does **not** blindly speak every 2 or 3 seconds. Instead, it speaks when something meaningful changes, for example:
- a new obstacle enters the path
- a vehicle appears from the side
- the path becomes clear again
- tracking is lost or recovered
- the system moves into check-in, contact, or emergency escalation
- a new VLM context update becomes relevant after urgent warnings have already been spoken

### What gets printed

Every time the planner decides something should be spoken, `runObserveDemo.py` prints a line like this:

```text
[tts][frame 128] pathHazard: I see a chair on the left side of your path. Shift a little away from it.
```

The most recent spoken line is also stored in:
- `state['ttsText']`
- `state['speechEvents']`
- `outputs/observeSpeechLog.jsonl`
- the `tts_utterance` rows in `outputs/observe.db`

### Read the saved speech log

```bash
python scripts/extractSpeechLog.py --jsonl outputs/observeSpeechLog.jsonl --limit 20
```

## Environment

Python 3.10+ is recommended.

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 1) Download a model

Default stable baseline:

```bash
python scripts/downloadModel.py --model yolo11n.pt
```

Newer CPU-focused option:

```bash
python scripts/downloadModel.py --model yolo26n.pt
```

This saves weights into `models/`.

## 2) Optional: export to ONNX

If you want easier deployment and often better CPU inference portability:

```bash
python scripts/exportOnnx.py --weights models/yolo11n.pt --imgsz 416
```

This creates an ONNX file next to your weights.

## 3) Run on a camera in normal frame-rate mode

```bash
python scripts/runCameraDemo.py \
  --model models/yolo11n.pt \
  --camera 0 \
  --detectEvery 2 \
  --selectionMode closestToCenter \
  --outputMode stdout
```

## 4) Run on a camera with high-rate control output

This is the mode to use for a gimbal controller.

Example at **200 Hz**:

```bash
python scripts/runCameraDemo.py \
  --model models/yolo11n.pt \
  --camera 0 \
  --detectEvery 2 \
  --controlHz 200 \
  --predictionLeadMs 8 \
  --selectionMode closestToCenter \
  --outputMode udpMatrix \
  --udpHost 127.0.0.1 \
  --udpPort 5005
```

Notes:
- `controlHz` is the high-rate projector loop. Set this to `100`, `200`, or `300`.
- `predictionLeadMs` pushes the state slightly into the future for actuator latency.
- Use `udpMatrix` or `stdoutMatrix` if your gimbal process wants the matrix by itself instead of the full JSON payload.
- The detector still runs at the best speed your CPU and camera allow. The **publisher** runs at the higher control rate.

## 5) Headless server mode on the AMD mini PC

```bash
python scripts/runCameraDemo.py \
  --model models/yolo11n.pt \
  --camera 0 \
  --headless \
  --cameraWidth 1280 \
  --cameraHeight 720 \
  --controlHz 200 \
  --predictionLeadMs 8 \
  --outputMode udpMatrix \
  --udpHost 127.0.0.1 \
  --udpPort 5005
```

## 6) Run on a video

```bash
python scripts/runVideoDemo.py \
  --model models/yolo11n.pt \
  --video path/to/input.mp4 \
  --save outputs/demo.mp4 \
  --outputMode jsonl \
  --jsonlPath outputs/gimbalStates.jsonl
```

## Gimbal output format

Each payload now includes both the current filtered state and the projected next state:

```json
{
  "frameIndex": 42,
  "timestamp": 1712345678.12,
  "targetLocked": true,
  "measurementSource": "highRateProjector",
  "currentStateMatrix": [[640.1], [318.4], [5.3], [-0.9], [123.5], [271.0]],
  "stateMatrix": [[645.4], [317.5], [5.3], [-0.9], [123.5], [271.0]],
  "nextCenter": [645.4, 317.5],
  "pixelError": [5.4, -2.5],
  "normalizedError": [0.0042, -0.0035],
  "bboxXyxy": [583.7, 182.0, 707.2, 453.0],
  "measuredBoxXyxy": [580.0, 181.0, 704.0, 452.0],
  "confidence": 0.91
}
```

`stateMatrix` is a **6x1** matrix:

```text
[x]
[y]
[vx]
[vy]
[w]
[h]
```

Where:
- `x`, `y` are the projected target center in image pixels
- `vx`, `vy` are pixel velocities
- `w`, `h` are predicted bounding box size

For the gimbal, `nextCenter` or `stateMatrix[0:2]` is usually the value you want to follow.


## Clear telemetry for Kalman state and actual box state

Each frame payload now includes named dictionaries so you do not have to manually unpack the 6x1 matrix:

```json
{
  "stateVectorOrder": ["x", "y", "xv", "yv", "w", "h"],
  "kalmanState": {
    "x": 640.1,
    "y": 318.4,
    "xv": 5.3,
    "yv": -0.9,
    "w": 123.5,
    "h": 271.0
  },
  "predictedKalmanState": {
    "x": 645.4,
    "y": 317.5,
    "xv": 5.3,
    "yv": -0.9,
    "w": 123.5,
    "h": 271.0
  },
  "actualBoxState": {
    "x": 642.0,
    "y": 316.5,
    "xv": 4.8,
    "yv": -1.2,
    "w": 124.0,
    "h": 271.0
  }
}
```

Meaning:
- `kalmanState` = current filtered state after the Kalman update
- `predictedKalmanState` = projected future state used for control
- `actualBoxState` = the detector or tracker measurement converted into `{x, y, xv, yv, w, h}` using frame-to-frame motion

Important:
- `x` and `y` are **box center** coordinates in pixels
- `xv` and `yv` are **pixels per second**
- the state order is **`[x, y, xv, yv, w, h]`**
- named dictionaries are the easiest source of truth and avoid confusion between `w,h` vs `h,w`

### Where the information is stored

1. Raw per-frame tracking telemetry:
- `outputs/observeTrackingStates.jsonl` when using `scripts/runObserveDemo.py`
- or whatever path you pass to `--jsonlPath`

2. OBSERV-E event log with the tracking payload nested inside SQLite:
- `outputs/observe.db`
- table: `events`
- column: `payloadJson`
- nested field: `trackingPayload`

The raw JSONL file is the best place to inspect every frame.

### Quick way to print the values

```bash
python scripts/extractStateTelemetry.py   --jsonl outputs/observeTrackingStates.jsonl   --limit 20
```

That prints:
- `kalmanState`
- `predictedKalmanState`
- `actualBoxState`
- `bboxXyxy`
- `measuredBoxXyxy`

### Live stdout example

`runObserveDemo.py` also prints these three dictionaries to the terminal each frame:
- `kalmanState`
- `predictedKalmanState`
- `actualBoxState`


## Bounding boxes in the UI

The displayed video uses:
- **green / amber** box for the measured detector or tracker box
- **red** box for the Kalman-predicted next box
- **yellow crosshair** for the image center

That gives you a direct visual check that the person stays centered and that the predictor is leading motion rather than lagging behind it.

## Benchmark on your AMD mini PC

```bash
python scripts/benchmarkModels.py \
  --models models/yolo11n.pt models/yolo26n.pt \
  --video path/to/video.mp4 \
  --frames 200
```

Keep the model that gives you the best real lock quality, not just the highest raw FPS.

## Intentional human-only training for realistic scenes

If you want the strongest human detector for your hackathon environment, build a merged human dataset and fine-tune.

### Step A: download datasets

COCO downloads directly:

```bash
python scripts/downloadDatasets.py --coco --extract
```

CrowdHuman and WiderPerson use official Google Drive / Baidu links, so the script prints where to place them:

```bash
python scripts/downloadDatasets.py --crowdHuman --widerPerson
```

### Step B: prepare the merged human dataset

Example with COCO + CrowdHuman + WiderPerson:

```bash
python scripts/prepareHumanRobustDataset.py \
  --cocoRoot datasets/coco \
  --crowdHumanRoot datasets/crowdHuman \
  --widerPersonRoot datasets/widerPerson \
  --outdir datasets/humanRobust
```

This creates:
- `datasets/humanRobust/images/train`
- `datasets/humanRobust/images/val`
- `datasets/humanRobust/labels/train`
- `datasets/humanRobust/labels/val`
- `datasets/humanRobust/humanRobustMerged.yaml`

### Step C: fine-tune the detector

```bash
python scripts/fineTunePersonModel.py \
  --model models/yolo11n.pt \
  --data datasets/humanRobust/humanRobustMerged.yaml \
  --epochs 40 \
  --imgsz 640 \
  --batch 16 \
  --device cpu
```

If you have a GPU box available for training, use that for the training stage and deploy the resulting weights back to the AMD mini PC.

## Practical tuning tips

- Start with `imgsz=416` on CPU.
- If you need more detector reliability, move to `imgsz=512` or `640` and benchmark again.
- For fast control output, keep `controlHz` high but do **not** expect the detector itself to infer at 200 Hz on CPU.
- For crowded scenes, fine-tune with CrowdHuman included.
- For street / campus / walking scenes, include WiderPerson too.
- If the tracker drifts, lower `detectEvery` from `3` to `2` or `1`.

## Files to edit for hardware integration

- `src/humanFollower/gimbalOutput.py` if your gimbal expects a different wire format
- `src/humanFollower/pipeline.py` if you want custom reacquisition or lock logic
- `src/humanFollower/kalmanFilter.py` if you want a different motion model

## Important note

No vision system can honestly guarantee detection of humans in **every** frame or scene. This package is designed to be practical and robust for a hackathon:
- human-only detector
- reacquisition logic
- tracking fallback
- high-rate motion prediction
- optional fine-tuning on realistic human datasets

That is the correct way to make it much more reliable without pretending it is infallible.

## OBSERV-E MVP extension added

This package now also includes a simple OBSERV-E hackathon layer built on top of the original human follower pipeline.

New pieces added:
- `src/humanFollower/hazardDetector.py`
- `src/humanFollower/riskEngine.py`
- `src/humanFollower/narration.py`
- `src/humanFollower/voiceCommands.py`
- `src/humanFollower/profileStore.py`
- `src/humanFollower/outreach.py`
- `src/humanFollower/observEPipeline.py`
- `scripts/runObserveDemo.py`
- `configs/observeMvp.yaml`

### What the OBSERV-E MVP does

- keeps the existing person-following and gimbal prediction flow
- runs a second detection pass for general hazards like cars, bicycles, chairs, benches, and other obstacles
- estimates path danger, hazard proximity, and traffic threat from image geometry
- computes a practical multi-signal risk score
- produces immediate warning text and slower scene summaries
- logs contact escalation events to JSONL instead of directly calling 911
- stores user / contact / event data in SQLite for demo use

### Recommended demo command

Single camera demo using one general YOLO model for both tracking and hazard detection:

```bash
python scripts/runObserveDemo.py \
  --trackModel models/yolo11n.pt \
  --hazardModel models/yolo11n.pt \
  --trackingCamera 0 \
  --userName Danish \
  --locationLabel "Hackathon demo zone"
```

Video demo:

```bash
python scripts/runObserveDemo.py \
  --trackModel models/yolo11n.pt \
  --hazardModel models/yolo11n.pt \
  --video path/to/input.mp4 \
  --save outputs/observeDemo.mp4 \
  --locationLabel "Campus walkway demo"
```

### Important note for models

If you fine-tune the tracking detector to be person-only, keep a separate general-purpose hazard detector weight for the hazard camera.

Good hackathon default:
- tracking model: person-focused or general YOLO
- hazard model: general YOLO such as `yolo11n.pt`

### Current scope

This is a practical hackathon MVP, not a fully deployed assistive device. The outreach path currently logs the escalation event and message content instead of directly placing calls. That keeps the system demo-safe while still showing the end-to-end decision flow.
