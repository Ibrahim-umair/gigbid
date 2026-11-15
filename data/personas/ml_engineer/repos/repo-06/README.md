# face-gate-poc

Proof of concept for the selfie step in an onboarding flow.

Checks, in order:
1. Exactly one face in frame
2. Face big enough, sharp enough, eyes and mouth visible
3. A random challenge (blink or turn head left/right) is completed within 6 seconds
4. A texture score from a small classifier to catch printed photos and phone screens

Each check returns a reason code, so a support agent can see why someone was rejected.

Not for production use: thresholds were tuned on a small private set and the classifier file is not included.

```
python gate.py --image selfie.jpg
python gate.py --video clip.mp4 --challenge blink
```
