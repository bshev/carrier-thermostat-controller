#!/usr/bin/python
__author__ = "Brian Shevitski"
__email__ = "brian.shevitski@gmail.com"
__version__ = "1.0.0"
__status__ = "Production"
__date__ = "2024/06/13"


import os, sys
import threading
import schedule
import time

import carrier_api
from carrier_api import const

import pandas as pd
import smtplib
from email.message import EmailMessage

from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("main.log", level="INFO", rotation="50 MB")

# Don't forget to set your env variables, currently export all in ~/.bashrc
THERMOSTAT_SERIAL = os.getenv("CARRIER_THERMOSTAT_SERIAL")
API_USR = os.getenv("CARRIER_API_USER")
API_PASS = os.getenv("CARRIER_API_PASSWORD")
EMAIL_SENDER_ADDRESS = os.getenv("NOTIFICATION_EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("NOTIFICATION_EMAIL_PASSWORD")
EMAIL_INBOX = os.getenv("NOTIFICATION_EMAIL_DESTINATION")

APIConnection = None


def ensure_API_Connection():
    global APIConnection
    if APIConnection is None:
        try:
            logger.info("Establishing API connection.")
            APIConnection = carrier_api.ApiConnection(API_USR, API_PASS)
        except Exception as e:
            logger.error(f"Failed to establish API connection {e}.")
    else:
        logger.debug("API connection already exists.")


def call_get_status():
    if APIConnection is not None:
        try:
            logger.info("Getting status.")
            response = APIConnection.get_status(THERMOSTAT_SERIAL)
            return response
        except Exception as e:
            logger.error(f"Failed to get status {e}.")
    else:
        logger.error("API connection does not exist.")


def parse_status(response):
    logger.debug("parsing status...")
    df_meta = pd.json_normalize(response).drop(
        columns=["atom:link", "$.xmlns:atom", "zones.zone"]
    )

    zone1_json = next(
        (zone for zone in response["zones"]["zone"] if zone["$"]["id"] == "1"), None
    )
    df_zone1 = pd.json_normalize(zone1_json)

    return df_meta, df_zone1


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
    TLS_PORT = 587  # 465 if using ssl

    # create the connection
    server = smtplib.SMTP(SERVER_ADDRESS, TLS_PORT)
    server.starttls()  # if using ssl this step is not needed

    # send email
    server.login(
        EMAIL_SENDER_ADDRESS, EMAIL_PASSWORD
    )  # login with mail_id and password
    text = msg.as_string()
    server.sendmail(EMAIL_SENDER_ADDRESS, EMAIL_INBOX, text)
    server.quit()


def job_monitor():
    message = "Script running"
    send_email(message, subject="Carrier Thermostat Script Monitor")


def threaded_job(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


def resume_schedule():
    """
    Function to ensure that the thermostat periodically returns to Wake/Home/Sleep pre-programmed
    cycle, even if thermostat users change temperature or turn off functionality.
    """
    logger.info("Checking schedule status.")
    try:
        ensure_API_Connection()
        status = call_get_status()

        df_meta, df_zone1 = parse_status(status)

        system_mode = df_meta["mode"].item()
        system_activity = df_zone1["currentActivity"].item()
        cooling_setpoint = df_zone1["clsp"].item()
        heating_setpoint = df_zone1["htsp"].item()

        # In HEAT mode (Winter) if the temp is set below 65 hold there.
        # (conditions not sub-zero, no danger of freezing pipes, etc.)
        # If the temp is set above 65, make sure to resume schedule.

        # In COOL mode (Summer) if the temp is set above 78, hold there.
        # (no real use case, at the moment).
        # If the temp is set below 78, resume schedule.

        PASSIVE_HEAT_SETPOINT = 65
        PASSIVE_COOL_SETPOINT = 78

        # If in AWAY mode, do nothing.

        if system_mode == const.SystemModes.OFF.value:
            logger.info("System Off.")
        elif (
            system_mode == const.SystemModes.HEAT.value
            and heating_setpoint > PASSIVE_HEAT_SETPOINT
        ):
            if system_activity == const.ActivityNames.AWAY.value:
                logger.info("System in Away mode")
            else:
                APIConnection.resume_schedule(THERMOSTAT_SERIAL, 1)
                logger.success("Resuming schedule.")
        elif (
            system_mode == const.SystemModes.COOL.value
            and cooling_setpoint < PASSIVE_COOL_SETPOINT
        ):
            if system_activity == const.ActivityNames.AWAY.value:
                logger.info("System in Away mode")
            else:
                APIConnection.resume_schedule(THERMOSTAT_SERIAL, 1)
                logger.success("Resuming schedule.")

    except Exception as e:
        logger.error(e)
        send_email(
            "Carrier Thermostat monitor program has halted.",
            subject="Carrier Thermostat Script Monitor Halted",
        )
        raise


def main():
    """
    Function to keep AirBnB guests from leaving thermostat at extreme values and breaking HVAC system.
    Queries Carrier server for thermostat parameters, if heater is too hot, lowers temp.
    If AC is too cold, raises temp.

    """
    try:
        ensure_API_Connection()
        status = call_get_status()

        df_meta, df_zone1 = parse_status(status)
        system_mode = df_meta["mode"].item()
        system_activity = df_zone1["currentActivity"].item()
        cooling_setpoint = df_zone1["clsp"].item()
        heating_setpoint = df_zone1["htsp"].item()
        current_room_temp = df_zone1["rt"].item()
        outdoor_temperature_sensor = df_meta["oat"].item()

        logger.info(f"Current System Mode: {system_mode}")
        logger.info(f"Current System Activity Mode: {system_activity}")
        logger.info(f"Current Room Temperature: {current_room_temp}")
        logger.info(f"Current Heat Setpoint: {heating_setpoint}")
        logger.info(f"Current Cool Setpoint: {cooling_setpoint}")

        # logger.info(f"")

        logger.debug(f"Current Outdoor Temperature: {outdoor_temperature_sensor}")

        # COOLING MODE TEMP SETPOINT MUST BE OVER 66, reverts to 68 if turned too low.
        # HEATING MODE TEMP SETPOINT MUST BE UNDER 72, reverts to 70 if too high.

        HEATING_THRESHOLD = 72
        COOLING_THRESHOLD = 66
        HEATING_HEAT_SETPOINT = 70
        HEATING_COLD_SETPOINT = 78  # must provide a cold setpoint in heating mode.
        COOLING_HEAT_SETPOINT = 60  # must provide a heat setpoint in cooling mode.
        COOLING_COLD_SETPOINT = 68

        if heating_setpoint > HEATING_THRESHOLD:
            logger.warning(
                f"Heat setpoint above {HEATING_THRESHOLD} at ({heating_setpoint})"
            )
            APIConnection.set_config_hold(
                THERMOSTAT_SERIAL, 1, const.ActivityNames.HOME
            )
            time.sleep(1)
            APIConnection.resume_schedule(THERMOSTAT_SERIAL, 1)
            time.sleep(1)
            APIConnection.set_config_manual_activity(
                THERMOSTAT_SERIAL,
                "1",
                HEATING_HEAT_SETPOINT,
                HEATING_COLD_SETPOINT,
                const.FanModes.OFF,
            )
            logger.success(f"Changing heat setpoint to {HEATING_HEAT_SETPOINT}")

        if cooling_setpoint < COOLING_THRESHOLD:
            logger.warning(
                f"Cool setpoint below {COOLING_THRESHOLD} at ({cooling_setpoint})"
            )
            APIConnection.set_config_hold(
                THERMOSTAT_SERIAL, 1, const.ActivityNames.HOME
            )
            time.sleep(1)
            APIConnection.resume_schedule(THERMOSTAT_SERIAL, 1)
            time.sleep(1)
            APIConnection.set_config_manual_activity(
                THERMOSTAT_SERIAL,
                "1",
                COOLING_HEAT_SETPOINT,
                COOLING_COLD_SETPOINT,
                const.FanModes.OFF,
            )
            logger.success(f"Changing cool setpoint to {COOLING_COLD_SETPOINT}")

    except Exception as e:
        logger.error(e)
        send_email(
            "Carrier Thermostat monitor program has halted.",
            subject="Carrier Thermostat Script Monitor Halted",
        )
        raise


if __name__ == "__main__":
    logger.info("Starting thermostat monitor")

    # run main function at start to verify everything is working
    main()

    schedule.every(15).minutes.do(threaded_job, main)  # monitor set point
    schedule.every(2).days.do(
        threaded_job, job_monitor
    )  # email to verify process is running
    schedule.every(1).hours.do(
        threaded_job, resume_schedule
    )  # wake/home/sleep mode scheduler

    while True:
        schedule.run_pending()
        time.sleep(1)
