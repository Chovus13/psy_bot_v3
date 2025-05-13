import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import logging
import json
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from orderbook import filter_walls, detect_trend
from levels import generate_signals
from logger import setup_logger, log_trade
from contextlib import asynccontextmanager

# Konfiguracija logovanja
log_dir = '/app/logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logger = setup_logger(__name__, os.path.join(log_dir, 'bot.log'))
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

# Globalne promenljive
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

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("/html/index.html", "r") as f:
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
            try:
                data = await websocket.receive_json()
                if data.get('action') == 'start' and not trading_task_running:
                    logger.info("Pokrećem trading task...")
                    trading_task_running = True
                    trading_task_instance = asyncio.create_task(trading_task())
                elif data.get('action') == 'stop' and trading_task_running:
                    logger.info("Zaustavljam trading task...")
                    trading_task_running = False
                    if trading_task_instance:
                        trading_task_instance.cancel()
                        trading_task_instance = None
            except:
                pass
            log_file = os.path.join(log_dir, 'bot.log')
            if os.path.exists(log_file):
                with open(log_file, "r") as f:
                    logs = f.readlines()
                    for log in logs[-10:]:
                        await websocket.send_text(log.strip())
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

async def setup_futures(exchange, symbol, leverage):
    try:
        await exchange.set_leverage(leverage, symbol)
        await exchange.set_margin_mode('isolated', symbol)
        logger.info(f"Postavljen leverage {leverage}x i izolovani margin za {symbol}")
    except Exception as e:
        logger.error(f"Greška pri postavljanju leverage/margin za {symbol}: {str(e)}")
        raise

async def fetch_orderbook_rest(exchange, symbol):
    try:
        orderbook = await exchange.fetch_order_book(symbol, limit=100)
        logger.info(f"REST API: Orderbook za {symbol} povučen")
        return orderbook
    except Exception as e:
        logger.error(f"Greška pri REST povlačenju orderbook-a: {str(e)}")
        return None

async def cancel_tp_sl(exchange, symbol):
    try:
        orders = await exchange.fetch_open_orders(symbol)
        for order in orders:
            if order['type'] in ['stop_market', 'take_profit_market']:
                await exchange.cancel_order(order['id'], symbol)
                logger.info(f"Cancelovan order: {order['id']} ({order['type']})")
    except Exception as e:
        logger.error(f"Greška pri cancel-ovanju TP/SL: {str(e)}")

async def close_position(exchange, symbol):
    try:
        position = await exchange.fetch_position(symbol)
        if position['contracts'] > 0:
            side = 'sell' if position['side'] == 'long' else 'buy'
            amount = position['contracts']
            await exchange.create_market_order(symbol, side, amount, params={'closePosition': True})
            logger.info(f"Zatvorena pozicija: {side} {amount} na {symbol}")
    except Exception as e:
        logger.error(f"Greška pri zatvaranju pozicije: {str(e)}")

async def manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit):
    try:
        position = await exchange.fetch_position(symbol)
        current_price = position['markPrice']
        entry_price = order['price']
        amount = order['amount']
        if order['side'] == 'buy':  # LONG
            new_stop = current_price - stop_loss
            if new_stop > entry_price:
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'sell', amount, None,
                    {'stopPrice': new_stop, 'closePosition': True}
                )
        else:  # SHORT
            new_stop = current_price + stop_loss
            if new_stop < entry_price:
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'buy', amount, None,
                    {'stopPrice': new_stop, 'closePosition': True}
                )
    except Exception as e:
        logger.error(f"Greška u trailing stop-loss-u za {symbol}: {str(e)}")

