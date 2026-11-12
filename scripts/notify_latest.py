from __future__ import annotations

import argparse
from datetime import date, datetime
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.notify import send_alarmer_message, resolve_service_selection, category_slugs
from migri_appointment.office_catalog import OFFICES_BY_CITY_SLUG, normalize_city_slug

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents/skills/check-migri-latest"


def qualifies(result, expected, after):
    if result.get("status") == "error":
        raise ValueError(result.get("evidence", "Unverified check"))
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"Observed filter mismatch: {key}")
    if result.get("status") == "error":
        raise ValueError(result.get("evidence", "Unverified check"))
    if not isinstance(result.get("evidence"), str) or not result["evidence"].strip():
        raise ValueError("Missing observation evidence")
    if result.get("status") == "no_availability":
        if result.get("latest_at") is not None:
            raise ValueError("Inconsistent no-availability result")
        return False
    if result.get("status") != "available" or not result.get("evidence") or not result.get("horizon"):
        raise ValueError("Incomplete availability evidence")
    latest = datetime.fromisoformat(result["latest_at"])
    if latest.utcoffset() is None:
        raise ValueError("Appointment timezone missing")
    local_date = latest.astimezone(ZoneInfo("Europe/Helsinki")).date()
    if local_date > date.fromisoformat(result["horizon"]):
        raise ValueError("Appointment exceeds observed horizon")
    return local_date > after


def parser():
    p = argparse.ArgumentParser(description="Check latest Migri availability through Codex and a shared browser")
    p.add_argument("--browser-skill", required=True, type=Path)
    p.add_argument("--after", required=True, type=date.fromisoformat)
    p.add_argument("--category", choices=category_slugs(), default="citizenship")
    p.add_argument("--service")
    p.add_argument("--city", type=normalize_city_slug, choices=sorted(OFFICES_BY_CITY_SLUG), default="helsinki")
    p.add_argument("--people", type=int, default=2)
    p.add_argument("--family-members", action="store_true")
    p.add_argument("--alarmer-key", default=os.environ.get("ALARMER_KEY"))
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--codex", default="codex")
    p.add_argument("--model")
    p.add_argument("--codex-profile")
    p.add_argument("--runtime-dir", type=Path, default=Path.home()/".cache/migri-appointment/browser-monitor")
    p.add_argument("--browser-profile", type=Path)
    p.add_argument("--playwright-module")
    p.add_argument("--click-delay-min", type=float, default=3)
    p.add_argument("--click-delay-max", type=float, default=6)
    p.add_argument("--timeout", type=float, default=600)
    return p


def main(argv=None):
    p = parser(); a = p.parse_args(argv)
    if not 1 <= a.people <= 6 or not 0 <= a.click_delay_min <= a.click_delay_max or a.timeout <= 0:
        p.error("Invalid people count, delay range, or timeout")
    if not a.no_notify and not a.alarmer_key:
        p.error("Supply --alarmer-key or ALARMER_KEY, or use --no-notify")
    a.browser_skill = a.browser_skill.expanduser().resolve()
    if not a.browser_skill.is_file():
        p.error("External browser skill does not exist")
    service = resolve_service_selection(p, a.category, a.service)
    runtime = a.runtime_dir.expanduser().resolve(); runtime.mkdir(parents=True, exist_ok=True)
    profile = (a.browser_profile or runtime/"profile").expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    expected = dict(city=OFFICES_BY_CITY_SLUG[a.city].slug, category=a.category, service=service.slug,
                    people=a.people, family_members=a.family_members)
    with (profile/"monitor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another check owns this browser; skipped."); return 0
        run = Path(tempfile.mkdtemp(prefix="run-", dir=runtime))
        request = dict(expected, browser_skill=str(a.browser_skill), browser_profile=str(profile),
                       runtime_dir=str(runtime), playwright_module=a.playwright_module,
                       click_delay_min=a.click_delay_min, click_delay_max=a.click_delay_max,
                       timeout_seconds=a.timeout, service_label=service.name_en)
        prompt = f"Use $check-migri-latest at {SKILL / 'SKILL.md'}. Read that skill and the external browser skill. Inspect current availability and return the schema result. Parameters: " + json.dumps(request)
        command = [a.codex, "exec", "--approve-for-me", "--cd", str(ROOT), "--add-dir", str(runtime),
                   "--output-schema", str(SKILL/"result.schema.json"), "--output-last-message", str(run/"result.json"), "-"]
        if a.model: command[2:2] = ["--model", a.model]
        if a.codex_profile: command[2:2] = ["--profile", a.codex_profile]
        env = dict(os.environ); env.pop("ALARMER_KEY", None)
        message = None; code = 0
        try:
            with (run/"codex.log").open("w") as log:
                child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log, env=env, start_new_session=True, text=True)
                try:
                    child.communicate(prompt, timeout=a.timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL); child.wait()
                    raise RuntimeError("Codex check timed out")
            if child.returncode:
                raise RuntimeError(f"Codex exited {child.returncode}; see {run / 'codex.log'}")
            result = json.loads((run/"result.json").read_text())
            if qualifies(result, expected, a.after):
                message = f"Migri latest appointment: {result['latest_at']}\n{service.name_en}, {expected['city']}, {a.people} people\nLater than {a.after}\nhttps://migri.vihta.com/"
            print(json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            code = 1; message = f"Migri latest-date check FAILED: {exc}"
        if message:
            print(message)
            if not a.no_notify:
                try:
                    if not send_alarmer_message(a.alarmer_key, message): return 2
                except Exception:
                    print("Notification delivery failed", file=sys.stderr); return 2
        print(f"Run logs: {run}")
        return code

if __name__ == "__main__":
    raise SystemExit(main())
