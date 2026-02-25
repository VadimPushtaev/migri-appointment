from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Iterable, Sequence

import requests

# Support direct execution: `python scripts/notify.py ...`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migri_appointment.client import DEFAULT_BASE_URL, MigriClient
from migri_appointment.types import Slot

ALARMBOT_URL = "https://alarmerbot.ru/"
MIGRI_LINK = "https://migri.vihta.com/"
FETCH_DELAY_SECONDS = 2.0


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def parse_week_ref(value: str) -> tuple[int, int]:
    try:
        year_text, week_text = value.split(":", maxsplit=1)
        year = int(year_text)
        week = int(week_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid week value '{value}', expected YEAR:WEEK (e.g. 2026:26)"
        ) from exc

    if not 1 <= week <= 53:
        raise argparse.ArgumentTypeError(f"Week must be in 1..53, got {week}")
    return year, week


def parse_week_selector(value: str) -> list[tuple[int, int]]:
    if ".." not in value:
        return [parse_week_ref(value)]

    start_raw, end_raw = value.split("..", maxsplit=1)
    start_year, start_week = parse_week_ref(start_raw)
    end_year, end_week = parse_week_ref(end_raw)

    if start_year != end_year:
        raise argparse.ArgumentTypeError("Week ranges must stay in the same year")
    if start_week > end_week:
        raise argparse.ArgumentTypeError("Week range start must be less than or equal to end")

    return [(start_year, week) for week in range(start_week, end_week + 1)]


def format_week(year: int, week: int) -> str:
    return f"{year}:w{week:02d}"


def format_utc_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.isoformat(timespec="minutes")
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%d %H:%M UTC")


def dedupe_weeks(weeks: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in weeks:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def send_alarmer_message(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
    response = requests.get(
        ALARMBOT_URL,
        params={"key": key, "message": text},
        timeout=timeout_seconds,
    )
    response_text = response.text if response.text else "<empty>"
    log(f"Alarmer request URL: {response.url}")
    log(f"Alarmer response status={response.status_code} body={response_text}")
    return response.ok


def build_slots_message(
    available: dict[tuple[int, int], list[Slot]],
    failures: list[tuple[int, int, str]],
) -> str:
    lines = ["Migri slots available:"]
    for (year, week), slots in available.items():
        sorted_slots = sorted(slots, key=lambda slot: slot.start_time)
        lines.append(f"- {format_week(year, week)}: {len(sorted_slots)} slot(s)")
        for slot in sorted_slots:
            lines.append(f"  {format_utc_timestamp(slot.start_time)}")

    if failures:
        failed_weeks = ", ".join(format_week(year, week) for year, week, _ in failures)
        lines.append(f"Failed weeks: {failed_weeks}")

    lines.append(f"Open Migri: {MIGRI_LINK}")
    return "\n".join(lines)


def build_no_slots_message(weeks: list[tuple[int, int]], failures: list[tuple[int, int, str]]) -> str:
    checked = ", ".join(format_week(year, week) for year, week in weeks)
    lines = [f"No slots found for: {checked}"]
    if failures:
        failed_weeks = ", ".join(format_week(year, week) for year, week, _ in failures)
        lines.append(f"Failed weeks: {failed_weeks}")
    lines.append(f"Open Migri: {MIGRI_LINK}")
    return "\n".join(lines)


def build_all_failed_message(failures: list[tuple[int, int, str]]) -> str:
    details = "; ".join(f"{format_week(y, w)} ({err})" for y, w, err in failures)
    return f"Migri check failed for all requested weeks: {details}\nOpen Migri: {MIGRI_LINK}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Migri slots and send AlarmerBot notifications.")
    parser.add_argument("--alarmer-key", required=True, help="AlarmerBot key.")
    parser.add_argument(
        "--week",
        dest="weeks",
        action="append",
        type=str,
        required=True,
        help=(
            "Week selector in YEAR:WEEK format or range YEAR:WEEK..YEAR:WEEK "
            "(e.g. 2026:1..2026:20). Repeat this flag to pass multiple selectors."
        ),
    )
    parser.add_argument(
        "--send-no-slots",
        action="store_true",
        help='Send "no slots found" notification when no availability is found.',
    )
    parser.add_argument("--language", default="fi", help="Migri language code (default: fi).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Migri API base URL.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    expanded_weeks: list[tuple[int, int]] = []
    for selector in args.weeks:
        expanded_weeks.extend(parse_week_selector(selector))
    weeks = dedupe_weeks(expanded_weeks)
    client = MigriClient(base_url=args.base_url, language=args.language)

    available: dict[tuple[int, int], list[Slot]] = {}
    failures: list[tuple[int, int, str]] = []

    for index, (year, week) in enumerate(weeks):
        if index > 0:
            log(f"Sleeping {FETCH_DELAY_SECONDS:.1f}s before next week fetch...")
            time.sleep(FETCH_DELAY_SECONDS)

        try:
            slots = client.get_slots("helsinki", year, week)
        except Exception as exc:
            failures.append((year, week, str(exc)))
            log(f"Failed to fetch {format_week(year, week)}: {exc}")
            continue

        log(f"Fetched {format_week(year, week)}: {len(slots)} slot(s)")
        if slots:
            available[(year, week)] = slots

    if len(failures) == len(weeks):
        message = build_all_failed_message(failures)
        try:
            sent = send_alarmer_message(args.alarmer_key, message)
        except requests.RequestException as exc:
            log(f"Notification failed: {exc}")
            return 2
        if not sent:
            log("Notification failed: non-2xx response from AlarmerBot")
            return 2
        return 1

    should_send = bool(available) or args.send_no_slots
    if not should_send:
        log("No slots found; notification skipped (use --send-no-slots to enable).")
        return 0

    if available:
        message = build_slots_message(available=available, failures=failures)
    else:
        message = build_no_slots_message(weeks=weeks, failures=failures)

    try:
        sent = send_alarmer_message(args.alarmer_key, message)
    except requests.RequestException as exc:
        log(f"Notification failed: {exc}")
        return 2

    if not sent:
        log("Notification failed: non-2xx response from AlarmerBot")
        return 2

    log("Notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
