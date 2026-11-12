# migri-appointment

Simple Python tooling for checking Migri appointment availability and sending
Telegram notifications via AlarmerBot.

## Features

- Typed Migri API client (`migri_appointment`) for Migri office slots across Finland.
- Notification CLI script (`scripts/notify.py`).
- Repeatable city selection via `--city`, defaulting to Helsinki.
- Hardcoded Migri category/service selection via `--category` and `--service`.
- Week selectors support both single week and ranges:
  - `2026:23`
  - `2026:1..2026:20`
- Date selectors support both single dates and ranges:
  - `2026-06-22`
  - `2026-06-22..2026-06-24`
- Exactly one of `--week` or `--date` must be provided.
- Optional no-slots notifications (`--send-no-slots`).
- Slot messages include every slot timestamp and a clickable Migri link.
- Large slot messages are capped to the earliest 20 slot timestamps by default
  to fit AlarmerBot URL limits.
- Timestamped logs with Alarmer request URL + response for debugging.
- Client-owned Migri API limits: one HTTP query every 2 seconds, at most 10
  queries in any 60-second window, and at most one query in flight.
- One Migri API session is shared by all city/week fetches in a process.
- A Migri `403` stops the run immediately so blocked clients do not keep querying.

## Requirements

- Python 3.11+
- Poetry

## Installation

```bash
poetry install
```

## Usage

Run with Poetry:

```bash
poetry run python scripts/notify.py --alarmer-key "<KEY>" --category citizenship --week 2026:23
```

Single-service category (`--service` is auto-selected and must not be passed):

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category citizenship --week 2026:23
```

Date-based selection:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category citizenship --date 2026-06-22
```

Date range:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service work --date 2026-06-22..2026-06-24
```

Choose a city (case-insensitive):

```bash
python scripts/notify.py --alarmer-key "<KEY>" --city oulu --category citizenship --date 2026-06-22
```

Repeat `--city` to check multiple cities in one process. All city/week fetches are
serialized and share the `MigriClient` HTTP query limiter:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --city helsinki --city tampere --city lahti --category citizenship --date 2027-05-16..2027-07-01
```

`MigriClient` creates one Migri API session lazily and shares it across all
city/week fetches made by that client. After that initial session query, each
city/week fetch makes one scheduling query. Both query methods use a
process-wide limiter shared by default across client instances. The limiter enforces:

- at least 2 seconds between query start times
- no more than 10 query starts in a rolling 60-second window
- no more than one in-flight query at a time

Multi-service category:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service permanent-residence-permit --week 2026:23
```

Week range:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service work --week 2026:1..2026:20
```

Multiple selectors:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service work --week 2026:1..2026:3 --week 2026:26
```

Send "no slots found" notifications too:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service permanent-residence-permit --week 2026:21..2026:22 --send-no-slots
```

