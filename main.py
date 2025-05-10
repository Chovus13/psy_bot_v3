import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import logging
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from orderbook import filter_walls, detect_trend
from levels import generate_signals, classify_wall_volume

# Konfiguracija logging-a
logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Učitavanje API ključeva
load_dotenv()
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')

# FastAPI aplikacija
app = FastAPI()

# Montaža static foldera za html/index.html
app.mount("/static", StaticFiles(directory="html"), name="static")

# Ruta za index.html
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("html/index.html", "r") as f:
        return f.read()

# WebSocket za komunikaciju sa frontend-om
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Slanje logova ili signala klijentu
            with open("bot.log", "r") as f:
                logs = f.readlines()
                for log in logs[-10:]:  # Slanje poslednjih 10 logova
                    await websocket.send_text(log.strip())
            await asyncio.sleep(5)  # Slanje svakih 5 sekundi
    except Exception as e:
        logger.error(f"Greška u WebSocket-u za frontend: {str(e)}")
    finally:
        await websocket.close()

async def setup_futures(exchange, symbol, leverage=20):
    """Postavlja leverage i izolovani margin za dati simbol."""
    try:
        await exchange.set_leverage(leverage, symbol)
        await exchange.set_margin_mode('isolated', symbol)
        logger.info(f"Uspešno postavljen leverage {leverage}x i izolovani margin za {symbol}")
    except Exception as e:
        logger.error(f"Greška pri postavljanju leverage/margin za {symbol}: {str(e)}")
        raise

async def fetch_orderbook_rest(exchange, symbol):
    """REST API fallback za orderbook."""
    try:
        orderbook = await exchange.fetch_order_book(symbol, limit=100)
        logger.info(f"REST API: Orderbook za {symbol} uspešno povučen")
        return orderbook
    except Exception as e:
        logger.error(f"Greška pri REST povlačenju orderbook-a za {symbol}: {str(e)}")
        return None

async def manage_trailing_stop(exchange, symbol, order, stop_loss, take_profit):
    """Upravlja trailing stop-loss-om (2:1 odnos)."""
    try:
        position = await exchange.fetch_position(symbol)
        current_price = position['markPrice']
        entry_price = order['price']
        if order['side'] == 'buy':  # LONG
            new_stop = current_price - stop_loss
            if new_stop > entry_price:
                new_stop = current_price - stop_loss
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'sell', order['amount'], None,
                    {'stopPrice': new_stop}
                )
        else:  # SHORT
            new_stop = current_price + stop_loss
            if new_stop < entry_price:
                new_stop = current_price + stop_loss
                logger.info(f"Trailing stop za {symbol} pomeren na {new_stop}")
                await exchange.create_order(
                    symbol, 'stop_market', 'buy', order['amount'], None,
                    {'stopPrice': new_stop}
                )
    except Exception as e:
        logger.error(f"Greška u trailing stop-loss-u za {symbol}: {str(e)}")

async def watch_orderbook(exchange, symbol):
    """Praćenje orderbook-a preko WebSocket-a sa REST fallback-om."""
    while True:
        try:
            orderbook = await exchange.watch_order_book(symbol, limit=100)
            logger.info(f"WebSocket: Orderbook za {symbol} uspešno povučen")
            current_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
            walls = filter_walls(orderbook, current_price)
            trend = detect_trend(orderbook, current_price)
            signals = generate_signals(current_price, walls, trend, rokada_status="on")
            
            for signal in signals:
                logger.info(f"Signal za {symbol}: {signal}")
                stop_loss = 0.00005  # 5 pipova (5. decimala)
                take_profit = stop_loss * 2  # 2:1 odnos
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

async def trading_task():
    """Zasebna petlja za trading logiku."""
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'urls': {
            'api': {
                'fapi': 'https://fapi.binance.com',  # Futures endpoint
            }
        }
    })

    # Testnet mod (za testiranje)
    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()
        logger.info("Marketi uspešno učitani")

        symbol = 'ETH/BTC:USDT'
        await setup_futures(exchange, symbol, leverage=20)

        await watch_orderbook(exchange, symbol)

    except Exception as e:
        logger.error(f"Greška u trading petlji: {str(e)}")
    finally:
        await exchange.close()

# Pokretanje trading petlje u pozadini
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(trading_task())