from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from migri_appointment.client import DEFAULT_REQUEST_HEADERS, MigriClient
from migri_appointment.errors import MigriApiError, UnsupportedOfficeError


class FakeResponse:
    def __init__(self, status_code: int, payload, url: str = "https://example.test/api"):
        self.status_code = status_code
        self._payload = payload
        self.url = url
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(payload) if not isinstance(payload, Exception) else ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.headers: dict[str, str] = {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "params": params,
                "headers": headers,
                "json": None,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("No fake responses left for call")
        return self._responses.pop(0)

    def post(self, url, params=None, headers=None, json=None, timeout=None):
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "params": params,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("No fake responses left for call")
        return self._responses.pop(0)


def make_client(
    monkeypatch: pytest.MonkeyPatch, responses: list[FakeResponse]
) -> tuple[FakeSession, MigriClient]:
    fake_session = FakeSession(responses)
    monkeypatch.setattr("migri_appointment.client.requests.Session", lambda: fake_session)
    client = MigriClient()
    return fake_session, client


def test_get_slots_returns_detailed_slots(monkeypatch: pytest.MonkeyPatch):
    fake_session, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(
                200,
                {
                    "resources": [
                        {"id": "r-1", "name": "Queue 1", "title": "Type A"},
                        {"id": "r-2", "name": "Queue 2", "title": "Type B"},
                    ],
                    "dailyTimesByOffice": [
                        [
                            {"resources": [1, 0], "startTimestamp": "2026-06-22T05:15:00.000Z"},
                        ],
                        [],
                        [],
                        [],
                        [],
                        [],
                        [],
                    ],
                },
            ),
        ],
    )

    slots = client.get_slots("helsinki", 2026, 26)

    assert len(slots) == 1
    assert slots[0].start_time == datetime(2026, 6, 22, 5, 15, tzinfo=timezone.utc)
    assert [r.id for r in slots[0].resources] == ["r-2", "r-1"]
    assert [r.name for r in slots[0].resources] == ["Queue 2", "Queue 1"]
    assert [r.title for r in slots[0].resources] == ["Type B", "Type A"]
    assert fake_session.calls[0]["method"] == "GET"

    assert fake_session.calls[1]["headers"]["vihta-session"] == "session-123"


def test_client_sets_curl_like_headers_by_default(monkeypatch: pytest.MonkeyPatch):
    fake_session, _ = make_client(monkeypatch, responses=[])
    for key, value in DEFAULT_REQUEST_HEADERS.items():
        assert fake_session.headers.get(key) == value


def test_get_slots_empty_week_returns_empty_list(monkeypatch: pytest.MonkeyPatch):
    _, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(200, {"resources": [], "dailyTimesByOffice": [[], [], [], [], [], [], []]}),
        ],
    )

    slots = client.get_slots("helsinki", 2026, 21)
    assert slots == []


def test_unsupported_office_raises(monkeypatch: pytest.MonkeyPatch):
    _, client = make_client(monkeypatch, responses=[])
    with pytest.raises(UnsupportedOfficeError):
        client.get_slots("espoo", 2026, 21)


@pytest.mark.parametrize("week", [0, 54])
def test_invalid_week_raises_value_error(monkeypatch: pytest.MonkeyPatch, week: int):
    _, client = make_client(monkeypatch, responses=[])
    with pytest.raises(ValueError):
        client.get_slots("helsinki", 2026, week)


def test_non_200_from_sessions_raises_migri_api_error(monkeypatch: pytest.MonkeyPatch):
    _, client = make_client(
        monkeypatch,
        responses=[FakeResponse(500, {"error": "boom"}, url="https://migri.vihta.com/public/migri/api/sessions")],
    )
    with pytest.raises(MigriApiError, match="session request failed with status 500"):
        client.get_slots("helsinki", 2026, 26)


def test_non_200_from_scheduling_raises_migri_api_error(monkeypatch: pytest.MonkeyPatch):
    _, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(
                503,
                {"error": "unavailable"},
                url=(
                    "https://migri.vihta.com/public/migri/api/scheduling/"
                    "offices/438cd01e-9d81-40d9-b31d-5681c11bd974/2026/w26"
                ),
            ),
        ],
    )
    with pytest.raises(MigriApiError, match="scheduling request failed with status 503"):
        client.get_slots("helsinki", 2026, 26)


def test_bad_resource_index_raises_migri_api_error(monkeypatch: pytest.MonkeyPatch):
    _, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(
                200,
                {
                    "resources": [{"id": "r-1", "name": "Queue 1", "title": "Type A"}],
                    "dailyTimesByOffice": [
                        [{"resources": [2], "startTimestamp": "2026-06-22T05:15:00.000Z"}],
                        [],
                        [],
                        [],
                        [],
                        [],
                        [],
                    ],
                },
            ),
        ],
    )
    with pytest.raises(MigriApiError, match="out of bounds"):
        client.get_slots("helsinki", 2026, 26)
