from typing import Optional, Tuple, List
import cv2
import numpy as np


BboxXyxy = Tuple[float, float, float, float]
BboxXywh = Tuple[int, int, int, int]


def _clampInt(value: float, minimum: int, maximum: int) -> int:
    return int(max(minimum, min(maximum, round(float(value)))))


def sanitizeBoundingBox(frameShape, bboxXyxy: BboxXyxy) -> Optional[BboxXywh]:
    frameHeight, frameWidth = frameShape[:2]
    x1, y1, x2, y2 = bboxXyxy

    x1Int = _clampInt(x1, 0, max(0, frameWidth - 2))
    y1Int = _clampInt(y1, 0, max(0, frameHeight - 2))
    x2Int = _clampInt(x2, x1Int + 1, max(x1Int + 1, frameWidth - 1))
    y2Int = _clampInt(y2, y1Int + 1, max(y1Int + 1, frameHeight - 1))

    width = x2Int - x1Int
    height = y2Int - y1Int
    if width < 2 or height < 2:
        return None

    return x1Int, y1Int, width, height


def xywhToXyxy(bboxXywh: BboxXywh) -> BboxXyxy:
    x, y, width, height = bboxXywh
    return float(x), float(y), float(x + width), float(y + height)


class OpticalFlowBoxTracker:
    def __init__(
        self,
        maxCorners: int = 100,
        qualityLevel: float = 0.01,
        minDistance: float = 4.0,
        winSize: int = 21,
        templateMarginRatio: float = 1.3,
        minTemplateScore: float = 0.50,
    ) -> None:
        self.maxCorners = int(maxCorners)
        self.qualityLevel = float(qualityLevel)
        self.minDistance = float(minDistance)
        self.winSize = int(winSize)
        self.templateMarginRatio = float(templateMarginRatio)
        self.minTemplateScore = float(minTemplateScore)

        self.prevGray = None
        self.prevPoints = None
        self.templatePatch = None
        self.bboxXywh: Optional[BboxXywh] = None
        self.isInitialized = False

    def reset(self) -> None:
        self.prevGray = None
        self.prevPoints = None
        self.templatePatch = None
        self.bboxXywh = None
        self.isInitialized = False

    def _buildGridPoints(self, bboxXywh: BboxXywh) -> np.ndarray:
        x, y, width, height = bboxXywh
        gridCountX = max(3, min(8, width // 12))
        gridCountY = max(3, min(10, height // 12))

        points: List[List[List[float]]] = []
        for yIndex in range(gridCountY):
            for xIndex in range(gridCountX):
                px = x + (xIndex + 0.5) * width / gridCountX
                py = y + (yIndex + 0.5) * height / gridCountY
                points.append([[float(px), float(py)]])
        return np.array(points, dtype=np.float32)

    def _extractPoints(self, grayFrame, bboxXywh: BboxXywh) -> np.ndarray:
        x, y, width, height = bboxXywh
        mask = np.zeros_like(grayFrame)
        mask[y:y + height, x:x + width] = 255
        points = cv2.goodFeaturesToTrack(
            grayFrame,
            maxCorners=self.maxCorners,
            qualityLevel=self.qualityLevel,
            minDistance=self.minDistance,
            mask=mask,
            blockSize=7,
        )
        if points is None or len(points) < 8:
            return self._buildGridPoints(bboxXywh)
        return points.astype(np.float32)

    def initialize(self, frame, bboxXyxy: BboxXyxy) -> bool:
        bboxXywh = sanitizeBoundingBox(frame.shape, bboxXyxy)
        if bboxXywh is None:
            self.reset()
            return False

        grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x, y, width, height = bboxXywh
        self.templatePatch = grayFrame[y:y + height, x:x + width].copy()
        self.prevGray = grayFrame
        self.prevPoints = self._extractPoints(grayFrame, bboxXywh)
        self.bboxXywh = bboxXywh
        self.isInitialized = True
        return True

    def _templateMatch(self, grayFrame) -> Tuple[bool, Optional[BboxXywh]]:
        if self.templatePatch is None or self.bboxXywh is None:
            return False, None

        templateHeight, templateWidth = self.templatePatch.shape[:2]
        if templateHeight < 2 or templateWidth < 2:
            return False, None

        frameHeight, frameWidth = grayFrame.shape[:2]
        x, y, width, height = self.bboxXywh
        searchWidth = max(width, int(width * self.templateMarginRatio))
        searchHeight = max(height, int(height * self.templateMarginRatio))

        searchX1 = max(0, x - searchWidth)
        searchY1 = max(0, y - searchHeight)
        searchX2 = min(frameWidth, x + width + searchWidth)
        searchY2 = min(frameHeight, y + height + searchHeight)
        searchRegion = grayFrame[searchY1:searchY2, searchX1:searchX2]

        if searchRegion.shape[0] < templateHeight or searchRegion.shape[1] < templateWidth:
            return False, None

        response = cv2.matchTemplate(searchRegion, self.templatePatch, cv2.TM_CCOEFF_NORMED)
        _, maxScore, _, maxLocation = cv2.minMaxLoc(response)
        if maxScore < self.minTemplateScore:
            return False, None

        matchedX = searchX1 + int(maxLocation[0])
        matchedY = searchY1 + int(maxLocation[1])
        matchedBox = sanitizeBoundingBox(
            grayFrame.shape,
            (matchedX, matchedY, matchedX + width, matchedY + height),
        )
        return matchedBox is not None, matchedBox

    def update(self, frame) -> Tuple[bool, Optional[BboxXyxy]]:
        if not self.isInitialized or self.bboxXywh is None or self.prevGray is None:
            return False, None

        grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        flowSucceeded = False
        updatedBox: Optional[BboxXywh] = None

        if self.prevPoints is not None and len(self.prevPoints) >= 4:
            nextPoints, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prevGray,
                grayFrame,
                self.prevPoints,
                None,
                winSize=(self.winSize, self.winSize),
                maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
            )
            if nextPoints is not None and status is not None:
                validMask = status.reshape(-1) == 1
                goodOld = self.prevPoints.reshape(-1, 2)[validMask]
                goodNew = nextPoints.reshape(-1, 2)[validMask]

                if len(goodOld) >= 4 and len(goodNew) >= 4:
                    displacement = goodNew - goodOld
                    dx = float(np.median(displacement[:, 0]))
                    dy = float(np.median(displacement[:, 1]))

                    oldSpanX = max(1.0, float(np.max(goodOld[:, 0]) - np.min(goodOld[:, 0])))
                    oldSpanY = max(1.0, float(np.max(goodOld[:, 1]) - np.min(goodOld[:, 1])))
                    newSpanX = max(1.0, float(np.max(goodNew[:, 0]) - np.min(goodNew[:, 0])))
                    newSpanY = max(1.0, float(np.max(goodNew[:, 1]) - np.min(goodNew[:, 1])))
                    scaleX = min(1.18, max(0.84, newSpanX / oldSpanX))
                    scaleY = min(1.18, max(0.84, newSpanY / oldSpanY))

                    x, y, width, height = self.bboxXywh
                    updatedBox = sanitizeBoundingBox(
                        grayFrame.shape,
                        (
                            x + dx,
                            y + dy,
                            x + dx + width * scaleX,
                            y + dy + height * scaleY,
                        ),
                    )
                    flowSucceeded = updatedBox is not None

        if not flowSucceeded:
            templateSucceeded, templateBox = self._templateMatch(grayFrame)
            if templateSucceeded and templateBox is not None:
                updatedBox = templateBox
            else:
                self.prevGray = grayFrame
                self.prevPoints = None
                return False, None

        assert updatedBox is not None
        self.bboxXywh = updatedBox
        x, y, width, height = updatedBox
        self.templatePatch = grayFrame[y:y + height, x:x + width].copy()
        self.prevGray = grayFrame
        self.prevPoints = self._extractPoints(grayFrame, updatedBox)
        return True, xywhToXyxy(updatedBox)


class CorrelationTracker:
    def __init__(self, trackerType: str = 'auto') -> None:
        self.trackerType = trackerType.lower().strip()
        self.tracker = None
        self.backendName = 'none'
        self.isInitialized = False
        self.flowTracker = OpticalFlowBoxTracker()

    def _candidateTrackerTypes(self) -> List[str]:
        if self.trackerType == 'auto':
            return ['kcf', 'mil']
        if self.trackerType in {'lkflow', 'flow', 'opticalflow'}:
            return []
        return [self.trackerType]

    def _createTrackerFromName(self, trackerName: str):
        normalized = trackerName.lower().strip()
        createCandidates = []

        if normalized == 'csrt':
            createCandidates = [
                ('TrackerCSRT', 'create'),
                ('legacy.TrackerCSRT', 'create'),
            ]
        elif normalized == 'kcf':
            createCandidates = [
                ('TrackerKCF', 'create'),
                ('legacy.TrackerKCF', 'create'),
            ]
        elif normalized == 'mil':
            createCandidates = [
                ('TrackerMIL', 'create'),
                ('legacy.TrackerMIL', 'create'),
            ]
        else:
            return None

        for objectPath, methodName in createCandidates:
            currentObject = cv2
            failed = False
            for pathPart in objectPath.split('.'):
                if not hasattr(currentObject, pathPart):
                    failed = True
                    break
                currentObject = getattr(currentObject, pathPart)
            if failed or not hasattr(currentObject, methodName):
                continue
            try:
                return getattr(currentObject, methodName)()
            except Exception:
                continue
        return None

    def reset(self) -> None:
        self.tracker = None
        self.backendName = 'none'
        self.isInitialized = False
        self.flowTracker.reset()

    def initialize(self, frame, bboxXyxy: BboxXyxy) -> None:
        self.reset()
        sanitizedBox = sanitizeBoundingBox(frame.shape, bboxXyxy)
        if sanitizedBox is None:
            return

        flowInitialized = self.flowTracker.initialize(frame, xywhToXyxy(sanitizedBox))

        for trackerName in self._candidateTrackerTypes():
            tracker = self._createTrackerFromName(trackerName)
            if tracker is None:
                continue
            try:
                initResult = tracker.init(frame, sanitizedBox)
                if initResult is None or bool(initResult):
                    self.tracker = tracker
                    self.backendName = trackerName
                    self.isInitialized = True
                    return
            except Exception:
                continue

        if flowInitialized:
            self.tracker = None
            self.backendName = 'lkFlow'
            self.isInitialized = True

    def update(self, frame) -> Tuple[bool, Optional[BboxXyxy]]:
        if not self.isInitialized:
            return False, None

        if self.tracker is not None:
            try:
                ok, xywh = self.tracker.update(frame)
                if ok:
                    x, y, width, height = xywh
                    sanitizedBox = sanitizeBoundingBox(frame.shape, (x, y, x + width, y + height))
                    if sanitizedBox is not None:
                        if self.flowTracker.isInitialized:
                            self.flowTracker.initialize(frame, xywhToXyxy(sanitizedBox))
                        return True, xywhToXyxy(sanitizedBox)
            except Exception:
                pass

        flowOk, flowBox = self.flowTracker.update(frame)
        if flowOk and flowBox is not None:
            self.backendName = 'lkFlow'
            return True, flowBox

        self.reset()
        return False, None
