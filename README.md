# Carrier Smart Thermostat Monitor

Script to query the Carrier web API and monitor the status of home heating/cooling system.
Uses someone else's API wrapper (carrier_api).

---
- Main functionality is to make sure AirBNB guests do not keep thermostat set point too high or low. 
- If the heating/cooling set point is above or below some preset bounds, the script automatically
changes the set points to presets (default is 73/68 for heating/cooling).
- Runs with scheduler every 15 minutes by default.
