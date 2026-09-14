from __future__ import annotations

from datetime import datetime, timezone
import json
import threading

import pytest

from migri_appointment.client import (
    DEFAULT_QUERY_LIMITER,
    DEFAULT_REQUEST_HEADERS,
    MigriClient,
    MigriQueryLimiter,
)
from migri_appointment.errors import (
    MigriApiError,
    MigriForbiddenError,
    UnsupportedOfficeError,
)


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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[FakeResponse],
    clock: FakeClock | None = None,
) -> tuple[FakeSession, MigriClient]:
    fake_session = FakeSession(responses)
    monkeypatch.setattr("migri_appointment.client.requests.Session", lambda: fake_session)
    fake_clock = clock or FakeClock()
    client = MigriClient(
        query_limiter=MigriQueryLimiter(
            clock=fake_clock.monotonic,
            sleeper=fake_clock.sleep,
        )
    )
    return fake_session, client


def test_query_limiter_enforces_interval_and_rolling_window():
    clock = FakeClock()
    limiter = MigriQueryLimiter(clock=clock.monotonic, sleeper=clock.sleep)
    query_starts: list[float] = []

    for _ in range(11):
        limiter.run(lambda: query_starts.append(clock.monotonic()))

    assert query_starts == [
        0.0,
        2.0,
        4.0,
        6.0,
        8.0,
        10.0,
        12.0,
        14.0,
        16.0,
        18.0,
        60.0,
    ]
    assert clock.sleeps == [2.0] * 9 + [42.0]


def test_query_limiter_allows_only_one_parallel_query():
    limiter = MigriQueryLimiter(
        min_interval_seconds=0,
        max_queries_per_window=100,
    )
    first_started = threading.Event()
    release_first = threading.Event()
    second_attempted = threading.Event()
    second_started = threading.Event()

    def first_query() -> None:
        first_started.set()
        assert release_first.wait(timeout=1)

    def run_second_query() -> None:
        second_attempted.set()
        limiter.run(second_started.set)

    first_thread = threading.Thread(target=lambda: limiter.run(first_query))
    first_thread.start()
    assert first_started.wait(timeout=1)

    second_thread = threading.Thread(target=run_second_query)
    second_thread.start()
    assert second_attempted.wait(timeout=1)
    assert not second_started.wait(timeout=0.05)

    release_first.set()
    first_thread.join(timeout=1)
    second_thread.join(timeout=1)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_started.is_set()


def test_get_slots_rate_limits_both_http_methods(monkeypatch: pytest.MonkeyPatch):
    clock = FakeClock()
    _, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(200, {"resources": [], "dailyTimesByOffice": []}),
        ],
        clock=clock,
    )

    client.get_slots("helsinki", 2026, 21)

    assert clock.sleeps == [2.0]


def test_clients_share_the_default_process_limiter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "migri_appointment.client.requests.Session",
        lambda: FakeSession([]),
    )

    first_client = MigriClient()
    second_client = MigriClient()

    assert first_client._query_limiter is DEFAULT_QUERY_LIMITER
    assert second_client._query_limiter is DEFAULT_QUERY_LIMITER


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


def test_client_sets_browser_like_headers_by_default(monkeypatch: pytest.MonkeyPatch):
    fake_session, _ = make_client(monkeypatch, responses=[])
    for key, value in DEFAULT_REQUEST_HEADERS.items():
        assert fake_session.headers.get(key) == value

    user_agent = fake_session.headers["User-Agent"]
    assert user_agent.startswith("Mozilla/5.0")
    assert "Chrome/" in user_agent
    assert user_agent.endswith("Safari/537.36")


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


def test_get_slots_reuses_session_between_week_queries(monkeypatch: pytest.MonkeyPatch):
    fake_session, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(200, {"resources": [], "dailyTimesByOffice": []}),
            FakeResponse(200, {"resources": [], "dailyTimesByOffice": []}),
        ],
    )

    client.get_slots("helsinki", 2026, 21)
    client.get_slots("helsinki", 2026, 22)

    assert [call["method"] for call in fake_session.calls] == ["GET", "POST", "POST"]
    assert fake_session.calls[1]["headers"]["vihta-session"] == "session-123"
    assert fake_session.calls[2]["headers"]["vihta-session"] == "session-123"


@pytest.mark.parametrize(
    ("city", "office_id"),
    [
        ("helsinki", "438cd01e-9d81-40d9-b31d-5681c11bd974"),
        ("turku", "074cc6f8-735b-4ea5-ad9a-9e517fef09bb"),
        ("raisio", "074cc6f8-735b-4ea5-ad9a-9e517fef09bb"),
        ("tampere", "08d44a6b-af37-4a30-8462-1d6f5fc5cd61"),
        ("oulu", "a4657f2f-eacd-4668-9c2b-92a7cdd44408"),
        ("lahti", "a893849c-c0d9-489b-92a3-6dd8a36ef9f9"),
        ("kuopio", "10a1fb12-3783-4a3b-a532-468b93bb85c9"),
        ("lappeenranta", "b84cfd93-4cf9-40e7-ad79-78aca8c422a0"),
        ("vaasa", "6b5d9667-e526-4136-af5a-b1d20f5d01b3"),
        ("rovaniemi", "891474c3-f7ee-4fe8-a542-38169726503a"),
        ("aland", "87558cb4-975b-46e9-a411-51ca67c56a08"),
        ("ÅLAND", "87558cb4-975b-46e9-a411-51ca67c56a08"),
        ("ahvenanmaa", "87558cb4-975b-46e9-a411-51ca67c56a08"),
        ("ahvenanmaa-aland", "87558cb4-975b-46e9-a411-51ca67c56a08"),
        ("mariehamn", "87558cb4-975b-46e9-a411-51ca67c56a08"),
    ],
)
def test_get_slots_resolves_supported_city(
    monkeypatch: pytest.MonkeyPatch, city: str, office_id: str
):
    fake_session, client = make_client(
        monkeypatch,
        responses=[
            FakeResponse(200, {"id": "session-123"}),
            FakeResponse(200, {"resources": [], "dailyTimesByOffice": [[], [], [], [], [], [], []]}),
        ],
    )

    client.get_slots(city, 2026, 21)

    assert fake_session.calls[1]["url"].endswith(f"/offices/{office_id}/2026/w21")


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


@pytest.mark.parametrize("failed_request", ["session", "scheduling"])
def test_403_raises_migri_forbidden_error(
    monkeypatch: pytest.MonkeyPatch, failed_request: str
):
    forbidden = FakeResponse(403, {"error": "forbidden"})
    responses = (
        [forbidden]
        if failed_request == "session"
        else [FakeResponse(200, {"id": "session-123"}), forbidden]
    )
    _, client = make_client(monkeypatch, responses=responses)

    with pytest.raises(MigriForbiddenError, match="failed with status 403"):
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
