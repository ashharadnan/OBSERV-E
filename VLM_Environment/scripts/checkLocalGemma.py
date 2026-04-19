from pathlib import Path
import sys

model_dir = Path(sys.argv[1] if len(sys.argv) > 1 else 'models/gemma-4-E2B-it')
required = ['config.json', 'processor_config.json', 'tokenizer_config.json']
missing = [name for name in required if not (model_dir / name).exists()]
if not model_dir.exists():
    raise SystemExit(f'Model directory not found: {model_dir}')
if missing:
    raise SystemExit(f'Model directory exists but is missing expected files: {missing}')
print(f'Local Gemma model looks present at {model_dir}')
