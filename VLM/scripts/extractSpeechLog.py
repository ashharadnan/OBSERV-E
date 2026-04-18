import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--jsonl', default='outputs/observeSpeechLog.jsonl')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()

    path = Path(args.jsonl)
    if not path.exists():
        raise FileNotFoundError(f'Speech log not found: {path}')

    rows = []
    with path.open('r', encoding='utf-8') as inputFile:
        for line in inputFile:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    for row in rows[-max(1, args.limit):]:
        print({
            'timestamp': row.get('timestamp'),
            'frameIndex': row.get('frameIndex'),
            'eventType': row.get('eventType'),
            'text': row.get('text'),
            'riskScore': row.get('riskScore'),
            'eventLevel': row.get('eventLevel'),
            'vlmSummary': row.get('vlmSummary'),
            'topHazard': row.get('topHazard'),
        })


if __name__ == '__main__':
    main()
