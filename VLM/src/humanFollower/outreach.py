from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class OutreachManager:
    def __init__(self, logPath: str = 'outputs/outreachEvents.jsonl', cooldownSec: float = 30.0) -> None:
        self.logPath = Path(logPath)
        self.logPath.parent.mkdir(parents=True, exist_ok=True)
        self.cooldownSec = float(cooldownSec)
        self.lastTriggerTime = 0.0
        self.lastLevel = 0

    def _write(self, payload: Dict) -> None:
        with open(self.logPath, 'a', encoding='utf-8') as outputFile:
            outputFile.write(json.dumps(payload) + '\n')

    def maybeEscalate(
        self,
        currentTime: float,
        userName: str,
        eventLevel: int,
        riskScore: float,
        summary: str,
        contacts: List[Dict],
        location: str = 'unknown',
    ) -> Optional[Dict]:
        if eventLevel < 3:
            self.lastLevel = eventLevel
            return None

        if (currentTime - self.lastTriggerTime) < self.cooldownSec and eventLevel <= self.lastLevel:
            return None

        target = contacts[0] if contacts else None
        payload = {
            'timestamp': float(currentTime),
            'eventLevel': int(eventLevel),
            'riskScore': float(riskScore),
            'userName': userName,
            'target': target,
            'location': location,
            'summary': summary,
            'mode': 'trusted_contact' if eventLevel == 3 else 'emergency',
            'message': (
                f'OBSERV-E alert: {userName} may need help. '
                f'Risk score {riskScore:.2f}. Last observation: {summary}. '
                f'Location: {location}.'
            ),
        }
        self._write(payload)
        self.lastTriggerTime = currentTime
        self.lastLevel = eventLevel
        return payload
