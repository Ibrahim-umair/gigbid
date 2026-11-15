"""Deploy GigBid to a Hugging Face Space (Docker SDK).

    hf auth login            # with a WRITE token
    python scripts/deploy_hf.py [--space gigbid] [--llm openai|fake] [--max-calls 150]

Uploads only git-tracked files (no .env, no databases), puts the Space Dockerfile/README at
the Space root, and stores secrets as Space secrets (never in files). Prints the URL and the
generated reviewer password (put it in the private submission comment)."""
import argparse
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="gigbid")
    ap.add_argument("--llm", default="openai", choices=["openai", "fake"])
    ap.add_argument("--max-calls", default="150")
    a = ap.parse_args()
    api = HfApi()
    user = api.whoami()["name"]
    repo = f"{user}/{a.space}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in files:
            if f.startswith((".github/", "infra/hf-space/")) or f == "README.md":
                continue
            (stage / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, stage / f)
        shutil.copy2(ROOT / "infra/hf-space/Dockerfile", stage / "Dockerfile")
        shutil.copy2(ROOT / "infra/hf-space/README.md", stage / "README.md")
        assert not (stage / ".env").exists()
        api.upload_folder(repo_id=repo, repo_type="space", folder_path=str(stage),
                          commit_message="Deploy GigBid")
    env = dotenv_values(ROOT / ".env")
    reviewer_pw = secrets.token_urlsafe(12)
    sec = {"APP_SECRET_KEY": secrets.token_urlsafe(32), "REVIEWER_PASSWORD": reviewer_pw,
           "DEMO_PASSWORD": secrets.token_urlsafe(16), "GIGBID_LLM": a.llm,
           "GIGBID_MAX_CALLS": a.max_calls}
    if a.llm == "openai":
        sec["OPENAI_API_KEY"] = env["OPENAI_API_KEY"]
    for k, v in sec.items():
        api.add_space_secret(repo, k, v)
    print(f"Space: https://huggingface.co/spaces/{repo}")
    print(f"App:   https://{user.lower()}-{a.space}.hf.space")
    print(f"Reviewer login: reviewer / {reviewer_pw}   (keep private)")


if __name__ == "__main__":
    main()
