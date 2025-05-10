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

def generate_signals(current_price, walls, trend, rokada_status="off"):
    signals = []
    support_walls = sorted(walls['support'], key=lambda x: x[1], reverse=True)
    resistance_walls = sorted(walls['resistance'], key=lambda x: x[1], reverse=True)

    for price, volume in support_walls:
        last_digit = int(str(round(price, 5))[-1])
        wall_type = classify_wall_volume(volume)
        if last_digit in TARGET_DIGITS:
            if last_digit in [2, 3]:
                signals.append({
                    'type': 'LONG',
                    'entry_price': price,
                    'stop_loss': round(price - 0.00005, 5),  # 5 pipova
                    'take_profit': round(price + 0.00010, 5),  # 2:1
                    'wall_type': wall_type,
                    'volume': volume
                })
        elif rokada_status == "on" and last_digit in SPECIAL_DIGITS and trend == 'DOWN':
            if last_digit == 1:
                signals.append({
                    'type': 'SHORT',
                    'entry_price': round(price - 0.00002, 5),
                    'stop_loss': round(price + 0.00005, 5),  # 5 pipova
                    'take_profit': round(price - 0.00010, 5),  # 2:1
                    'wall_type': wall_type,
                    'volume': volume
                })

    for price, volume in resistance_walls:
        last_digit = int(str(round(price, 5))[-1])
        wall_type = classify_wall_volume(volume)
        if last_digit in TARGET_DIGITS:
            if last_digit in [7, 8]:
                signals.append({
                    'type': 'SHORT',
                    'entry_price': price,
                    'stop_loss': round(price + 0.00005, 5),  # 5 pipova
                    'take_profit': round(price - 0.00010, 5),  # 2:1
                    'wall_type': wall_type,
                    'volume': volume
                })
        elif rokada_status == "on" and last_digit in SPECIAL_DIGITS and trend == 'UP':
            if last_digit == 9:
                signals.append({
                    'type': 'LONG',
                    'entry_price': round(price + 0.00002, 5),
                    'stop_loss': round(price - 0.00005, 5),  # 5 pipova
                    'take_profit': round(price + 0.00010, 5),  # 2:1
                    'wall_type': wall_type,
                    'volume': volume
                })

    for signal in signals:
        logging.info(f"Signal: {signal['type']} na {signal['entry_price']}, zid: {signal['wall_type']} ({signal['volume']} ETH)")
    return signals