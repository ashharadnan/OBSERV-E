import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Read tracking JSONL and print Kalman + actual box states.')
    parser.add_argument('--jsonl', required=True, help='Path to observeTrackingStates.jsonl or camera tracking JSONL')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()

    jsonlPath = Path(args.jsonl)
    if not jsonlPath.exists():
        raise FileNotFoundError(f'JSONL file not found: {jsonlPath}')

    count = 0
    with open(jsonlPath, 'r', encoding='utf-8') as inputFile:
        for line in inputFile:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            row = {
                'frameIndex': payload.get('frameIndex'),
                'measurementSource': payload.get('measurementSource'),
                'kalmanState': payload.get('kalmanState'),
                'predictedKalmanState': payload.get('predictedKalmanState'),
                'actualBoxState': payload.get('actualBoxState'),
                'bboxXyxy': payload.get('bboxXyxy'),
                'measuredBoxXyxy': payload.get('measuredBoxXyxy'),
            }
            print(json.dumps(row, indent=2))
            count += 1
            if count >= args.limit:
                break


if __name__ == '__main__':
    main()
