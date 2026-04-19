from typing import Optional, Dict, Any
import threading
import time
import cv2
import yaml

from .correlationTracker import CorrelationTracker
from .detector import PersonDetector
from .geometry import clampBox, xyxyToXywhCenter, xywhCenterToXyxy
from .kalmanFilter import ConstantVelocityBoxKalmanFilter
from .targetSelector import TargetSelector
from .gimbalOutput import GimbalStatePublisher, buildPayload
from .stateTelemetry import measurementBoxToState, stateMatrixToNamedState
from .angles import computeAngleState


class HumanFollowerPipeline:
    def __init__(self, modelPath: str, configPath: str) -> None:
        with open(configPath, 'r', encoding='utf-8') as inputFile:
            config = yaml.safe_load(inputFile)

        detectorConfig = config['detector']
        trackingConfig = config['tracking']
        kalmanConfig = config['kalman']
        outputConfig = config['output']
        cameraConfig = config.get('camera', {})

        self.detector = PersonDetector(
            modelPath=modelPath,
            confThreshold=detectorConfig['confThreshold'],
            iouThreshold=detectorConfig['iouThreshold'],
            imageSize=detectorConfig['imageSize'],
            device=detectorConfig['device'],
            personClassId=detectorConfig['personClassId'],
        )
        self.selector = TargetSelector(
            selectionMode=trackingConfig['selectionMode'],
            maxAssociationDistanceRatio=trackingConfig['maxAssociationDistanceRatio'],
            minAssociationIou=trackingConfig['minAssociationIou'],
        )
        self.kalmanFilter = ConstantVelocityBoxKalmanFilter(**kalmanConfig)
        self.tracker = CorrelationTracker(trackerType=trackingConfig['trackerType'])
        self.publisher = GimbalStatePublisher(**outputConfig)

        self.detectEvery = int(trackingConfig['detectEvery'])
        self.maxLostFrames = int(trackingConfig['maxLostFrames'])
        self.maxPredictionAgeSec = float(trackingConfig.get('maxPredictionAgeSec', 0.75))
        self.commandLookaheadSec = float(trackingConfig.get('commandLookaheadSec', 0.0))
        self.horizontalFovDeg = float(cameraConfig.get('horizontalFovDeg', 78.0))
        self.verticalFovDeg = float(cameraConfig.get('verticalFovDeg', 49.0))
        self.kalmanParams = {
            'dt': float(kalmanConfig.get('dt', self.kalmanFilter.dt)),
            'processNoisePosition': float(kalmanConfig.get('processNoisePosition', self.kalmanFilter.processNoisePosition)),
            'processNoiseVelocity': float(kalmanConfig.get('processNoiseVelocity', self.kalmanFilter.processNoiseVelocity)),
            'processNoiseSize': float(kalmanConfig.get('processNoiseSize', self.kalmanFilter.processNoiseSize)),
            'measurementNoisePosition': float(kalmanConfig.get('measurementNoisePosition', self.kalmanFilter.measurementNoisePosition)),
            'measurementNoiseSize': float(kalmanConfig.get('measurementNoiseSize', self.kalmanFilter.measurementNoiseSize)),
            'initialCovariance': float(kalmanConfig.get('initialCovariance', self.kalmanFilter.initialCovariance)),
            'horizontalFovDeg': float(self.horizontalFovDeg),
            'verticalFovDeg': float(self.verticalFovDeg),
        }

        self.lostFrames = 0
        self.frameIndex = 0
        self.lastBox = None
        self.lastConfidence = 0.0
        self.lastTime = None
        self.lastMeasurementState = None
        self.lastMeasurementTimestamp = None

        self.snapshotLock = threading.Lock()
        self.latestSnapshot = {
            'frameIndex': 0,
            'visionTimestamp': 0.0,
            'frameWidth': 0,
            'frameHeight': 0,
            'targetLocked': False,
            'confidence': 0.0,
            'measurementSource': 'none',
            'currentStateMatrix': None,
            'measuredBoxXyxy': None,
            'actualBoxState': None,
            'kalmanState': None,
        }
        self.latestAnnotatedFrame = None

    def close(self) -> None:
        self.publisher.close()

    def _computeDt(self) -> float:
        currentTime = time.time()
        if self.lastTime is None:
            self.lastTime = currentTime
            return self.kalmanFilter.dt

        dt = max(1e-3, min(0.25, currentTime - self.lastTime))
        self.lastTime = currentTime
        return dt

    def _annotateFrame(
        self,
        frame,
        measuredBox,
        predictedBox,
        nextCenter,
        measurementSource: str,
        targetLocked: bool,
        confidence: float,
        angleState,
        kalmanState,
        predictedKalmanState,
    ):
        annotatedFrame = frame.copy()
        frameHeight, frameWidth = annotatedFrame.shape[:2]
        frameCenterX = int(frameWidth / 2)
        frameCenterY = int(frameHeight / 2)

        cv2.circle(annotatedFrame, (frameCenterX, frameCenterY), 5, (0, 255, 255), -1)
        cv2.line(annotatedFrame, (frameCenterX - 18, frameCenterY), (frameCenterX + 18, frameCenterY), (0, 255, 255), 1)
        cv2.line(annotatedFrame, (frameCenterX, frameCenterY - 18), (frameCenterX, frameCenterY + 18), (0, 255, 255), 1)

        if measuredBox is not None:
            x1, y1, x2, y2 = [int(value) for value in measuredBox]
            measurementColor = (0, 255, 0) if measurementSource == 'detector' else (255, 200, 0)
            cv2.rectangle(annotatedFrame, (x1, y1), (x2, y2), measurementColor, 2)
            cv2.putText(
                annotatedFrame,
                f'person {confidence:.2f} {measurementSource}',
                (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                measurementColor,
                2,
                cv2.LINE_AA,
            )

        if predictedBox is not None:
            x1, y1, x2, y2 = [int(value) for value in predictedBox]
            cv2.rectangle(annotatedFrame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(
                annotatedFrame,
                'kalman predicted person',
                (x1, min(frameHeight - 10, y2 + 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        if nextCenter is not None:
            nextX, nextY = int(nextCenter[0]), int(nextCenter[1])
            cv2.circle(annotatedFrame, (nextX, nextY), 6, (0, 0, 255), -1)
            cv2.line(annotatedFrame, (frameCenterX, frameCenterY), (nextX, nextY), (0, 0, 255), 2)

        statusText = 'LOCKED' if targetLocked else 'SEARCHING'
        cv2.putText(
            annotatedFrame,
            statusText,
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0) if targetLocked else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotatedFrame,
            f'tracker:{self.tracker.backendName}',
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        info_lines = []
        if angleState is not None:
            info_lines.append(
                f"yaw:{angleState.get('yawErrorDeg', 0.0):.2f} pitch:{angleState.get('pitchErrorDeg', 0.0):.2f}"
            )
            info_lines.append(
                f"yawRate:{angleState.get('yawRateDegPerSec', 0.0):.2f} pitchRate:{angleState.get('pitchRateDegPerSec', 0.0):.2f}"
            )
        if predictedKalmanState is not None:
            info_lines.append(
                f"pred x:{predictedKalmanState.get('x', 0.0):.1f} y:{predictedKalmanState.get('y', 0.0):.1f} "
                f"vx:{predictedKalmanState.get('xv', 0.0):.1f} vy:{predictedKalmanState.get('yv', 0.0):.1f}"
            )
            info_lines.append(
                f"pred w:{predictedKalmanState.get('w', 0.0):.1f} h:{predictedKalmanState.get('h', 0.0):.1f}"
            )
        elif kalmanState is not None:
            info_lines.append(
                f"curr x:{kalmanState.get('x', 0.0):.1f} y:{kalmanState.get('y', 0.0):.1f} "
                f"vx:{kalmanState.get('xv', 0.0):.1f} vy:{kalmanState.get('yv', 0.0):.1f}"
            )

        y = max(90, frameHeight - 110)
        for line in info_lines[:4]:
            cv2.putText(
                annotatedFrame,
                line,
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 24

        return annotatedFrame

    def _updateFromBox(self, frame, bboxXyxy, confidence: float, source: str, currentTime: float) -> Dict[str, Any]:
        frameHeight, frameWidth = frame.shape[:2]
        selectedBox = clampBox(bboxXyxy, frameWidth, frameHeight)
        centerX, centerY, width, height = xyxyToXywhCenter(selectedBox)
        self.kalmanFilter.update(centerX, centerY, width, height)
        actualBoxState = measurementBoxToState(
            selectedBox,
            timestamp=currentTime,
            previousState=self.lastMeasurementState,
            previousTimestamp=self.lastMeasurementTimestamp,
        )
        self.lastMeasurementState = actualBoxState
        self.lastMeasurementTimestamp = float(currentTime)
        self.lastBox = selectedBox
        self.lastConfidence = float(confidence)
        self.lostFrames = 0
        return {
            'selectedBox': selectedBox,
            'selectedConfidence': float(confidence),
            'measurementSource': source,
            'targetLocked': True,
            'actualBoxState': actualBoxState,
        }

    def processFrame(self, frame, publishState: bool = True, drawUi: bool = True) -> Dict[str, Any]:
        frameHeight, frameWidth = frame.shape[:2]
        currentTime = time.time()
        dt = self._computeDt()

        if self.kalmanFilter.isInitialized:
            self.kalmanFilter.predict(dt=dt)

        measuredBox = None
        actualBoxState = None
        selectedConfidence = self.lastConfidence
        measurementSource = 'none'
        targetLocked = False

        shouldDetect = (
            (self.frameIndex % max(1, self.detectEvery) == 0)
            or (not self.tracker.isInitialized)
            or (self.lostFrames > 0)
        )

        if shouldDetect:
            detections = self.detector.predict(frame)
            predictedCenter = self.kalmanFilter.getFutureCenter(dt=dt) if self.kalmanFilter.isInitialized else None
            selectedDetection = self.selector.select(
                detections=detections,
                frameWidth=frameWidth,
                frameHeight=frameHeight,
                predictedCenter=predictedCenter,
                previousBox=self.lastBox,
            )

            if selectedDetection is not None:
                detectionResult = self._updateFromBox(
                    frame,
                    selectedDetection.bboxXyxy,
                    confidence=selectedDetection.confidence,
                    source='detector',
                    currentTime=currentTime,
                )
                measuredBox = detectionResult['selectedBox']
                actualBoxState = detectionResult['actualBoxState']
                selectedConfidence = detectionResult['selectedConfidence']
                measurementSource = detectionResult['measurementSource']
                targetLocked = detectionResult['targetLocked']
                self.tracker.initialize(frame, measuredBox)
            else:
                trackerOk, trackerBox = self.tracker.update(frame)
                if trackerOk and trackerBox is not None:
                    trackerResult = self._updateFromBox(
                        frame,
                        trackerBox,
                        confidence=self.lastConfidence,
                        source='tracker',
                        currentTime=currentTime,
                    )
                    measuredBox = trackerResult['selectedBox']
                    actualBoxState = trackerResult['actualBoxState']
                    selectedConfidence = trackerResult['selectedConfidence']
                    measurementSource = trackerResult['measurementSource']
                    targetLocked = trackerResult['targetLocked']
                else:
                    self.lostFrames += 1
        else:
            trackerOk, trackerBox = self.tracker.update(frame)
            if trackerOk and trackerBox is not None:
                trackerResult = self._updateFromBox(
                    frame,
                    trackerBox,
                    confidence=self.lastConfidence,
                    source='tracker',
                    currentTime=currentTime,
                )
                measuredBox = trackerResult['selectedBox']
                actualBoxState = trackerResult['actualBoxState']
                selectedConfidence = trackerResult['selectedConfidence']
                measurementSource = trackerResult['measurementSource']
                targetLocked = trackerResult['targetLocked']
            else:
                self.lostFrames += 1

        if not targetLocked and self.kalmanFilter.isInitialized and self.lostFrames <= self.maxLostFrames:
            measurementSource = 'predictionOnly'
            targetLocked = True
            selectedConfidence = max(0.0, self.lastConfidence * 0.98)

        if self.lostFrames > self.maxLostFrames:
            self.tracker.reset()
            self.kalmanFilter.reset()
            self.lastBox = None
            self.lastConfidence = 0.0
            self.lastMeasurementState = None
            self.lastMeasurementTimestamp = None
            measuredBox = None
            actualBoxState = None
            selectedConfidence = 0.0
            measurementSource = 'none'
            targetLocked = False

        predictedBox = None
        nextCenter = None
        stateMatrix = None
        currentStateMatrix = None
        kalmanState = None
        predictedKalmanState = None
        covarianceDiag = None
        pixelError = None
        normalizedError = None

        if self.kalmanFilter.isInitialized:
            currentStateMatrix = self.kalmanFilter.getCurrentStateMatrix()
            stateMatrix = self.kalmanFilter.getFutureStateMatrix(dt=max(dt, self.commandLookaheadSec))
            kalmanState = stateMatrixToNamedState(currentStateMatrix)
            predictedKalmanState = stateMatrixToNamedState(stateMatrix)
            covarianceDiag = self.kalmanFilter.getCovarianceDiagonal()

            nextCenter = (float(stateMatrix[0][0]), float(stateMatrix[1][0]))
            futureWidth = max(1.0, float(stateMatrix[4][0]))
            futureHeight = max(1.0, float(stateMatrix[5][0]))
            predictedBox = clampBox(
                xywhCenterToXyxy(nextCenter[0], nextCenter[1], futureWidth, futureHeight),
                frameWidth,
                frameHeight,
            )
            frameCenter = (frameWidth / 2.0, frameHeight / 2.0)
            pixelError = (nextCenter[0] - frameCenter[0], nextCenter[1] - frameCenter[1])
            normalizedError = (pixelError[0] / max(1.0, frameWidth), pixelError[1] / max(1.0, frameHeight))

        angleState = computeAngleState(
            frameWidth=frameWidth,
            frameHeight=frameHeight,
            nextCenter=nextCenter,
            predictedKalmanState=predictedKalmanState,
            horizontalFovDeg=self.horizontalFovDeg,
            verticalFovDeg=self.verticalFovDeg,
        )

        payload = buildPayload(
            frameIndex=self.frameIndex,
            bboxXyxy=predictedBox,
            confidence=selectedConfidence,
            measurementSource=measurementSource,
            targetLocked=targetLocked,
            stateMatrix=stateMatrix,
            currentStateMatrix=currentStateMatrix,
            kalmanState=kalmanState,
            predictedKalmanState=predictedKalmanState,
            actualBoxState=actualBoxState,
            nextCenter=nextCenter,
            pixelError=pixelError,
            normalizedError=normalizedError,
            measuredBoxXyxy=measuredBox,
            extraFields={
                'trackerBackend': self.tracker.backendName,
                'lostFrames': int(self.lostFrames),
                'visionDt': float(dt),
                'angles': angleState,
                'covarianceDiag': covarianceDiag,
                'kalmanParams': dict(self.kalmanParams),
            },
        )
        if publishState:
            self.publisher.publish(payload)

        annotatedFrame = self._annotateFrame(
            frame,
            measuredBox=measuredBox,
            predictedBox=predictedBox,
            nextCenter=nextCenter,
            measurementSource=measurementSource,
            targetLocked=targetLocked,
            confidence=selectedConfidence,
            angleState=angleState,
            kalmanState=kalmanState,
            predictedKalmanState=predictedKalmanState,
        ) if drawUi else None

        with self.snapshotLock:
            self.latestSnapshot = {
                'frameIndex': int(self.frameIndex),
                'visionTimestamp': float(currentTime),
                'frameWidth': int(frameWidth),
                'frameHeight': int(frameHeight),
                'targetLocked': bool(targetLocked),
                'confidence': float(selectedConfidence),
                'measurementSource': measurementSource,
                'currentStateMatrix': currentStateMatrix,
                'measuredBoxXyxy': measuredBox,
                'actualBoxState': actualBoxState,
                'kalmanState': kalmanState,
                'horizontalFovDeg': float(self.horizontalFovDeg),
                'verticalFovDeg': float(self.verticalFovDeg),
                'kalmanParams': dict(self.kalmanParams),
                'covarianceDiag': covarianceDiag,
            }
            self.latestAnnotatedFrame = None if annotatedFrame is None else annotatedFrame.copy()

        result = {
            'frame': annotatedFrame,
            'payload': payload,
            'targetLocked': targetLocked,
            'detectedThisFrame': bool(shouldDetect),
        }
        self.frameIndex += 1
        return result

    def getLatestAnnotatedFrame(self):
        with self.snapshotLock:
            if self.latestAnnotatedFrame is None:
                return None
            return self.latestAnnotatedFrame.copy()

    def sampleProjectionPayload(self, predictFromNowDt: float = 0.0) -> Dict[str, Any]:
        with self.snapshotLock:
            snapshot = dict(self.latestSnapshot)

        currentStateMatrix = snapshot.get('currentStateMatrix')
        if currentStateMatrix is None:
            return buildPayload(
                frameIndex=snapshot.get('frameIndex', 0),
                bboxXyxy=None,
                confidence=0.0,
                measurementSource='none',
                targetLocked=False,
                stateMatrix=None,
                currentStateMatrix=None,
                kalmanState=None,
                predictedKalmanState=None,
                actualBoxState=snapshot.get('actualBoxState'),
                nextCenter=None,
                pixelError=None,
                normalizedError=None,
                measuredBoxXyxy=None,
                extraFields={
                    'publisherSource': 'highRateProjector',
                    'visionAgeSec': None,
                    'kalmanParams': dict(snapshot.get('kalmanParams', self.kalmanParams)),
                },
            )

        frameWidth = max(1, int(snapshot['frameWidth']))
        frameHeight = max(1, int(snapshot['frameHeight']))
        visionAgeSec = max(0.0, time.time() - float(snapshot['visionTimestamp']))
        totalProjectionDt = visionAgeSec + max(0.0, float(predictFromNowDt))
        projectedStateMatrix = ConstantVelocityBoxKalmanFilter.projectStateMatrix(currentStateMatrix, dt=totalProjectionDt)

        nextCenter = (float(projectedStateMatrix[0][0]), float(projectedStateMatrix[1][0]))
        futureWidth = max(1.0, float(projectedStateMatrix[4][0]))
        futureHeight = max(1.0, float(projectedStateMatrix[5][0]))
        predictedBox = clampBox(
            xywhCenterToXyxy(nextCenter[0], nextCenter[1], futureWidth, futureHeight),
            frameWidth,
            frameHeight,
        )
        frameCenter = (frameWidth / 2.0, frameHeight / 2.0)
        pixelError = (nextCenter[0] - frameCenter[0], nextCenter[1] - frameCenter[1])
        normalizedError = (pixelError[0] / max(1.0, frameWidth), pixelError[1] / max(1.0, frameHeight))
        targetLocked = bool(snapshot['targetLocked']) and visionAgeSec <= self.maxPredictionAgeSec
        projectedNamedState = stateMatrixToNamedState(projectedStateMatrix)
        angleState = computeAngleState(
            frameWidth=frameWidth,
            frameHeight=frameHeight,
            nextCenter=nextCenter,
            predictedKalmanState=projectedNamedState,
            horizontalFovDeg=float(snapshot.get('horizontalFovDeg', self.horizontalFovDeg)),
            verticalFovDeg=float(snapshot.get('verticalFovDeg', self.verticalFovDeg)),
        )
        covarianceDiag = snapshot.get('covarianceDiag')

        return buildPayload(
            frameIndex=int(snapshot['frameIndex']),
            bboxXyxy=predictedBox,
            confidence=float(snapshot['confidence']),
            measurementSource='highRateProjector' if targetLocked else 'staleProjection',
            targetLocked=targetLocked,
            stateMatrix=projectedStateMatrix,
            currentStateMatrix=currentStateMatrix,
            kalmanState=stateMatrixToNamedState(currentStateMatrix),
            predictedKalmanState=projectedNamedState,
            actualBoxState=snapshot.get('actualBoxState'),
            nextCenter=nextCenter,
            pixelError=pixelError,
            normalizedError=normalizedError,
            measuredBoxXyxy=snapshot.get('measuredBoxXyxy'),
            extraFields={
                'publisherSource': 'highRateProjector',
                'visionAgeSec': float(visionAgeSec),
                'projectionDt': float(totalProjectionDt),
                'angles': angleState,
                'covarianceDiag': covarianceDiag,
                'kalmanParams': dict(self.kalmanParams),
            },
        )
