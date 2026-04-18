import argparse
from pathlib import Path
import sys
import threading
import time
import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from humanFollower.pipeline import HumanFollowerPipeline


def applyOverrides(configPath: Path, args) -> Path:
    with open(configPath, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)

    config['tracking']['detectEvery'] = args.detectEvery
    config['tracking']['selectionMode'] = args.selectionMode
    config['tracking']['commandLookaheadSec'] = args.predictionLeadMs / 1000.0
    config['output']['outputMode'] = args.outputMode
    config['output']['udpHost'] = args.udpHost
    config['output']['udpPort'] = args.udpPort
    if args.jsonlPath is not None:
        config['output']['jsonlPath'] = args.jsonlPath

    temporaryPath = configPath.parent / '_runtime_camera_config.yaml'
    with open(temporaryPath, 'w', encoding='utf-8') as outputFile:
        yaml.safe_dump(config, outputFile, sort_keys=False)
    return temporaryPath


def runSingleRateLoop(capture, pipeline: HumanFollowerPipeline, args) -> None:
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        result = pipeline.processFrame(frame, publishState=True, drawUi=not args.headless)
        if not args.headless:
            cv2.imshow('humanFollower', result['frame'])
            pressed = cv2.waitKey(1) & 0xFF
            if pressed in (27, ord('q')):
                break


def runHighRateLoop(capture, pipeline: HumanFollowerPipeline, args) -> None:
    stopEvent = threading.Event()
    frameLock = threading.Lock()
    latestUiFrame = {'frame': None}

    def visionLoop() -> None:
        while not stopEvent.is_set():
            ok, frame = capture.read()
            if not ok:
                stopEvent.set()
                break
            result = pipeline.processFrame(frame, publishState=False, drawUi=not args.headless)
            if not args.headless:
                with frameLock:
                    latestUiFrame['frame'] = result['frame']

    def controlLoop() -> None:
        loopPeriod = 1.0 / max(1.0, float(args.controlHz))
        nextTick = time.perf_counter()
        while not stopEvent.is_set():
            payload = pipeline.sampleProjectionPayload(predictFromNowDt=args.predictionLeadMs / 1000.0)
            pipeline.publisher.publish(payload)
            nextTick += loopPeriod
            sleepSeconds = nextTick - time.perf_counter()
            if sleepSeconds > 0.0:
                time.sleep(sleepSeconds)
            else:
                nextTick = time.perf_counter()

    visionThread = threading.Thread(target=visionLoop, daemon=True)
    controlThread = threading.Thread(target=controlLoop, daemon=True)
    visionThread.start()
    controlThread.start()

    try:
        while not stopEvent.is_set():
            if not args.headless:
                with frameLock:
                    displayFrame = None if latestUiFrame['frame'] is None else latestUiFrame['frame'].copy()
                if displayFrame is not None:
                    cv2.imshow('humanFollower', displayFrame)
                pressed = cv2.waitKey(1) & 0xFF
                if pressed in (27, ord('q')):
                    stopEvent.set()
                    break
            else:
                time.sleep(0.01)
    finally:
        stopEvent.set()
        visionThread.join(timeout=2.0)
        controlThread.join(timeout=2.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--config', default='configs/default.yaml')
    parser.add_argument('--detectEvery', type=int, default=2)
    parser.add_argument('--selectionMode', choices=['closestToCenter', 'highestConfidence', 'largest'], default='closestToCenter')
    parser.add_argument('--outputMode', choices=['stdout', 'udp', 'jsonl', 'stdoutMatrix', 'udpMatrix'], default='stdout')
    parser.add_argument('--udpHost', default='127.0.0.1')
    parser.add_argument('--udpPort', type=int, default=5005)
    parser.add_argument('--jsonlPath', default=None)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--controlHz', type=float, default=0.0)
    parser.add_argument('--predictionLeadMs', type=float, default=8.0)
    parser.add_argument('--cameraWidth', type=int, default=0)
    parser.add_argument('--cameraHeight', type=int, default=0)
    args = parser.parse_args()

    configPath = applyOverrides(Path(args.config), args)
    pipeline = HumanFollowerPipeline(modelPath=args.model, configPath=str(configPath))
    capture = cv2.VideoCapture(args.camera)

    if args.cameraWidth > 0:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.cameraWidth)
    if args.cameraHeight > 0:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.cameraHeight)

    if not capture.isOpened():
        raise RuntimeError(f'Unable to open camera index {args.camera}')

    try:
        if args.controlHz > 0.0:
            runHighRateLoop(capture, pipeline, args)
        else:
            runSingleRateLoop(capture, pipeline, args)
    finally:
        capture.release()
        pipeline.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
