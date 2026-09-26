import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="NetSentinel", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


static_dir = Path(os.getenv("NETSENTINEL_STATIC_DIR", ""))
if os.getenv("NETSENTINEL_STATIC_DIR") and static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
