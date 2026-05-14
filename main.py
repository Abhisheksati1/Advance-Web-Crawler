from uvicorn import run
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.crawl_url import crawl_url


# from crawler.message_broker.sub_broker import receive_task_fetch_link


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
    var ws = new WebSocket("ws://127.0.0.1:8001/ws");

    ws.onmessage = function(event) {

        var messages = document.getElementById('messages')

        var message = document.createElement('li')

        var content = document.createTextNode(event.data)

        message.appendChild(content)

        messages.appendChild(message)
    };

    function sendMessage(event) {

        var input = document.getElementById("messageText")

        // Convert comma-separated text into array
        var urls = input.value
            .split(",")
            .map(item => item.trim())
            .filter(Boolean)

        // Send JSON array
        ws.send(JSON.stringify(urls))

        input.value = ''

        event.preventDefault()
    }
</script>
    </body>
</html>
"""


# @app.get("/")
# async def health_check():
#     return JSONResponse(
#         status_code=200,
#         content={"status": "running"}
#     )

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
        await crawl_url(data, websocket)
        await websocket.send_text(f"Message text was: {data}")