Increase the number of slot timestamps included in a notification:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --category residence-permit --service permanent-residence-permit --date 2026-06-22..2026-12-19 --max-notification-slots 40
```

You may use either `--week` or `--date`, but not both in the same command.

## Cities

If `--city` is omitted, the script checks Helsinki. Supported canonical cities are:

- `helsinki`
- `turku` (office in Raisio; `raisio` is also accepted)
- `tampere`
- `oulu`
- `lahti`
- `kuopio`
- `lappeenranta`
- `vaasa`
- `rovaniemi`
- `aland` (office in Mariehamn; `åland`, `ahvenanmaa`,
  `ahvenanmaa-aland`, and `mariehamn` are also accepted)

## Categories and Services

Categories:

- `citizenship`
- `eu-registration-brexit`
- `residence-permit`
- `temporary-protection`
- `travel-document`

Services:

- `citizenship`
  - auto-selected: `citizenship-matters`
- `eu-registration-brexit`
  - `eu-citizen-registration`
  - `family-member-card`
  - `brexit-appointments`
- `residence-permit`
  - `work`
  - `family`
  - `study`
  - `other-grounds`
  - `permanent-residence-permit`
  - `renew-permanent-residence-permit-card`
  - `renew-residence-permit-card`
- `temporary-protection`
  - auto-selected: `temporary-protection-residence-permit-card`
- `travel-document`
  - `aliens-passport`
  - `refugee-travel-document`

## Cron Example

Every 10 minutes, check today and tomorrow in Oulu, with no-slots messages:

```cron
*/10 * * * * ALARMER_KEY="YOUR_ALARMER_KEY" /home/vadim/.local/bin/poetry -C /home/vadim/migri-appointment run python scripts/notify.py --alarmer-key "$ALARMER_KEY" --city oulu --category residence-permit --service permanent-residence-permit --date "$(date +\%F)" --date "$(date -d '+1 day' +\%F)" --send-no-slots >> /home/vadim/migri-appointment/notify.log 2>&1
```

Note: `%` must be escaped as `\%` in crontab.

Multiple cities can be checked with one cron process:

```cron
*/10 * * * * ALARMER_KEY="YOUR_ALARMER_KEY" /home/vadim/.local/bin/poetry -C /home/vadim/migri-appointment run python scripts/notify.py --alarmer-key "$ALARMER_KEY" --city helsinki --city tampere --city lahti --category citizenship --date "2027-05-16..2027-07-01" >> /home/vadim/migri-appointment/notify.log 2>&1
```

## Output and Logging

The script logs:

- fetch result per week with timestamps
- date-mode notifications are filtered by Helsinki local calendar date
- exact Alarmer request URL
- Alarmer response status + body

This is helpful when debugging delivery issues.

## Troubleshooting

- If Migri returns a `403`/WAF-style response, the run stops immediately. Retry
  later and keep request pace conservative.
- Migri queries are automatically paced by `MigriClient`.
- Verify Alarmer key and inspect logged response body for delivery errors.

## Tests

```bash
poetry run pytest -q
```

## Browser-based latest-date monitor

`python scripts/notify_latest.py` launches Codex to use the repository skill
`.agents/skills/check-migri-latest`. It checks the latest available appointment
through the visible website and alerts on every run whose Helsinki calendar date
is strictly after `--after`. Failures produce a separate alert and nonzero exit.

```bash
export ALARMER_KEY="YOUR_KEY"
poetry run python scripts/notify_latest.py --browser-skill ~/.codex/skills/shared-browser/SKILL.md --people 2 --category citizenship --city helsinki --after 2027-05-01
```

The external shared-browser skill is required and is not bundled or modified.
Install/authenticate Codex beforehand and provide a desktop session with Chrome
and an existing Playwright installation. Use `--playwright-module` if needed.
Codex uses automatic approval review; rejected browser access is a failed check.
Use `--no-notify` for a live check without Telegram delivery.

Run `--help` for model/profile, browser profile, runtime directory, timeout,
family-members, service, and click-delay options. Defaults are a 600-second
limit and random 3–6-second click delays. A dedicated persistent browser is left
open and reused; the skill verifies filters and refreshes availability each run.
Runtime/controller files and per-run Codex logs are stored under
`~/.cache/migri-appointment/browser-monitor`; remove old run directories manually
as needed. A profile lock prevents overlapping checks. No appointment is booked.

Example hourly cron command (supply ALARMER_KEY and desktop environment through
your local configuration; no cron job is installed automatically):

```cron
0 * * * * /home/vadim/.local/bin/poetry -C /home/vadim/migri-appointment run python scripts/notify_latest.py --browser-skill /home/vadim/.codex/skills/shared-browser/SKILL.md --after 2027-05-01 >> /home/vadim/migri-appointment/notify.log 2>&1
```

Exit codes: 0 successful check or overlapping run skipped; 1 check failed;
2 notification failed. The earlier API-based `scripts/notify.py` is unchanged.
