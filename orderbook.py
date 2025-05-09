import ccxt
import logging
import numpy as np
logging.basicConfig(level=logging.INFO)

def get_orderbook(symbol='ETH/BTC'):
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'enable_futures': True,
    })
    try:
        orderbook = exchange.fetch_order_book(symbol, limit=1000)
        return orderbook
    except Exception as e:
        logging.error(f"Greška pri dohvatanju orderbook-a: {e}")
        return {}

def filter_walls(orderbook, current_price, threshold=0.05):
    walls = []
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        logging.error("Orderbook nije ispravan, vraćam praznu listu zidova")
        return walls

    bids = np.array(orderbook['bids'])
    asks = np.array(orderbook['asks'])
    
    # Pronalaženje "rokade" - klastera gde su velike količine koncentrisane
    bid_volumes = bids[:, 1]
    ask_volumes = asks[:, 1]
    
    total_bid_volume = sum(bid_volumes)
    total_ask_volume = sum(ask_volumes)
    
    # Identifikacija klastera za podršku (bids)
    bid_clusters = []
    for i in range(len(bids) - 10):
        cluster_volume = sum(bid_volumes[i:i+10])
        if cluster_volume > threshold * total_bid_volume:
            avg_price = np.mean(bids[i:i+10, 0])
            walls.append({'type': 'support', 'price': float(avg_price), 'amount': float(cluster_volume)})
    
    # Identifikacija klastera za otpor (asks)
    ask_clusters = []
    for i in range(len(asks) - 10):
        cluster_volume = sum(ask_volumes[i:i+10])
        if cluster_volume > threshold * total_ask_volume:
            avg_price = np.mean(asks[i:i+10, 0])
            walls.append({'type': 'resistance', 'price': float(avg_price), 'amount': float(cluster_volume)})
    
    logging.info(f"Pronađeni zidovi: {walls}")
    return walls

def detect_trend(orderbook, current_price):
    buy_pressure = sum([amount for price, amount in orderbook['bids'] if price > current_price * 0.99])
    sell_pressure = sum([amount for price, amount in orderbook['asks'] if price < current_price * 1.01])
    if buy_pressure > sell_pressure * 1.5:
        return 'UP'
    elif sell_pressure > buy_pressure * 1.5:
        return 'DOWN'
    return 'NEUTRAL'