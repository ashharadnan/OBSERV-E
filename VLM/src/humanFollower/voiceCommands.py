from __future__ import annotations

from typing import Dict


class VoiceCommandParser:
    def parseText(self, text: str) -> Dict[str, bool]:
        normalized = (text or '').lower().strip()
        if not normalized:
            return {
                'help': False,
                'cancel': False,
                'okay': False,
                'stop': False,
                'follow': False,
            }

        return {
            'help': any(term in normalized for term in ['help', 'call for help', 'emergency']),
            'cancel': any(term in normalized for term in ['cancel', 'stop alert', 'do not call']),
            'okay': any(term in normalized for term in ["i'm okay", 'i am okay', 'im okay', 'okay']),
            'stop': 'stop' in normalized,
            'follow': 'follow' in normalized,
        }
