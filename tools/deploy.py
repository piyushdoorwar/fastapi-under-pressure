"""Deploy a new API process the way the platform does.

    python tools/deploy.py --strategy rolling
    python tools/deploy.py --strategy recreate --port 8001

"recreate": stop the running process (SIGTERM, then
SIGKILL after 10 seconds, like `docker stop`), then
start a new one on the same port. The balancer finds
it again once it answers its health check.

"rolling" (chapter 14): start the new process on the
other port (8001 or 8002), wait until the balancer
has it in rotation, then stop the old one, which
drains itself (secondloop.serve).

Each API process writes its PID to
/tmp/secondloop-api-PORT.pid.
"""

import argparse
import os
import signal
import subprocess
import sys
import time

import httpx2

GRACE = 10.0


def pid_file(port: int) -> str:
    return f"/tmp/secondloop-api-{port}.pid"


def start(port: int) -> int:
    path = f"/tmp/secondloop-api-{port}.log"
    with open(path, "a") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "secondloop.serve",
             "--port", str(port)],
            stdout=log, stderr=log,
            start_new_session=True,
        )
    with open(pid_file(port), "w") as f:
        f.write(str(proc.pid))
    return proc.pid


def wait_healthy(port: int, path: str) -> float:
    start_at = time.monotonic()
    while True:
        try:
            resp = httpx2.get(
                f"http://127.0.0.1:{port}{path}",
                timeout=0.5,
            )
            if resp.status_code == 200:
                return time.monotonic() - start_at
        except httpx2.HTTPError:
            pass
        time.sleep(0.05)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def stop(port: int) -> float:
    with open(pid_file(port)) as f:
        pid = int(f.read())
    start_at = time.monotonic()
    os.kill(pid, signal.SIGTERM)
    while alive(pid):
        if time.monotonic() - start_at > GRACE:
            os.kill(pid, signal.SIGKILL)
        time.sleep(0.05)
    return time.monotonic() - start_at


def recreate(port: int) -> None:
    t0 = time.monotonic()
    took = stop(port)
    print(f"{time.monotonic() - t0:5.2f} s: old process"
          f" stopped ({took:.2f} s)")
    start(port)
    took = wait_healthy(port, "/healthz")
    print(f"{time.monotonic() - t0:5.2f} s: new process"
          f" answering ({took:.2f} s to start)")


BALANCER = "http://127.0.0.1:8000/_lb/backends"
PORTS = (8001, 8002)


def running_port() -> int:
    for port in PORTS:
        try:
            with open(pid_file(port)) as f:
                if alive(int(f.read())):
                    return port
        except FileNotFoundError:
            pass
    raise SystemExit("no API process is running")


def in_rotation(port: int) -> float:
    start_at = time.monotonic()
    url = f"http://127.0.0.1:{port}"
    while not httpx2.get(BALANCER).json().get(url):
        time.sleep(0.05)
    return time.monotonic() - start_at


def rolling() -> None:
    t0 = time.monotonic()
    old = running_port()
    new = PORTS[1] if old == PORTS[0] else PORTS[0]
    start(new)
    took = wait_healthy(new, "/readyz")
    print(f"{time.monotonic() - t0:5.2f} s: new process"
          f" on {new} ready ({took:.2f} s to start)")
    in_rotation(new)
    print(f"{time.monotonic() - t0:5.2f} s: balancer"
          f" sends it traffic")
    took = stop(old)
    print(f"{time.monotonic() - t0:5.2f} s: old process"
          f" on {old} drained and stopped ({took:.2f} s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--strategy", choices=["rolling", "recreate"],
        default="rolling",
    )
    parser.add_argument("--start", action="store_true",
                        help="only start a first process")
    args = parser.parse_args()
    if args.start:
        start(args.port)
        wait_healthy(args.port, "/healthz")
    elif args.strategy == "recreate":
        recreate(args.port)
    else:
        rolling()
