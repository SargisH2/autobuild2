const wsBuild = new WebSocket("wss://fast-chat-769dfc347d36.herokuapp.com/ws_build");
const wsChat = new WebSocket("wss://fast-chat-769dfc347d36.herokuapp.com/ws_Chat");
// const wsBuild = new WebSocket("ws://localhost:8000/ws_build"); // local tests
// const wsChat = new WebSocket("ws://localhost:8000/ws_Chat"); // local tests

const heartbeatMessage = JSON.stringify({ type: "heartbeat" });
const HEARTBEAT_INTERVAL = 20000; // 20 seconds

function addLog(text){
    appLogs.innerHTML += '<pre>'+text+'</pre>';
}

function sendHeartbeatBuild() {
    wsBuild.send(heartbeatMessage);
}
function sendHeartbeatChat() {
    wsChat.send(heartbeatMessage);
}
wsBuild.onopen = function(event) {
    console.log("Build open");
    heartbeatIntervalID = setInterval(sendHeartbeatBuild, HEARTBEAT_INTERVAL);
};
wsBuild.onclose = function(event) {
    if (heartbeatIntervalID) clearInterval(heartbeatIntervalID);
    console.log('-- WSBuild closed --');
};
wsChat.onopen = function(event) {
    console.log("Chat open");
    heartbeatIntervalID2 = setInterval(sendHeartbeatChat, HEARTBEAT_INTERVAL);
};
wsChat.onclose = function(event) {
    if (heartbeatIntervalID2) clearInterval(heartbeatIntervalID2);
    console.log('-- WSChat closed --');
    addLog("Disconnected...");
};

const fileInput = document.getElementById("configFile");
const taskInput = document.getElementById("task_input");
const maxRoundsInput = document.getElementById("max_rounds_input");
const agentCountInput = document.getElementById("agent_count_input");
const apiKeyInput = document.getElementById("api_key_input");
const modelInput = document.getElementById("select_model");
const humanInputMode = document.getElementById("human_input_mode");
const speakerSelectionMode = document.getElementById("speaker_selection_mode");
const buildButton = document.getElementById("build_button");
const appLogs = document.getElementById("logs");
const chatInput = document.getElementById("chat_input");
const messagesUl = document.getElementById("messages");
var configs = []

function sendBuildMessage() {
    let apiKey = apiKeyInput.value;
    if(apiKey.length < 5){
        addLog("Enter valid key");
        return;
    }

    let uploaded = false; // Flag to check if a file is uploaded
    // Collect input values from the user interface
    let rounds = maxRoundsInput.value
    let humanMode = humanInputMode.value;
    let speakerMode = speakerSelectionMode.value
    let tools = getSelectedToolValues(); // Function to get selected tool values
    if(fileInput.files.length == 1){
        const uploadedFile = fileInput.files[0];
        if (uploadedFile.type === "application/json") {
            const reader = new FileReader();
            reader.onload = function(event) {
                // Prepare the JSON data to be sent
                const fileData = event.target.result;
                var jsonData = JSON.stringify({
                    type: "building_file",
                    data: {
                        "filedata": fileData,
                        "rounds": rounds,
                        "api_key": apiKey,
                        "human_input_mode": humanMode,
                        "speaker_selection_mode": speakerMode,
                        "tools": tools
                    }
                    
                })
                wsBuild.send(jsonData);
            };
            reader.readAsText(uploadedFile);
            uploaded = true;
        }
    }
    // Handle case where no file is uploaded, but user inputs are provided
    if(!uploaded){
        messagesUl.innerHTML = ""; // Clear any previous messages
        let buildingTask = taskInput.value;
        if(!buildingTask.length) return;
        let agents = agentCountInput.value;
        let model = modelInput.value;
        
        // Set default values if input is not valid
        if(!(+rounds > 2)) rounds = 10;
        if(!(+agents > 2)) agents = 5;

        // Prepare the JSON data
        let data = {
            "task": buildingTask,
            "agent_count": agents,
            "model": model,
            "rounds": rounds,
            "api_key": apiKey,
            "human_input_mode": humanMode,
            "speaker_selection_mode": speakerMode,
            "tools": tools
        } 

        var jsonData = JSON.stringify({
            type: "building_task",
            data: data
        })
        addLog(jsonData);
        wsBuild.send(jsonData);
    }
}


wsBuild.onmessage = function(event) {
    try {
        var result = JSON.parse(event.data);
        addLog(result.names);
        configs = result.configs;
    } catch (e) {
        addLog(event.data); // If JSON parsing fails, log the raw data
    }
};

function printMessage(text){
    messagesUl.innerHTML += `<li><pre>${text}</pre></li>`;

}

function sendMessage(){
    let message = chatInput.value;
    if(!message.length) return; // Exit if the message is empty
    chatInput.value = '';
    printMessage("User: "+ message)
    wsChat.send(message);
}

function Save(filename = 'configs.json') {
    if(configs.length == 0) return;
    addLog("Saving...")

    // Create a JSON file from configs and initiate download
    const jsonString = JSON.stringify(configs, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const link = document.createElement('a');
    link.download = filename;
    link.href = window.URL.createObjectURL(blob);

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Save chat history as an HTML file
    const chat = messagesUl.innerHTML
    if(chat.length == 0) return;
    const blob2 = new Blob([chat], { type: 'text/html' });
    const link2 = document.createElement('a');
    link2.download = 'chat.html';
    link2.href = window.URL.createObjectURL(blob2);

    document.body.appendChild(link2);
    link2.click();
    document.body.removeChild(link2);

}

wsChat.onmessage = function(event) {
    printMessage(event.data);
};

function terminate(){
    wsBuild.close();
    wsChat.close();
}

async function refine() {
    const prompt = taskInput.value;
    if(prompt.length < 5) return;

    // Sends a POST request to the '/refine/' endpoint
    const response = await fetch('/refine/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: prompt }),
    });

    const refinedPrompt = await response.json();
    document.getElementById('task_input').value = refinedPrompt
}

function getSelectedToolValues() {
    const checkboxes = document.querySelectorAll('#tools .tool:checked');
    const values = Array.from(checkboxes).map(checkbox => checkbox.value);
    return values;
}