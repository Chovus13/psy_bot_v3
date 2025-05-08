import ccxt
import sqlite3
import os
import json
import time
import datetime
import logging
from orderbook import OrderBook, detect_large_wall
from levels import get_nearest_levels
import config
import matplotlib.pyplot as plt
import numpy as np

# Postavi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        logger.info("Inicijalizujem TradingBot...")
        # Inicijalizacija SQLite baze
        if not os.path.exists('logs'):
            os.makedirs('logs')
        conn = sqlite3.connect('logs/trades.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS trades
                     (timestamp TEXT, price REAL, level REAL, side TEXT, confidence REAL, result REAL)''')
        conn.commit()
        conn.close()

        logger.info("Povezujem se na Binance...")
        try:
            is_sandbox = False
            fapi_endpoint = 'https://fapi.binance.com/fapi/v1' if not is_sandbox else 'https://testnet.binancefuture.com/fapi/v1'
            self.exchange = ccxt.binance({
                'apiKey': config.API_KEY,
                'secret': config.API_SECRET,
                'enableRateLimit': True,
                'urls': {
                    'fapi': fapi_endpoint
                }
            })
            self.exchange.options['defaultType'] = 'future'
            self.exchange.load_markets()
            self.symbol = config.SYMBOL
            logger.info(f"Simbol: {self.symbol}, Endpoint: {fapi_endpoint}")
            self.orderbook = OrderBook(self.exchange, self.symbol)
        except Exception as e:
            logger.error(f"Greška pri povezivanju na Binance: {e}")
            raise

        self.current_price = 0
        self.support = 0
        self.resistance = 0
        self.position = 'None'
        self.min_balance = 0.001
        self.is_live = False
        self.take_from_here = False
        self.trade_at_night = False
        self.leverage = 3
        self.advanced_mode = False
        self.trade_amount = 0.06
        self.is_running = False
        self.stop_loss = None
        self.take_profit = None
        self.position_amount = 0

    def check_balance(self):
        try:
            logger.info("Proveravam Futures balans...")
            balance = self.exchange.fetch_balance(params={'type': 'future'})
            btc_balance = balance['BTC']['free']
            logger.info(f"Trenutni Futures BTC balans: {btc_balance}")
            return btc_balance
        except Exception as e:
            logger.error(f"Greška pri proveri Futures balansa: {e}")
            return 0

    def check_unimmr(self):
        try:
            logger.info("Proveravam UniMMR...")
            account_info = self.exchange.fapiPrivateV2GetAccount()
            unimmr = float(account_info.get('uniMMR', '0'))
            logger.info(f"UniMMR: {unimmr}")
            return unimmr
        except Exception as e:
            logger.error(f"Greška pri očitavanju UniMMR-a: {e}")
            return 0

    def calculate_amount(self, percentage=10):
        balance = self.check_balance()
        notional = balance * percentage / 100
        amount = notional / self.current_price if self.current_price > 0 else 0
        logger.info(f"Izračunata količina: {amount}")
        return amount

    def place_order(self, side, amount):
        try:
            logger.info(f"Postavljam Futures porudžbinu: {side}, količina: {amount}")
            # Postavi leverage
            self.exchange.set_leverage(leverage=self.leverage, symbol=self.symbol)
            order = self.exchange.create_market_order(self.symbol, side, amount, params={'type': 'future'})
            logger.info(f"Futures porudžbina postavljena: {order}")
            level = self.support if side == 'buy' else self.resistance
            self.log_trade(self.current_price, level, side, confidence=0.8, result=None)
            return order
        except Exception as e:
            logger.error(f"Greška pri postavljanju Futures porudžbine: {e}")
            return None

    def log_trade(self, price, level, side, confidence, result=None):
        logger.info(f"Upisujem trejd u bazu: price={price}, level={level}, side={side}")
        conn = sqlite3.connect('logs/trades.db')
        c = conn.cursor()
        c.execute("INSERT INTO trades (timestamp, price, level, side, confidence, result) VALUES (datetime('now'), ?, ?, ?, ?, ?)",
                  (price, level, side, confidence, result))
        conn.commit()
        conn.close()

        # Upisujemo i u trading.log
        with open("/app/logs/trading.log", "a") as f:
            f.write(f"{datetime.datetime.now()}: Trade - Price: {price}, Level: {level}, Side: {side}, Confidence: {confidence}, Result: {result}\n")

    def set_sl_tp(self, stop_loss_percentage=5, take_profit_percentage=10):
        self.stop_loss = self.current_price * (1 - stop_loss_percentage / 100) if self.position == 'Long' else self.current_price * (1 + stop_loss_percentage / 100)
        self.take_profit = self.current_price * (1 + take_profit_percentage / 100) if self.position == 'Long' else self.current_price * (1 - take_profit_percentage / 100)
        logger.info(f"Stop Loss: {self.stop_loss}, Take Profit: {self.take_profit}")

    def check_sl_tp(self):
        if self.take_from_here:
            logger.info("Take From Here aktiviran, SL/TP isključen")
            return
        if self.position == 'Long':
            if self.current_price <= self.stop_loss:
                logger.info("Stop Loss aktiviran, zatvaram Long poziciju")
                self.place_order('sell', self.position_amount)
                self.position = 'None'
                self.position_amount = 0
                self.stop_loss = None
                self.take_profit = None
            elif self.current_price >= self.take_profit:
                logger.info("Take Profit aktiviran, zatvaram Long poziciju")
                self.place_order('sell', self.position_amount)
                self.position = 'None'
                self.position_amount = 0
                self.stop_loss = None
                self.take_profit = None
        elif self.position == 'Short':
            if self.current_price >= self.stop_loss:
                logger.info("Stop Loss aktiviran, zatvaram Short poziciju")
                self.place_order('buy', self.position_amount)
                self.position = 'None'
                self.position_amount = 0
                self.stop_loss = None
                self.take_profit = None
            elif self.current_price <= self.take_profit:
                logger.info("Take Profit aktiviran, zatvaram Short poziciju")
                self.place_order('buy', self.position_amount)
                self.position = 'None'
                self.position_amount = 0
                self.stop_loss = None
                self.take_profit = None

    def plot_orderbook(self):
        if not self.orderbook.bids or not self.orderbook.asks:
            logger.warning("Nema podataka za grafikon")
            return

        bid_prices = [bid[0] for bid in self.orderbook.bids]
        bid_volumes = [bid[1] for bid in self.orderbook.bids]
        ask_prices = [ask[0] for ask in self.orderbook.asks]
        ask_volumes = [ask[1] for ask in self.orderbook.asks]

        plt.figure(figsize=(10, 6))
        plt.step(bid_prices, np.cumsum(bid_volumes), label='Bids', color='green')
        plt.step(ask_prices, np.cumsum(ask_volumes), label='Asks', color='red')
        plt.axvline(x=self.current_price, color='blue', linestyle='--', label='Cena')
        plt.axvline(x=self.support, color='green', linestyle='--', label='Podrška')
        plt.axvline(x=self.resistance, color='red', linestyle='--', label='Otpor')
        plt.xlabel('Cena')
        plt.ylabel('Kumulativni volumen')
        plt.title('Knjiga naloga')
        plt.legend()
        plt.grid()
        plt.savefig('logs/orderbook.png')
        plt.close()
        logger.info("Grafikon sačuvan u logs/orderbook.png")

    def is_trading_allowed(self):
        if self.trade_at_night:
            logger.info("Trgovanje noću je uključeno, dozvoljavam trgovanje...")
            return True
        current_hour = datetime.datetime.utcnow().hour
        if 22 <= current_hour or current_hour < 7:  # 22:00 - 07:00 UTC
            logger.info("Trgovanje nije dozvoljeno između 22:00 i 07:00 UTC")
            return False
        logger.info("Trgovanje je dozvoljeno u trenutnom vremenskom periodu")
        return True

    def load_data_json(self):
        default_data = {
            "price": 0,
            "support": 0,
            "resistance": 0,
            "position": "None",
            "balance": 0,
            "unimmr": 0,
            "logs": [],
            "isLive": False,
            "takeFromHere": False,
            "tradeAtNight": False,
            "leverage": 3,
            "advancedMode": False,
            "tradeAmount": 0.06,
            "isRunning": False  # Bot je podrazumevano zaustavljen
        }
        data_path = "/app/data.json"
        if not os.path.exists(data_path) or os.path.getsize(data_path) == 0:
            logger.info("data.json ne postoji ili je prazan, kreiram novi fajl sa podrazumevanim vrednostima...")
            with open(data_path, "w") as f:
                json.dump(default_data, f, indent=2)
            return default_data
        try:
            with open(data_path, "r") as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Greška pri parsiranju data.json: {e}, vraćam podrazumevane vrednosti...")
            with open(data_path, "w") as f:
                json.dump(default_data, f, indent=2)
            return default_data

    def run(self):
        logger.info("Bot pokrenut")
        while True:
            try:
                # Učitaj data.json
                data = self.load_data_json()
                self.is_live = data.get("isLive", False)
                self.take_from_here = data.get("takeFromHere", False) if self.is_live else False
                self.trade_at_night = data.get("tradeAtNight", False)
                self.leverage = max(1, min(20, data.get("leverage", 3)))
                self.advanced_mode = data.get("advancedMode", False)
                self.trade_amount = max(0.01, min(1.0, data.get("tradeAmount", 0.06)))
                self.is_running = data.get("isRunning", False)

                if not self.is_running:
                    logger.info("Bot je zaustavljen. Čekam na START komandu...")
                    time.sleep(5)
                    continue

                # Postavi Futures endpoint u zavisnosti od moda
                fapi_endpoint = 'https://fapi.binance.com/fapi/v1' if self.is_live else 'https://testnet.binancefuture.com/fapi/v1'
                self.exchange.urls['fapi'] = fapi_endpoint
                logger.info(f"Ažuriran Futures endpoint: {fapi_endpoint}")

                # Ažuriraj orderbook i nivoe
                logger.info("Ažuriram orderbook...")
                self.orderbook.update()
                self.current_price = self.orderbook.get_mid_price()
                logger.info(f"Trenutna cena: {self.current_price}")
                self.support, self.resistance = get_nearest_levels(self.current_price, self.advanced_mode)
                logger.info(f"Podrška: {self.support}, Otpor: {self.resistance}")

                # Provera prisustva velikih zidova
                orderbook_data = {'bids': self.orderbook.bids, 'asks': self.orderbook.asks}
                has_support_wall, support_wall_price, support_wall_volume = detect_large_wall(orderbook_data,
                                                                                              self.support, 'buy',
                                                                                              threshold=config.WALL_THRESHOLD_BTC,
                                                                                              proximity_pct=0.01)
                has_resistance_wall, resistance_wall_price, resistance_wall_volume = detect_large_wall(orderbook_data,
                                                                                                       self.resistance,
                                                                                                       'sell',
                                                                                                       threshold=config.WALL_THRESHOLD_BTC,
                                                                                                       proximity_pct=0.01)
                logger.info(
                    f"Zid na podršci: {has_support_wall} (cena: {support_wall_price}, volumen: {support_wall_volume} ETH), Zid na otporu: {has_resistance_wall} (cena: {resistance_wall_price}, volumen: {resistance_wall_volume} ETH)")
                with open("/app/logs/trading.log", "a") as f:
                    f.write(
                        f"{datetime.datetime.now()}: Zid na podršci: {has_support_wall} (cena: {support_wall_price}, volumen: {support_wall_volume} ETH), Zid na otporu: {has_resistance_wall} (cena: {resistance_wall_price}, volumen: {resistance_wall_volume} ETH)\n")

                # Analiza WALL-ova za određivanje pravca tržišta (za poboljšanu verziju)
                market_direction = 'neutral'
                if self.advanced_mode:
                    total_bids_volume = sum(bid[1] for bid in orderbook_data['bids'] if abs(
                        bid[0] - self.current_price) <= self.current_price * config.WALL_PROXIMITY_PCT)
                    total_asks_volume = sum(ask[1] for ask in orderbook_data['asks'] if abs(
                        ask[0] - self.current_price) <= self.current_price * config.WALL_PROXIMITY_PCT)
                    if total_bids_volume > total_asks_volume * 1.5:
                        market_direction = 'bullish'
                        logger.info("Tržište je bullish (više kupaca u orderbook-u)")
                    elif total_asks_volume > total_bids_volume * 1.5:
                        market_direction = 'bearish'
                        logger.info("Tržište je bearish (više prodavaca u orderbook-u)")

                # Očitaj balans i UniMMR
                balance = self.check_balance()
                unimmr = self.check_unimmr()

                # Provera trenutne pozicije
                if self.position == 'Long' and self.current_price >= self.resistance:
                    logger.info("Cena iznad otpora, zatvaram Long poziciju")
                    self.place_order('sell', self.position_amount)
                    self.position = 'None'
                    self.position_amount = 0
                    self.stop_loss = None
                    self.take_profit = None
                elif self.position == 'Short' and self.current_price <= self.support:
                    logger.info("Cena ispod podrške, zatvaram Short poziciju")
                    self.place_order('buy', self.position_amount)
                    self.position = 'None'
                    self.position_amount = 0
                    self.stop_loss = None
                    self.take_profit = None

                # Postavi SL/TP ako postoji pozicija
                if self.position != 'None' and (
                        self.stop_loss is None or self.take_profit is None) and not self.take_from_here:
                    self.set_sl_tp()

                # Proveri SL/TP
                if self.position != 'None':
                    self.check_sl_tp()

                # Logika za otvaranje pozicija
                if self.is_trading_allowed():
                    tolerance = self.current_price * 0.0025  #MK Povećavamo toleranciju na 0.25%   (bilo 0.001 za tight,  a za brz ulaz 0.005)
                    if balance >= self.min_balance:
                        amount = self.trade_amount
                        logger.info(f"Količina za trgovanje: {amount} ETH")

                        if self.advanced_mode and market_direction != 'neutral':
                            if market_direction == 'bullish':
                                if self.current_price > self.resistance - tolerance and self.position == 'None':
                                    logger.info("Poboljšana verzija: Tržište bullish, otvaram LONG na otporu")
                                    self.place_order('buy', amount)
                                    self.position = 'Long'
                                    self.position_amount = amount
                                    if not self.take_from_here:
                                        self.set_sl_tp()
                            elif market_direction == 'bearish':
                                if self.current_price < self.support + tolerance and self.position == 'None':
                                    logger.info("Poboljšana verzija: Tržište bearish, otvaram SHORT na podršci")
                                    self.place_order('sell', amount)
                                    self.position = 'Short'
                                    self.position_amount = amount
                                    if not self.take_from_here:
                                        self.set_sl_tp()
                        else:
                            if self.current_price < self.support + tolerance and self.position == 'None' and has_support_wall:
                                logger.info(
                                    "Cena ispod podrške (sa tolerancijom) i detektovan zid, otvaram Long poziciju")
                                self.place_order('buy', amount)
                                self.position = 'Long'
                                self.position_amount = amount
                                if not self.take_from_here:
                                    self.set_sl_tp()
                            elif self.current_price > self.resistance - tolerance and self.position == 'None' and has_resistance_wall:
                                logger.info(
                                    "Cena iznad otpora (sa tolerancijom) i detektovan zid, otvaram Short poziciju")
                                self.place_order('sell', amount)
                                self.position = 'Short'
                                self.position_amount = amount
                                if not self.take_from_here:
                                    self.set_sl_tp()

                # Kreiraj grafikon
                self.plot_orderbook()

                # Ažuriraj data.json za Web interfejs
                logs = []
                if os.path.exists("/app/logs/trading.log"):
                    with open("/app/logs/trading.log", "r") as f:
                        logs = f.readlines()[-5:]

                data = {
                    "price": self.current_price,
                    "support": self.support,
                    "resistance": self.resistance,
                    "position": self.position,
                    "balance": balance,
                    "unimmr": unimmr if unimmr is not None else 0,
                    "logs": logs,
                    "isLive": self.is_live,
                    "takeFromHere": self.take_from_here,
                    "tradeAtNight": self.trade_at_night,
                    "leverage": self.leverage,
                    "advancedMode": self.advanced_mode,
                    "tradeAmount": self.trade_amount,
                    "isRunning": self.is_running
                }
                with open("/app/data.json", "w") as f:
                    json.dump(data, f, indent=2)

                time.sleep(10)
            except Exception as e:
                logger.error(f"Greška u glavnoj petlji: {e}")
                time.sleep(10)

if __name__ == "__main__":
    logger.info("Pokrećem TradingBot...")
    bot = TradingBot()
    bot.run()