from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import time
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import requests

# Support direct execution: `python scripts/notify.py ...`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migri_appointment.client import DEFAULT_BASE_URL, MigriClient
from migri_appointment.service_catalog import CATEGORIES_BY_SLUG, SERVICE_CATEGORIES, ServiceOption
from migri_appointment.types import Slot

ALARMBOT_URL = "https://alarmerbot.ru/"
MIGRI_LINK = "https://migri.vihta.com/"
FETCH_DELAY_SECONDS = 2.0
HELSINKI_TZ = ZoneInfo("Europe/Helsinki")


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


def parse_date_ref(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date value '{value}', expected YYYY-MM-DD (e.g. 2026-06-22)"
        ) from exc


def parse_date_selector(value: str) -> list[date]:
    if ".." not in value:
        return [parse_date_ref(value)]

    start_raw, end_raw = value.split("..", maxsplit=1)
    start_date = parse_date_ref(start_raw)
    end_date = parse_date_ref(end_raw)

    if start_date > end_date:
        raise argparse.ArgumentTypeError("Date range start must be less than or equal to end")

    result: list[date] = []
    current = start_date
    while current <= end_date:
        result.append(current)
        current += timedelta(days=1)
    return result


def format_week(year: int, week: int) -> str:
    return f"{year}:w{week:02d}"


def format_date_ref(value: date) -> str:
    return value.isoformat()


def format_utc_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.isoformat(timespec="minutes")
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%d %H:%M UTC")


