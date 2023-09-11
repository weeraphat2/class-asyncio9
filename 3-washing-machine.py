import time
import random
import json
import asyncio
import aiomqtt
from enum import Enum
import sys
import os

student_id = "6310301022"


class MachineStatus():
    def __init__(self) -> None:
        self.pressure = round(random.uniform(2000,3000), 2)
        self.temperature = round(random.uniform(25.0,40.0), 2)
        self.water_level = round(random.uniform(0, 100), 2)  
        self.detergent_level = round(random.uniform(0, 100), 2)
    #
    # add more machine status
    #


class MachineMaintStatus():
    def __init__(self) -> None:
        self.filter = random.choice(["clear", "clogged"])
        self.noise = random.choice(["quiet", "noisy"])
    #
    # add more maintenance status
    #


class WashingMachine:
    def __init__(self, serial):
        self.MACHINE_STATUS = 'OFF'
        self.SERIAL = serial

    async def waiting(self):
        try:
            print(f'{time.ctime()} - Start waiting')
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            print(f'{time.ctime()} - Waiting function is canceled!')
            raise

        print(f'{time.ctime()} - Waiting 10 second already! -> TIMEOUT!')
        self.MACHINE_STATUS = 'FAULT'
        self.FAULT_TYPE = 'TIMEOUT'
        print(
            f'{time.ctime()} - [{self.SERIAL}] STATUS: {self.MACHINE_STATUS}')

    async def waiting_task(self):
        self.task = asyncio.create_task(self.waiting())
        return self.task

    async def cancel_waiting(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            print(f'{time.ctime()} - Get message before timeout!')


async def publish_message(w, client, app, action, name, value):
    print(f"{time.ctime()} - [{w.SERIAL}] {name}:{value}")
    await asyncio.sleep(2)
    payload = {
        "action": "get",
        "project": student_id,
        "model": "model-01",
        "serial": w.SERIAL,
        "name": name,
        "value": value
    }
    print(
        f"{time.ctime()} - PUBLISH - [{w.SERIAL}] - {payload['name']} > {payload['value']}")
    await client.publish(f"v1cdti/{app}/{action}/{student_id}/model-01/{w.SERIAL}", payload=json.dumps(payload))


async def CoroWashingMachine(w, w_sensor, client):
    # washing coroutine
    while True:
        wait_next = round(10*random.random(), 2)
        print(
            f"{time.ctime()} - [{w.SERIAL}] Waiting new message... {wait_next} seconds.")
        await asyncio.sleep(wait_next)
        if w.MACHINE_STATUS == 'OFF':
            continue

        if w.MACHINE_STATUS == 'READY':
            print(f"{time.ctime()} - [{w.SERIAL}-{w.MACHINE_STATUS}]")
            await publish_message(w, client, 'hw', 'get', 'STATUS', 'READY')
            await publish_message(w, client, 'hw', 'get', 'DOOR', 'CLOSE')

            w.MACHINE_STATUS = 'FILLING'
            await publish_message(w, client, 'hw', 'get', 'STATUS', 'FILLING')
            task = w.waiting_task()
            await task


        if w.MACHINE_STATUS == 'FAULT':
            await publish_message(w, client, 'hw', 'get', 'FAULT', w.FAULT_TYPE)
            while w.MACHINE_STATUS == 'FAULT':
                print(
                    f"{time.ctime()} - [{w.SERIAL}] Waiting to clear fault...")
                await asyncio.sleep(1)

        if w.MACHINE_STATUS == 'HEATING':
            task = w.waiting_task()
            await task
            while w.MACHINE_STATUS == 'HEATING':
                await asyncio.sleep(2)

        if w.MACHINE_STATUS == 'WASHING':
            continue


async def listen(w, w_sensor, client):
    async with client.messages() as messages:
        await client.subscribe(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}")
        async for message in messages:
            mgs_decode = json.loads(message.payload)
            if message.topic.matches(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}"):
                print(
                    f"FROM MQTT: [{mgs_decode['serial']} {mgs_decode['name']} {mgs_decode['value']}]")

                if mgs_decode['name'] == "STATUS":
                    w.MACHINE_STATUS = mgs_decode['value']

                if w.MACHINE_STATUS == 'FILLING':
                    if mgs_decode['name'] == "WATERLEVEL":
                        w_sensor.fulldetect = mgs_decode['value']
                        if w_sensor.fulldetect == 'FULL':
                            w.MACHINE_STATUS = 'HEATING'
                            print(
                                f'{time.ctime()} - [{w.SERIAL}] STATUS: {w.MACHINE_STATUS}')
                            await publish_message(w, client, 'hw', 'get', 'STATUS', w.MACHINE_STATUS)

                        await w.cancel_waiting()

                if w.MACHINE_STATUS == 'HEATING':
                    if mgs_decode['name'] == "TEMPERATURE":
                        w_sensor.heatreach = mgs_decode['value']
                        if w_sensor.heatreach == 'REACH':
                            w.MACHINE_STATUS = 'WASH'
                            print(
                                f'{time.ctime()} - [{w.SERIAL}] STATUS: {w.MACHINE_STATUS}')
                            await publish_message(w, client, 'hw', 'get', 'STATUS', w.MACHINE_STATUS)

                        await w.cancel_waiting()

                if mgs_decode['name'] == "FAULT":
                    if mgs_decode['value'] == 'CLEAR':
                        w.MACHINE_STATUS = 'OFF'
                        await publish_message(w, client, 'hw', 'get', 'STATUS', w.MACHINE_STATUS)


async def main():
    w = WashingMachine(serial='SN-001')
    w_sensor = MachineStatus()
    # async with aiomqtt.Client("test.mosquitto.org") as client:
    async with aiomqtt.Client("broker.hivemq.com") as client:
        await asyncio.gather(listen(w, w_sensor, client), CoroWashingMachine(w, w_sensor, client))


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())
# Run your async application as usual


asyncio.run(main())