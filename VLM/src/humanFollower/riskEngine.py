from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RiskState:
    riskScore: float
    eventLevel: int
    fallScore: float
    hazardProximity: float
    immobility: float
    nonResponse: float
    voiceHelp: float
    pathDanger: float
    trafficThreat: float
    reasons: list[str]


class RiskEngine:
    def __init__(
        self,
        fallWeight: float = 0.22,
        hazardWeight: float = 0.16,
        immobilityWeight: float = 0.12,
        nonResponseWeight: float = 0.18,
        voiceHelpWeight: float = 0.20,
        pathDangerWeight: float = 0.12,
        trafficThreatWeight: float = 0.18,
        cautionThreshold: float = 0.33,
        checkInThreshold: float = 0.52,
        contactThreshold: float = 0.72,
        emergencyThreshold: float = 0.88,
    ) -> None:
        self.fallWeight = float(fallWeight)
        self.hazardWeight = float(hazardWeight)
        self.immobilityWeight = float(immobilityWeight)
        self.nonResponseWeight = float(nonResponseWeight)
        self.voiceHelpWeight = float(voiceHelpWeight)
        self.pathDangerWeight = float(pathDangerWeight)
        self.trafficThreatWeight = float(trafficThreatWeight)
        self.cautionThreshold = float(cautionThreshold)
        self.checkInThreshold = float(checkInThreshold)
        self.contactThreshold = float(contactThreshold)
        self.emergencyThreshold = float(emergencyThreshold)

    @staticmethod
    def _clip(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def compute(self, signals: Dict[str, float]) -> RiskState:
        fallScore = self._clip(signals.get('fallScore', 0.0))
        hazardProximity = self._clip(signals.get('hazardProximity', 0.0))
        immobility = self._clip(signals.get('immobility', 0.0))
        nonResponse = self._clip(signals.get('nonResponse', 0.0))
        voiceHelp = self._clip(signals.get('voiceHelp', 0.0))
        pathDanger = self._clip(signals.get('pathDanger', 0.0))
        trafficThreat = self._clip(signals.get('trafficThreat', 0.0))

        riskScore = self._clip(
            fallScore * self.fallWeight
            + hazardProximity * self.hazardWeight
            + immobility * self.immobilityWeight
            + nonResponse * self.nonResponseWeight
            + voiceHelp * self.voiceHelpWeight
            + pathDanger * self.pathDangerWeight
            + trafficThreat * self.trafficThreatWeight
        )

        reasons: list[str] = []
        if fallScore >= 0.5:
            reasons.append('possible fall posture')
        if trafficThreat >= 0.55:
            reasons.append('traffic nearby')
        if pathDanger >= 0.55:
            reasons.append('path blockage')
        if immobility >= 0.55:
            reasons.append('unexpected immobility')
        if nonResponse >= 0.55:
            reasons.append('no user response')
        if voiceHelp >= 0.45:
            reasons.append('help request')

        eventLevel = 0
        if riskScore >= self.cautionThreshold:
            eventLevel = 1
        if riskScore >= self.checkInThreshold:
            eventLevel = 2
        if riskScore >= self.contactThreshold:
            eventLevel = 3
        if riskScore >= self.emergencyThreshold:
            eventLevel = 4

        return RiskState(
            riskScore=riskScore,
            eventLevel=eventLevel,
            fallScore=fallScore,
            hazardProximity=hazardProximity,
            immobility=immobility,
            nonResponse=nonResponse,
            voiceHelp=voiceHelp,
            pathDanger=pathDanger,
            trafficThreat=trafficThreat,
            reasons=reasons,
        )
