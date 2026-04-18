from typing import Dict, Optional
import json
import socket
import time
from pathlib import Path


class GimbalStatePublisher:
    def __init__(
        self,
        outputMode: str = 'stdout',
        udpHost: str = '127.0.0.1',
        udpPort: int = 5005,
        jsonlPath: Optional[str] = None,
    ) -> None:
        self.outputMode = outputMode
        self.udpHost = udpHost
        self.udpPort = int(udpPort)
        self.jsonlPath = jsonlPath
        self.udpSocket = None
        self.jsonlFile = None

        if self.outputMode in ('udp', 'udpMatrix'):
            self.udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        elif self.outputMode == 'jsonl':
            if not self.jsonlPath:
                raise ValueError('jsonlPath must be provided when outputMode=jsonl')
            jsonlPath = Path(self.jsonlPath)
            jsonlPath.parent.mkdir(parents=True, exist_ok=True)
            self.jsonlFile = open(jsonlPath, 'a', encoding='utf-8')

    def publish(self, payload: Dict) -> None:
        serialized = json.dumps(payload, separators=(',', ':'))
        matrixOnly = json.dumps(payload.get('stateMatrix'), separators=(',', ':'))

        if self.outputMode == 'stdout':
            print(serialized, flush=True)
            return

        if self.outputMode == 'stdoutMatrix':
            print(matrixOnly, flush=True)
            return

        if self.outputMode == 'udp':
            assert self.udpSocket is not None
            self.udpSocket.sendto(serialized.encode('utf-8'), (self.udpHost, self.udpPort))
            return

        if self.outputMode == 'udpMatrix':
            assert self.udpSocket is not None
            self.udpSocket.sendto(matrixOnly.encode('utf-8'), (self.udpHost, self.udpPort))
            return

        if self.outputMode == 'jsonl':
            assert self.jsonlFile is not None
            self.jsonlFile.write(serialized + '\n')
            self.jsonlFile.flush()
            return

        raise ValueError(f'Unsupported outputMode: {self.outputMode}')

    def close(self) -> None:
        if self.udpSocket is not None:
            self.udpSocket.close()
            self.udpSocket = None
        if self.jsonlFile is not None:
            self.jsonlFile.close()
            self.jsonlFile = None


def buildPayload(
    frameIndex: int,
    bboxXyxy,
    confidence: float,
    measurementSource: str,
    targetLocked: bool,
    stateMatrix,
    nextCenter,
    pixelError,
    normalizedError,
    currentStateMatrix=None,
    measuredBoxXyxy=None,
    kalmanState=None,
    predictedKalmanState=None,
    actualBoxState=None,
    extraFields: Optional[Dict] = None,
) -> Dict:
    payload = {
        'frameIndex': int(frameIndex),
        'timestamp': time.time(),
        'targetLocked': bool(targetLocked),
        'measurementSource': measurementSource,
        'stateVectorOrder': ['x', 'y', 'xv', 'yv', 'w', 'h'],
        'stateMatrix': stateMatrix,
        'currentStateMatrix': currentStateMatrix,
        'kalmanState': kalmanState,
        'predictedKalmanState': predictedKalmanState,
        'actualBoxState': actualBoxState,
        'nextCenter': [float(nextCenter[0]), float(nextCenter[1])] if nextCenter is not None else None,
        'pixelError': [float(pixelError[0]), float(pixelError[1])] if pixelError is not None else None,
        'normalizedError': [float(normalizedError[0]), float(normalizedError[1])] if normalizedError is not None else None,
        'bboxXyxy': [float(value) for value in bboxXyxy] if bboxXyxy is not None else None,
        'measuredBoxXyxy': [float(value) for value in measuredBoxXyxy] if measuredBoxXyxy is not None else None,
        'confidence': float(confidence),
    }
    if extraFields:
        payload.update(extraFields)
    return payload
