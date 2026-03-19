from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

import pytest

from migri_appointment.types import Resource, Slot
from scripts import notify


@pytest.fixture(autouse=True)
def disable_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notify.time, "sleep", lambda _: None)


def make_fake_client_factory(
    mapping: dict[tuple[int, int], object],
    expected_service_selection_id: str | None = None,
):
    class FakeClient:
        def __init__(self, base_url: str, language: str, service_selection_id: str):
            self.base_url = base_url
            self.language = language
            self.service_selection_id = service_selection_id
            if expected_service_selection_id is not None:
                assert service_selection_id == expected_service_selection_id

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


def test_parse_date_selector_single():
    assert notify.parse_date_selector("2026-06-22") == [date(2026, 6, 22)]


def test_parse_date_selector_range():
    assert notify.parse_date_selector("2026-12-31..2027-01-02") == [
        date(2026, 12, 31),
        date(2027, 1, 1),
        date(2027, 1, 2),
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


@pytest.mark.parametrize(
    "raw_value",
    [
        "2026/06/22",
        "foo",
        "2026-02-30",
        "2026-06-23..2026-06-22",
        "2026-06-22..oops",
    ],
)
def test_parse_date_selector_invalid(raw_value: str):
    with pytest.raises(argparse.ArgumentTypeError):
        notify.parse_date_selector(raw_value)


def test_main_sends_when_slots_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            mapping={
                (2026, 21): [],
                (2026, 26): [
                    slot_at(2026, 6, 22, 6, 15),
                    slot_at(2026, 6, 22, 5, 15),
                ],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 21): [],
                (2026, 22): [],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 21): [],
                (2026, 22): [],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 21): [],
                (2026, 26): RuntimeError("temporary error"),
                (2026, 27): [sample_slot()],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 21): RuntimeError("boom-21"),
                (2026, 22): RuntimeError("boom-22"),
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 26): [sample_slot()],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
        ),
    )
    monkeypatch.setattr(notify, "send_alarmer_message", lambda *args, **kwargs: False)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
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
            mapping={
                (2026, 21): [],
                (2026, 22): [],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
        ),
    )
    monkeypatch.setattr(notify, "send_alarmer_message", lambda *args, **kwargs: True)

    sleep_calls: list[float] = []
    monkeypatch.setattr(notify.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
            "--week",
            "2026:21..2026:22",
            "--send-no-slots",
        ]
    )

    assert rc == 0
    assert sleep_calls == [notify.FETCH_DELAY_SECONDS]


def test_main_rejects_missing_week_and_date(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "residence-permit",
                "--service",
                "permanent-residence-permit",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "exactly one of --week or --date must be provided" in captured.err


def test_main_rejects_mixing_week_and_date(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "residence-permit",
                "--service",
                "permanent-residence-permit",
                "--week",
                "2026:26",
                "--date",
                "2026-06-22",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "exactly one of --week or --date must be provided" in captured.err


def test_main_date_mode_sends_when_slots_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            mapping={
                (2026, 26): [
                    slot_at(2026, 6, 21, 22, 30),
                    slot_at(2026, 6, 22, 5, 15),
                    slot_at(2026, 6, 23, 5, 15),
                ],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
            "--date",
            "2026-06-22",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    text = sent_messages[0]
    assert "- 2026-06-22: 2 slot(s)" in text
    assert "2026-06-22 01:30 EEST" in text
    assert "2026-06-22 08:15 EEST" in text
    assert "2026-06-23" not in text
    assert "2026:w26" not in text


def test_main_date_mode_sends_no_slots_message_when_flag_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            mapping={
                (2026, 26): [],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
            "--date",
            "2026-06-22..2026-06-23",
            "--send-no-slots",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    text = sent_messages[0]
    assert "No slots found for: 2026-06-22, 2026-06-23" in text
    assert "Failed dates:" not in text
    assert "2026:w26" not in text


def test_main_date_mode_includes_failed_dates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            mapping={
                (2026, 26): RuntimeError("temporary error"),
                (2026, 27): [slot_at(2026, 6, 29, 5, 15)],
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
            "--date",
            "2026-06-22",
            "--date",
            "2026-06-29",
        ]
    )

    assert rc == 0
    assert len(sent_messages) == 1
    text = sent_messages[0]
    assert "- 2026-06-29: 1 slot(s)" in text
    assert "Failed dates: 2026-06-22" in text
    assert "Failed weeks:" not in text


def test_main_date_mode_all_failed_returns_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            mapping={
                (2026, 26): RuntimeError("boom-26"),
            },
            expected_service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
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
            "--category",
            "residence-permit",
            "--service",
            "permanent-residence-permit",
            "--date",
            "2026-06-22..2026-06-23",
        ]
    )

    assert rc == 1
    assert len(sent_messages) == 1
    text = sent_messages[0]
    assert "failed for all requested dates" in text
    assert "2026-06-22 (boom-26)" in text
    assert "2026-06-23 (boom-26)" in text


def test_main_auto_selects_singleton_category(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        notify,
        "MigriClient",
        make_fake_client_factory(
            expected_service_selection_id="000564ce-b800-4c2e-8040-62f50a09f55e",
            mapping={
                (2026, 26): [sample_slot()],
            },
        ),
    )
    monkeypatch.setattr(notify, "send_alarmer_message", lambda *args, **kwargs: True)

    rc = notify.main(
        [
            "--alarmer-key",
            "abc-key",
            "--category",
            "citizenship",
            "--week",
            "2026:26",
        ]
    )

    assert rc == 0


def test_main_rejects_service_for_singleton_category(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "citizenship",
                "--service",
                "citizenship-matters",
                "--week",
                "2026:26",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "must not be provided" in captured.err


def test_main_requires_service_for_multi_service_category(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "residence-permit",
                "--week",
                "2026:26",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--service is required for category 'residence-permit'" in captured.err


def test_main_rejects_invalid_service_for_category(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "travel-document",
                "--service",
                "work",
                "--week",
                "2026:26",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid --service 'work' for category 'travel-document'" in captured.err


def test_main_rejects_invalid_category(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        notify.main(
            [
                "--alarmer-key",
                "abc-key",
                "--category",
                "unknown-category",
                "--week",
                "2026:26",
            ]
        )

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice: 'unknown-category'" in captured.err
