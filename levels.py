import logging
from config import TARGET_DIGITS, SPECIAL_DIGITS, PROFIT_TARGET, MIN_WALL_VOLUME, HILL_WALL_VOLUME, MOUNTAIN_WALL_VOLUME, EPIC_WALL_VOLUME

logging.basicConfig(level=logging.INFO)

def classify_wall_volume(volume):
    if volume >= EPIC_WALL_VOLUME:
        return "Planina"
    elif volume >= MOUNTAIN_WALL_VOLUME:
        return "Brdo"
    elif volume >= HILL_WALL_VOLUME:
        return "Brdašce"
    return "Zid"

def generate_signals(current_price, walls, trend):
    signals = []
    support_walls = sorted(walls['support'], key=lambda x: x[1], reverse=True)  # Sortiraj po volumenu
    resistance_walls = sorted(walls['resistance'], key=lambda x: x[1], reverse=True)

    for price, volume in support_walls:
        last_digit = int(str(price)[-1])
        wall_type = classify_wall_volume(volume)
        if last_digit in TARGET_DIGITS:  # 2, 3 za LONG
            signals.append({
                'type': 'LONG',
                'entry_price': price,
                'stop_loss': round(price - 0.00010, 5),
                'take_profit': round(price + PROFIT_TARGET, 5),
                'wall_type': wall_type,
                'volume': volume
            })
        elif last_digit == 1 and trend == 'DOWN':  # Rokada: SHORT na 9
            signals.append({
                'type': 'SHORT',
                'entry_price': round(price - 0.00002, 5),  # Ciljaj 9 (npr. 0.01999)
                'stop_loss': round(price + 0.00010, 5),
                'take_profit': round(price - PROFIT_TARGET - 0.00002, 5),
                'wall_type': wall_type,
                'volume': volume
            })

    for price, volume in resistance_walls:
        last_digit = int(str(price)[-1])
        wall_type = classify_wall_volume(volume)
        if last_digit in TARGET_DIGITS:  # 7, 8 za SHORT
            signals.append({
                'type': 'SHORT',
                'entry_price': price,
                'stop_loss': round(price + 0.00010, 5),
                'take_profit': round(price - PROFIT_TARGET, 5),
                'wall_type': wall_type,
                'volume': volume
            })
        elif last_digit == 9 and trend == 'UP':  # Rokada: LONG na 1
            signals.append({
                'type': 'LONG',
                'entry_price': round(price + 0.00002, 5),  # Ciljaj 1 (npr. 0.02011)
                'stop_loss': round(price - 0.00010, 5),
                'take_profit': round(price + PROFIT_TARGET + 0.00002, 5),
                'wall_type': wall_type,
                'volume': volume
            })

    for signal in signals:
        logging.info(f"Signal: {signal['type']} na {signal['entry_price']}, zid: {signal['wall_type']} ({signal['volume']} ETH)")
    return signals