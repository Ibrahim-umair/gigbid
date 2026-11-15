import os
import time
from collections import OrderedDict

import torch
from celery import Celery
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BROKER = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery = Celery("shelf", broker=BROKER, backend=BROKER)
api = FastAPI(title="model-shelf")

MEM_BUDGET_GB = float(os.getenv("MEM_BUDGET_GB", "21"))
CATALOG = {
    "doc-type": {"repo": "acme/doc-type-classifier", "gb": 1.4},
    "lang-id": {"repo": "acme/lang-detect-small", "gb": 0.5},
}


class Registry:
    def __init__(self):
        self.loaded = OrderedDict()

    def used_gb(self):
        return sum(CATALOG[k]["gb"] for k in self.loaded)

    def get(self, name):
        if name in self.loaded:
            self.loaded.move_to_end(name)
            return self.loaded[name]
        need = CATALOG[name]["gb"]
        while self.loaded and self.used_gb() + need > MEM_BUDGET_GB:
            old, (tok, mdl) = self.loaded.popitem(last=False)
            del mdl
            torch.cuda.empty_cache()
        tok = AutoTokenizer.from_pretrained(CATALOG[name]["repo"])
        mdl = AutoModelForSequenceClassification.from_pretrained(CATALOG[name]["repo"]).half().cuda().eval()
        self.loaded[name] = (tok, mdl)
        return self.loaded[name]


registry = Registry()


class Job(BaseModel):
    text: str


@celery.task(name="infer")
def infer(name, text):
    tok, mdl = registry.get(name)
    t0 = time.time()
    with torch.inference_mode():
        enc = tok(text, return_tensors="pt", truncation=True, max_length=512).to("cuda")
        probs = mdl(**enc).logits.softmax(-1)[0]
    idx = int(probs.argmax())
    return {"label": mdl.config.id2label[idx], "score": float(probs[idx]),
            "ms": round((time.time() - t0) * 1000, 1)}


@api.post("/jobs/{model}")
async def submit(model: str, job: Job):
    if model not in CATALOG:
        raise HTTPException(404, "unknown model")
    return {"job_id": infer.delay(model, job.text).id}


@api.get("/jobs/{job_id}")
async def status(job_id: str):
    res = celery.AsyncResult(job_id)
    return {"state": res.state, "result": res.result if res.ready() else None}
