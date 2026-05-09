#!/usr/bin/python
__author__ = "Brian Shevitski"
__email__ = "brian.shevitski@gmail.com"
__version__ = "1.1.0"
__status__ = "Production"
__date__ = "2026/05/08"


import asyncio
import os, sys
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage

import carrier_api
from carrier_api import const

from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("main.log", level="INFO", rotation="10 MB")

load_dotenv()

THERMOSTAT_SERIAL = os.getenv("CARRIER_THERMOSTAT_SERIAL")
API_USR = os.getenv("CARRIER_API_USER")
API_PASS = os.getenv("CARRIER_API_PASSWORD")
EMAIL_SENDER_ADDRESS = os.getenv("NOTIFICATION_EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("NOTIFICATION_EMAIL_PASSWORD")
EMAIL_INBOX = os.getenv("NOTIFICATION_EMAIL_DESTINATION")

DB_PATH = "thermostat.db"

def send_email(message_text, subject):
    global EMAIL_SENDER_ADDRESS
    global EMAIL_PASSWORD
    global EMAIL_INBOX

    logger.info("Running email notification monitor")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER_ADDRESS
    msg["To"] = EMAIL_INBOX
    msg.set_content(message_text)

    SERVER_ADDRESS = "smtp.gmail.com"
    TLS_PORT = 587

    server = smtplib.SMTP(SERVER_ADDRESS, TLS_PORT)
    server.starttls()
    server.login(EMAIL_SENDER_ADDRESS, EMAIL_PASSWORD)
    text = msg.as_string()
    server.sendmail(EMAIL_SENDER_ADDRESS, EMAIL_INBOX, text)
    server.quit()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            ts           TEXT NOT NULL,
            room_temp    REAL,
            heat_sp      REAL,
            cool_sp      REAL,
            outdoor_temp REAL,
            mode         TEXT,
            activity     TEXT
        )
    """)
    con.commit()
    con.close()


def log_reading(system):
    zone = system.status.zones[0]
    ts = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO readings VALUES (?,?,?,?,?,?,?)",
        (
            ts,
            zone.temperature,
            zone.heat_set_point,
            zone.cool_set_point,
            system.status.outdoor_temperature,
            system.status.mode,
            zone.current_activity.value,
        ),
    )
    con.commit()
    con.close()

APIConnection = None
api_failure_since = None  # datetime of first consecutive connection failure
api_outage_alerted = False  # whether the 24-hour alert has been sent this outage

async def ensure_API_Connection():
    global APIConnection, api_failure_since, api_outage_alerted
    if APIConnection is None:
        try:
            logger.info("Establishing API connection.")
            APIConnection = carrier_api.ApiConnectionGraphql(API_USR, API_PASS)
            await APIConnection.login()
            # Reset failure tracking on successful connection
            api_failure_since = None
            api_outage_alerted = False
        except Exception as e:
            logger.error(f"Failed to establish API connection {e}.")
            now = datetime.now(timezone.utc)
            if api_failure_since is None:
                api_failure_since = now
            elif not api_outage_alerted:
                hours_down = (now - api_failure_since).total_seconds() / 3600
                if hours_down >= 24:
                    try:
                        send_email(
                            f"Carrier API has been unreachable for {hours_down:.1f} hours. "
                            f"First failure: {api_failure_since.isoformat()}",
                            subject="Carrier Thermostat API Unreachable 24h",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send outage email: {e}")
                    api_outage_alerted = True
    else:
        logger.debug("API connection already exists.")


async def call_get_status():
    global APIConnection
    if APIConnection is not None:
        try:
            logger.info("Getting status.")
            systems = await APIConnection.load_data()
            return systems
        except Exception as e:
            logger.error(f"Failed to get status {e}.")
            APIConnection = None  # force reconnect attempt next cycle
    else:
        logger.error("API connection does not exist.")


async def get_thermostat_data():
    await ensure_API_Connection()
    systems = await call_get_status()
    if not systems:
        raise RuntimeError("API returned no data")
    system = systems[0]
    zone = system.status.zones[0]
    return {
        "system": system,
        "system_mode": system.status.mode,
        "system_activity": zone.current_activity.value,
        "heating_setpoint": zone.heat_set_point,
        "cooling_setpoint": zone.cool_set_point,
        "room_temp": zone.temperature,
        "outdoor_temp": system.status.outdoor_temperature,
    }


async def resume_schedule():
    """
    Periodically returns the thermostat to its pre-programmed schedule.
    """
    logger.info("Running periodic schedule resume.")
    try:
        await ensure_API_Connection()
        systems = await call_get_status()
        if not systems:
            raise RuntimeError("API returned no data")
        system = systems[0]
        if system.status.mode == const.SystemModes.OFF.value:
            logger.info("System is OFF, skipping schedule resume.")
            return
        await APIConnection.resume_schedule(THERMOSTAT_SERIAL, "1")
        logger.success("Schedule resumed.")
    except Exception as e:
        logger.error(e)


async def main():
    """
    Keeps AirBnB guests from leaving the thermostat at extreme values.
    Queries Carrier server for thermostat parameters; resumes schedule if setpoints are out of range.
    """
    try:
        data = await get_thermostat_data()
        system_mode = data["system_mode"]
        system_activity = data["system_activity"]
        heating_setpoint = data["heating_setpoint"]
        cooling_setpoint = data["cooling_setpoint"]
        current_room_temp = data["room_temp"]
        outdoor_temperature_sensor = data["outdoor_temp"]

        log_reading(data["system"])

        logger.info(f"Current System Mode: {system_mode}")
        logger.info(f"Current System Activity Mode: {system_activity}")
        logger.info(f"Current Room Temperature: {current_room_temp}")
        logger.info(f"Current Heat Setpoint: {heating_setpoint}")
        logger.info(f"Current Cool Setpoint: {cooling_setpoint}")
        logger.debug(f"Current Outdoor Temperature: {outdoor_temperature_sensor}")

        if system_mode == const.SystemModes.OFF.value:
            logger.info("System is OFF, skipping setpoint check.")
            return

        if system_activity == const.ActivityTypes.AWAY.value:
            logger.info("System is in AWAY activity, skipping setpoint check.")
            return

        HEATING_THRESHOLD = 71
        COOLING_THRESHOLD = 69

        if system_mode == const.SystemModes.AUTO.value:
            logger.warning("System set to AUTO mode, resuming schedule.")
            await APIConnection.resume_schedule(THERMOSTAT_SERIAL, "1")
            logger.success("Schedule resumed (AUTO mode).")
        elif heating_setpoint > HEATING_THRESHOLD:
            logger.warning(
                f"Heat setpoint above {HEATING_THRESHOLD} at ({heating_setpoint}), resuming schedule."
            )
            await APIConnection.resume_schedule(THERMOSTAT_SERIAL, "1")
            logger.success("Schedule resumed (heat setpoint too high).")
        elif cooling_setpoint < COOLING_THRESHOLD:
            logger.warning(
                f"Cool setpoint below {COOLING_THRESHOLD} at ({cooling_setpoint}), resuming schedule."
            )
            await APIConnection.resume_schedule(THERMOSTAT_SERIAL, "1")
            logger.success("Schedule resumed (cool setpoint too low).")

    except Exception as e:
        logger.error(e)


async def run_main_loop():
    while True:
        await main()
        await asyncio.sleep(600)  # every 10 minutes


async def run_resume_loop():
    while True:
        await resume_schedule()
        await asyncio.sleep(28800)  # every 8 hours


async def run():
    init_db()
    await ensure_API_Connection()
    await asyncio.gather(
        run_main_loop(),
        run_resume_loop(),
    )


if __name__ == "__main__":
    logger.info("Starting thermostat monitor")
    asyncio.run(run())
