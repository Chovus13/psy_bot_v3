import logging
import numpy as np
from config import WALL_RANGE_SPREAD, MIN_WALL_VOLUME, PRICE_PRECISION, VOLUME_PRECISION

logging.basicConfig(level=logging.INFO)

def filter_walls(orderbook, current_price, threshold=0.01):
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        logging.error("Orderbook nije ispravan, vraćam prazan dictionary")
        return {'support': [], 'resistance': []}

    bids = np.array(orderbook['bids'])
    asks = np.array(orderbook['asks'])
    
    bid_volumes = bids[:, 1]
    ask_volumes = asks[:, 1]
    
    total_bid_volume = sum(bid_volumes)
    total_ask_volume = sum(ask_volumes)
    
    support_walls = []
    for i in range(len(bids) - 10):
        cluster_volumes = bid_volumes[i:i+10]
        cluster_prices = bids[i:i+10, 0]
        cluster_volume = sum(cluster_volumes)
        if max(cluster_prices) - min(cluster_prices) <= WALL_RANGE_SPREAD and cluster_volume >= MIN_WALL_VOLUME:
            if cluster_volume > threshold * total_bid_volume:
                avg_price = np.mean(cluster_prices)
                support_walls.append([round(float(avg_price), PRICE_PRECISION), round(float(cluster_volume), VOLUME_PRECISION)])
    
    resistance_walls = []
    for i in range(len(asks) - 10):
        cluster_volumes = ask_volumes[i:i+10]
        cluster_prices = asks[i:i+10, 0]
        cluster_volume = sum(cluster_volumes)
        if max(cluster_prices) - min(cluster_prices) <= WALL_RANGE_SPREAD and cluster_volume >= MIN_WALL_VOLUME:
            if cluster_volume > threshold * total_ask_volume:
                avg_price = np.mean(cluster_prices)
                resistance_walls.append([round(float(avg_price), PRICE_PRECISION), round(float(cluster_volume), VOLUME_PRECISION)])
    
    walls = {
        'support': support_walls,
        'resistance': resistance_walls
    }
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