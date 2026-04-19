# Local Gemma files

## Files changed for the local Gemma build

- `VLM_Environment/scripts/runVlmEnvironment.py`
  - selects `local` or `http` backend
  - still draws local YOLO bounding boxes and class labels
  - still publishes packed environment structs when requested

- `VLM_Environment/src/vlm_environment/local_gemma.py`
  - loads Gemma 4 locally with Transformers
  - accepts camera frames and detector metadata
  - returns the same summary shape as the HTTP narrator

- `VLM_Environment/src/vlm_environment/narrator.py`
  - unchanged HTTP/OpenAI-compatible client for future AMD self-hosting

- `VLM_Environment/configs/vlmEnvironmentFast.yaml`
  - default backend is now `local`
  - default model is `google/gemma-4-E2B-it`
  - default model path is `models/gemma-4-E2B-it`

- `VLM_Environment/requirements.txt`
  - adds Transformers, Accelerate, TorchVision, Pillow, and Hugging Face CLI

- `VLM_Environment/scripts/installLocalGemma.sh`
  - installs dependencies and downloads Gemma 4 E2B to the local models directory

- `VLM_Environment/scripts/checkLocalGemma.py`
  - verifies the local Gemma directory exists before you run the app
