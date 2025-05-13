import json
import logging
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# Konfiguracija logovanja
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# FastAPI aplikacija
app = FastAPI()

# CORS middleware za frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Globalna promenljiva iz main.py
trading_task_running = False

@app.get("/logs/orderbook.png")
async def serve_orderbook_image(t: str = None):
    """Vraća orderbook.png iz logs foldera."""
    try:
        return FileResponse("/app/logs/orderbook.png")
    except Exception as e:
        logger.error(f"Greška pri serviranju orderbook.png: {e}")
        return {"status": "error", "message": "Slika nije pronađena"}

@app.post("/manual")
async def manual_control(command: dict):
    """Upravlja manualnim komandama i rokada modom."""
    cmd = command.get("command")
    value = command.get("value", "on")
    logger.info(f"Manual kontrola: {cmd}, vrednost: {value}")

    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Greška pri čitanju data.json: {e}")
        data = {
            'price': 0, 'support': 0, 'resistance': 0, 'position': 'None',
            'balance': 0, 'unimmr': 0, 'logs': [], 'manual': 'off',
            'rokada': 'off', 'trade_amount': 0.01, 'leverage': 1, 'rsi': 'off'
        }

    if cmd == "toggle":
        data['manual'] = value
    elif cmd in ["rokada_on", "rokada_off"]:
        data['rokada'] = "on" if cmd == "rokada_on" else "off"
    else:
        data['manual'] = "on"
        data['manual_command'] = cmd

    try:
        with open("/app/data.json", "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"data.json ažuriran sa komandom: {cmd}")
    except Exception as e:
        logger.error(f"Greška pri pisanju u data.json: {e}")

    return {"status": "success", "command": cmd, "value": value}

@app.post("/update_data")
async def update_data(updates: dict):
    """Ažurira data.json sa novim podacima."""
    logger.info(f"Ažuriranje data.json: {updates}")
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Greška pri čitanju data.json: {e}")
        data = {
            'price': 0, 'support': 0, 'resistance': 0, 'position': 'None',
            'balance': 0, 'unimmr': 0, 'logs': [], 'manual': 'off',
            'rokada': 'off', 'trade_amount': 0.01, 'leverage': 1, 'rsi': 'off'
        }

    data.update(updates)
    try:
        with open("/app/data.json", "w") as f:
            json.dump(data, f, indent=2)
        logger.info("data.json uspešno ažuriran")
    except Exception as e:
        logger.error(f"Greška pri pisanju u data.json: {e}")

    return {"status": "success", "updates": updates}

@app.get("/get_data")
async def get_data():
    """Vraća trenutne podatke iz data.json."""
    try:
        with open("/app/data.json", "r") as f:
            data = json.load(f)
        logger.info(f"Vraćam podatke iz data.json: {data}")
        return data
    except Exception as e:
        logger.error(f"Greška pri čitanju data.json: {e}")
        default_data = {
            'price': 0, 'support': 0, 'resistance': 0, 'position': 'None',
            'balance': 0, 'unimmr': 0, 'logs': [], 'manual': 'off',
            'rokada': 'off', 'trade_amount': 0.01, 'leverage': 1, 'rsi': 'off'
        }
        return default_data

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket za real-time ažuriranje frontenda."""
    await websocket.accept()
    logger.info("WebSocket konekcija uspostavljena")
    try:
        while True:
            try:
                with open("/app/data.json", "r") as f:
                    data = json.load(f)
                data.update({
                    'isLive': True,
                    'takeFromHere': False,
                    'tradeAtNight': False,
                    'advancedMode': False,
                    'isRunning': trading_task_running
                })
                await websocket.send_json(data)
                logger.debug("Poslati podaci preko WebSocket-a")
            except Exception as e:
                logger.error(f"Greška pri slanju WebSocket poruke: {e}")
                break
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"WebSocket greška: {e}")
    finally:
        await websocket.close()
        logger.info("WebSocket konekcija zatvorena")