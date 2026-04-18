# OBSERV-E Voice Companion

This package gives you three ways to get robot speech into the web app:

1. **Bluetooth direct**
   - Best when `navigator.bluetooth` is available.
2. **USB direct with Web Serial**
   - Best on desktop Chrome when Bluetooth is missing.
3. **Bridge mode**
   - Best for phones and for browsers that do not expose Bluetooth.
   - The server sends robot speech to the browser with Server-Sent Events.

## Start the web app

```bash
npm install
cp .env.example .env
# put ELEVENLABS_API_KEY in .env
npm start
```

Open `http://localhost:3000`.

## Best fallback when Bluetooth is unavailable in Chrome

### Desktop USB mode
1. Plug the Arduino into USB.
2. Open the app in Chrome.
3. Press **Connect with USB**.
4. Pick the Arduino serial device.

### Phone or mobile browser mode
1. Run the Node server on the laptop or robot computer.
2. Make sure the phone and laptop are on the same network.
3. Open the app from the phone using the laptop IP, for example `http://192.168.1.25:3000`.
4. Press **Connect with bridge**.
5. Feed speech into the bridge using one of the scripts below.

## Feed OBSERV-E speech into the bridge

### From the JSONL speech log

```bash
python scripts/pushSpeechToServer.py \
  --jsonl /path/to/outputs/observeSpeechLog.jsonl \
  --server http://localhost:3000
```

### From the Arduino over USB

```bash
pip install pyserial
python scripts/robotSerialToServer.py \
  --port /dev/ttyACM0 \
  --server http://localhost:3000
```

That script also forwards queued web commands like `ack` back to the Arduino.

## Arduino sketch

Flash:
- `arduino/RobotBleBridge/RobotBleBridge.ino`

The sketch:
- advertises as `OBSERVE-Robot`
- forwards serial lines to BLE notifications
- receives web commands over BLE

## Notes

- The app always prints the exact text that will be spoken under **What will be spoken**.
- Urgent lines interrupt normal ones.
- Normal lines are deduplicated and stale queued lines are dropped.


## Linux Chrome Bluetooth note
On Linux, Chrome may not expose `navigator.bluetooth` until `chrome://flags/#enable-experimental-web-platform-features` is enabled and Chrome is fully relaunched. The app now disables the service worker on localhost to avoid stale cache issues during local development.
