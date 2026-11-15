"""CI: fail if anything under gigsim/ changed since it was frozen (gigsim.sha256)."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "gigsim").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            data = p.read_bytes().replace(b"\r\n", b"\n")
            h.update(p.relative_to(ROOT).as_posix().encode() + data)
    return h.hexdigest()


if __name__ == "__main__":
    lock = ROOT / "gigsim.sha256"
    if "--freeze" in sys.argv:
        lock.write_text(digest() + "\n")
        print("frozen", digest())
    elif lock.read_text().strip() != digest():
        sys.exit("gigsim/ was modified after freezing")
    else:
        print("gigsim unchanged")
