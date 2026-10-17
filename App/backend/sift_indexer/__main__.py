"""Service entry point. Electron supplies a loopback socket and per-launch token."""

from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path

import uvicorn

from .api import create_app


def main() -> None:
    secret = os.environ["SIFT_SERVICE_TOKEN"]
    db_path = Path(os.environ["SIFT_DB_PATH"])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(db_path, secret)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    print(json.dumps({"sift_ready": True, "port": port}), flush=True)
    config = uvicorn.Config(app, host="127.0.0.1", log_level="warning")
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    main()
