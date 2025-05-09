# api.py
import json
import logging
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
import asyncio

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.get("/")
async def serve_html():
    logging.info("GET / zahtev primljen, vraćam HTML")
    return FileResponse("/usr/share/nginx/html/index.html")

@app.get("/logs/orderbook.png")
async def serve_orderbook_image(t: str):
    return FileResponse("/app/logs/orderbook.png")

@app.post("/manual")
async def manual_control(command: str, value: str = "on"):
    logging.info(f"Manual kontrola: {command}, vrednost: {value}")
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Greška pri čitanju data.json: {e}")
        data = {}

    if command == "toggle":
        data['manual'] = value
    else:
        data['manual'] = "on"
        data['manual_command'] = command

    try:
        with open("/app/data.json", "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Greška pri pisanju u data.json: {e}")
    
    return {"status": "success", "command": command, "value": value}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket konekcija uspostavljena")
    try:
        while True:
            try:
                with open("/app/data.json", "r") as f:
                    data = json.load(f)
            except Exception as e:
                logging.error(f"Greška pri čitanju data.json: {e}")
                data = {'price': 0, 'support': 0, 'resistance': 0, 'position': 'None', 'balance': 0, 'unimmr': 0, 'logs': []}
            
            data.update({
                'isLive': False,
                'takeFromHere': False,
                'tradeAtNight': False,
                'leverage': 3,
                'advancedMode': False,
                'tradeAmount': 0.06,
                'isRunning': True
            })
            
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"WebSocket greška: {e}")
    finally:
        await websocket.close()