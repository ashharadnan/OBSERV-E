#!/usr/bin/env python3
import argparse
import json
import time
from urllib import request

import serial


def post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=10) as resp:
        resp.read()


def get_next_command(url: str):
    with request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data.get('command')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--server', default='http://localhost:3000')
    args = parser.parse_args()

    message_url = args.server.rstrip('/') + '/api/robot-message'
    status_url = args.server.rstrip('/') + '/api/robot-status'
    next_command_url = args.server.rstrip('/') + '/api/robot-command/next'

    ser = serial.Serial(args.port, args.baud, timeout=0.2)
    post_json(status_url, {'text': f'USB robot bridge started on {args.port}', 'source': 'robot_serial_bridge', 'priority': 'low', 'ts': int(time.time() * 1000)})

    last_poll = 0.0
    try:
        while True:
            raw = ser.readline().decode('utf-8', errors='replace').strip()
            if raw:
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    obj = {'text': raw, 'priority': 'normal', 'source': 'arduino_serial'}

                target_url = message_url
                text = str(obj.get('text') or raw).strip()
                if raw.startswith('WEB_COMMAND:') or 'heartbeat' in text.lower() or 'connected' in text.lower() or 'ready' in text.lower():
                    target_url = status_url
                post_json(target_url, {
                    'text': text,
                    'priority': str(obj.get('priority', 'normal' if target_url == message_url else 'low')),
                    'eventType': str(obj.get('eventType', 'robot_update')),
                    'source': str(obj.get('source', 'arduino_serial')),
                    'ts': int(obj.get('ts') or time.time() * 1000)
                })
                print('bridge:', raw)

            now = time.time()
            if now - last_poll > 0.5:
                last_poll = now
                try:
                    command = get_next_command(next_command_url)
                    if command:
                        ser.write((json.dumps(command) + '\n').encode('utf-8'))
                        print('command:', command)
                except Exception:
                    pass
    finally:
        ser.close()


if __name__ == '__main__':
    main()
