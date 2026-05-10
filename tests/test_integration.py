import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio
import main

"""
These tests are only used to test if the code can actually communicate with the thermostat.
"""

def test_send_email():
    main.send_email("pytest integration test — email is working.", subject="Carrier Thermostat Email Test")


def test_resume_schedule():
    asyncio.run(main.resume_schedule())


def test_main():
    asyncio.run(main.main())
