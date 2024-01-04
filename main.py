import os
import json
import autogen
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import List
from assistants_chat import CustomGroupChatManager, CustomGroupChat
from tool_functions import *
from autogen.agentchat.contrib import agent_builder
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent
from pydantic import BaseModel
from openai import OpenAI, AsyncOpenAI
client = OpenAI()

async def run_async(func, *args):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, func, *args)
    return result
main_loop = asyncio.get_event_loop()
async def custom_print(websocket: WebSocket, *args, **kwargs): # sending message with websocket
    message = ' '.join(map(str, args))
    try:
        await websocket.send_text(message)
    except Exception as e:
        print("Error sending message:", e)
    print(*args, **kwargs)

available_tools = {
    "weather": get_weather_json
}
all_func_map = {
    "get_weather": get_weather
}

config_path = 'OAI_CONFIG_LIST'  # modify path
default_llm_config = {
    'temperature': 0
}

max_round = 10
agent_list = []
oai_model = "gpt-4-1106-preview"
human_input_mode = "NEVER"
speaker_selection_mode = "auto"

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates", auto_reload=True)

# Initialize a list to store messages
messages: List[str] = [] ##### handle it later (don't touch for now)

# Initialize the builder
builder = agent_builder.AgentBuilder(config_path=config_path, builder_model='gpt-4-1106-preview', agent_model='gpt-4-1106-preview')




def is_heartbeat(data): # handling receivet heartbeat message
    flag = False
    try:
        message = json.loads(data)
    except json.JSONDecodeError:
        return flag
    
    if message.get("type") == "heartbeat":
        print("Heartbeat")
        flag = True
    return flag

async def check_openai_api_key(api_key, socket): # check key validation
    new_client = AsyncOpenAI(api_key=api_key)
    await new_client.models.list()
    os.environ["OPENAI_API_KEY"] = api_key
    
@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    # Render the chat interface using a template
    return templates.TemplateResponse("chat.html", {"request": request, "messages": messages})

@app.websocket("/ws_build")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        user_message = await websocket.receive_text()
        if is_heartbeat(user_message): continue
        global max_round, agent_list, oai_model, human_input_mode, speaker_selection_mode

        user_message = json.loads(user_message)
        type = user_message.get("type")
        data = user_message.get("data")

        # Update global variables based on received data
        max_round = int(data['rounds']) if data.get("rounds") else max_round
        api_key = data['api_key']
        human_input_mode = data['human_input_mode']
        speaker_selection_mode = data['speaker_selection_mode']
        tools = data.get("tools")
            
        use_coding = "coding" in tools

        # API key validation and setup
        await websocket.send_text("Checking api key...")
        
        try:
            await check_openai_api_key(api_key, websocket)
            await websocket.send_text("valid API key")
        except Exception as e:
            await websocket.send_text("Api key error. check validation: " + api_key)
            continue
        
        await websocket.send_text("Creating agents...")

        # Handling different types of received messages
        if type == "building_file":
            # Process data from a configs file
            configs = json.loads(data.get("filedata"))
            agent_list, agent_configs = builder.build(cached_configs=configs)
            await websocket.send_text("Building_task: "+ agent_configs["building_task"])
        else:
            task = data['task']
            agent_count = int(data['agent_count'])
            oai_model = data['model']
            agent_builder.AgentBuilder.max_agents = agent_count
            builder.agent_model = oai_model

            agent_builder.print = lambda *args, **kwargs: asyncio.run_coroutine_threadsafe(custom_print(websocket, *args, **kwargs), main_loop) #explore
            agent_list, agent_configs = await run_async(builder.build, task, default_llm_config, use_coding, None, True) # use this for heartbeats
            # agent_list, agent_configs = builder.build(task, default_llm_config, use_oai_assistant=True, coding=use_coding) # without async
        
        # Add user agent if coding is not used (in other case user_proxy created by the builder)
        if not use_coding:
            await websocket.send_text("Adding user...")
            agent_list = [
                autogen.UserProxyAgent(
                    name="user",
                    is_termination_msg=lambda x: "TERMINATE" in x.get("content"),
                    system_message="User console.",
                    human_input_mode="NEVER",
                )
            ] + agent_list
        
        # Setup tools assistant if coding tool is not the only tool
        if not (tools == ['coding']):
            llm_config = {
                    "config_list": [{"model": "gpt-4-1106-preview"}],
                    "assistant_id": None,
                     "tools": [
                        {
                            "type": "function",
                            "function": available_tools[tool_name],
                        } for tool_name in tools if tool_name in available_tools.keys()
                    ]
                }
            tools_assistant =  GPTAssistantAgent(
                name="Tools_manager",                            
                instructions=(
                    "Use available tools for answering."
                ),
                llm_config=llm_config,
                verbose=True,
            )
            for tool_name in tools:
                if tool_name in available_tools.keys():
                    function_name = available_tools[tool_name]["name"]
                    tools_assistant.register_function(
                        function_map={
                            function_name: all_func_map[function_name]
                        }
                    )
                    print("Tool registered!", tools_assistant.name, function_name)
            agent_list.insert(1, tools_assistant)

        # Send back the names and configurations of the agents
        agent_names = [agent.name for agent in agent_list]
        print("agents:", agent_names)
        await websocket.send_text(json.dumps({
             "names": agent_names,
             "configs": agent_configs
        }))

async def start_task(execution_task: str, llm_config: dict, websocket: WebSocket):
    config_list = [
        {
            "model": oai_model,
            "api_key": os.environ['OPENAI_API_KEY']
        }
    ]

    # Create a CustomGroupChat instance with predefined agents and configurations (groupchat with overrided manual dpeaker selection)
    group_chat = CustomGroupChat(agents=agent_list, messages=[], max_round=max_round, speaker_selection_method=speaker_selection_mode)
    await group_chat.set_websocket(websocket=websocket)
    
    # Initialize CustomGroupChatManager with group chat and combined llm_config (Manager: sending chat messages with websocket)
    manager = CustomGroupChatManager(
        groupchat = group_chat, llm_config={"config_list": config_list, **llm_config}
    )
    await manager.set_websocket(websocket=websocket)

    try:
        agent_list[0].human_input_mode = human_input_mode
    except Exception:
        pass
    await agent_list[0].a_initiate_chat(manager, message=execution_task)

@app.websocket("/ws_Chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        user_message = await websocket.receive_text()
        if is_heartbeat(user_message): continue

        # Start a task based on the received user message
        try:
            await start_task(
                execution_task=user_message,
                llm_config=default_llm_config,
                websocket=websocket
            )
        except Exception as e:
            await websocket.send_text("Error in start_task function. here is the message: " + e)

        builder.clear_all_agents()


class Prompt(BaseModel): # append options for handling received user messages too
    value: str

@app.post("/refine/")
async def create_item(prompt: Prompt):
    user_message = prompt.value
    try:
        response = client.chat.completions.create( # refine building task
            model="gpt-3.5-turbo",
            messages=[
              {
                "role": "system",
                "content": "Your task is to revise and improve the clarity or structure of the user's message. Do not perform any actions or provide direct answers based on the user's content. Focus solely on editing the user's message for better clarity and coherence."
              },
              {
                "role": "user",
                "content": user_message
              }
            ],
            temperature=0,
            max_tokens=256,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        edited_prompt = response.choices[0].message.content
        print("Prompt refined")
        return edited_prompt
    except Exception as e:
        print("Invalid key")
        return user_message
