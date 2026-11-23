"""One-command local demo (test profile: ZeroMQ + direct + SQLite). No Docker, no broker, ~10 seconds.

    make demo      or      PROFILE=test python scripts/demo_local.py
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = {**os.environ, "PROFILE": "test", "DB_URL": "sqlite:///data/demo.db", "PYTHONPATH": str(ROOT)}
py = sys.executable


def step(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}", flush=True)


for f in (ROOT / "data").glob("demo.db*"):
    f.unlink()

step("1/4 start bridge (ZeroMQ SUB -> validate -> SQLite raw)")
bridge = subprocess.Popen([py, "-m", "iotpipe.bridge"], cwd=ROOT, env=env)
time.sleep(1.5)

step("2/4 simulate 4 devices x 120 readings (with injected defects)")
subprocess.run([py, "-m", "iotpipe.simulator", "--devices", "4", "--per-device", "120", "--rate", "0"],
               cwd=ROOT, env=env, check=True)
time.sleep(1.5)  # let the bridge flush its last batch
bridge.send_signal(signal.SIGINT)
bridge.wait(timeout=15)

step("3/4 ELT: raw -> staging -> analytics + assertions + governance")
etl = subprocess.run([py, "-m", "iotpipe.etl.runner"], cwd=ROOT, env=env)

step("4/4 report")
subprocess.run([py, "-m", "iotpipe.etl.report"], cwd=ROOT, env=env, check=True)
sys.exit(etl.returncode)