def format_local_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.isoformat(timespec="minutes")
    local_dt = dt.astimezone(HELSINKI_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


def dedupe_weeks(weeks: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in weeks:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def dedupe_dates(values: Iterable[date]) -> list[date]:
    result: list[date] = []
    seen: set[date] = set()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def week_ref_for_date(value: date) -> tuple[int, int]:
    week_info = value.isocalendar()
    return week_info.year, week_info.week


def dates_to_weeks(values: Iterable[date]) -> list[tuple[int, int]]:
    return dedupe_weeks(week_ref_for_date(item) for item in values)


def slot_local_date(slot: Slot) -> date:
    return slot.start_time.astimezone(HELSINKI_TZ).date()


def filter_slots_for_dates(slots: list[Slot], requested_dates: set[date]) -> list[Slot]:
    return [slot for slot in slots if slot_local_date(slot) in requested_dates]


def failed_dates_from_week_failures(
    requested_dates: list[date], failures: list[tuple[int, int, str]]
) -> list[tuple[date, str]]:
    errors_by_week = {(year, week): error for year, week, error in failures}
    result: list[tuple[date, str]] = []
    for requested_date in requested_dates:
        error = errors_by_week.get(week_ref_for_date(requested_date))
        if error is not None:
            result.append((requested_date, error))
    return result


def expand_week_selectors(parser: argparse.ArgumentParser, selectors: Sequence[str]) -> list[tuple[int, int]]:
    expanded_weeks: list[tuple[int, int]] = []
    for selector in selectors:
        try:
            expanded_weeks.extend(parse_week_selector(selector))
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    return dedupe_weeks(expanded_weeks)


def expand_date_selectors(parser: argparse.ArgumentParser, selectors: Sequence[str]) -> list[date]:
    expanded_dates: list[date] = []
    for selector in selectors:
        try:
            expanded_dates.extend(parse_date_selector(selector))
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    return dedupe_dates(expanded_dates)


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


def build_slots_message_by_week(
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


def build_slots_message_by_date(
    available: dict[date, list[Slot]],
    failures: list[tuple[date, str]],
) -> str:
    lines = ["Migri slots available:"]
    for selected_date, slots in available.items():
        sorted_slots = sorted(slots, key=lambda slot: slot.start_time)
        lines.append(f"- {format_date_ref(selected_date)}: {len(sorted_slots)} slot(s)")
        for slot in sorted_slots:
            lines.append(f"  {format_local_timestamp(slot.start_time)}")

    if failures:
        failed_dates = ", ".join(format_date_ref(selected_date) for selected_date, _ in failures)
        lines.append(f"Failed dates: {failed_dates}")

    lines.append(f"Open Migri: {MIGRI_LINK}")
    return "\n".join(lines)


def build_no_slots_message_by_week(
    weeks: list[tuple[int, int]], failures: list[tuple[int, int, str]]
) -> str:
    checked = ", ".join(format_week(year, week) for year, week in weeks)
    lines = [f"No slots found for: {checked}"]
    if failures:
        failed_weeks = ", ".join(format_week(year, week) for year, week, _ in failures)
        lines.append(f"Failed weeks: {failed_weeks}")
    lines.append(f"Open Migri: {MIGRI_LINK}")
    return "\n".join(lines)


def build_no_slots_message_by_date(dates: list[date], failures: list[tuple[date, str]]) -> str:
    checked = ", ".join(format_date_ref(value) for value in dates)
    lines = [f"No slots found for: {checked}"]
    if failures:
        failed_dates = ", ".join(format_date_ref(selected_date) for selected_date, _ in failures)
        lines.append(f"Failed dates: {failed_dates}")
    lines.append(f"Open Migri: {MIGRI_LINK}")
    return "\n".join(lines)


def build_all_failed_message_by_week(failures: list[tuple[int, int, str]]) -> str:
    details = "; ".join(f"{format_week(y, w)} ({err})" for y, w, err in failures)
    return f"Migri check failed for all requested weeks: {details}\nOpen Migri: {MIGRI_LINK}"


def build_all_failed_message_by_date(failures: list[tuple[date, str]]) -> str:
    details = "; ".join(f"{format_date_ref(selected_date)} ({err})" for selected_date, err in failures)
    return f"Migri check failed for all requested dates: {details}\nOpen Migri: {MIGRI_LINK}"


def category_slugs() -> list[str]:
    return [category.slug for category in SERVICE_CATEGORIES]


def resolve_service_selection(
    parser: argparse.ArgumentParser, category_slug: str, service_slug: str | None
) -> ServiceOption:
    category = CATEGORIES_BY_SLUG[category_slug]
    if len(category.services) == 1:
        if service_slug is not None:
            parser.error(
                f"--service must not be provided for category '{category_slug}'; "
                f"it auto-selects '{category.services[0].slug}'"
            )
        return category.services[0]

    if service_slug is None:
        valid_services = ", ".join(service.slug for service in category.services)
        parser.error(
            f"--service is required for category '{category_slug}'. "
            f"Valid services: {valid_services}"
        )

    services_by_slug = {service.slug: service for service in category.services}
    selected = services_by_slug.get(service_slug)
    if selected is None:
        valid_services = ", ".join(service.slug for service in category.services)
        parser.error(
            f"invalid --service '{service_slug}' for category '{category_slug}'. "
            f"Valid services: {valid_services}"
        )
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Migri slots and send AlarmerBot notifications.")
    parser.add_argument("--alarmer-key", required=True, help="AlarmerBot key.")
    parser.add_argument(
        "--category",
        required=True,
        choices=category_slugs(),
        help="Hardcoded Migri category slug.",
    )
    parser.add_argument(
        "--service",
        help=(
            "Hardcoded service slug for the selected category. Required only when the "
            "category has multiple services and forbidden when it has only one."
        ),
    )
    parser.add_argument(
        "--week",
        dest="weeks",
        action="append",
        type=str,
        help=(
            "Week selector in YEAR:WEEK format or range YEAR:WEEK..YEAR:WEEK "
            "(e.g. 2026:1..2026:20). Repeat this flag to pass multiple selectors."
        ),
    )
    parser.add_argument(
        "--date",
        dest="dates",
        action="append",
        type=str,
        help=(
            "Date selector in YYYY-MM-DD format or range YYYY-MM-DD..YYYY-MM-DD "
            "(e.g. 2026-06-22..2026-06-24). Repeat this flag to pass multiple selectors."
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
    selected_service = resolve_service_selection(parser, args.category, args.service)
    has_weeks = bool(args.weeks)
    has_dates = bool(args.dates)
    if has_weeks == has_dates:
        parser.error("exactly one of --week or --date must be provided")

    requested_dates: list[date] | None = None
    if has_weeks:
        weeks = expand_week_selectors(parser, args.weeks)
    else:
        requested_dates = expand_date_selectors(parser, args.dates)
        weeks = dates_to_weeks(requested_dates)

    client = MigriClient(
        base_url=args.base_url,
        language=args.language,
        service_selection_id=selected_service.service_selection_id,
    )

    available_by_week: dict[tuple[int, int], list[Slot]] = {}
    available_by_date: dict[date, list[Slot]] = {}
    failures: list[tuple[int, int, str]] = []
    requested_date_set = set(requested_dates or [])

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
        if has_weeks:
            if slots:
                available_by_week[(year, week)] = slots
            continue

        filtered_slots = filter_slots_for_dates(slots, requested_date_set)
        for slot in filtered_slots:
            selected_date = slot_local_date(slot)
            available_by_date.setdefault(selected_date, []).append(slot)

    if len(failures) == len(weeks):
        if has_weeks:
            message = build_all_failed_message_by_week(failures)
        else:
            failed_dates = failed_dates_from_week_failures(requested_dates or [], failures)
            message = build_all_failed_message_by_date(failed_dates)
        try:
            sent = send_alarmer_message(args.alarmer_key, message)
        except requests.RequestException as exc:
            log(f"Notification failed: {exc}")
            return 2
        if not sent:
            log("Notification failed: non-2xx response from AlarmerBot")
            return 2
        return 1

    if has_weeks:
        available = available_by_week
        should_send = bool(available) or args.send_no_slots
    else:
        ordered_available_by_date = {
            requested_date: available_by_date[requested_date]
            for requested_date in requested_dates or []
            if requested_date in available_by_date
        }
        available = ordered_available_by_date
        should_send = bool(available) or args.send_no_slots

    if not should_send:
        log("No slots found; notification skipped (use --send-no-slots to enable).")
        return 0

    if has_weeks:
        if available:
            message = build_slots_message_by_week(available=available, failures=failures)
        else:
            message = build_no_slots_message_by_week(weeks=weeks, failures=failures)
    else:
        failed_dates = failed_dates_from_week_failures(requested_dates or [], failures)
        if available:
            message = build_slots_message_by_date(available=available, failures=failed_dates)
        else:
            message = build_no_slots_message_by_date(
                dates=requested_dates or [], failures=failed_dates
            )

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
