import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', required=True)
    parser.add_argument('--imgsz', type=int, default=640)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError('Ultralytics must be installed before exporting to ONNX.') from error

    model = YOLO(args.weights)
    exportPath = model.export(format='onnx', imgsz=args.imgsz)
    print(f'Exported ONNX model to {exportPath}')


if __name__ == '__main__':
    main()
