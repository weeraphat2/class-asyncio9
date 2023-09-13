import time
import random
import json
import asyncio
import aiomqtt
from enum import Enum

student_id = "6300001"

# State 
S_OFF       = 'OFF'
S_READY     = 'READY'
S_FAULT     = 'FAULT'
S_FILLWATER = 'FILLWATER'
S_HEATWATER = 'HEATWATER'
S_WASH      = 'WASH'
S_RINSE     = 'RINSE'
S_SPIN      = 'SPIN'

# Function
S_DOORCLOSED            = 'DOORCLOSE'
S_FULLLEVELDETECTED     = 'FULLLEVELDETECTED'
S_TEMPERATUREREACHED    = 'TEMPERATUREREACHED'
S_FUNCTIONCOMPLETED     = 'FUNCTIONCOMPLETED'
S_TIMEOUT               = 'TIMEOUT'
S_MOTORFAILURE          = 'MOTORFAILURE'
S_FAULTCLEARED          = 'FAULTCLEARED'

async def publish_message(w, client, app, action, name, value):
    await asyncio.sleep(1)
    payload = {
                "action"    : "get",
                "project"   : student_id,
                "model"     : "model-01",
                "serial"    : w.SERIAL,
                "name"      : name,
                "value"     : value
            }
    print(f"{time.ctime()} - PUB topic: v1cdti/{app}/{action}/{student_id}/model-01/{w.SERIAL} payload: {name}:{value}")
    await client.publish(f"v1cdti/{app}/{action}/{student_id}/model-01/{w.SERIAL}"
                        , payload=json.dumps(payload))

async def fillwater(w, filltime=100):
    print(f"{time.ctime()} - [{w.SERIAL}] Waiting for fill water maxinum {filltime} seconds")
    await asyncio.sleep(filltime)

class MachineStatus(Enum):
    pressure = round(random.uniform(2000,3000), 2)
    temperature = round(random.uniform(25.0,40.0), 2)

class MachineMaintStatus(Enum):
    filter = random.choice(["clear", "clogged"])
    noise = random.choice(["quiet", "noisy"])

class WashingMachine:
    def __init__(self, serial):
        self.SERIAL = serial
        self.STATE = 'OFF'
        self.Task = None
        self.event = asyncio.Event()

async def CoroWashingMachine(w, client):

    while True:
        wait_next = round(10*random.random(),2)
        
        if w.STATE == S_OFF:
            print(f"{time.ctime()} - [{w.SERIAL}-{w.STATE}]... {wait_next} seconds.")
            await asyncio.sleep(wait_next)
            continue

        if w.STATE == S_FAULT:
            print(f"{time.ctime()} - [{w.SERIAL}-{w.STATE}] Waiting to start... {wait_next} seconds.")
            await asyncio.sleep(wait_next)
            continue

        if w.STATE == S_READY:
            print(f"{time.ctime()} - [{w.SERIAL}-{w.STATE}]")

            await publish_message(w, client, "app", "get", "STATUS", "READY")
            # door close
            
            # fill water untill full level detected within 10 seconds if not full then timeout 
            try:
                async with asyncio.timeout(10):
                    await fillwater(w)
            except TimeoutError:
                print(f"{time.ctime()} - Fill water timeouted")
                if w.STATE == 'FULLLEVELDETECTED':
                    await publish_message(w, client, "app", "get", "STATUS", "WATERHEATER")
                else:
                    await publish_message(w, client, "app", "get", "STATUS", "FAULT")
                    w.STATE = 'FALUT'
                    continue
        

        # wash 10 seconds, if out of balance detected then fault

        # rinse 10 seconds, if motor failure detect then fault

        # spin 10 seconds, if motor failure detect then fault

        # When washing is in FAULT state, wait until get FAULTCLEARED

        wait_next = round(5*random.random(),2)
        print(f"sleep {wait_next} seconds")
        await asyncio.sleep(wait_next)
            

async def listen(w, client):
    async with client.messages() as messages:
        print(f"{time.ctime()} - SUB topic: v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}")
        await client.subscribe(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}")
        async for message in messages:
            m_decode = json.loads(message.payload)
            if message.topic.matches(f"v1cdti/hw/set/{student_id}/model-01/{w.SERIAL}"):
                # set washing machine status
                print(f"{time.ctime()} - MQTT [{m_decode['serial']}]:{m_decode['name']} => {m_decode['value']}")
                if (m_decode['name']=="STATUS" and m_decode['value']==S_READY):
                    w.STATE = S_READY
                elif (m_decode['name']=="STATUS" and m_decode['value']==S_FULLLEVELDETECTED):
                    w.STATE = S_FULLLEVELDETECTED
                elif (m_decode['name']=="STATUS" and m_decode['value']==S_FAULT):
                    w.STATE = S_FAULT
                elif (m_decode['name']=="STATUS" and m_decode['value']==S_FAULTCLEARED):
                    w.STATE = S_FAULTCLEARED
                elif (m_decode['name']=="STATUS" and m_decode['value']==S_OFF):
                    w.STATE = "OFF"
                else:
                    print(f"{time.ctime()} - ERROR MQTT [{m_decode['serial']}]:{m_decode['name']} => {m_decode['value']}")

async def main():
    w = WashingMachine(serial='SN-001')
    async with aiomqtt.Client("broker.hivemq.com") as client:
        await asyncio.gather(listen(w, client) , CoroWashingMachine(w, client)
                             )

asyncio.run(main())