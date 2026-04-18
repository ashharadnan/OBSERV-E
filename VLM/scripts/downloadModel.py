import argparse
import shutil
from pathlib import Path


supportedModels = ['yolo11n.pt', 'yolo26n.pt']


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, choices=supportedModels)
    parser.add_argument('--outdir', default='models')
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError('Ultralytics must be installed before downloading a model.') from error

    model = YOLO(args.model)
    resolvedPath = Path(model.ckpt_path if getattr(model, 'ckpt_path', None) else args.model)
    if not resolvedPath.exists():
        raise RuntimeError(f'Ultralytics did not resolve a local checkpoint for {args.model}')

    destinationPath = Path(args.outdir) / args.model
    destinationPath.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolvedPath, destinationPath)
    print(f'Downloaded {args.model} to {destinationPath}')


if __name__ == '__main__':
    main()
