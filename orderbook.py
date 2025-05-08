import ccxt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import logging

# Postavi logging
logger = logging.getLogger(__name__)

class OrderBook:
    def __init__(self, exchange, symbol):
        self.exchange = exchange
        self.symbol = symbol
        self.bids = []
        self.asks = []
        self.mid_price = 0

    def update(self):
        try:
            logger.info("Učitavam orderbook...")
            orderbook = self.exchange.fetch_order_book(self.symbol, limit=100)  #MK smanjio sa 1000 na 100
            self.bids = orderbook['bids']
            self.asks = orderbook['asks']
            self.mid_price = self.get_mid_price()
            logger.info("Orderbook uspešno ažuriran.")
        except Exception as e:
            logger.error(f"Greška pri ažuriranju orderbook-a: {e}")
            self.bids = []
            self.asks = []
            self.mid_price = 0

    def get_mid_price(self):
        if self.bids and self.asks:
            highest_bid = self.bids[0][0]
            lowest_ask = self.asks[0][0]
            return (highest_bid + lowest_ask) / 2
        return 0

    def plot(self, support=None, resistance=None):
        try:
            # Pripremi podatke za grafikon
            bid_prices = [x[0] for x in self.bids]
            bid_volumes = [x[1] for x in self.bids]
            ask_prices = [x[0] for x in self.asks]
            ask_volumes = [x[1] for x in self.asks]

            # Kreiraj grafikon
            plt.figure(figsize=(10, 6))
            plt.bar(bid_prices, bid_volumes, color='green', alpha=0.5, label='Bids')
            plt.bar(ask_prices, ask_volumes, color='red', alpha=0.5, label='Asks')

            # Dodaj linije za podršku i otpor ako su prisutni
            if support is not None:
                plt.axvline(support, color='blue', linestyle='--', label=f'Podrška: {support}')
            if resistance is not None:
                plt.axvline(resistance, color='purple', linestyle='--', label=f'Otpor: {resistance}')

            # Dodaj trenutnu cenu
            if self.mid_price:
                plt.axvline(self.mid_price, color='black', linestyle='-', label=f'Cena: {self.mid_price}')

            plt.xlabel('Cena')
            plt.ylabel('Volumen (ETH)')
            plt.title('Knjiga naloga')
            plt.legend()
            plt.grid(True)

            # Sačuvaj grafikon
            plt.savefig('/app/logs/orderbook.png')
            plt.close()
            logger.info("Grafikon sačuvan u logs/orderbook.png")
        except Exception as e:
            logger.error(f"Greška pri kreiranju grafikona: {e}")

def detect_large_wall(orderbook_data, level, side, threshold=1, proximity_pct=0.005):      #MK bilo bez threhold (razmak), stavio 1, a proximity na 0.005 a bilo (0.01)
    """
    Detektuje velike zidove u orderbook-u unutar užeg opsega.
    Vraća tuple: (da li postoji zid, cena zida, ukupan volumen zida)
    """
    price_range = level * proximity_pct  # Smanjujemo opseg na ±1%
    total_volume = 0
    wall_price = None

    if side == 'buy':
        orders = orderbook_data['bids']
        for price, volume in orders:
            if abs(price - level) <= price_range:
                total_volume += volume
                if wall_price is None or volume > orders[orders.index([price, volume]) - 1][1]:
                    wall_price = price
    else:
        orders = orderbook_data['asks']
        for price, volume in orders:
            if abs(price - level) <= price_range:
                total_volume += volume
                if wall_price is None or volume > orders[orders.index([price, volume]) - 1][1]:
                    wall_price = price

    has_wall = total_volume >= threshold
    return has_wall, wall_price if wall_price is not None else level, total_volume