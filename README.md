# migri-appointment

Simple Python tooling for checking Migri appointment availability and sending
Telegram notifications via AlarmerBot.

## Features

- Typed Migri API client (`migri_appointment`) for Helsinki office slots.
- Notification CLI script (`scripts/notify.py`).
- Hardcoded Migri category/service selection via `--category` and `--service`.
- Week selectors support both single week and ranges:
  - `2026:23`
  - `2026:1..2026:20`
- Optional no-slots notifications (`--send-no-slots`).
- Slot messages include every slot timestamp and a clickable Migri link.
- Timestamped logs with Alarmer request URL + response for debugging.
- 2 second delay between week fetches to reduce request burst.

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

Every 10 minutes, current year weeks 21 and 22, with no-slots messages:

```cron
*/10 * * * * ALARMER_KEY="YOUR_ALARMER_KEY" /home/vadim/.local/bin/poetry -C /home/vadim/migri-appointment run python scripts/notify.py --alarmer-key "$ALARMER_KEY" --category residence-permit --service permanent-residence-permit --week "$(date +\%Y):21" --week "$(date +\%Y):22" --send-no-slots >> /home/vadim/migri-appointment/notify.log 2>&1
```

Note: `%` must be escaped as `\%` in crontab.

## Output and Logging

The script logs:

- fetch result per week with timestamps
- sleep intervals between requests
- exact Alarmer request URL
- Alarmer response status + body

This is helpful when debugging delivery issues.

## Troubleshooting

- If Migri returns `403`/WAF-style responses, retry later and keep request pace
  conservative.
- Keep fetch intervals moderate (the script already sleeps 2s between weeks).
- Verify Alarmer key and inspect logged response body for delivery errors.

## Tests

```bash
poetry run pytest -q
```
