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
- A global 2 second delay between city/week fetches to reduce request bursts.

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
serialized and share the same two-second delay:

```bash
python scripts/notify.py --alarmer-key "<KEY>" --city helsinki --city tampere --city lahti --category citizenship --date 2027-05-16..2027-07-01
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
