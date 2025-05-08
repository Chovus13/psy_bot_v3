import sqlite3
import os
import logging

def setup_logger(name, log_file):
    """Konfiguriše logger za pisanje u fajl."""
    if not os.path.exists(os.path.dirname(log_file)):
        os.makedirs(os.path.dirname(log_file))
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    return logger

def init_db():
    """Inicijalizuje SQLite bazu za logovanje trgovina."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    conn = sqlite3.connect('logs/trades.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (timestamp TEXT, price REAL, level REAL, side TEXT, confidence REAL, result REAL)''')
    conn.commit()
    conn.close()

def log_trade(price, level, side, confidence, result=None):
    """Loguje trgovinu u SQLite bazu."""
    conn = sqlite3.connect('logs/trades.db')
    c = conn.cursor()
    c.execute("INSERT INTO trades (timestamp, price, level, side, confidence, result) VALUES (datetime('now'), ?, ?, ?, ?, ?)",
              (price, level, side, confidence, result))
    conn.commit()
    conn.close()