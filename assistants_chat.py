import autogen
import asyncio
from threading import Thread
from fastapi import WebSocket
from time import sleep

async def receive_message(websocket, output=None):
    if output:
        await websocket.send_text(output)
    return await websocket.receive_text()

def run_async_in_thread(coroutine):
    def start_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    new_loop = asyncio.new_event_loop()
    t = Thread(target=start_loop, args=(new_loop,))
    t.start()
    asyncio.run_coroutine_threadsafe(coroutine, new_loop)

class CustomGroupChat(autogen.GroupChat):
    """Group chat with customized speaker selection"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.websocket = None

    async def set_websocket(self, websocket: WebSocket):
        """Sets the WebSocket for real-time communication."""
        self.websocket = websocket

    def manual_select_speaker(self, agents):
        """Manually select the next speaker."""
        run_async_in_thread(self.websocket.send_text("Please select the next speaker from the following list:"))
        
        _n_agents = len(agents)
        for i in range(_n_agents):
            run_async_in_thread(self.websocket.send_text(f"{i+1}: {agents[i].name}"))
        
        try_count = 0
        while try_count <= 3:
            if try_count >= 3:
                run_async_in_thread(self.websocket.send_text(f"You have tried {try_count} times. The next speaker will be selected automatically."))
                break
            try:
                send_msg = "Enter the number of the next speaker (enter `q` to use auto selection): "
                i = run_async_in_thread(receive_message(self.websocket, send_msg))
                # i = input(send_msg)
                if type(i) is not str:
                    sleep(2)
                    continue
                elif i == "q":
                    break
                
                i = int(i)
                try_count += 1
                if i > 0 and i <= _n_agents:
                    return agents[i - 1]
                else:
                    raise ValueError
                
            except ValueError:
                run_async_in_thread(self.websocket.send_text(f"Invalid input. Please enter a number between 1 and {_n_agents}."))
        
        return None
    

# Custom Group Chat Manager class
class CustomGroupChatManager(autogen.GroupChatManager):
    """Manages group chats with custom behavior, integrating WebSocket communication."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.websocket = None

    async def set_websocket(self, websocket: WebSocket):
        """Sets the WebSocket for real-time communication."""
        self.websocket = websocket

    async def a_receive(self, message, sender, request_reply, silent=False):
        """Handles message reception and forwards it to the WebSocket client."""
        await super().a_receive(message, sender, request_reply, silent)
        if self.websocket:
            await self.websocket.send_text(f"{sender.name}: {message['content'] if type(message) is not str else message}")
