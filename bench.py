"""Benchmark launcher - Ticket-04 part 1 (Test Contract v1.3).

python3 bench.py --seed 42 --duration 30 --out bench.json [--browser PATH] [--port P]

Serves this folder (serve.make_server), opens the game in a Chromium-family browser as a 1280x720 app
window with vsync and the frame-rate limit off, and waits for the page (?bench=1) to POST its frame
times to /api/bench. Writes bench.json and exits 0. No result within duration + 120 s -> exit 1.
Pure stdlib. Browser lookup: --browser, $BENCH_BROWSER, Chrome / Chromium / Edge in the usual places
and on PATH, Playwright's Chromium. With none of them the default browser is opened (webbrowser.open):
then the window size and vsync cannot be controlled and the result says "vsync_off": false.
peak_mem_mb is always null: a web build cannot read the browser's RSS (see README).
"""
import time

T0_MS = int(time.time() * 1000)          # process start, for load_ms

import argparse  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import webbrowser  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import serve  # noqa: E402
from game import benchstats  # noqa: E402

CONTRACT_VERSION = "1.3"
RENDERER_PREFIX = "three.js r128 WebGL"
GRACE_AFTER_EXIT_S = 3.0

BROWSER_FLAGS = ["--window-size=1280,720", "--no-first-run", "--no-default-browser-check",
                 "--disable-gpu-vsync", "--disable-frame-rate-limit",
                 # keep the measured window at exactly 1280x720 device pixels and never throttled
                 "--force-device-scale-factor=1", "--disable-background-timer-throttling",
                 "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
                 "--disable-features=CalculateNativeWinOcclusion"]


class BenchError(RuntimeError):
    pass


# ----------------------------------------------------------------- browser lookup
def _env_paths(names, *parts):
    out = []
    for n in names:
        base = os.environ.get(n)
        if base:
            out.append(os.path.join(base, *parts))
    return out


def _fixed_candidates():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        pf = ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA")
        return (_env_paths(pf, "Google", "Chrome", "Application", "chrome.exe")
                + _env_paths(pf, "Chromium", "Application", "chrome.exe")
                + _env_paths(pf, "Microsoft", "Edge", "Application", "msedge.exe"))
    if sys.platform == "darwin":
        apps = ["/Applications", os.path.join(home, "Applications")]
        names = [("Google Chrome.app", "Google Chrome"), ("Chromium.app", "Chromium"),
                 ("Microsoft Edge.app", "Microsoft Edge")]
        return [os.path.join(a, app, "Contents", "MacOS", exe) for app, exe in names for a in apps]
    return []


PATH_NAMES = ["google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser",
              "microsoft-edge", "microsoft-edge-stable", "msedge"]


