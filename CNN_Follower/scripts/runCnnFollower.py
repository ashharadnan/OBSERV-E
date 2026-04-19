
import argparse
from pathlib import Path
import sys
import threading
import time
import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cnn_follower.pipeline import HumanFollowerPipeline
from cnn_follower.upsampleProjector import HighRateKalmanProjector


def buildConsoleSummary(visionPayload, projectionPayload):
    if visionPayload is None:
        return {'status': 'waiting_for_frames'}

    summary = {
        'frameIndex': visionPayload.get('frameIndex'),
        'targetLocked': visionPayload.get('targetLocked'),
        'confidence': visionPayload.get('confidence'),
        'measurementSource': visionPayload.get('measurementSource'),
        'measuredBoxXyxy': visionPayload.get('measuredBoxXyxy'),
        'predictedBoxXyxy': visionPayload.get('bboxXyxy'),
        'kalmanState': visionPayload.get('kalmanState'),
        'predictedKalmanState': visionPayload.get('predictedKalmanState'),
        'actualBoxState': visionPayload.get('actualBoxState'),
        'angles': visionPayload.get('angles'),
        'visionDt': visionPayload.get('visionDt'),
        'transportHint': 'Use include/gimbal_packets.h for binary packet layout.',
    }
    if projectionPayload is not None:
        summary['upsampledProjection'] = {
            'measurementSource': projectionPayload.get('measurementSource'),
            'stateMatrix': projectionPayload.get('stateMatrix'),
            'predictedKalmanState': projectionPayload.get('predictedKalmanState'),
            'angles': projectionPayload.get('angles'),
            'visionAgeSec': projectionPayload.get('visionAgeSec'),
            'projectionDt': projectionPayload.get('projectionDt'),
        }
    return summary


def resizeMaxWidth(frame, maxWidth: int):
    if frame is None or maxWidth <= 0:
        return frame
    height, width = frame.shape[:2]
    if width <= maxWidth:
        return frame
    scale = maxWidth / float(width)
    return cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))


def applyOverrides(configPath: Path, args) -> Path:
    with open(configPath, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)

    config['tracking']['detectEvery'] = args.detectEvery
    config['tracking']['selectionMode'] = args.selectionMode
    config['tracking']['commandLookaheadSec'] = args.predictionLeadMs / 1000.0
    config['output']['outputMode'] = args.outputMode
    config['output']['udpHost'] = args.udpHost
    config['output']['udpPort'] = args.udpPort
    if args.jsonlPath:
        config['output']['jsonlPath'] = args.jsonlPath

    cameraConfig = config.setdefault('camera', {})
    if args.horizontalFovDeg is not None:
        cameraConfig['horizontalFovDeg'] = args.horizontalFovDeg
    if args.verticalFovDeg is not None:
        cameraConfig['verticalFovDeg'] = args.verticalFovDeg
    if args.maxFrameWidth is not None:
        cameraConfig['maxFrameWidth'] = args.maxFrameWidth
    if args.captureWidth is not None:
        cameraConfig['captureWidth'] = args.captureWidth
    if args.captureHeight is not None:
        cameraConfig['captureHeight'] = args.captureHeight
    if args.controlHz is not None:
        cameraConfig['upsampleControlHz'] = args.controlHz

    temporaryPath = configPath.parent / '_runtime_cnn_config.yaml'
    with open(temporaryPath, 'w', encoding='utf-8') as outputFile:
        yaml.safe_dump(config, outputFile, sort_keys=False)
    return temporaryPath


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='models/yolo11n.pt')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--video', default=None)
    parser.add_argument('--config', default='configs/cnnFollowerFast.yaml')
    parser.add_argument('--detectEvery', type=int, default=8)
    parser.add_argument('--selectionMode', choices=['closestToCenter', 'highestConfidence', 'largest'], default='closestToCenter')
    parser.add_argument('--outputMode', choices=['none', 'stdout', 'udp', 'jsonl', 'stdoutMatrix', 'udpMatrix', 'stdoutStructHex', 'udpStruct'], default='none')
    parser.add_argument('--udpHost', default='127.0.0.1')
    parser.add_argument('--udpPort', type=int, default=5005)
    parser.add_argument('--jsonlPath', default=None)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--controlHz', type=float, default=60.0)
    parser.add_argument('--predictionLeadMs', type=float, default=0.0)
    parser.add_argument('--cameraWidth', '--captureWidth', dest='captureWidth', type=int, default=640)
    parser.add_argument('--cameraHeight', '--captureHeight', dest='captureHeight', type=int, default=360)
    parser.add_argument('--maxFrameWidth', type=int, default=416)
    parser.add_argument('--horizontalFovDeg', type=float, default=78.0)
    parser.add_argument('--verticalFovDeg', type=float, default=49.0)
    parser.add_argument('--printEvery', type=int, default=15)
    args = parser.parse_args()

    configPath = applyOverrides(Path(args.config), args)
    pipeline = HumanFollowerPipeline(modelPath=args.model, configPath=str(configPath))

    capture = cv2.VideoCapture(args.video if args.video else args.camera)
    if args.captureWidth > 0:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.captureWidth)
    if args.captureHeight > 0:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.captureHeight)
    try:
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    if not capture.isOpened():
        raise RuntimeError('Unable to open camera or video source')

    stopEvent = threading.Event()
    frameLock = threading.Lock()
    latestUiFrame = {'frame': None}
    latestPayload = {'payload': None}

    def visionLoop() -> None:
        while not stopEvent.is_set():
            ok, frame = capture.read()
            if not ok:
                stopEvent.set()
                break
            frame = resizeMaxWidth(frame, args.maxFrameWidth)
            result = pipeline.processFrame(frame, publishState=False, drawUi=not args.headless)
            payload = result['payload']
            latestPayload['payload'] = payload
            if payload['frameIndex'] % max(1, args.printEvery) == 0:
                projectionPayload = pipeline.sampleProjectionPayload(predictFromNowDt=args.predictionLeadMs / 1000.0)
                print(buildConsoleSummary(payload, projectionPayload), flush=True)
            if not args.headless:
                with frameLock:
                    latestUiFrame['frame'] = result['frame']

    projector = HighRateKalmanProjector(
        pipeline=pipeline,
        controlHz=args.controlHz,
        predictionLeadMs=args.predictionLeadMs,
    )

    visionThread = threading.Thread(target=visionLoop, daemon=True)
    visionThread.start()
    if args.controlHz > 0.0:
        projector.start()

    try:
        while not stopEvent.is_set():
            if not args.headless:
                with frameLock:
                    displayFrame = None if latestUiFrame['frame'] is None else latestUiFrame['frame'].copy()
                if displayFrame is not None:
                    cv2.imshow('cnnFollower', displayFrame)
                pressed = cv2.waitKey(1) & 0xFF
                if pressed in (27, ord('q')):
                    stopEvent.set()
                    break
            else:
                time.sleep(0.01)
    finally:
        stopEvent.set()
        projector.stop()
        visionThread.join(timeout=2.0)
        capture.release()
        pipeline.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
