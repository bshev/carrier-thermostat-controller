#!/usr/bin/python
__author__ = "Brian Shevitski"
__email__ = "brian.shevitski@gmail.com"
__version__ = "0.0.0"
__status__ = "Development"
__date__ = "2024/02/26"


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
logger.add("main.log", level="INFO", rotation="100 MB")

# Dont forget to set api user/pass and thermostat serial in environment variables
THERMOSTAT_SERIAL = os.getenv("CARRIER_THERMOSTAT_SERIAL")
API_USR = os.getenv("CARRIER_API_USER")
API_PASS = os.getenv("CARRIER_API_PASSWORD")
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

#Dont forget to set your env variables.
EMAIL_SENDER_ADDRESS = os.getenv("NOTIFICATION_EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("NOTIFICATION_EMAIL_PASSWORD")
EMAIL_INBOX = os.getenv("NOTIFICATION_EMAIL_DESTINATION")


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


def main():
    try:
        ensure_API_Connection()
        status = call_get_status()

        df_meta, df_zone1 = parse_status(status)

        system_mode = df_meta["mode"].item()
        cooling_setpoint = df_zone1["clsp"].item()
        heating_setpoint = df_zone1["htsp"].item()
        current_room_temp = df_zone1["rt"].item()
        outdoor_temperature_sensor = df_meta["oat"].item()

        logger.info(f"Current System Mode: {system_mode}")
        logger.info(f"Current Room Temperature: {current_room_temp}")
        logger.info(f"Current Heat Setpoint: {heating_setpoint}")
        logger.info(f"Current Cool Setpoint: {cooling_setpoint}")

        logger.debug(f"Current Outdoor Temperature: {outdoor_temperature_sensor}")

        HEATING_THRESHOLD = 75
        COOLING_THRESHOLD = 64
        HEATING_HEAT_SETPOINT = 73
        HEATING_COLD_SETPOINT = 78
        COOLING_HEAT_SETPOINT = 60
        COOLING_COLD_SETPOINT = 68

        if heating_setpoint > HEATING_THRESHOLD:
            logger.warning(f"Heat setpoint above 75 at ({heating_setpoint})")
            APIConnection.set_config_manual_activity(
                THERMOSTAT_SERIAL,
                "1",
                HEATING_HEAT_SETPOINT,
                HEATING_COLD_SETPOINT,
                const.FanModes.OFF,
            )
            logger.info("Changing heat setpoint to 73")

        if cooling_setpoint < COOLING_THRESHOLD:
            logger.warning(f"Cool setpoint below 64 at ({cooling_setpoint})")
            APIConnection.set_config_manual_activity(
                THERMOSTAT_SERIAL,
                "1",
                COOLING_HEAT_SETPOINT,
                COOLING_COLD_SETPOINT,
                const.FanModes.OFF,
            )
            logger.info("Changing cool setpoint to 68")
    except Exception as e:
        logger.error(e)
        send_email(
            "Carrier Thermostat monitor program has halted.",
            subject="Carrier Thermostat Script Monitor Halted",
        )
        raise


if __name__ == "__main__":
    logger.info("Starting thermostat monitor")

    schedule.every(15).minutes.do(threaded_job, main)
    schedule.every().day.do(threaded_job, job_monitor)

    while True:
        schedule.run_pending()
        time.sleep(1)
