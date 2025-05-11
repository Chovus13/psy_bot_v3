import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import logging
import json
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from orderbook import filter_walls, detect_trend
from levels import generate_signals, classify_wall_volume
from contextlib import asynccontextmanager

# --- KONFIGURACIJA LOGOVANJA ---
log_dir = '/app/logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    filename=os.path.join(log_dir, 'bot.log'),
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'
)
logger = logging.getLogger(__name__)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Učitavanje API ključeva
load_dotenv()
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')
if not api_key or not api_secret:
    logger.error("API_KEY ili API_SECRET nisu postavljeni u .env fajlu!")
    raise ValueError("API_KEY ili API_SECRET nisu postavljeni!")

# FastAPI aplikacija
app = FastAPI()

# Globalne promenljive za trading task
trading_task_running = False
trading_task_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Pokrećem Psy Bot v3...")
    yield
    logger.info("Gasim Psy Bot v3...")
    if trading_task_instance:
        trading_task_instance.cancel()
        await asyncio.sleep(0)

app.router.lifespan_context = lifespan

# Montaža static foldera
app.mount("/static", StaticFiles(directory="html"), name="static")

# Ruta za index.html
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("html/index.html", "r") as f:
        return f.read()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "trading_active": trading_task_running}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global trading_task_running, trading_task_instance
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get('action') == 'start' and not trading_task_running:
                logger.info("Pokrećem trading task preko WebSocket-a...")
                trading_task_running = True
                trading_task_instance = asyncio.create_task(trading_task())
            elif data.get('action') == 'stop' and trading_task_running:
                logger.info("Zaustavljam trading task...")
                trading_task_running = False
                if trading_task_instance:
                    trading_task_instance.cancel()
                    trading_task_instance = None
            log_file = os.path.join(log_dir, 'bot.log')
            if os.path.exists(log_file):
                with open(log_file, "r") as f:
                    logs = f.readlines()
                    for log in logs[-10:]:
                        await websocket.send_text(log.strip())
            else:
                await websocket.send_text("Log fajl još nije kreiran.")
            await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"Greška u WebSocket-u: {str(e)}")
    finally:
        await websocket.close()

async def fetch_balance(exchange):
    try:
        balance = await exchange.fetch_balance()
        usdt_balance = balance['USDT']['free'] if 'USDT' in balance else 0
        logger.info(f"USDT balans: {usdt_balance}")
        return usdt_balance
    except Exception as e:
        logger.error(f"Greška pri dohvatanju balansa: {str(e)}")
        return 0

async def setup_futures(exchange, symbol, leverage=20):
    try:
        markets = await exchange.load_markets()
        market = markets[symbol]
        if market['type'] not in ['linear', 'inverse']:
            logger.error(f"Simbol {symbol} nije linearni ili inverzni kontrakt!")
            raise ValueError(f"Simbol {symbol} nije podržan za leverage.")
        await exchange.set_leverage(leverage, symbol)
        await exchange.set_margin_mode('isolated', symbol)
        logger.info(f"Uspešno postavljen leverage {leverage}x i izolovani margin za {symbol}")
    except Exception as e:
        logger.error(f"Greška pri postavljanju leverage/margin za {symbol}: {str(e)}")
        raise

async def fetch_orderbook_rest(exchange, symbol):
    try:
        orderbook = await exchange.fetch_order_book(symbol, limit=100)
        logger.info(f"REST API: Orderbook za {symbol} uspešno povučen")
        return orderbook
    except Exception as e:
        logger.error(f"Greška pri REST povlačenju orderbook-a za {symbol}: {str(e)}")
        return None

async def manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit):
    try:
        position = await exchange.fetch_position(symbol)
        current_price = position['markPrice']
        entry_price = order['price']
        if order['side'] == 'buy':  # LONG
            new_stop = current_price - stop_loss
            if new_stop > entry_price:
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'sell', order['amount'], None,
                    {'stopPrice': new_stop}
                )
        else:  # SHORT
            new_stop = current_price + stop_loss
            if new_stop < entry_price:
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'buy', order['amount'], None,
                    {'stopPrice': new_stop}
                )
    except Exception as e:
        logger.error(f"Greška u trailing stop-loss-u za {symbol}: {str(e)}")

