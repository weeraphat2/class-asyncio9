import time
import random
import json
import asyncio
import aiomqtt
from enum import Enum
import sys
import os

student_id = "6310301022"

async def listen(client):
    async with client.messages() as messages:

        await client.subscribe(f"v1cdti/app/monitor/{student_id}/model-01/#")
        print(f"{time.ctime()}  SUB topic: v1cdti/app/monitor/{student_id}/model-01/#")

        async for message in messages:
            m_decode = json.loads(message.payload)

            if message.topic.matches(f"v1cdti/app/monitor/{student_id}/model-01/#"):
                print(f"{time.ctime()} - MQTT {m_decode['project']} [{m_decode['serial']}]:{m_decode['name']} => {m_decode['value']}")

async def main():
    async with aiomqtt.Client("broker.hivemq.com") as client:
        await asyncio.gather(listen(client))

# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())
# Run your async application as usual

asyncio.run(main())