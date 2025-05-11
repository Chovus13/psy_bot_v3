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
async def manual_control(command: dict):
    cmd = command.get("command")
    value = command.get("value", "on")
    logging.info(f"Manual kontrola: {cmd}, vrednost: {value}")
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Greška pri čitanju data.json: {e}")
        data = {}

    if cmd == "toggle":
        data['manual'] = value
    elif cmd in ["rokada_on", "rokada_off"]:
        data['rokada'] = "on" if cmd == "rokada_on" else "off"
    else:
        data['manual'] = "on"
        data['manual_command'] = cmd

    try:
        with open("/app/data.json", "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Greška pri pisanju u data.json: {e}")
    
    return {"status": "success", "command": cmd, "value": value}

@app.post("/update_data")
async def update_data(updates: dict):
    logging.info(f"Ažuriranje data.json: {updates}")
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Greška pri čitanju data.json: {e}")
        data = {}

    data.update(updates)
    try:
        with open("/app/data.json", "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Greška pri pisanju u data.json: {e}")
    
    return {"status": "success", "updates": updates}

@app.get("/get_data")
async def get_data():
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
        logging.info(f"Vraćam podatke iz data.json: {data}")
        return data
    except Exception as e:
        logging.error(f"Greška pri čitanju data.json: {e}")
        data = {
            'price': 0,
            'support': 0,
            'resistance': 0,
            'position': 'None',
            'balance': 0,
            'unimmr': 0,
            'logs': [],
            'manual': 'off',
            'rokada': 'off',
            'trade_amount': 0.01,
            'leverage': 2,
            'rsi': 'off'
        }
        return data

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket konekcija uspostavljena")
    connected = True
    try:
        while connected:
            try:
                with open("/app/data.json", "r") as f:
                    data = json.load(f)
                logging.info(f"Šaljem podatke preko WebSocket-a: {data}")
            except Exception as e:
                logging.error(f"Greška pri čitanju data.json: {e}")
                data = {
                    'price': 0,
                    'support': 0,
                    'resistance': 0,
                    'position': 'None',
                    'balance': 0,
                    'unimmr': 0,
                    'logs': [],
                    'manual': 'off',
                    'rokada': 'off',
                    'trade_amount': 0.01,
                    'leverage': 2,
                    'rsi': 'off'
                }
            
            data.update({
                'isLive': True,
                'takeFromHere': False,
                'tradeAtNight': False,
                'advancedMode': False,
                'isRunning': trading_task_running
            })
            
            try:
                await websocket.send_json(data)
            except Exception as e:
                logging.error(f"Greška pri slanju WebSocket poruke: {e}")
                connected = False
                break
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"WebSocket greška: {e}")
    finally:
        connected = False
        try:
            await websocket.close()
            logging.info("WebSocket konekcija zatvorena")
        except Exception as e:
            logging.error(f"Greška pri zatvaranju WebSocket-a: {e}")