from __future__ import annotations

from typing import Dict, Optional


class NarrationEngine:
    def __init__(self, summaryIntervalSec: float = 2.0) -> None:
        self.summaryIntervalSec = float(summaryIntervalSec)
        self.lastSummaryTime = 0.0
        self.lastImmediateAlert = ''

    def buildImmediateAlert(self, state: Dict) -> Optional[str]:
        riskLevel = int(state.get('eventLevel', 0))
        topHazard = state.get('topHazard')
        if riskLevel >= 4:
            return 'Emergency risk is very high. Starting emergency escalation.'
        if riskLevel >= 3:
            return 'High risk detected. Contacting your trusted person now.'
        if riskLevel >= 2:
            return 'I think you may need help. Say I am okay or press cancel.'
        if topHazard is None:
            return None

        label = topHazard.label.replace('_', ' ')
        side = topHazard.side
        if label in {'car', 'truck', 'bus', 'motorcycle', 'bicycle', 'scooter'}:
            if side == 'center':
                return f'Stop. {label} ahead.'
            return f'{label.capitalize()} approaching from your {side}.'
        if topHazard.inPathCorridor:
            if side == 'center':
                return f'Obstacle ahead. {label} in your path.'
            return f'Obstacle near your path on the {side}. {label} ahead.'
        return None

    def buildSummary(self, state: Dict, currentTime: float) -> Optional[str]:
        if currentTime - self.lastSummaryTime < self.summaryIntervalSec:
            return None

        topHazard = state.get('topHazard')
        if topHazard is None:
            text = 'The path looks mostly clear right now.'
        else:
            label = topHazard.label.replace('_', ' ')
            side = topHazard.side
            if topHazard.inPathCorridor:
                text = f'I see a {label} ahead in the walking path.'
            elif side == 'center':
                text = f'I see a {label} ahead, but not directly blocking the path.'
            else:
                text = f'I see a {label} on your {side}.'

        self.lastSummaryTime = currentTime
        return text