async def watch_orderbook(exchange, symbol):
    while trading_task_running:
        try:
            orderbook = await exchange.watch_order_book(symbol, limit=100)
            logger.info(f"WebSocket: Orderbook za {symbol} uspešno povučen")
            current_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
            walls = filter_walls(orderbook, current_price)
            trend = detect_trend(orderbook, current_price)
            signals = generate_signals(current_price, walls, trend, rokada_status="on")
            
            for signal in signals:
                logger.info(f"Signal za {symbol}: {signal}")
                stop_loss = 0.00005
                take_profit = stop_loss * 2
                signal['stop_loss'] = round(signal['entry_price'] - stop_loss, 5) if signal['type'] == 'LONG' else round(signal['entry_price'] + stop_loss, 5)
                signal['take_profit'] = round(signal['entry_price'] + take_profit, 5) if signal['type'] == 'LONG' else round(signal['entry_price'] - take_profit, 5)

                if signal['type'] == 'LONG':
                    order = await exchange.create_limit_buy_order(symbol, amount=0.01, price=signal['entry_price'])
                    logger.info(f"Kreiran LONG nalog: {order}")
                    await exchange.create_order(
                        symbol, 'stop_market', 'sell', 0.01, None,
                        {'stopPrice': signal['stop_loss'], 'closePosition': True}
                    )
                    await exchange.create_order(
                        symbol, 'take_profit_market', 'sell', 0.01, None,
                        {'stopPrice': signal['take_profit'], 'closePosition': True}
                    )
                    asyncio.create_task(manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit))
                elif signal['type'] == 'SHORT':
                    order = await exchange.create_limit_sell_order(symbol, amount=0.01, price=signal['entry_price'])
                    logger.info(f"Kreiran SHORT nalog: {order}")
                    await exchange.create_order(
                        symbol, 'stop_market', 'buy', 0.01, None,
                        {'stopPrice': signal['stop_loss'], 'closePosition': True}
                    )
                    await exchange.create_order(
                        symbol, 'take_profit_market', 'buy', 0.01, None,
                        {'stopPrice': signal['take_profit'], 'closePosition': True}
                    )
                    asyncio.create_task(manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit))

                # Ažuriraj data.json sa novim podacima
                try:
                    with open('/app/data.json', 'r') as f:
                        data = json.load(f)
                    data['price'] = current_price
                    data['position'] = signal['type']
                    data['unimmr'] = 0  # Ažuriraj ovo sa stvarnim PNL-om ako je dostupno
                    with open('/app/data.json', 'w') as f:
                        json.dump(data, f)
                except Exception as e:
                    logger.error(f"Greška pri ažuriranju data.json: {str(e)}")

        except Exception as e:
            logger.error(f"Greška u WebSocket-u za {symbol}: {str(e)}, prelazim na REST")
            orderbook = await fetch_orderbook_rest(exchange, symbol)
            if orderbook:
                current_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
                walls = filter_walls(orderbook, current_price)
                trend = detect_trend(orderbook, current_price)
                signals = generate_signals(current_price, walls, trend, rokada_status="on")
                for signal in signals:
                    logger.info(f"REST Signal za {symbol}: {signal}")
        await asyncio.sleep(1)

async def trading_task():
    global trading_task_running
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'urls': {
            'api': {
                'fapi': 'https://fapi.binance.com'  # LIVE API
            }
        }
    })

    try:
        await exchange.load_markets()
        logger.info("Marketi uspešno učitani")

        symbol = 'ETH/USDT'
        with open('/app/data.json', 'r') as f:
            data = json.load(f)
        leverage = data.get('leverage', 2)  # Uzmi leverage iz data.json
        trade_amount = data.get('trade_amount', 0.01)  # Uzmi trade amount iz data.json

        # Dohvati balans i ažuriraj data.json
        usdt_balance = await fetch_balance(exchange)
        data['balance'] = usdt_balance
        with open('/app/data.json', 'w') as f:
            json.dump(data, f)

        await setup_futures(exchange, symbol, leverage=leverage)

        await watch_orderbook(exchange, symbol)

    except Exception as e:
        logger.error(f"Greška u trading petlji: {str(e)}")
        trading_task_running = False
    finally:
        await exchange.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)