from typing import Optional, Tuple, List
import numpy as np


StateMatrix = List[List[float]]


class ConstantVelocityBoxKalmanFilter:
    def __init__(
        self,
        dt: float = 1.0,
        processNoisePosition: float = 1.0,
        processNoiseVelocity: float = 10.0,
        processNoiseSize: float = 1.0,
        measurementNoisePosition: float = 8.0,
        measurementNoiseSize: float = 12.0,
        initialCovariance: float = 50.0,
    ) -> None:
        self.dt = float(dt)
        self.processNoisePosition = float(processNoisePosition)
        self.processNoiseVelocity = float(processNoiseVelocity)
        self.processNoiseSize = float(processNoiseSize)
        self.measurementNoisePosition = float(measurementNoisePosition)
        self.measurementNoiseSize = float(measurementNoiseSize)
        self.initialCovariance = float(initialCovariance)

        self.stateVector = np.zeros((6, 1), dtype=np.float64)
        self.covariance = np.eye(6, dtype=np.float64) * self.initialCovariance
        self.isInitialized = False

        self.measurementMatrix = np.array(
            [
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        self.measurementNoise = np.diag(
            [
                self.measurementNoisePosition,
                self.measurementNoisePosition,
                self.measurementNoiseSize,
                self.measurementNoiseSize,
            ]
        ).astype(np.float64)

    def reset(self) -> None:
        self.stateVector = np.zeros((6, 1), dtype=np.float64)
        self.covariance = np.eye(6, dtype=np.float64) * self.initialCovariance
        self.isInitialized = False

    def _buildTransition(self, dt: float) -> np.ndarray:
        usedDt = max(1e-4, float(dt))
        return np.array(
            [
                [1.0, 0.0, usedDt, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, usedDt, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    def _buildProcessNoise(self, dt: float) -> np.ndarray:
        usedDt = max(1e-4, float(dt))
        positionNoise = self.processNoisePosition * usedDt * usedDt
        velocityNoise = self.processNoiseVelocity * usedDt
        sizeNoise = self.processNoiseSize * usedDt
        return np.diag(
            [
                positionNoise,
                positionNoise,
                velocityNoise,
                velocityNoise,
                sizeNoise,
                sizeNoise,
            ]
        ).astype(np.float64)

    def initialize(self, centerX: float, centerY: float, width: float, height: float) -> None:
        self.stateVector = np.array(
            [[centerX], [centerY], [0.0], [0.0], [max(1.0, width)], [max(1.0, height)]],
            dtype=np.float64,
        )
        self.covariance = np.eye(6, dtype=np.float64) * self.initialCovariance
        self.isInitialized = True

    def predict(self, dt: Optional[float] = None) -> np.ndarray:
        if not self.isInitialized:
            raise RuntimeError('Kalman filter must be initialized before predict().')

        usedDt = self.dt if dt is None else float(dt)
        transition = self._buildTransition(usedDt)
        processNoise = self._buildProcessNoise(usedDt)

        self.stateVector = transition @ self.stateVector
        self.covariance = transition @ self.covariance @ transition.T + processNoise
        return self.stateVector.copy()

    def update(self, centerX: float, centerY: float, width: float, height: float) -> np.ndarray:
        if not self.isInitialized:
            self.initialize(centerX, centerY, width, height)
            return self.stateVector.copy()

        measurement = np.array(
            [[centerX], [centerY], [max(1.0, width)], [max(1.0, height)]],
            dtype=np.float64,
        )
        innovation = measurement - (self.measurementMatrix @ self.stateVector)
        innovationCovariance = self.measurementMatrix @ self.covariance @ self.measurementMatrix.T + self.measurementNoise
        kalmanGain = self.covariance @ self.measurementMatrix.T @ np.linalg.inv(innovationCovariance)

        self.stateVector = self.stateVector + kalmanGain @ innovation
        identity = np.eye(6, dtype=np.float64)
        self.covariance = (identity - kalmanGain @ self.measurementMatrix) @ self.covariance
        return self.stateVector.copy()

    def predictFuture(self, dt: Optional[float] = None) -> np.ndarray:
        if not self.isInitialized:
            raise RuntimeError('Kalman filter must be initialized before predictFuture().')

        usedDt = self.dt if dt is None else float(dt)
        transition = self._buildTransition(usedDt)
        return (transition @ self.stateVector).copy()

    @staticmethod
    def projectStateMatrix(stateMatrix: StateMatrix, dt: float) -> StateMatrix:
        numericState = np.array(stateMatrix, dtype=np.float64).reshape(6, 1)
        usedDt = max(1e-4, float(dt))
        transition = np.array(
            [
                [1.0, 0.0, usedDt, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, usedDt, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        projectedState = transition @ numericState
        return [[float(value)] for value in projectedState.reshape(-1)]

    def getCurrentStateMatrix(self) -> StateMatrix:
        return [[float(value)] for value in self.stateVector.reshape(-1)]

    def getFutureStateMatrix(self, dt: Optional[float] = None) -> StateMatrix:
        futureState = self.predictFuture(dt=dt)
        return [[float(value)] for value in futureState.reshape(-1)]


    def getCurrentNamedState(self) -> dict:
        return {
            'x': float(self.stateVector[0, 0]),
            'y': float(self.stateVector[1, 0]),
            'xv': float(self.stateVector[2, 0]),
            'yv': float(self.stateVector[3, 0]),
            'w': max(1.0, float(self.stateVector[4, 0])),
            'h': max(1.0, float(self.stateVector[5, 0])),
        }

    def getFutureNamedState(self, dt: Optional[float] = None) -> dict:
        futureState = self.predictFuture(dt=dt)
        return {
            'x': float(futureState[0, 0]),
            'y': float(futureState[1, 0]),
            'xv': float(futureState[2, 0]),
            'yv': float(futureState[3, 0]),
            'w': max(1.0, float(futureState[4, 0])),
            'h': max(1.0, float(futureState[5, 0])),
        }

    def getCurrentBox(self) -> Tuple[float, float, float, float]:
        centerX = float(self.stateVector[0, 0])
        centerY = float(self.stateVector[1, 0])
        width = max(1.0, float(self.stateVector[4, 0]))
        height = max(1.0, float(self.stateVector[5, 0]))
        return centerX, centerY, width, height

    def getFutureCenter(self, dt: Optional[float] = None) -> Tuple[float, float]:
        futureState = self.predictFuture(dt=dt)
        return float(futureState[0, 0]), float(futureState[1, 0])
