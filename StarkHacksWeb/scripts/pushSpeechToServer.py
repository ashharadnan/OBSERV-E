#!/usr/bin/env python3
import argparse
import json
import os
import time
from urllib import request


def post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=10) as resp:
        resp.read()


def follow_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue
            yield line.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jsonl', required=True)
    parser.add_argument('--server', default='http://localhost:3000')
    args = parser.parse_args()

    message_url = args.server.rstrip('/') + '/api/robot-message'
    status_url = args.server.rstrip('/') + '/api/robot-status'

    post_json(status_url, {'text': 'Speech log bridge started', 'source': 'speech_log_bridge', 'priority': 'low', 'ts': int(time.time() * 1000)})

    for line in follow_jsonl(args.jsonl):
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            obj = {'text': line, 'priority': 'normal', 'eventType': 'robot_update', 'source': 'speech_log'}

        text = str(obj.get('text') or obj.get('utterance') or '').strip()
        if not text:
            continue

        payload = {
            'text': text,
            'priority': str(obj.get('priority', 'normal')),
            'eventType': str(obj.get('eventType', 'tts_utterance')),
            'source': str(obj.get('source', 'speech_log')),
            'ts': int(obj.get('ts') or time.time() * 1000)
        }
        try:
            post_json(message_url, payload)
            print('sent:', payload['text'])
        except Exception as exc:
            print('post failed:', exc)
            time.sleep(1.0)


if __name__ == '__main__':
    main()
