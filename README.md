# Carrier Thermostat Controller

Monitors and controls a Carrier smart thermostat via the Carrier web API. Enforces
temperature bounds to prevent guests from pushing set points to extremes, restores the
programmed schedule periodically, and sends email alerts on API outages. Logs all
readings to a local SQLite database.

## Setup

### Install dependencies

```bash
poetry install --without dev
```

### Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:

```
CARRIER_THERMOSTAT_SERIAL=
CARRIER_API_USER=
CARRIER_API_PASSWORD=
NOTIFICATION_EMAIL_SENDER=
NOTIFICATION_EMAIL_PASSWORD=
NOTIFICATION_EMAIL_DESTINATION=
```

### Run

```bash
poetry run python main.py
```

## What It Does

- **Setpoint enforcement** — polls every 10 minutes; if the heat set point exceeds 71°F or
  the cool set point drops below 69°F (and the system is not OFF or AWAY), resumes the
  programmed schedule. Also resumes immediately if AUTO mode is detected.
- **Scheduled restore** — unconditionally resumes the thermostat's programmed schedule
  every 8 hours.
- **API outage alerting** — if the Carrier API is unreachable for 24+ consecutive hours,
  sends a one-time email notification.
- **Database logging** — inserts each poll result (room temp, set points, outdoor temp,
  mode, activity) into `thermostat.db`.

## Running persistently (tmux)

The script runs two async loops indefinitely. Use tmux to keep it alive across SSH sessions:

```bash
tmux new -s thermostat
poetry run python main.py
# detach: Ctrl-B D
```

Reattach later:

```bash
tmux attach -t thermostat
```

Logs are written to `main.log` (rotated at 10 MB) and stdout.
