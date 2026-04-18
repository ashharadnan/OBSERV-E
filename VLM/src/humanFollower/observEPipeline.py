from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Tuple
import time
import cv2
import yaml

from .hazardDetector import HazardDetector
from .narration import NarrationEngine
from .outreach import OutreachManager
from .profileStore import ProfileStore
from .riskEngine import RiskEngine
from .voiceCommands import VoiceCommandParser
from .groqVisionNarrator import GroqVisionNarrator
from .conversationSpeech import ConversationSpeechEngine


class ObservePipeline:
    def __init__(self, trackingPipeline, configPath: str, hazardModelPath: str, dbPath: Optional[str] = None) -> None:
        with open(configPath, 'r', encoding='utf-8') as inputFile:
            config = yaml.safe_load(inputFile)

        observeConfig = config['observe']
        hazardConfig = config['hazardDetector']
        riskConfig = config['riskEngine']
        narrationConfig = config['narration']
        outreachConfig = config['outreach']
        vlmConfig = config.get('vlm', {})

        self.trackingPipeline = trackingPipeline
        self.hazardDetector = HazardDetector(
            modelPath=hazardModelPath,
            confThreshold=hazardConfig['confThreshold'],
            iouThreshold=hazardConfig['iouThreshold'],
            imageSize=hazardConfig['imageSize'],
            device=hazardConfig['device'],
            pathCorridorRatio=hazardConfig['pathCorridorRatio'],
        )
        self.riskEngine = RiskEngine(**riskConfig)
        self.narration = NarrationEngine(**narrationConfig)
        self.outreach = OutreachManager(**outreachConfig)
        self.voiceParser = VoiceCommandParser()
        self.vlmNarrator = GroqVisionNarrator(**vlmConfig)

        self.userName = observeConfig.get('userName', 'User')
        self.checkInDelaySec = float(observeConfig.get('checkInDelaySec', 10.0))
        self.summaryEveryFrames = int(observeConfig.get('summaryEveryFrames', 45))
        self.immobilityWindowSec = float(observeConfig.get('immobilityWindowSec', 2.0))
        self.locationLabel = observeConfig.get('locationLabel', 'demo area')

        speechConfig = config.get('speech', {})
        speechConfig = dict(speechConfig)
        speechConfig.setdefault('userName', self.userName)
        self.speech = ConversationSpeechEngine(**speechConfig)

        self.store = ProfileStore(dbPath or observeConfig.get('dbPath', 'outputs/observe.db'))
        self.userId = self.store.ensureDefaultUser(name=self.userName, emergencyEnabled=observeConfig.get('emergencyEnabled', False))
        contacts = self.store.getContacts(self.userId)
        if not contacts:
            defaultContacts = observeConfig.get('defaultContacts', [])
            for index, contact in enumerate(defaultContacts, start=1):
                self.store.addContact(
                    userId=self.userId,
                    name=contact.get('name', f'Contact {index}'),
                    phone=contact.get('phone', ''),
                    relation=contact.get('relation', 'trusted_contact'),
                    priorityOrder=index,
                    allowSms=bool(contact.get('allowSms', True)),
                    allowCall=bool(contact.get('allowCall', True)),
                )

        self.trackedCenters = deque()
        self.checkInStartTime: Optional[float] = None
        self.userMarkedOkay = False
        self.lastVoiceSignals: Dict[str, bool] = {
            'help': False,
            'cancel': False,
            'okay': False,
            'stop': False,
            'follow': False,
        }
        self.frameIndex = 0

    def close(self) -> None:
        self.vlmNarrator.close()
        self.store.close()

    def ingestVoiceText(self, text: str) -> Dict[str, bool]:
        self.lastVoiceSignals = self.voiceParser.parseText(text)
        if self.lastVoiceSignals['cancel'] or self.lastVoiceSignals['okay']:
            self.userMarkedOkay = True
            self.checkInStartTime = None
        return dict(self.lastVoiceSignals)

    def _updateMotionHistory(self, payload: Dict, currentTime: float) -> Tuple[float, float]:
        center = payload.get('nextCenter')
        if center is None or not payload.get('targetLocked', False):
            self.trackedCenters.clear()
            return 0.0, 0.0

        centerPoint = (float(center[0]), float(center[1]))
        self.trackedCenters.append((currentTime, centerPoint))
        while self.trackedCenters and (currentTime - self.trackedCenters[0][0]) > self.immobilityWindowSec:
            self.trackedCenters.popleft()

        if len(self.trackedCenters) < 2:
            return 0.0, 0.0

        startTime, startPoint = self.trackedCenters[0]
        endTime, endPoint = self.trackedCenters[-1]
        elapsed = max(1e-3, endTime - startTime)
        dx = endPoint[0] - startPoint[0]
        dy = endPoint[1] - startPoint[1]
        movementDistance = (dx * dx + dy * dy) ** 0.5
        speed = movementDistance / elapsed
        return speed, elapsed

    def _computeFallScore(self, measuredBox, frameHeight: int) -> float:
        if measuredBox is None:
            return 0.0
        x1, y1, x2, y2 = measuredBox
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        centerY = y1 + height / 2.0
        widePosture = width / height
        nearGround = centerY / max(1.0, frameHeight)
        score = 0.0
        if widePosture > 0.95:
            score += min(0.6, (widePosture - 0.95) * 0.8)
        if nearGround > 0.68:
            score += min(0.5, (nearGround - 0.68) * 1.2)
        return max(0.0, min(1.0, score))

    def _computeImmobility(self, speed: float, historySec: float, pathDanger: float) -> float:
        if historySec < max(0.6, self.immobilityWindowSec * 0.6):
            return 0.0
        if speed >= 18.0:
            return 0.0
        base = min(1.0, max(0.0, (18.0 - speed) / 18.0))
        if pathDanger > 0.35:
            base = min(1.0, base + 0.2)
        return base

    def _computeNonResponse(self, currentTime: float, riskScore: float) -> float:
        if self.userMarkedOkay:
            return 0.0
        if riskScore < self.riskEngine.checkInThreshold:
            self.checkInStartTime = None
            return 0.0
        if self.checkInStartTime is None:
            self.checkInStartTime = currentTime
            return 0.0
        elapsed = currentTime - self.checkInStartTime
        return max(0.0, min(1.0, elapsed / max(1.0, self.checkInDelaySec)))

    def _overlayHazards(self, frame, hazards) -> None:
        for hazard in hazards[:8]:
            x1, y1, x2, y2 = [int(value) for value in hazard.bboxXyxy]
            color = (0, 0, 255) if hazard.inPathCorridor else (255, 120, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame,
                f'{hazard.label}:{hazard.dangerScore:.2f}',
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )

    def _overlayState(self, frame, state: Dict) -> None:
        textRows = [
            f"risk:{state['riskScore']:.2f} level:{state['eventLevel']}",
            f"path:{state['pathDanger']:.2f} traffic:{state['trafficThreat']:.2f}",
            f"immobile:{state['immobility']:.2f} nonResponse:{state['nonResponse']:.2f}",
        ]
        if state.get('vlmSummary'):
            textRows.append('vlm:' + str(state['vlmSummary'])[:72])
        elif state.get('vlmError'):
            textRows.append('vlm_error:' + str(state['vlmError'])[:72])
        y = 26
        for row in textRows:
            cv2.putText(frame, row, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
            y += 26

        immediateAlert = state.get('immediateAlert')
        if immediateAlert:
            cv2.putText(frame, immediateAlert[:95], (20, max(120, frame.shape[0] - 55)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)

        speechHistory = state.get('speechHistory', [])
        if speechHistory:
            baseY = frame.shape[0] - 24
            visibleHistory = speechHistory[-2:]
            for historyIndex, historyRow in enumerate(reversed(visibleHistory)):
                y = baseY - historyIndex * 28
                cv2.putText(frame, 'tts: ' + str(historyRow)[:100], (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 220, 0), 2, cv2.LINE_AA)

    def process(self, trackingFrame, hazardFrame=None, voiceText: str = '') -> Dict[str, Any]:
        currentTime = time.time()
        trackingResult = self.trackingPipeline.processFrame(trackingFrame, publishState=False, drawUi=True)
        trackingPayload = trackingResult['payload']
        usedHazardFrame = trackingFrame if hazardFrame is None else hazardFrame
        hazardDetections = self.hazardDetector.predict(usedHazardFrame)
        hazardSummary = self.hazardDetector.summarizeHazards(hazardDetections)

        if voiceText:
            self.ingestVoiceText(voiceText)

        speed, historySec = self._updateMotionHistory(trackingPayload, currentTime)
        fallScore = self._computeFallScore(trackingPayload.get('measuredBoxXyxy'), frameHeight=trackingFrame.shape[0])
        immobility = self._computeImmobility(speed=speed, historySec=historySec, pathDanger=hazardSummary['pathDanger'])

        preliminarySignals = {
            'fallScore': fallScore,
            'hazardProximity': hazardSummary['hazardProximity'],
            'immobility': immobility,
            'nonResponse': 0.0,
            'voiceHelp': 1.0 if self.lastVoiceSignals.get('help', False) else 0.0,
            'pathDanger': hazardSummary['pathDanger'],
            'trafficThreat': hazardSummary['vehicleThreat'],
        }
        preliminaryRisk = self.riskEngine.compute(preliminarySignals)
        nonResponse = self._computeNonResponse(currentTime, preliminaryRisk.riskScore)

        finalSignals = dict(preliminarySignals)
        finalSignals['nonResponse'] = nonResponse
        riskState = self.riskEngine.compute(finalSignals)

        state: Dict[str, Any] = {
            'timestamp': currentTime,
            'frameIndex': self.frameIndex,
            'trackingPayload': trackingPayload,
            'hazards': hazardDetections,
            'topHazard': hazardSummary['topHazard'],
            'fallScore': riskState.fallScore,
            'hazardProximity': riskState.hazardProximity,
            'immobility': riskState.immobility,
            'nonResponse': riskState.nonResponse,
            'voiceHelp': riskState.voiceHelp,
            'pathDanger': riskState.pathDanger,
            'trafficThreat': riskState.trafficThreat,
            'riskScore': riskState.riskScore,
            'eventLevel': riskState.eventLevel,
            'reasons': riskState.reasons,
            'speedPixelsPerSec': float(speed),
            'historySec': float(historySec),
        }

        immediateAlert = self.narration.buildImmediateAlert(state)
        localSummary = self.narration.buildSummary(state, currentTime)
        self.vlmNarrator.submit(usedHazardFrame, state, currentTime)
        latestVlmResult = self.vlmNarrator.getLatestResult()
        latestVlmError = self.vlmNarrator.getLatestError()
        vlmSummary = None if latestVlmResult is None else latestVlmResult.summary
        summary = vlmSummary or localSummary
        state['immediateAlert'] = immediateAlert
        state['summary'] = summary
        state['localSummary'] = localSummary
        state['vlmSummary'] = vlmSummary
        state['vlmError'] = latestVlmError
        state['vlmTimestamp'] = None if latestVlmResult is None else latestVlmResult.timestamp
        state['vlmPriorityHazard'] = None if latestVlmResult is None else latestVlmResult.priorityHazard
        state['vlmRecommendedAction'] = None if latestVlmResult is None else latestVlmResult.recommendedAction
        state['vlmConfidence'] = None if latestVlmResult is None else latestVlmResult.confidence

        speechEvents = self.speech.update(state, currentTime=currentTime)
        state['speechEvents'] = [
            {
                'timestamp': event.timestamp,
                'eventType': event.eventType,
                'text': event.text,
                'priority': event.priority,
                'source': event.source,
            }
            for event in speechEvents
        ]
        state['ttsText'] = None if not speechEvents else speechEvents[-1].text
        state['speechHistory'] = self.speech.getHistory()

        contacts = self.store.getContacts(self.userId)
        escalation = self.outreach.maybeEscalate(
            currentTime=currentTime,
            userName=self.userName,
            eventLevel=riskState.eventLevel,
            riskScore=riskState.riskScore,
            summary=summary or immediateAlert or 'risk detected',
            contacts=contacts,
            location=self.locationLabel,
        )
        state['escalation'] = escalation

        for speechEvent in state.get('speechEvents', []):
            self.store.logEvent(
                timestamp=speechEvent['timestamp'],
                eventType='tts_utterance',
                riskScore=riskState.riskScore,
                summary=speechEvent['text'],
                payload={
                    'eventType': speechEvent['eventType'],
                    'priority': speechEvent['priority'],
                    'source': speechEvent['source'],
                    'frameIndex': state['frameIndex'],
                    'trackingPayload': trackingPayload,
                    'vlmSummary': state.get('vlmSummary'),
                },
                location=self.locationLabel,
            )

        self.store.logEvent(
            timestamp=currentTime,
            eventType='observe_state',
            riskScore=riskState.riskScore,
            summary=summary or immediateAlert or 'no summary',
            payload={
                'eventLevel': riskState.eventLevel,
                'reasons': riskState.reasons,
                'trackingPayload': trackingPayload,
                'topHazard': None if hazardSummary['topHazard'] is None else {
                    'label': hazardSummary['topHazard'].label,
                    'dangerScore': hazardSummary['topHazard'].dangerScore,
                    'side': hazardSummary['topHazard'].side,
                },
                'escalation': escalation,
                'vlmSummary': state.get('vlmSummary'),
                'vlmError': state.get('vlmError'),
                'speechEvents': state.get('speechEvents', []),
                'speechHistory': state.get('speechHistory', []),
            },
            location=self.locationLabel,
        )

        hazardOverlayFrame = usedHazardFrame.copy()
        self._overlayHazards(hazardOverlayFrame, hazardDetections)
        self._overlayState(hazardOverlayFrame, state)
        trackedOverlayFrame = trackingResult['frame'].copy()
        self._overlayState(trackedOverlayFrame, state)

        result = {
            'trackingFrame': trackedOverlayFrame,
            'hazardFrame': hazardOverlayFrame,
            'trackingPayload': trackingPayload,
            'state': state,
        }
        self.frameIndex += 1
        return result
