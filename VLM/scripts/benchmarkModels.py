import argparse
import time
from pathlib import Path
import cv2
import yaml
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from humanFollower.detector import PersonDetector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--video', required=True)
    parser.add_argument('--frames', type=int, default=200)
    parser.add_argument('--config', default='configs/default.yaml')
    args = parser.parse_args()

    with open(args.config, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)
    detectorConfig = config['detector']

    for modelPath in args.models:
        detector = PersonDetector(
            modelPath=modelPath,
            confThreshold=detectorConfig['confThreshold'],
            iouThreshold=detectorConfig['iouThreshold'],
            imageSize=detectorConfig['imageSize'],
            device=detectorConfig['device'],
            personClassId=detectorConfig['personClassId'],
        )
        capture = cv2.VideoCapture(args.video)
        frameCount = 0
        startTime = time.time()

        while frameCount < args.frames:
            ok, frame = capture.read()
            if not ok:
                break
            detector.predict(frame)
            frameCount += 1

        elapsed = max(1e-6, time.time() - startTime)
        fps = frameCount / elapsed
        print(f'{modelPath}: {fps:.2f} FPS over {frameCount} frames')
        capture.release()


if __name__ == '__main__':
    main()
