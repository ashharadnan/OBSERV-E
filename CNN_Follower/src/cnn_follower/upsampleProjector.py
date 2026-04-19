
from __future__ import annotations

import threading
import time
from typing import Optional


class HighRateKalmanProjector:
    def __init__(self, pipeline, controlHz: float = 60.0, predictionLeadMs: float = 0.0) -> None:
        self.pipeline = pipeline
        self.controlHz = max(1.0, float(controlHz))
        self.predictionLeadMs = max(0.0, float(predictionLeadMs))
        self.stopEvent = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.stopEvent.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopEvent.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None

    def _loop(self) -> None:
        loopPeriod = 1.0 / self.controlHz
        nextTick = time.perf_counter()
        while not self.stopEvent.is_set():
            payload = self.pipeline.sampleProjectionPayload(
                predictFromNowDt=self.predictionLeadMs / 1000.0,
            )
            self.pipeline.publisher.publish(payload)
            nextTick += loopPeriod
            sleepSeconds = nextTick - time.perf_counter()
            if sleepSeconds > 0.0:
                time.sleep(sleepSeconds)
            else:
                nextTick = time.perf_counter()
