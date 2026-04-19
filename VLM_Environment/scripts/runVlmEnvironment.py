import argparse
from pathlib import Path
import os
import socket
import sys
import time
from urllib.parse import urlparse

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from vlm_environment.cstruct import pack_environment_packet
from vlm_environment.local_gemma import LocalGemmaClient
from vlm_environment.narrator import EnvironmentVlmClient
from vlm_environment.sceneDetector import SceneDetector


class EnvironmentPacketPublisher:
    def __init__(self, outputMode: str = 'none', udpHost: str = '127.0.0.1', udpPort: int = 5010) -> None:
        self.outputMode = outputMode
        self.udpHost = str(udpHost)
        self.udpPort = int(udpPort)
        self.sock = None
        if self.outputMode == 'udpStruct':
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def publish(self, frameIndex: int, timestamp: float, summary, detections) -> None:
        if self.outputMode == 'none':
            return
        packet = pack_environment_packet(frameIndex=frameIndex, timestamp=timestamp, summary=summary, detections=detections)
        if self.outputMode == 'stdoutStructHex':
            print({'environmentPacketHex': packet.hex()}, flush=True)
            return
        if self.outputMode == 'udpStruct':
            assert self.sock is not None
            self.sock.sendto(packet, (self.udpHost, self.udpPort))
            return
        raise ValueError(f'Unsupported outputMode: {self.outputMode}')

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def resizeMaxWidth(frame, maxWidth: int):
    if frame is None or maxWidth <= 0:
        return frame
    height, width = frame.shape[:2]
    if width <= maxWidth:
        return frame
    scale = maxWidth / float(width)
    return cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))


