from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pytest

from migri_appointment.types import Resource, Slot
from scripts import notify


@pytest.fixture(autouse=True)
def disable_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notify.time, "sleep", lambda _: None)


def make_fake_client_factory(mapping: dict[tuple[int, int], object]):
    class FakeClient:
        def __init__(self, base_url: str, language: str):
            self.base_url = base_url
            self.language = language

        def get_slots(self, office_name: str, year: int, week: int):
            assert office_name == "helsinki"
            value = mapping[(year, week)]
            if isinstance(value, Exception):
                raise value
            return value

    return FakeClient


def sample_slot() -> Slot:
    return Slot(
        start_time=datetime(2026, 6, 22, 5, 15, tzinfo=timezone.utc),
        resources=[Resource(id="r-1", name="Queue 1", title="Type A")],
    )


def slot_at(year: int, month: int, day: int, hour: int, minute: int) -> Slot:
    return Slot(
        start_time=datetime(year, month, day, hour, minute, tzinfo=timezone.utc),
        resources=[Resource(id="r-1", name="Queue 1", title="Type A")],
    )


def test_parse_week_selector_single():
    assert notify.parse_week_selector("2026:26") == [(2026, 26)]


def test_parse_week_selector_range():
    assert notify.parse_week_selector("2026:1..2026:3") == [
        (2026, 1),
        (2026, 2),
        (2026, 3),
    ]


@pytest.mark.parametrize(
    "raw_value",
    [
        "2026-w26",
        "foo",
        "2026:0",
        "2026:54",
        "2026:20..2026:1",
        "2026:1..2027:2",
        "2026:1..oops",
    ],
)
def test_parse_week_selector_invalid(raw_value: str):
    with pytest.raises(argparse.ArgumentTypeError):
        notify.parse_week_selector(raw_value)


def test_main_sends_when_slots_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): [],
                (2026, 26): [
                    slot_at(2026, 6, 22, 6, 15),
                    slot_at(2026, 6, 22, 5, 15),
                ],
            }
        ),
    )

    sent_messages: list[tuple[str, str]] = []

    def fake_send(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
        sent_messages.append((key, text))
        return True

    monkeypatch.setattr(notify, "send_alarmer_message", fake_send)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21",
            "--week",
            "2026:26",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    key, text = sent_messages[0]
    assert key == "abc-key"
    assert "Migri slots available" in text
    assert "2026:w26" in text
    assert "2026-06-22 05:15 UTC" in text
    assert "2026-06-22 06:15 UTC" in text
    assert text.index("2026-06-22 05:15 UTC") < text.index("2026-06-22 06:15 UTC")
    assert f"Open Migri: {notify.MIGRI_LINK}" in text


def test_main_skips_when_no_slots_and_flag_not_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): [],
                (2026, 22): [],
            }
        ),
    )

    calls = {"count": 0}

    def fake_send(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
        calls["count"] += 1
        return True

    monkeypatch.setattr(notify, "send_alarmer_message", fake_send)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21",
            "--week",
            "2026:22",
        ]
    )

    assert rc == 0
    assert calls["count"] == 0


def test_main_sends_no_slots_message_when_flag_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): [],
                (2026, 22): [],
            }
        ),
    )

    sent_messages: list[str] = []

    def fake_send(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
        sent_messages.append(text)
        return True

    monkeypatch.setattr(notify, "send_alarmer_message", fake_send)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21..2026:22",
            "--send-no-slots",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    assert "No slots found" in sent_messages[0]
    assert "2026:w21" in sent_messages[0]
    assert "2026:w22" in sent_messages[0]
    assert f"Open Migri: {notify.MIGRI_LINK}" in sent_messages[0]


def test_main_includes_partial_failures(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): [],
                (2026, 26): RuntimeError("temporary error"),
                (2026, 27): [sample_slot()],
            }
        ),
    )

    sent_messages: list[str] = []

    def fake_send(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
        sent_messages.append(text)
        return True

    monkeypatch.setattr(notify, "send_alarmer_message", fake_send)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21",
            "--week",
            "2026:26",
            "--week",
            "2026:27",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    text = sent_messages[0]
    assert "2026:w27" in text
    assert "Failed weeks: 2026:w26" in text


def test_main_all_failed_returns_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): RuntimeError("boom-21"),
                (2026, 22): RuntimeError("boom-22"),
            }
        ),
    )

    sent_messages: list[str] = []

    def fake_send(key: str, text: str, timeout_seconds: float = 10.0) -> bool:
        sent_messages.append(text)
        return True

    monkeypatch.setattr(notify, "send_alarmer_message", fake_send)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21",
            "--week",
            "2026:22",
        ]
    )

    assert rc == 1
    assert len(sent_messages) == 1
    assert "failed for all requested weeks" in sent_messages[0]
    assert f"Open Migri: {notify.MIGRI_LINK}" in sent_messages[0]


def test_main_notification_failure_returns_two(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 26): [sample_slot()],
            }
        ),
    )
    monkeypatch.setattr(notify, "send_alarmer_message", lambda *args, **kwargs: False)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:26",
        ]
    )

    assert rc == 2


def test_send_alarmer_message_logs_url_and_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    class FakeResponse:
        ok = True
        status_code = 200
        url = "https://alarmerbot.ru/?key=test-key&message=test-message"
        text = "OK"

    monkeypatch.setattr(notify.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = notify.send_alarmer_message("test-key", "test-message")

    assert result is True
    captured = capsys.readouterr().out
    assert "Alarmer request URL: https://alarmerbot.ru/?key=test-key&message=test-message" in captured
    assert "Alarmer response status=200 body=OK" in captured


def test_main_waits_between_week_fetches(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            {
                (2026, 21): [],
                (2026, 22): [],
            }
        ),
    )
    monkeypatch.setattr(notify, "send_alarmer_message", lambda *args, **kwargs: True)

    sleep_calls: list[float] = []
    monkeypatch.setattr(notify.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--week",
            "2026:21..2026:22",
            "--send-no-slots",
        ]
    )

    assert rc == 0
    assert sleep_calls == [notify.FETCH_DELAY_SECONDS]
