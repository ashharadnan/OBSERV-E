# CNN Follower

Single-person follower with Kalman prediction, angles, and high-rate projector thread.

## Run
```bash
python scripts/runCnnFollower.py --model models/yolo11n.pt --camera 0 --printEvery 10
```

## UDP packed struct output
```bash
python scripts/runCnnFollower.py --model models/yolo11n.pt --camera 0 --outputMode udpStruct --udpHost 127.0.0.1 --udpPort 5005
```
