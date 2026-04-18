from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional
import json
import time


@dataclass
class SpeechEvent:
    timestamp: float
    eventType: str
    text: str
    priority: int
    source: str


class ConversationSpeechEngine:
    def __init__(
        self,
        userName: str = 'User',
        enabled: bool = True,
        minGapSec: float = 1.2,
        interruptGapSec: float = 0.55,
        sameHazardCooldownSec: float = 5.0,
        contextCooldownSec: float = 3.5,
        clearPathHoldSec: float = 1.0,
        clearPathCooldownSec: float = 5.0,
        nonResponseReminderSec: float = 3.0,
        historySize: int = 4,
        logPath: str = 'outputs/observeSpeechLog.jsonl',
    ) -> None:
        self.userName = str(userName)
        self.enabled = bool(enabled)
        self.minGapSec = float(minGapSec)
        self.interruptGapSec = float(interruptGapSec)
        self.sameHazardCooldownSec = float(sameHazardCooldownSec)
        self.contextCooldownSec = float(contextCooldownSec)
        self.clearPathHoldSec = float(clearPathHoldSec)
        self.clearPathCooldownSec = float(clearPathCooldownSec)
        self.nonResponseReminderSec = float(nonResponseReminderSec)
        self.history: Deque[str] = deque(maxlen=max(1, int(historySize)))
        self.logPath = Path(logPath)
        self.logPath.parent.mkdir(parents=True, exist_ok=True)

        self.lastSpokenTime = 0.0
        self.lastEventLevel = 0
        self.lastTargetLocked: Optional[bool] = None
        self.lastHazardSignature: Optional[str] = None
        self.lastHazardSeverityBucket = 0
        self.lastTrafficBucket = 0
        self.lastPathBucket = 0
        self.lastVlmSeenTimestamp = 0.0
        self.lastVlmSpokenTimestamp = 0.0
        self.pendingContext: Optional[Dict[str, Any]] = None
        self.lastSpokenByKey: Dict[str, float] = {}
        self.clearPathSince: Optional[float] = None

    def getHistory(self) -> List[str]:
        return list(self.history)

    def update(self, state: Dict[str, Any], currentTime: Optional[float] = None) -> List[SpeechEvent]:
        if not self.enabled:
            return []

        now = time.time() if currentTime is None else float(currentTime)
        payload = state.get('trackingPayload', {})
        targetLocked = bool(payload.get('targetLocked', False))
        eventLevel = int(state.get('eventLevel', 0))
        topHazard = state.get('topHazard')
        pathDanger = float(state.get('pathDanger', 0.0))
        trafficThreat = float(state.get('trafficThreat', 0.0))
        nonResponse = float(state.get('nonResponse', 0.0))
        immediateAlert = str(state.get('immediateAlert') or '').strip()
        localSummary = str(state.get('localSummary') or '').strip()
        vlmSummary = str(state.get('vlmSummary') or '').strip()
        vlmAction = str(state.get('vlmRecommendedAction') or '').strip()
        vlmTimestamp = float(state.get('vlmTimestamp') or 0.0)

        candidates: List[SpeechEvent] = []

        if self.lastTargetLocked is None:
            self.lastTargetLocked = targetLocked
        elif self.lastTargetLocked and not targetLocked:
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='trackingLost',
                    text='I lost sight of you for a moment. Please step back into view or say here.',
                    priority=100,
                    source='tracking',
                )
            )
        elif (not self.lastTargetLocked) and targetLocked:
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='trackingRecovered',
                    text='I see you again. I am back with you.',
                    priority=88,
                    source='tracking',
                )
            )
        self.lastTargetLocked = targetLocked

        if eventLevel >= 4 and self.lastEventLevel < 4:
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='emergencyEscalation',
                    text='This looks like an emergency. I am escalating now.',
                    priority=120,
                    source='risk',
                )
            )
        elif eventLevel >= 3 and self.lastEventLevel < 3:
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='contactEscalation',
                    text='I still think you may need help. I am contacting your trusted person now.',
                    priority=115,
                    source='risk',
                )
            )
        elif eventLevel >= 2 and self.lastEventLevel < 2:
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='checkIn',
                    text='I think something may be wrong. Are you okay? Say I am okay or say cancel.',
                    priority=110,
                    source='risk',
                )
            )
        elif eventLevel >= 2 and nonResponse >= 0.45 and self._cooldownPassed('checkInReminder', now, self.nonResponseReminderSec):
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='checkInReminder',
                    text='I still have not heard from you. Please say I am okay if you are safe.',
                    priority=112,
                    source='risk',
                )
            )

        hazardCandidate = self._buildHazardCandidate(
            topHazard=topHazard,
            pathDanger=pathDanger,
            trafficThreat=trafficThreat,
            immediateAlert=immediateAlert,
            now=now,
        )
        if hazardCandidate is not None:
            candidates.append(hazardCandidate)

        if vlmTimestamp > self.lastVlmSeenTimestamp:
            self.lastVlmSeenTimestamp = vlmTimestamp
            contextText = self._buildContextText(vlmSummary=vlmSummary, vlmAction=vlmAction, localSummary=localSummary)
            if contextText:
                self.pendingContext = {
                    'timestamp': now,
                    'text': contextText,
                    'priority': 46 if eventLevel <= 1 else 36,
                }

        if self.pendingContext is not None and self._cooldownPassed('contextSpeech', now, self.contextCooldownSec):
            candidates.append(
                SpeechEvent(
                    timestamp=now,
                    eventType='contextUpdate',
                    text=str(self.pendingContext['text']),
                    priority=int(self.pendingContext['priority']),
                    source='vlm' if vlmSummary else 'local_context',
                )
            )

        chosen = self._chooseEvent(candidates, now)
        self.lastEventLevel = eventLevel

        if topHazard is None or (pathDanger < 0.25 and trafficThreat < 0.25):
            if self.lastHazardSignature is not None:
                if self.clearPathSince is None:
                    self.clearPathSince = now
                elif (now - self.clearPathSince) >= self.clearPathHoldSec and self._cooldownPassed('pathClear', now, self.clearPathCooldownSec):
                    clearText = 'Okay, that immediate obstacle is no longer in your path.'
                    if chosen is None and (now - self.lastSpokenTime) >= self.minGapSec:
                        chosen = SpeechEvent(
                            timestamp=now,
                            eventType='pathClear',
                            text=clearText,
                            priority=42,
                            source='hazard',
                        )
                    self.lastHazardSignature = None
                    self.lastHazardSeverityBucket = 0
                    self.lastTrafficBucket = 0
                    self.lastPathBucket = 0
            else:
                self.clearPathSince = None
        else:
            self.clearPathSince = None

        events: List[SpeechEvent] = []
        if chosen is not None:
            events.append(chosen)
            self.lastSpokenTime = now
            self.lastSpokenByKey[chosen.eventType] = now
            if chosen.eventType in {'pathHazard', 'trafficThreat'} and self.lastHazardSignature is not None:
                self.lastSpokenByKey[f'hazard:{self.lastHazardSignature}'] = now
            if chosen.eventType == 'contextUpdate':
                self.lastSpokenByKey['contextSpeech'] = now
                self.lastVlmSpokenTimestamp = self.lastVlmSeenTimestamp
                self.pendingContext = None
            self.history.append(chosen.text)
            self._logEvent(chosen, state)

        return events

    def _buildHazardCandidate(self, topHazard, pathDanger: float, trafficThreat: float, immediateAlert: str, now: float) -> Optional[SpeechEvent]:
        if topHazard is None:
            return None

        severity = max(float(getattr(topHazard, 'dangerScore', 0.0)), pathDanger, trafficThreat)
        isVehicle = getattr(topHazard, 'label', '') in {'car', 'truck', 'bus', 'motorcycle', 'bicycle', 'scooter', 'train'}
        if severity < (0.28 if not isVehicle else 0.24):
            return None

        hazardSignature = self._hazardSignature(topHazard)
        severityBucket = self._dangerBucket(severity)
        pathBucket = self._dangerBucket(pathDanger)
        trafficBucket = self._dangerBucket(trafficThreat)

        isNewHazard = hazardSignature != self.lastHazardSignature
        worsened = severityBucket > self.lastHazardSeverityBucket or pathBucket > self.lastPathBucket or trafficBucket > self.lastTrafficBucket
        persistentCooldownPassed = self._cooldownPassed(f'hazard:{hazardSignature}', now, self.sameHazardCooldownSec)

        self.lastHazardSignature = hazardSignature
        self.lastHazardSeverityBucket = severityBucket
        self.lastTrafficBucket = trafficBucket
        self.lastPathBucket = pathBucket

        allowPersistentReminder = persistentCooldownPassed and self.pendingContext is None and (isVehicle or severityBucket >= 4)
        if not (isNewHazard or worsened or allowPersistentReminder):
            return None

        if isVehicle and trafficThreat >= 0.4:
            text = self._vehicleText(topHazard, trafficThreat, isNewHazard=isNewHazard)
            return SpeechEvent(
                timestamp=now,
                eventType='trafficThreat',
                text=text,
                priority=96 if trafficThreat >= 0.7 else 82,
                source='hazard',
            )

        text = self._obstacleText(topHazard, pathDanger, immediateAlert, isNewHazard=isNewHazard)
        return SpeechEvent(
            timestamp=now,
            eventType='pathHazard',
            text=text,
            priority=78 if pathDanger >= 0.55 else 64,
            source='hazard',
        )

    @staticmethod
    def _hazardSignature(topHazard) -> str:
        return '|'.join([
            str(getattr(topHazard, 'label', 'unknown')),
            str(getattr(topHazard, 'side', 'center')),
            'path' if bool(getattr(topHazard, 'inPathCorridor', False)) else 'offpath',
        ])

    @staticmethod
    def _dangerBucket(value: float) -> int:
        if value >= 0.8:
            return 4
        if value >= 0.6:
            return 3
        if value >= 0.4:
            return 2
        if value >= 0.25:
            return 1
        return 0

    def _chooseEvent(self, candidates: List[SpeechEvent], now: float) -> Optional[SpeechEvent]:
        if not candidates:
            return None
        candidates.sort(key=lambda event: event.priority, reverse=True)
        top = candidates[0]
        elapsed = now - self.lastSpokenTime
        neededGap = self.interruptGapSec if top.priority >= 100 else self.minGapSec
        if elapsed < neededGap:
            return None
        return top

    def _cooldownPassed(self, key: str, now: float, cooldownSec: float) -> bool:
        lastTime = self.lastSpokenByKey.get(key, 0.0)
        return (now - lastTime) >= float(cooldownSec)

    def _vehicleText(self, hazard, trafficThreat: float, isNewHazard: bool) -> str:
        label = str(getattr(hazard, 'label', 'vehicle')).replace('_', ' ')
        side = str(getattr(hazard, 'side', 'center'))
        if side == 'center':
            if trafficThreat >= 0.7:
                return f'Stop for a moment. There is a {label} moving into the space ahead.'
            return f'I see a {label} ahead. Please wait a second and let it pass.'
        if isNewHazard:
            return f'Heads up. I see a {label} coming from your {side} side.'
        return f'That {label} is still close on your {side}. Please keep clear.'

    def _obstacleText(self, hazard, pathDanger: float, immediateAlert: str, isNewHazard: bool) -> str:
        label = str(getattr(hazard, 'label', 'obstacle')).replace('_', ' ')
        side = str(getattr(hazard, 'side', 'center'))
        if pathDanger >= 0.7:
            if side == 'center':
                return f'Slow down. There is a {label} directly ahead in your path.'
            return f'Slow down. There is a {label} crowding your path on the {side}.'
        if isNewHazard:
            if side == 'center':
                return f'I see a {label} ahead. A small adjustment around it would be safer.'
            return f'I see a {label} on the {side} side of your path. Shift a little away from it.'
        if immediateAlert:
            return immediateAlert
        return f'That {label} is still near your path. Keep easing away from it.'

    def _buildContextText(self, vlmSummary: str, vlmAction: str, localSummary: str) -> Optional[str]:
        sourceText = vlmSummary or localSummary
        sourceText = str(sourceText).strip()
        if not sourceText:
            return None
        sourceText = sourceText.rstrip('. ')
        lowered = sourceText.lower()
        if lowered.startswith('i see '):
            sourceText = sourceText[5:]
        elif lowered.startswith('there is '):
            sourceText = sourceText[9:]

        if sourceText:
            sourceText = sourceText[0].lower() + sourceText[1:] if len(sourceText) > 1 else sourceText.lower()

        if vlmAction:
            action = vlmAction.rstrip('. ')
            action = action[0].lower() + action[1:] if len(action) > 1 else action.lower()
            return f'Also, I notice {sourceText}. I suggest you {action}.'
        return f'Also, I notice {sourceText}.'

    def _logEvent(self, event: SpeechEvent, state: Dict[str, Any]) -> None:
        payload = {
            'timestamp': event.timestamp,
            'eventType': event.eventType,
            'text': event.text,
            'priority': event.priority,
            'source': event.source,
            'frameIndex': state.get('frameIndex'),
            'riskScore': state.get('riskScore'),
            'eventLevel': state.get('eventLevel'),
            'pathDanger': state.get('pathDanger'),
            'trafficThreat': state.get('trafficThreat'),
            'vlmSummary': state.get('vlmSummary'),
            'topHazard': None if state.get('topHazard') is None else {
                'label': state['topHazard'].label,
                'side': state['topHazard'].side,
                'dangerScore': state['topHazard'].dangerScore,
            },
        }
        with self.logPath.open('a', encoding='utf-8') as outputFile:
            outputFile.write(json.dumps(payload) + '\n')
