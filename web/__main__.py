"""``python -m web [--port 8020]`` — run the server in the foreground."""

import argparse

import uvicorn


def main():
    p = argparse.ArgumentParser(description="Pendragon GM web app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8020)
    p.add_argument("--reload", action="store_true")
    a = p.parse_args()
    uvicorn.run("web.app:create_app", factory=True, host=a.host, port=a.port,
                reload=a.reload, timeout_graceful_shutdown=2)   # open tabs' live streams mustn't block a restart


if __name__ == "__main__":
    main()
