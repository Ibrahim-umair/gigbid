# dock-counter

Counts things (we used it for pallets) as they cross a line in a camera picture.

The detector is a YOLOv8 nano/small model. The useful part of this repo is how the stream is read: the camera is read in a background thread that only ever keeps the latest frame, so slow inference never makes the picture lag or skip. If the camera goes quiet for 5 seconds the reader reconnects.

```
python counter.py --source rtsp://user:pass@10.0.0.21/stream1 --weights best.pt --line 0.55
```

Outputs a CSV of crossings (timestamp, track id, direction) and optionally an annotated video.

Tips: lower `--imgsz` to 512 on weak GPUs; use `--half` when CUDA is available.
