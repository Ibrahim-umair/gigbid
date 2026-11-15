import argparse
import csv
import queue
import threading
import time

import cv2
from ultralytics import YOLO


class LatestFrame(threading.Thread):
    """Reads the stream continuously and keeps only the newest frame."""

    def __init__(self, source):
        super().__init__(daemon=True)
        self.source = source
        self.q = queue.Queue(maxsize=1)
        self.last_ok = time.time()
        self.cap = cv2.VideoCapture(source)

    def run(self):
        while True:
            ok, frame = self.cap.read()
            if not ok:
                if time.time() - self.last_ok > 5:
                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.source)
                    self.last_ok = time.time()
                time.sleep(0.05)
                continue
            self.last_ok = time.time()
            if self.q.full():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    pass
            self.q.put(frame)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--weights", default="best.pt")
    ap.add_argument("--line", type=float, default=0.5)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--half", action="store_true")
    a = ap.parse_args()

    model = YOLO(a.weights)
    reader = LatestFrame(a.source)
    reader.start()
    last_y, counted = {}, 0
    with open("crossings.csv", "a", newline="") as fh:
        w = csv.writer(fh)
        while True:
            frame = reader.q.get()
            h = frame.shape[0]
            line_y = int(h * a.line)
            res = model.track(frame, persist=True, imgsz=a.imgsz, half=a.half, verbose=False)[0]
            if res.boxes.id is None:
                continue
            for box, tid in zip(res.boxes.xyxy.tolist(), res.boxes.id.int().tolist()):
                cy = (box[1] + box[3]) / 2
                prev = last_y.get(tid)
                if prev is not None and (prev - line_y) * (cy - line_y) < 0:
                    counted += 1
                    w.writerow([time.time(), tid, "down" if cy > prev else "up"])
                    fh.flush()
                last_y[tid] = cy


if __name__ == "__main__":
    main()
