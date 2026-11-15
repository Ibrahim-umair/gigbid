import argparse
import json
import random
import time

import cv2
import mediapipe as mp
import numpy as np

mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=2, refine_landmarks=True)
L_EYE = [33, 160, 158, 133, 153, 144]
R_EYE = [362, 385, 387, 263, 373, 380]


def ear(pts):
    a = np.linalg.norm(pts[1] - pts[5])
    b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3])
    return (a + b) / (2.0 * c)


def landmarks(frame):
    h, w = frame.shape[:2]
    res = mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        return []
    return [np.array([(p.x * w, p.y * h) for p in f.landmark]) for f in res.multi_face_landmarks]


def quality(frame, pts):
    x0, y0 = pts.min(0).astype(int)
    x1, y1 = pts.max(0).astype(int)
    crop = frame[max(y0, 0):y1, max(x0, 0):x1]
    if crop.size == 0:
        return {"size_ok": False, "sharp": 0.0, "bright": 0.0}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return {"size_ok": (x1 - x0) > 0.2 * frame.shape[1],
            "sharp": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            "bright": float(gray.mean())}


def check_image(path):
    frame = cv2.imread(path)
    faces = landmarks(frame)
    if len(faces) != 1:
        return {"pass": False, "reason": "FACE_COUNT_%d" % len(faces)}
    q = quality(frame, faces[0])
    if not q["size_ok"]:
        return {"pass": False, "reason": "FACE_TOO_SMALL"}
    if q["sharp"] < 60:
        return {"pass": False, "reason": "BLURRY"}
    return {"pass": True, "reason": "OK", **q}


def blink_challenge(video, timeout=6.0):
    cap = cv2.VideoCapture(video)
    t0, closed = time.time(), False
    while time.time() - t0 < timeout:
        ok, frame = cap.read()
        if not ok:
            break
        faces = landmarks(frame)
        if len(faces) != 1:
            continue
        e = (ear(faces[0][L_EYE]) + ear(faces[0][R_EYE])) / 2
        if e < 0.19:
            closed = True
        elif closed and e > 0.25:
            return True
    return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--video")
    ap.add_argument("--challenge", default=random.choice(["blink"]))
    a = ap.parse_args()
    out = check_image(a.image) if a.image else {"pass": blink_challenge(a.video)}
    print(json.dumps(out))
