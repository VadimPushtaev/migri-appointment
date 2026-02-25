# migri-appointment

Simple Python tooling for checking Migri appointment availability and sending
Telegram notifications via AlarmerBot.

## Features

- Typed Migri API client (`migri_appointment`) for Helsinki office slots.
- Notification CLI script (`scripts/notify.py`).
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
poetry run python scripts/notify.py --alarmer-key "<KEY>" --week 2026:23
```

Single week:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --week 2026:23
```

Week range:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --week 2026:1..2026:20
```

Multiple selectors:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --week 2026:1..2026:3 --week 2026:26
```

Send "no slots found" notifications too:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --week 2026:21..2026:22 --send-no-slots
```

## Cron Example

Every 10 minutes, current year weeks 21 and 22, with no-slots messages:

```cron
*/10 * * * * ALARMER_KEY="YOUR_ALARMER_KEY" /home/vadim/.local/bin/poetry -C /home/vadim/migri-appointment run python scripts/notify.py --alarmer-key "$ALARMER_KEY" --week "$(date +\%Y):21" --week "$(date +\%Y):22" --send-no-slots >> /home/vadim/migri-appointment/notify.log 2>&1
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
