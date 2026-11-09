import json
import subprocess
import time


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, cwd=None):
    """Run a command, raise with readable stderr tail on failure."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:6]))} ...\n{tail}")
    return res.stdout


def media_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


def retry(fn, attempts=4, delay=3, what="operation"):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"{what}: attempt {i + 1}/{attempts} failed: {e}")
            if i < attempts - 1:
                time.sleep(delay * (2 ** i))
    raise last
