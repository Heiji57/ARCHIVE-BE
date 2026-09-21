#!/usr/bin/env python3
"""Reserve host ports per Superset workspace so parallel workspaces don't collide.

  ports.py allocate <workspace_path>   prints KEY=VALUE lines (source them from a shell)
  ports.py release  <workspace_path>   frees the reservation

A block is skipped if any of its ports is bound right now OR reserved by another
workspace, so a stopped workspace keeps its ports and never collides on restart.
"""
import fcntl
import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path

# Own file: other repos use ~/.superset/port-allocations.json with a different scheme and lock.
REGISTRY = Path.home() / ".superset" / "archive-be-port-allocations.json"
FIRST, LAST, BLOCK = 20000, 29999, 10  # below the Linux ephemeral range (32768+)
NAMES = ("API_PORT", "POSTGRES_PORT", "REDIS_PORT")


def is_free(port):
    with socket.socket() as s:
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def locked_registry(fn):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            reg = json.loads(fh.read() or "{}")
        except ValueError:
            reg = {}
        reg = {p: b for p, b in reg.items() if os.path.isdir(p)}  # drop deleted workspaces
        result = fn(reg)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(reg, indent=2))
        return result


def allocate(ws):
    def pick(reg):
        if ws not in reg:
            taken = set(reg.values())
            blocks = list(range(FIRST, LAST + 1, BLOCK))
            start = int(hashlib.sha1(ws.encode()).hexdigest(), 16) % len(blocks)
            for i in range(len(blocks)):
                c = blocks[(start + i) % len(blocks)]
                if c not in taken and all(is_free(c + n) for n in range(len(NAMES))):
                    reg[ws] = c
                    break
            else:
                sys.exit(f"no free port block in {FIRST}-{LAST}")
        return reg[ws]

    base = locked_registry(pick)
    # Derived from the path only (not env vars) so the compose project name never drifts
    # between setup / run / teardown; a drift would orphan the old stack and collide on ports.
    slug = re.sub(r"[^a-z0-9]+", "-", Path(ws).name.lower()).strip("-") or "ws"
    for i, n in enumerate(NAMES):
        print(f"{n}={base + i}")
    print(f"COMPOSE_PROJECT_NAME=archive-{slug}-{hashlib.sha1(ws.encode()).hexdigest()[:6]}")


def release(ws):
    locked_registry(lambda reg: reg.pop(ws, None))


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] in ("allocate", "release"):
    {"allocate": allocate, "release": release}[sys.argv[1]](sys.argv[2])
else:
    sys.exit(__doc__)
