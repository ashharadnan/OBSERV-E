import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--project', default='outputs/fineTuneRuns')
    parser.add_argument('--name', default='humanRobustFineTune')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError('Ultralytics must be installed before training.') from error

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        project=args.project,
        name=args.name,
        device=args.device,
        classes=[0],
        close_mosaic=10,
        degrees=0.0,
        translate=0.08,
        scale=0.30,
        shear=0.0,
        perspective=0.0005,
        fliplr=0.5,
        mixup=0.05,
        copy_paste=0.10,
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.25,
    )


if __name__ == '__main__':
    main()
