import time
import random
import json
import asyncio
import aiomqtt
from enum import Enum
import sys
import os

student_id = "6310301022"

class MachineStatus(Enum):
    pressure = round(random.uniform(2000, 3000), 2)
    temperature = round(random.uniform(25.0, 40.0), 2)

class MachineMaintStatus(Enum):
    filter = random.choice(["clear", "clogged"])
    noise = random.choice(["quiet", "noisy"])

class WashingMachine:
    def __init__(self, serial):
        self.SERIAL = serial
        self.Task = None
        self.MACHINE_STATUS = 'OFF'
        self.FAULT = None
        self.OPERATION = None
        self.OPERATION_value = None

    async def Running(self):
        print(f"{time.ctime()} - [{self.SERIAL}-{self.MACHINE_STATUS}] START")
        await asyncio.sleep(3600)

    def nextState(self):
        if self.MACHINE_STATUS == 'WASH':
            self.MACHINE_STATUS = 'RINSE'
        elif self.MACHINE_STATUS == 'RINSE':
            self.MACHINE_STATUS = 'SPIN'
        elif self.MACHINE_STATUS == 'SPIN':
            self.MACHINE_STATUS = 'OFF'

    async def Running_Task(self, client: aiomqtt.Client, invert: bool):
        self.Task = asyncio.create_task(self.Running())
        wait_coro = asyncio.wait_for(self.Task, timeout=10)
        try:
            await wait_coro
        except asyncio.TimeoutError:
            print(f"{time.ctime()} - [{self.SERIAL}-{self.MACHINE_STATUS}] Timeout")
            if not invert:
                self.MACHINE_STATUS = 'FAULT'
                self.FAULT = 'TIMEOUT'
                await publish_message(self, client, "hw", "get", "STATUS", self.MACHINE_STATUS)
                await publish_message(self, client, "hw", "get", "FAULT", self.FAULT)
            else:
                self.nextState()
        except asyncio.CancelledError:
            print(f"{time.ctime()} - [{self.SERIAL}] Cancelled")

    async def Cancel_Task(self):
        self.Task.cancel()

async def publish_message(w, client, app, action, name, value):
    print(f"{time.ctime()} - [{w.SERIAL}] {name}:{value}")
    payload = {
        "action": "get",
        "project": student_id,
        "model": "model-01",
        "serial": w.SERIAL,
        "name": name,
        "value": value
    }
    print(f"{time.ctime()} - PUBLISH - [{w.SERIAL}] - {payload['name']} > {payload['value']}")
    await client.publish(f"v1cdti/{app}/{action}/{student_id}/model-01/{w.SERIAL}", payload=json.dumps(payload))

async def CoroWashingMachine(w: WashingMachine, client: aiomqtt.Client, event: asyncio.Event):
    while True:
        if w.MACHINE_STATUS == 'OFF':
            print(f"{time.ctime()} - [{w.SERIAL}-{w.MACHINE_STATUS}] Waiting to start...")
            await event.wait()
            event.clear()
        if w.MACHINE_STATUS == 'READY':
            await publish_message(w, client, "hw", "get", "STATUS", "READY")
            await publish_message(w, client, 'hw', 'get', 'LID', 'CLOSE')
            w.MACHINE_STATUS = 'FILLWATER'
            await publish_message(w, client, "hw", "get", "STATUS", "FILLWATER")
            await w.Running_Task(client, invert=False)
        if w.MACHINE_STATUS == 'HEATWATER':
            await publish_message(w, client, "hw", "get", "STATUS", "HEATWATER")
            await w.Running_Task(client, invert=False)
        if w.MACHINE_STATUS in ['WASH', 'RINSE', 'SPIN']:
            await publish_message(w, client, "hw", "get", "STATUS", w.MACHINE_STATUS)
            await w.Running_Task(client, invert=True)
        if w.MACHINE_STATUS == 'FAULT':
            print(f"{time.ctime()} - [{w.SERIAL}-{w.MACHINE_STATUS}-{w.FAULT}] Waiting to clear fault...")
            await event.wait()
            event.clear()

async def listen(w: WashingMachine, client: aiomqtt.Client, event: asyncio.Event):
    async with client.messages() as messages:
        await client.subscribe(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}")
        await client.subscribe(f"v1cdti/app/get/{student_id}/model-01/")
        async for message in messages:
            m_decode = json.loads(message.payload)
            if message.topic.matches(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}"):
                # set washing machine status
                print(f"{time.ctime()} - MQTT - [{m_decode['serial']}]:{m_decode['name']} => {m_decode['value']}")
                match m_decode['name']:
                    case "STATUS":
                        w.MACHINE_STATUS = m_decode['value']
                        if m_decode['value'] == 'READY':
                            if not event.is_set():
                                event.set()
                    case "FAULT":
                        if m_decode['value'] == "FAULTCLEARED":
                            w.MACHINE_STATUS = 'OFF'
                            if not event.is_set():
                                event.set()
                        elif m_decode['value'] == "OUTOFBALANCE" and w.MACHINE_STATUS == 'WASH':
                            w.MACHINE_STATUS = "FAULT"
                            w.FAULT = 'OUTOFBALANCE'
                        elif m_decode['value'] == "MOTORFAILURE" and w.MACHINE_STATUS in ['RINSE', 'SPIN']:
                            w.MACHINE_STATUS = "FAULT"
                            w.FAULT = 'MOTORFAILURE'
                    case "WATERFULLLEVEL":
                        if w.MACHINE_STATUS == 'FILLWATER' and m_decode['value'] == "FULL":
                            await w.Cancel_Task()
                            w.MACHINE_STATUS = "HEATWATER"
                    case "TEMPERATUREREACHED":
                        if w.MACHINE_STATUS == 'HEATWATER' and m_decode['value'] == "REACHED":
                            await w.Cancel_Task()
                            w.MACHINE_STATUS = "WASH"
            elif message.topic.matches(f"v1cdti/app/get/{student_id}/model-01/"):
                await publish_message(w, client, "app", "monitor", "STATUS", w.MACHINE_STATUS)

async def main():
    n = 10
    W = [WashingMachine(serial=f'SN-00{i+1}') for i in range(n)]
    Events = [asyncio.Event() for i in range(n)]
    async with aiomqtt.Client("broker.hivemq.com") as client:
        listenTask = []
        CoroWashingMachineTask = []
        for w, event in zip(W, Events):
            listenTask.append(listen(w, client, event))
            CoroWashingMachineTask.append(CoroWashingMachine(w, client, event))
        await asyncio.gather(*listenTask, *CoroWashingMachineTask)

# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())
# Run your async application as usual
asyncio.run(main())