def overlayScene(frame, detections, summary, latestError, backendName: str, remoteEnabled: bool):
    out = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = [int(v) for v in detection.bboxXyxy]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 220, 0), 2)
        label = f'{detection.label} {detection.confidence:.2f}'
        cv2.putText(out, label[:48], (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 0), 2, cv2.LINE_AA)
    lines = ['VLM environment mode + scene boxes']
    lines.append(f"objects: {len(detections)}  backend: {backendName}  enabled: {'on' if remoteEnabled else 'off'}")
    if summary is not None:
        lines.append('summary: ' + str(summary.summary))
        if summary.priorityHazard:
            lines.append('hazard: ' + str(summary.priorityHazard))
        if summary.recommendedAction:
            lines.append('action: ' + str(summary.recommendedAction))
    elif latestError:
        lines.append('vlm: ' + str(latestError)[:95])
    else:
        lines.append('vlm: waiting for first response')
    y = 28
    for line in lines[:5]:
        cv2.putText(out, line[:110], (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2, cv2.LINE_AA)
        y += 28
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--video', default=None)
    parser.add_argument('--config', default='configs/vlmEnvironmentFast.yaml')
    parser.add_argument('--backend', choices=['http', 'local'], default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--modelPath', default=None)
    parser.add_argument('--endpoint', default=None)
    parser.add_argument('--apiKeyEnv', default=None)
    parser.add_argument('--apiKey', default='')
    parser.add_argument('--detectorModel', default='models/yolo11n.pt')
    parser.add_argument('--disableVlm', action='store_true')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--maxFrameWidth', type=int, default=416)
    parser.add_argument('--printEvery', type=int, default=4)
    parser.add_argument('--outputMode', choices=['none', 'stdoutStructHex', 'udpStruct'], default='none')
    parser.add_argument('--udpHost', default='127.0.0.1')
    parser.add_argument('--udpPort', type=int, default=5010)
    args = parser.parse_args()

    with open(args.config, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)
    vlmConfig = dict(config.get('vlm', {}))
    detectorConfig = dict(config.get('detector', {}))

    if args.backend:
        vlmConfig['backend'] = args.backend
    if args.model:
        vlmConfig['model'] = args.model
    if args.modelPath:
        vlmConfig['modelPath'] = args.modelPath
    if args.endpoint:
        vlmConfig['endpoint'] = args.endpoint
    if args.apiKeyEnv:
        vlmConfig['apiKeyEnv'] = args.apiKeyEnv
    if args.apiKey:
        vlmConfig['apiKey'] = args.apiKey
        os.environ[vlmConfig.get('apiKeyEnv', 'VLM_API_KEY')] = args.apiKey

    backend = str(vlmConfig.get('backend', 'local')).strip().lower()
    vlmEnabled = bool(vlmConfig.get('enabled', True)) and not args.disableVlm
    endpointToCheck = str(vlmConfig.get('endpoint', '')).strip()
    hostToCheck = urlparse(endpointToCheck).hostname or ''
    if backend == 'http' and hostToCheck in {'your_amd_server', 'example.com', 'localhost.localdomain'}:
        print({'warning': 'Placeholder VLM host detected. Remote VLM disabled; showing local scene boxes only.'}, flush=True)
        vlmEnabled = False

    detector = SceneDetector(
        modelPath=args.detectorModel,
        confThreshold=float(detectorConfig.get('confThreshold', 0.25)),
        iouThreshold=float(detectorConfig.get('iouThreshold', 0.45)),
        imageSize=int(detectorConfig.get('imageSize', 224)),
        device=str(detectorConfig.get('device', 'cpu')),
        allowedLabels=list(detectorConfig.get('allowedLabels', [])) or None,
        maxDetections=int(detectorConfig.get('maxDetections', 8)),
    )

    if backend == 'local':
        vlmConfig['enabled'] = vlmEnabled
        client = LocalGemmaClient(**vlmConfig)
    else:
        vlmConfig['enabled'] = vlmEnabled
        client = EnvironmentVlmClient(**vlmConfig)

    publisher = EnvironmentPacketPublisher(outputMode=args.outputMode, udpHost=args.udpHost, udpPort=args.udpPort)
    capture = cv2.VideoCapture(args.video if args.video else args.camera)
    if not capture.isOpened():
        raise RuntimeError('Unable to open camera or video source')

    frameIndex = 0
    lastPrintedError = None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame = resizeMaxWidth(frame, args.maxFrameWidth)
            now = time.time()
            detections = detector.predict(frame)
            if vlmEnabled:
                client.submit(frame, now, detections=detections)
            latest = client.getLatestResult() if vlmEnabled else None
            latestError = client.getLatestError() if vlmEnabled else None
            publisher.publish(frameIndex=frameIndex, timestamp=now, summary=latest, detections=detections)

            if frameIndex % max(1, args.printEvery) == 0:
                payload = {
                    'frameIndex': frameIndex,
                    'backend': backend,
                    'vlmEnabled': vlmEnabled,
                    'detections': [
                        {
                            'label': item.label,
                            'classId': int(item.classId),
                            'confidence': round(float(item.confidence), 3),
                            'bboxXyxy': [round(float(v), 1) for v in item.bboxXyxy],
                        }
                        for item in detections
                    ],
                }
                if latest is not None:
                    payload.update({
                        'summary': latest.summary,
                        'priorityHazard': latest.priorityHazard,
                        'recommendedAction': latest.recommendedAction,
                        'vlmConfidence': latest.confidence,
                    })
                elif latestError:
                    payload['vlmError'] = latestError
                print(payload, flush=True)
                lastPrintedError = latestError
            elif latestError and latestError != lastPrintedError and frameIndex % max(1, args.printEvery * 3) == 0:
                print({'vlmError': latestError}, flush=True)
                lastPrintedError = latestError

            frameIndex += 1
            if not args.headless:
                cv2.imshow('vlmEnvironment', overlayScene(frame, detections, latest, latestError, backend, vlmEnabled))
                pressed = cv2.waitKey(1) & 0xFF
                if pressed in (27, ord('q')):
                    break
            else:
                time.sleep(0.01)
    finally:
        capture.release()
        publisher.close()
        client.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