async def watch_orderbook(exchange, symbol):
    global trading_task_running
    while trading_task_running:
        try:
            # Učitaj data.json
            with open('/app/data.json', 'r') as f:
                data = json.load(f)
            rokada_status = data.get('rokada', 'off')
            trade_amount = data.get('trade_amount', 0.01)
            leverage = data.get('leverage', 1)
            manual_mode = data.get('manual', 'off')
            manual_command = data.get('manual_command', '')

            # Obrada manualnih komandi
            if manual_mode == 'on' and manual_command:
                if manual_command == 'disable_tp_sl':
                    await cancel_tp_sl(exchange, symbol)
                    data['manual_command'] = ''  # Reset komande
                elif manual_command == 'close_position':
                    await close_position(exchange, symbol)
                    data['manual_command'] = ''
                    data['position'] = 'None'
                with open('/app/data.json', 'w') as f:
                    json.dump(data, f)

            orderbook = await exchange.watch_order_book(symbol, limit=100)
            logger.info(f"WebSocket: Orderbook za {symbol} povučen")
            current_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
            walls = filter_walls(orderbook, current_price)
            trend = detect_trend(orderbook, current_price)
            signals = generate_signals(current_price, walls, trend, rokada_status)

            for signal in signals:
                logger.info(f"Signal za {symbol}: {signal}")
                stop_loss = 0.00005
                take_profit = stop_loss * 2
                signal['stop_loss'] = (
                    round(signal['entry_price'] - stop_loss, 5)
                    if signal['type'] == 'LONG'
                    else round(signal['entry_price'] + stop_loss, 5)
                )
                signal['take_profit'] = (
                    round(signal['entry_price'] + take_profit, 5)
                    if signal['type'] == 'LONG'
                    else round(signal['entry_price'] - take_profit, 5)
                )

                if manual_mode == 'off':  # Trguj samo ako nije manual mod
                    if signal['type'] == 'LONG':
                        order = await exchange.create_limit_buy_order(
                            symbol, amount=trade_amount, price=signal['entry_price']
                        )
                        logger.info(f"Kreiran LONG nalog: {order}")
                        await exchange.create_order(
                            symbol, 'stop_market', 'sell', trade_amount, None,
                            {'stopPrice': signal['stop_loss'], 'closePosition': True}
                        )
                        await exchange.create_order(
                            symbol, 'take_profit_market', 'sell', trade_amount, None,
                            {'stopPrice': signal['take_profit'], 'closePosition': True}
                        )
                        log_trade(
                            signal['entry_price'], signal['entry_price'],
                            'LONG', signal['volume'], None
                        )
                        asyncio.create_task(
                            manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit)
                        )
                    elif signal['type'] == 'SHORT':
                        order = await exchange.create_limit_sell_order(
                            symbol, amount=trade_amount, price=signal['entry_price']
                        )
                        logger.info(f"Kreiran SHORT nalog: {order}")
                        await exchange.create_order(
                            symbol, 'stop_market', 'buy', trade_amount, None,
                            {'stopPrice': signal['stop_loss'], 'closePosition': True}
                        )
                        await exchange.create_order(
                            symbol, 'take_profit_market', 'buy', trade_amount, None,
                            {'stopPrice': signal['take_profit'], 'closePosition': True}
                        )
                        log_trade(
                            signal['entry_price'], signal['entry_price'],
                            'SHORT', signal['volume'], None
                        )
                        asyncio.create_task(
                            manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit)
                        )

                # Ažuriraj data.json
                data['price'] = current_price
                data['position'] = signal['type'] if manual_mode == 'off' else data['position']
                data['support'] = walls['support'][0][0] if walls['support'] else 0
                data['resistance'] = walls['resistance'][0][0] if walls['resistance'] else 0
                with open('/app/data.json', 'w') as f:
                    json.dump(data, f)

        except Exception as e:
            logger.error(f"Greška u WebSocket-u za {symbol}: {str(e)}, prelazim na REST")
            orderbook = await fetch_orderbook_rest(exchange, symbol)
            if orderbook:
                current_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
                walls = filter_walls(orderbook, current_price)
                trend = detect_trend(orderbook, current_price)
                signals = generate_signals(current_price, walls, trend, rokada_status)
                for signal in signals:
                    logger.info(f"REST Signal za {symbol}: {signal}")
        await asyncio.sleep(1)

async def trading_task():
    global trading_task_running
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'adjustForTimeDifference': True, 'defaultType': 'future'}
    })

    try:
        await exchange.load_markets()
        logger.info("Marketi učitani")
        symbol = os.getenv('PAR', 'ETH/BTC')
        with open('/app/data.json', 'r') as f:
            data = json.load(f)
        leverage = data.get('leverage', 1)
        usdt_balance = await fetch_balance(exchange)
        data['balance'] = usdt_balance
        with open('/app/data.json', 'w') as f:
            json.dump(data, f)
        await setup_futures(exchange, symbol, leverage)
        await watch_orderbook(exchange, symbol)
    except Exception as e:
        logger.error(f"Greška u trading petlji: {str(e)}")
        trading_task_running = False
    finally:
        await exchange.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)