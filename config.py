# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Postavke za zidove (može se čitati iz .env)
WALL_RANGE_SPREAD = float(os.getenv('WALL_RANGE_SPREAD', 0.0005))
MIN_WALL_VOLUME = float(os.getenv('MIN_WALL_VOLUME', 10.0))
HILL_WALL_VOLUME = float(os.getenv('HILL_WALL_VOLUME', 50.0))
MOUNTAIN_WALL_VOLUME = float(os.getenv('MOUNTAIN_WALL_VOLUME', 100.0))
EPIC_WALL_VOLUME = float(os.getenv('EPIC_WALL_VOLUME', 500.0))

# Preciznost
PRICE_PRECISION = int(os.getenv('PRICE_PRECISION', 5))
VOLUME_PRECISION = int(os.getenv('VOLUME_PRECISION', 2))

# Strategija
TARGET_DIGITS = [int(d) for d in os.getenv('TARGET_DIGITS', '2,3,7,8').split(',')]
SPECIAL_DIGITS = [int(d) for d in os.getenv('SPECIAL_DIGITS', '1,9').split(',')]
PROFIT_TARGET = float(os.getenv('PROFIT_TARGET', 0.00010))  # 2:1 u odnosu na stop-loss