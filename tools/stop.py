"""Stop the API the way a container platform does.

    python tools/stop.py --pid 4242 --grace 10

Sends SIGTERM, waits up to --grace seconds for the
process to exit, then sends SIGKILL. `docker stop`
waits 10 seconds by default; Kubernetes waits 30.
"""

import argparse
import os
import signal
import time


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def main(args):
    start = time.monotonic()
    os.kill(args.pid, signal.SIGTERM)
    print("0.0 s: SIGTERM")
    while alive(args.pid):
        took = time.monotonic() - start
        if took >= args.grace:
            os.kill(args.pid, signal.SIGKILL)
            print(f"{took:.1f} s: still running, SIGKILL")
            return
        time.sleep(0.1)
    took = time.monotonic() - start
    print(f"{took:.1f} s: exited by itself")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--grace", type=float, default=10)
    main(parser.parse_args())
