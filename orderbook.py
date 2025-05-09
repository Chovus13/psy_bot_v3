# main.py (blago ažurirana verzija)
import time
import ccxt
import os
import json
import telegram
from orderbook import get_orderbook, filter_walls, detect_trend
from levels import generate_signals
from config import PRICE_PRECISION, LEVERAGE, PROFIT_TARGET

import logging
logging.basicConfig(level=logging.INFO)

def send_telegram_message(message):
    try:
        bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        bot.send_message(chat_id=os.getenv('TELEGRAM_CHAT_ID'), text=message)
    except Exception as e:
        logging.error(f"Greška pri slanju Telegram poruke: {e}")

def read_data_json():
    try:
        with open('/app/data.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Greška pri čitanju data.json: {e}")
        return {}

def update_data_json(price, support, resistance, position, balance=0, unimmr=0, manual="off"):
    data = {
        'price': price,
        'support': support,
        'resistance': resistance,
        'position': position if position else 'None',
        'balance': balance,
        'unimmr': unimmr,
        'logs': [],
        'manual': manual
    }
    try:
        with open('/app/data.json', 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Greška pri pisanju u data.json: {e}")

def place_order(exchange, symbol, side, price, amount, is_demo=False, is_sandbox=False):
    if is_sandbox:
        message = f"[SANDBOX] Simuliram {side} order na {price} za {amount} ETH (zbog IS_SANDBOX=True)"
        logging.info(message)
        send_telegram_message(message)
        return {"simulated": True}
    if is_demo:
        message = f"[DEMO] Simuliram {side} order na {price} za {amount} ETH"
        logging.info(message)
        send_telegram_message(message)
        return {"simulated": True}
    try:
        order = exchange.create_limit_order(symbol, side, amount, price)
        message = f"Postavljen {side} order na {price} za {amount} ETH"
        logging.info(message)
        send_telegram_message(message)
        return order
    except Exception as e:
        message = f"Greška pri postavljanju ordera: {e}"
        logging.error(message)
        send_telegram_message(message)
        return None

def close_position(exchange, symbol, position, is_demo=False, is_sandbox=False):
    if is_sandbox:
        message = f"[SANDBOX] Simuliram zatvaranje pozicije: {position['side']} (zbog IS_SANDBOX=True)"
        logging.info(message)
        send_telegram_message(message)
        return
    if is_demo:
        message = f"[DEMO] Simuliram zatvaranje pozicije: {position['side']}"
        logging.info(message)
        send_telegram_message(message)
        return
    side = 'sell' if position['side'] == 'buy' else 'buy'
    amount = position['amount']
    price = exchange.fetch_ticker(symbol)['last']
    place_order(exchange, symbol, side, price, amount, is_demo, is_sandbox)

def monitor_position(exchange, symbol, position, is_demo=False, is_sandbox=False):
    if not position:
        return None
    current_price = exchange.fetch_ticker(symbol)['last']
    if current_price is None:
        logging.error("Ne mogu dohvatiti trenutnu cenu!")
        return None
    entry_price = position['entry_price']
    side = position['side']
    amount = position['amount']
    profit = (current_price - entry_price) * amount if side == 'buy' else (entry_price - current_price) * amount
    status = "Raketa 🚀" if profit > 0 else "Bomba 💣"
    message = (
        f"Pozicija: {side.upper()} | Ulaz: {entry_price} | Trenutna cena: {current_price} | "
        f"Profit/Gubitak: {profit:.2f} USDT | Status: {status}"
    )
    logging.info(message)
    send_telegram_message(message)
    return profit

def check_position_shift(exchange, symbol, current_position, trend, signals, is_demo=False, is_sandbox=False):
    if not current_position:
        return current_position
    current_side = current_position['side']
    if (current_side == 'buy' and trend == 'DOWN') or (current_side == 'sell' and trend == 'UP'):
        logging.info(f"Obrnut trend! Zatvaram poziciju: {current_side}")
        close_position(exchange, symbol, current_position, is_demo, is_sandbox)
        return None
    return current_position

def update_trailing_stop(exchange, symbol, position, is_demo=False, is_sandbox=False):
    if not position or not position.get('tp_sl_active', True):
        return position
    current_price = exchange.fetch_ticker(symbol)['last']
    if current_price is None:
        logging.error("Ne mogu dohvatiti trenutnu cenu za trailing stop!")
        return position
    entry_price = position['entry_price']
    side = position['side']
    trailing_distance = 2.0

    if side == 'buy' and current_price > entry_price + trailing_distance:
        new_sl = round(current_price - trailing_distance, PRICE_PRECISION)
        if new_sl > position['stop_loss']:
            position['stop_loss'] = new_sl
            logging.info(f"Ažuriran trailing SL: {new_sl}")
    elif side == 'sell' and current_price < entry_price - trailing_distance:
        new_sl = round(current_price + trailing_distance, PRICE_PRECISION)
        if new_sl < position['stop_loss']:
            position['stop_loss'] = new_sl
            logging.info(f"Ažuriran trailing SL: {new_sl}")

    if (side == 'buy' and current_price >= position['take_profit']) or \
       (side == 'sell' and current_price <= position['take_profit']):
        close_position(exchange, symbol, position, is_demo, is_sandbox)
        logging.info("Pozicija zatvorena zbog Take Profit!")
        return None
    if (side == 'buy' and current_price <= position['stop_loss']) or \
       (side == 'sell' and current_price >= position['stop_loss']):
        close_position(exchange, symbol, position, is_demo, is_sandbox)
        logging.info("Pozicija zatvorena zbog Stop Loss!")
        return None
    return position

def manual_control(exchange, symbol, current_position, command):
    if command == "disable_tp_sl":
        if current_position:
            logging.info("Gasim TP/SL za trenutnu poziciju")
            current_position['tp_sl_active'] = False
        return current_position
    elif command == "set_tp_sl":
        logging.info("Unos TP/SL nije moguć preko API-ja, koristi GUI za unos vrednosti.")
        return current_position
    elif command == "close_position":
        if current_position:
            close_position(exchange, symbol, current_position)
            logging.info("Pozicija zatvorena!")
            return None
        return current_position
    return current_position

def main():
    is_sandbox = os.getenv('IS_SANDBOX', 'False').lower() == 'true'
    is_demo = os.getenv('IS_DEMO', 'False').lower() == 'true'
    bot_running = os.getenv('BOT_RUNNING', 'False').lower() == 'true'
    fapi_endpoint = 'https://fapi.binance.com/fapi/v1' if not is_sandbox else 'https://testnet.binancefuture.com/fapi/v1'
    
    symbol = 'ETH/USDT:USDT-250926'
    logging.info("Povezujem se na Binance...")
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'enable_futures': True,
            'urls': {
                'fapi': fapi_endpoint
            }
        })
        exchange.options['defaultType'] = 'future'
        exchange.load_markets()
        
        if symbol not in exchange.markets or not exchange.markets[symbol].get('future', False):
            logging.error(f"Futures par {symbol} nije pronađen! Dostupni futures parovi:")
            for market in exchange.markets.values():
                if market.get('type') == 'future':
                    logging.info(f"Simbol: {market['symbol']}, Future: {market.get('future')}, ContractType: {market.get('contractType', 'N/A')}")
            return
        
        logging.info(f"Simbol: {symbol}, Endpoint: {fapi_endpoint}, DEMO mod: {is_demo}, Sandbox: {is_sandbox}, Bot Running: {bot_running}")
        exchange.set_leverage(LEVERAGE, symbol)
    except Exception as e:
        logging.error(f"Greška pri povezivanju na Binance: {e}")
        return
    
    current_position = None
    manual_mode = False

    while True:
        try:
            if not bot_running:
                logging.info("Bot je zaustavljen (BOT_RUNNING=False). Čekam promenu...")
                update_data_json(0, 0, 0, None, manual="off")
                time.sleep(60)
                bot_running = os.getenv('BOT_RUNNING', 'False').lower() == 'true'
                continue

            # Dohvati balans
            balance_info = exchange.fetch_balance()
            btc_balance = balance_info.get('BTC', {}).get('free', 0)
            unimmr = 0
            if not is_demo and not is_sandbox:
                try:
                    positions = exchange.fetch_positions(symbols=[symbol])
                    unimmr = sum(pos['unrealizedPnl'] for pos in positions if pos['symbol'] == symbol)
                except Exception as e:
                    logging.error(f"Greška pri dohvatanju unrealized MMR: {e}")

            ticker = exchange.fetch_ticker(symbol)
            logging.info(f"Ticker podaci: {ticker}")
            if not isinstance(ticker, dict) or 'last' not in ticker:
                logging.error(f"Ne mogu dohvatiti ticker za {symbol}: {ticker}")
                update_data_json(0, 0, 0, None, btc_balance, unimmr, manual="off")
                time.sleep(60)
                continue
            current_price = round(float(ticker['last']), PRICE_PRECISION)

            orderbook = get_orderbook(symbol)
            logging.info(f"Orderbook podaci: {orderbook}")
            if not isinstance(orderbook, dict) or 'bids' not in orderbook or 'asks' not in orderbook:
                logging.error(f"Ne mogu dohvatiti orderbook za {symbol}: {orderbook}")
                update_data_json(current_price, 0, 0, None, btc_balance, unimmr, manual="off")
                time.sleep(60)
                continue

            walls = filter_walls(orderbook, current_price)
            trend = detect_trend(orderbook, current_price)

            # Ako nema zidova, koristi podrazumevane vrednosti za support i resistance
            support = min([wall['price'] for wall in walls if wall['type'] == 'support'], default=current_price * 0.99) if walls else current_price * 0.99
            resistance = max([wall['price'] for wall in walls if wall['type'] == 'resistance'], default=current_price * 1.01) if walls else current_price * 1.01
            position = current_position['side'] if current_position else None

            data = read_data_json()
            manual_command = data.get('manual', 'off')
            if manual_command == 'on':
                manual_mode = True
            elif manual_command == 'off':
                manual_mode = False

            logging.info(f"Trenutna cena: {current_price} | Trend: {trend} | Manual Mode: {manual_mode}")
            update_data_json(current_price, support, resistance, position, btc_balance, unimmr, manual=manual_command)

            if current_position:
                monitor_position(exchange, symbol, current_position, is_demo, is_sandbox)

            if manual_mode:
                command = data.get('manual_command', '')
                if command:
                    current_position = manual_control(exchange, symbol, current_position, command)
                    update_data_json(current_price, support, resistance, position, btc_balance, unimmr, manual="on", manual_command="")
                continue

            current_position = check_position_shift(exchange, symbol, current_position, trend, [], is_demo, is_sandbox)

            if current_position:
                current_position = update_trailing_stop(exchange, symbol, current_position, is_demo, is_sandbox)

            if not current_position:
                signals = generate_signals(current_price, walls, trend)
                logging.info(f"Generisani signali: {signals}")
                for signal in signals:
                    amount = 0.06
                    order = place_order(exchange, symbol, signal['type'].lower(), signal['entry_price'], amount, is_demo, is_sandbox)
                    if order:
                        current_position = {
                            'side': signal['type'].lower(),
                            'entry_price': signal['entry_price'],
                            'amount': amount,
                            'take_profit': signal['take_profit'],
                            'stop_loss': signal['stop_loss'],
                            'tp_sl_active': True
                        }
                        logging.info(f"Otvorena pozicija: {signal['type']} na {signal['entry_price']}")
                        update_data_json(current_price, support, resistance, current_position['side'], btc_balance, unimmr, manual=manual_command)
                        break

            time.sleep(15)
        except Exception as e:
            logging.error(f"Greška u glavnoj petlji: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()