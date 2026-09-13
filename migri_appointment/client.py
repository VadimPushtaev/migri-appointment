from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime
from functools import wraps
import json
import threading
import time
from typing import Any, TypeVar, cast

import requests

from .errors import MigriApiError, UnsupportedOfficeError
from .office_catalog import OFFICES_BY_CITY_SLUG, normalize_city_slug
from .types import Resource, Slot

DEFAULT_BASE_URL = "https://migri.vihta.com/public/migri/api"
DEFAULT_SERVICE_SELECTION_ID = "3e03034d-a44b-4771-b1e5-2c4a6f581b7d"
DEFAULT_OFFICE_MAP = {
    city_slug: office.office_id for city_slug, office in OFFICES_BY_CITY_SLUG.items()
}
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "curl/8.0.0",
    "Accept": "*/*",
}
DEFAULT_MIN_QUERY_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_QUERIES_PER_WINDOW = 10
DEFAULT_QUERY_WINDOW_SECONDS = 60.0

QueryResult = TypeVar("QueryResult")
QueryMethod = TypeVar("QueryMethod", bound=Callable[..., object])


class MigriQueryLimiter:
    """Thread-safe, rolling-window limiter for Migri HTTP queries."""

    def __init__(
        self,
        min_interval_seconds: float = DEFAULT_MIN_QUERY_INTERVAL_SECONDS,
        max_queries_per_window: int = DEFAULT_MAX_QUERIES_PER_WINDOW,
        window_seconds: float = DEFAULT_QUERY_WINDOW_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        if max_queries_per_window < 1:
            raise ValueError("max_queries_per_window must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self._min_interval_seconds = min_interval_seconds
        self._max_queries_per_window = max_queries_per_window
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._query_starts: deque[float] = deque()
        self._lock = threading.Lock()

    def run(self, query: Callable[[], QueryResult]) -> QueryResult:
        # The lock is deliberately held while waiting and during the query. This
        # makes the rolling-window state atomic and permits only one in-flight
        # Migri HTTP request for this limiter.
        with self._lock:
            while True:
                now = self._clock()
                self._discard_expired_queries(now)

                interval_wait = 0.0
                if self._query_starts:
                    interval_wait = (
                        self._query_starts[-1] + self._min_interval_seconds - now
                    )

                window_wait = 0.0
                if len(self._query_starts) >= self._max_queries_per_window:
                    window_wait = self._query_starts[0] + self._window_seconds - now

                wait_seconds = max(interval_wait, window_wait)
                if wait_seconds <= 0:
                    break
                self._sleeper(wait_seconds)

            self._query_starts.append(self._clock())
            return query()

    def _discard_expired_queries(self, now: float) -> None:
        window_start = now - self._window_seconds
        while self._query_starts and self._query_starts[0] <= window_start:
            self._query_starts.popleft()


DEFAULT_QUERY_LIMITER = MigriQueryLimiter()


def migri_query(method: QueryMethod) -> QueryMethod:
    """Apply the client's shared Migri query limits to an HTTP method."""

    @wraps(method)
    def wrapped(self: MigriClient, *args: Any, **kwargs: Any) -> object:
        return self._query_limiter.run(lambda: method(self, *args, **kwargs))

    return cast(QueryMethod, wrapped)


class MigriClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        language: str = "fi",
        office_map: dict[str, str] | None = None,
        service_selection_id: str = DEFAULT_SERVICE_SELECTION_ID,
        timeout_seconds: float = 15.0,
        default_headers: dict[str, str] | None = None,
        query_limiter: MigriQueryLimiter | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._office_map = office_map or DEFAULT_OFFICE_MAP
        self._service_selection_id = service_selection_id
        self._timeout_seconds = timeout_seconds
        self._query_limiter = (
            query_limiter if query_limiter is not None else DEFAULT_QUERY_LIMITER
        )
        self._http = requests.Session()
        self._http.headers.update(DEFAULT_REQUEST_HEADERS)
        if default_headers:
            self._http.headers.update(default_headers)

    def get_slots(self, office_name: str, year: int, week: int) -> list[Slot]:
        if not 1 <= week <= 53:
            raise ValueError(f"week must be in range 1..53, got {week}")

        office_key = normalize_city_slug(office_name)
        office_id = self._office_map.get(office_key)
        if office_id is None:
            raise UnsupportedOfficeError(
                f"unsupported office '{office_name}', supported: {sorted(self._office_map)}"
            )

        session_id = self._create_session()
        payload = self._fetch_week(office_id=office_id, year=year, week=week, session_id=session_id)
        return self._parse_slots(payload)

    @migri_query
    def _create_session(self) -> str:
        url = f"{self._base_url}/sessions"
        response = self._http.get(url, timeout=self._timeout_seconds)
        if not response.ok:
            self._raise_http_error(response, context="session request")

        body = self._safe_json(response, context="session response")
        session_id = body.get("id")
        if not isinstance(session_id, str) or not session_id:
            raise MigriApiError("session response missing string field 'id'")
        return session_id

    @migri_query
    def _fetch_week(self, office_id: str, year: int, week: int, session_id: str) -> dict:
        url = f"{self._base_url}/scheduling/offices/{office_id}/{year}/w{week}"
        response = self._http.post(
            url,
            params={"start_hours": 0, "end_hours": 24, "mode": "SINGLE"},
            headers={"vihta-session": session_id},
            json={
                "serviceSelections": [{"values": [self._service_selection_id]}],
                "extraServices": [],
            },
            timeout=self._timeout_seconds,
        )
        if not response.ok:
            self._raise_http_error(response, context="scheduling request")
        return self._safe_json(response, context="scheduling response")

    def _raise_http_error(self, response: requests.Response, context: str) -> None:
        status_code = getattr(response, "status_code", "unknown")
        url = getattr(response, "url", "<unknown>")
        body_excerpt = self._response_excerpt(response)
        raise MigriApiError(
            f"{context} failed with status {status_code} for {url}; response body: {body_excerpt}"
        )

    def _response_excerpt(self, response: requests.Response, max_len: int = 500) -> str:
        text_value = getattr(response, "text", None)
        if isinstance(text_value, str) and text_value.strip():
            excerpt = " ".join(text_value.split())
        else:
            try:
                payload = response.json()
                excerpt = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            except ValueError:
                excerpt = "<empty>"

        if len(excerpt) > max_len:
            return excerpt[:max_len] + "..."
        return excerpt

    def _safe_json(self, response: requests.Response, context: str) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise MigriApiError(f"{context} was not valid JSON") from exc
        if not isinstance(body, dict):
            raise MigriApiError(f"{context} must be a JSON object")
        return body

    def _parse_slots(self, payload: dict) -> list[Slot]:
        raw_resources = payload.get("resources")
        raw_days = payload.get("dailyTimesByOffice")
        if not isinstance(raw_resources, list):
            raise MigriApiError("scheduling response missing list field 'resources'")
        if not isinstance(raw_days, list):
            raise MigriApiError("scheduling response missing list field 'dailyTimesByOffice'")

        resources = [self._parse_resource(item) for item in raw_resources]
        slots: list[Slot] = []

        for day_index, raw_day in enumerate(raw_days):
            if not isinstance(raw_day, list):
                raise MigriApiError(f"dailyTimesByOffice[{day_index}] must be a list")
            for raw_slot in raw_day:
                if not isinstance(raw_slot, dict):
                    raise MigriApiError("slot entry must be an object")
                slots.append(self._parse_slot(raw_slot, resources))

        return slots

    def _parse_resource(self, raw_resource: object) -> Resource:
        if not isinstance(raw_resource, dict):
            raise MigriApiError("resource entry must be an object")

        resource_id = raw_resource.get("id")
        name = raw_resource.get("name")
        title = raw_resource.get("title")
        if not isinstance(resource_id, str):
            raise MigriApiError("resource.id must be a string")
        if not isinstance(name, str):
            raise MigriApiError("resource.name must be a string")
        if not isinstance(title, str):
            raise MigriApiError("resource.title must be a string")

        return Resource(id=resource_id, name=name, title=title)

    def _parse_slot(self, raw_slot: dict, resources: list[Resource]) -> Slot:
        raw_start_timestamp = raw_slot.get("startTimestamp")
        if not isinstance(raw_start_timestamp, str):
            raise MigriApiError("slot.startTimestamp must be a string")

        try:
            start_time = datetime.fromisoformat(raw_start_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MigriApiError("slot.startTimestamp has invalid ISO format") from exc

        raw_indexes = raw_slot.get("resources")
        if not isinstance(raw_indexes, list):
            raise MigriApiError("slot.resources must be a list")

        resolved_resources: list[Resource] = []
        for idx in raw_indexes:
            if not isinstance(idx, int):
                raise MigriApiError("slot.resources values must be integers")
            if idx < 0 or idx >= len(resources):
                raise MigriApiError(f"slot resource index out of bounds: {idx}")
            resolved_resources.append(resources[idx])

        return Slot(start_time=start_time, resources=resolved_resources)
