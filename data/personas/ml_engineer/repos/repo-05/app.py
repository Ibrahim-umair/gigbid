import sqlite3
from datetime import datetime

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI(title="pantry-notes")
model = SentenceTransformer("all-MiniLM-L6-v2")
db = sqlite3.connect("pantry.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT, added TEXT, vec BLOB)")


class Note(BaseModel):
    text: str


@app.post("/notes")
def add_note(n: Note):
    vec = model.encode(n.text, normalize_embeddings=True).astype(np.float32)
    db.execute("INSERT INTO notes (text, added, vec) VALUES (?,?,?)",
               (n.text, datetime.utcnow().isoformat(), vec.tobytes()))
    db.commit()
    return {"ok": True}


@app.get("/search")
def search(q: str, k: int = 5):
    qv = model.encode(q, normalize_embeddings=True).astype(np.float32)
    rows = db.execute("SELECT id, text, added, vec FROM notes").fetchall()
    if not rows:
        return []
    mat = np.stack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    sims = mat @ qv
    top = np.argsort(-sims)[:k]
    return [{"id": rows[i][0], "text": rows[i][1], "added": rows[i][2], "score": round(float(sims[i]), 3)}
            for i in top]


@app.delete("/notes/{note_id}")
def delete_note(note_id: int):
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    return {"deleted": note_id}


@app.get("/health")
def health():
    count = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    return {"status": "ok", "notes": count}
