#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("This script needs pyserial. Install it with: pip install pyserial", file=sys.stderr)
    raise


def parse_args():
    parser = argparse.ArgumentParser(description="Tail OBSERV-E speech log and forward JSON lines to Arduino over serial.")
    parser.add_argument("--jsonl", required=True, help="Path to outputs/observeSpeechLog.jsonl")
    parser.add_argument("--port", required=True, help="Serial port for the Arduino, such as /dev/ttyACM0 or COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--replay-last", type=int, default=3, help="How many recent messages to replay when starting")
    return parser.parse_args()


def format_payload(raw):
    text = raw.get("text") or raw.get("utterance") or raw.get("speechText") or ""
    text = str(text).strip()
    if not text:
        return None
    payload = {
        "text": text,
        "priority": raw.get("priority", "normal"),
        "eventType": raw.get("eventType", "speech"),
        "ts": int(raw.get("timestampMs") or raw.get("ts") or time.time() * 1000)
    }
    return json.dumps(payload, separators=(",", ":"))


def replay_recent_lines(port, path, count):
    if count <= 0 or not path.exists():
        return
    lines = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            lines.append(line)
    for line in lines[-count:]:
        try:
            payload = format_payload(json.loads(line))
            if payload:
                port.write((payload + "\n").encode("utf-8"))
                print(f"Replayed: {payload}")
                time.sleep(0.2)
        except json.JSONDecodeError:
            continue


def tail_file(port, path):
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(0, os.SEEK_END)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(0.2)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = format_payload(raw)
            if not payload:
                continue
            port.write((payload + "\n").encode("utf-8"))
            print(f"Forwarded: {payload}")


def main():
    args = parse_args()
    path = Path(args.jsonl)
    if not path.exists():
      raise FileNotFoundError(f"Could not find {path}")

    with serial.Serial(args.port, args.baud, timeout=1) as port:
        time.sleep(2.0)
        replay_recent_lines(port, path, args.replay_last)
        tail_file(port, path)


if __name__ == "__main__":
    main()