def _playwright_chromium():
    roots = []
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and os.environ["PLAYWRIGHT_BROWSERS_PATH"] != "0":
        roots.append(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        roots += _env_paths(["LOCALAPPDATA"], "ms-playwright")
    elif sys.platform == "darwin":
        roots.append(os.path.join(home, "Library", "Caches", "ms-playwright"))
    else:
        roots.append(os.path.join(home, ".cache", "ms-playwright"))
    pats = ["chromium-*/chrome-win64/chrome.exe", "chromium-*/chrome-win/chrome.exe",
            "chromium-*/chrome-linux64/chrome", "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac-x64/Chromium.app/Contents/MacOS/Chromium"]
    found = []
    for r in roots:
        for pat in pats:
            found += sorted(glob.glob(os.path.join(r, *pat.split("/"))), reverse=True)
    if not found:       # the playwright package may know a path we did not guess
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                found.append(p.chromium.executable_path)
        except Exception:
            pass
    return found


def find_browser(explicit=None):
    """Path to a Chromium-family browser, or None. Raises BenchError if an explicit choice is unusable."""
    for label, choice in (("--browser", explicit), ("BENCH_BROWSER", os.environ.get("BENCH_BROWSER"))):
        if choice:
            path = choice if os.path.isfile(choice) else shutil.which(choice)
            if not path:
                raise BenchError(f"{label} does not point to a browser: {choice}")
            return path
    candidates = _fixed_candidates() + [shutil.which(n) for n in PATH_NAMES] + _playwright_chromium()
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def needs_no_sandbox(exe):
    """Chrome-for-Testing (Playwright's Chromium) does not start its renderer outside Playwright
    without --no-sandbox; Chrome refuses to run as root without it."""
    if "ms-playwright" in (exe or "").replace("\\", "/"):
        return True
    return hasattr(os, "geteuid") and os.geteuid() == 0


def browser_label(user_agent, exe):
    """'Chrome 157.0.0.0' / 'Edge 157.0.0.0' from the User-Agent the page's request carried."""
    ua = user_agent or ""
    m = re.search(r"\bEdg/([\d.]+)", ua)            # Edge's UA also says Chrome/..., so look for Edg first
    if m:
        return f"Edge {m.group(1)}"
    m = re.search(r"\bChrom(?:e|ium)/([\d.]+)", ua)
    if m:
        low = (exe or "").lower().replace("\\", "/")
        name = "Chromium" if ("chromium" in low or "ms-playwright" in low) else "Chrome"
        return f"{name} {m.group(1)}"
    return os.path.basename(exe) if exe else "unknown browser"


# ----------------------------------------------------------------- run the page
def _stop_browser(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_bench(seed, duration, port=0, browser=None, log=print):
    """Returns the bench.json dict. Raises BenchError on failure."""
    exe = find_browser(browser)
    box, done = {}, threading.Event()

    def sink(data):
        box.setdefault("data", data)
        done.set()

    httpd = serve.make_server(port, bench_sink=sink, quiet=True)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/web/index.html?bench=1&seed={seed}&duration={duration}"
    profile = tempfile.mkdtemp(prefix="ddl-bench-")
    proc = None
    vsync_off = exe is not None
    started = time.monotonic()
    deadline = started + duration + 120
    try:
        if exe:
            log(f"bench: {os.path.basename(exe)} -> {url}")
            args = [exe, f"--app={url}", f"--user-data-dir={profile}"] + BROWSER_FLAGS
            if needs_no_sandbox(exe):
                args.append("--no-sandbox")
            kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
            if sys.platform != "win32":
                kw["start_new_session"] = True
            proc = subprocess.Popen(args, **kw)
        else:
            log("bench: no Chromium-family browser found; using the default browser "
                "(window size and vsync cannot be controlled, vsync_off=false)")
            if not webbrowser.open(url):
                raise BenchError("could not open any browser; install Chrome/Chromium/Edge or use --browser PATH")
        exited_at = None
        while not done.wait(0.25):
            now = time.monotonic()
            if now > deadline:
                raise BenchError(f"no benchmark result within {duration + 120} s "
                                 "(page did not finish; try --browser PATH)")
            if proc is not None and proc.poll() is not None and proc.returncode != 0:
                exited_at = exited_at or now
                if now - exited_at > GRACE_AFTER_EXIT_S:
                    raise BenchError(f"browser exited with code {proc.returncode} before sending a result")
        data = box["data"]
    finally:
        _stop_browser(proc)
        httpd.shutdown()
        httpd.server_close()
        for _ in range(5):              # the browser may still hold files for a moment
            shutil.rmtree(profile, ignore_errors=True)
            if not os.path.exists(profile):
                break
            time.sleep(0.5)
    return build_result(data, exe)


def build_result(data, exe):
    """bench.json content from the page's POST {first_frame_epoch_ms, dts_ms, renderer, warmup_s}."""
    try:
        dts = data["dts_ms"]
        first = float(data["first_frame_epoch_ms"])
        if not isinstance(dts, list) or isinstance(first, bool):
            raise TypeError
        stats = benchstats.compute(dts)
    except (KeyError, TypeError, ValueError) as e:
        raise BenchError(f"invalid result from the page: {e!r}")
    renderer = str(data.get("renderer") or "").strip()
    if not renderer.startswith("three.js"):
        renderer = RENDERER_PREFIX + (f" · {renderer}" if renderer else "")
    label = browser_label(data.get("user_agent"), exe)
    if label.split()[0].lower() not in renderer.lower():     # the page may already name the browser
        renderer += f" · {label}"
    return {"contract_version": CONTRACT_VERSION,
            "avg_fps": stats["avg_fps"], "p1_low_fps": stats["p1_low_fps"],
            "frame_ms_p95": stats["frame_ms_p95"], "frames": stats["frames"],
            "load_ms": max(0, int(round(first - T0_MS))),
            "peak_mem_mb": None,
            "vsync_off": exe is not None,
            "renderer": renderer,
            "os": platform.platform()}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n")
        sys.exit(2)


def main(argv=None):
    ap = _Parser(description="Dao Den Long benchmark (Test Contract v1.3)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--duration", type=float, default=30, help="measured seconds after a 3 s warm-up")
    ap.add_argument("--out", required=True)
    ap.add_argument("--browser", help="path to a Chromium-family browser (else $BENCH_BROWSER, else auto)")
    ap.add_argument("--port", type=int, default=0, help="server port (default: any free port)")
    a = ap.parse_args(argv)
    if not a.duration > 0:
        ap.error("--duration must be > 0")
    duration = int(a.duration) if float(a.duration).is_integer() else a.duration
    try:
        result = run_bench(a.seed, duration, a.port, a.browser,
                           log=lambda m: print(m, file=sys.stderr, flush=True))
    except BenchError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    try:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        sys.stderr.write(f"error: cannot write output: {e}\n")
        return 1
    print(f"bench: {result['frames']} frames, avg {result['avg_fps']} fps, p1 low {result['p1_low_fps']} fps, "
          f"p95 {result['frame_ms_p95']} ms, load {result['load_ms']} ms -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
