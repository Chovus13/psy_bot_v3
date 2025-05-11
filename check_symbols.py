import asyncio
import ccxt.async_support as ccxt

async def check_markets():
    exchange = ccxt.binance({
        'apiKey': os.getenv('API_KEY'),  # Ako koristiš LIVE, ubaci ključeve u .env
        'secret': os.getenv('API_SECRET'),
        'enableRateLimit': True,
        'urls': {
            'api': {
                'fapi': 'https://fapi.binance.com'  # LIVE API
                #'fapi': 'https://testnet.binancefuture.com'  # Testnet ako želiš
            }
        }
    })

    #exchange.set_sandbox_mode(True)  # Iskomentariši za LIVE
    try:
        markets = await exchange.load_markets()
        futures_markets = [
            symbol for symbol, market in markets.items()
            if market['active'] and market['type'] in ['linear', 'inverse'] and 'USDT' in symbol
        ]
        print("Dostupni USDT futures simboli:", futures_markets)
    except Exception as e:
        print(f"Greška: {str(e)}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(check_markets())