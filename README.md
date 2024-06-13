# Carrier Smart Thermostat Monitor 🌡👁️

Script to query the Carrier web API and monitor the status of the home heating/cooling system. This script utilizes an external API wrapper (`carrier_api`).

---

## Main Functionality

- **Automatic Thermostat Management**:
  - Ensures AirBnB guests do not set the thermostat too high or too low for prolonged periods and degrade the HVAC system.
  - Automatically adjusts the heating/cooling set points if they exceed preset bounds.
    - **Heating Mode**: Lowers the heat set point to 70°F if detected at or above 72°F.
    - **Cooling Mode**: Raises the cool set point to 68°F if detected below 66°F.
  - Runs with a scheduler every 15 minutes by default.

- **Scheduled Temperature Profile**:
  - Ensures the system returns to the scheduled WAKE/HOME/SLEEP temperature profile every two hours.
  - Runs with a scheduler every two hours by default.
  - Does not affect AWAY mode.

- **Email Notifications**:
  - Sends an email every two days to verify that the script is running.

## Usage

1. Install dependencies.

from `Pipfile`:
```shell
pipenv install --deploy
```
If Pipenv is not available, a `requirements.txt` is provided.

2. Set up environment variables. Add the following lines to ~/.bashrc:
```shell
export CARRIER_THERMOSTAT_SERIAL="your_thermostat_serial"
export CARRIER_API_USER="your_api_user"
export CARRIER_API_PASSWORD="your_api_password"
export NOTIFICATION_EMAIL_SENDER="your_email_sender_address"
export NOTIFICATION_EMAIL_PASSWORD="your_email_password"
export NOTIFICATION_EMAIL_DESTINATION="your_email_destination"
```
