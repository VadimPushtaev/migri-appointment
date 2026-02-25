from __future__ import annotations

import json
from datetime import datetime

import requests

from .errors import MigriApiError, UnsupportedOfficeError
from .types import Resource, Slot

DEFAULT_BASE_URL = "https://migri.vihta.com/public/migri/api"
DEFAULT_SERVICE_SELECTION_ID = "3e03034d-a44b-4771-b1e5-2c4a6f581b7d"
DEFAULT_OFFICE_MAP = {"helsinki": "438cd01e-9d81-40d9-b31d-5681c11bd974"}
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "curl/8.0.0",
    "Accept": "*/*",
}


class MigriClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        language: str = "fi",
        office_map: dict[str, str] | None = None,
        service_selection_id: str = DEFAULT_SERVICE_SELECTION_ID,
        timeout_seconds: float = 15.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._office_map = office_map or DEFAULT_OFFICE_MAP
        self._service_selection_id = service_selection_id
        self._timeout_seconds = timeout_seconds
        self._http = requests.Session()
        self._http.headers.update(DEFAULT_REQUEST_HEADERS)
        if default_headers:
            self._http.headers.update(default_headers)

    def get_slots(self, office_name: str, year: int, week: int) -> list[Slot]:
        if not 1 <= week <= 53:
            raise ValueError(f"week must be in range 1..53, got {week}")

        office_key = office_name.strip().lower()
        office_id = self._office_map.get(office_key)
        if office_id is None:
            raise UnsupportedOfficeError(
                f"unsupported office '{office_name}', supported: {sorted(self._office_map)}"
            )

        session_id = self._create_session()
        payload = self._fetch_week(office_id=office_id, year=year, week=week, session_id=session_id)
        return self._parse_slots(payload)

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
