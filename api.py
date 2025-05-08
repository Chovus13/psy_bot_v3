from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
import os

app = FastAPI()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>PsyBot GUI</title>
        <script src="https://unpkg.com/react@17/umd/react.development.js"></script>
        <script src="https://unpkg.com/react-dom@17/umd/react-dom.development.js"></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background-color: #f0f0f0; transition: background-color 0.3s, color 0.3s; }
            body.dark-mode { background-color: #333; color: #fff; }
            h1 { color: #333; }
            h1.dark-mode { color: #fff; }
            p { font-size: 16px; margin: 5px 0; }
            ul { list-style-type: none; padding: 0; }
            li { padding: 5px 0; background-color: #fff; margin: 2px 0; border-radius: 3px; padding-left: 10px; }
            li.dark-mode { background-color: #555; }
            .control-container { margin: 20px 0; }
            button { padding: 10px 20px; margin: 5px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            button.dark-mode { background-color: #555; color: #fff; }
            button.dark-mode:hover { background-color: #777; }
            .chart-container { margin-top: 20px; text-align: center; }
            .chart { max-width: 100%; height: auto; }
            .levels { margin-top: 10px; }
            .level-bar { height: 10px; border-radius: 3px; margin: 5px 0; }
            .support { background-color: green; }
            .resistance { background-color: red; }
            .leverage-input, .trade-amount-input { padding: 8px; margin: 5px; border-radius: 3px; border: 1px solid #ccc; }
            .trade-indicator { display: inline-block; margin-left: 10px; font-weight: bold; color: green; }
            .trade-indicator.blink { animation: blink 1s infinite; }
            @keyframes blink {
                50% { opacity: 0; }
            }
        </style>
    </head>
    <body>
        <div id="root"></div>
        <script type="text/babel">
            const { useState, useEffect } = React;

            function App() {
                const [data, setData] = useState({
                    price: 0,
                    support: 0,
                    resistance: 0,
                    position: 'None',
                    balance: 0,
                    unimmr: 0,
                    logs: [],
                    isLive: false,
                    takeFromHere: false,
                    tradeAtNight: false,
                    leverage: 3,
                    advancedMode: false,
                    tradeAmount: 0.06,
                    isRunning: false
                });
                const [darkMode, setDarkMode] = useState(false);
                const [ws, setWs] = useState(null);
                const [chartUrl, setChartUrl] = useState('/logs/orderbook.png?t=' + new Date().getTime());

                useEffect(() => {
                    console.log("Pokušaj povezivanja na WebSocket...");
                    const wsUrl = window.location.hostname === 'localhost' ? 'ws://localhost:8000/ws' : `ws://${window.location.hostname}:8000/ws`;
                    console.log("WebSocket URL:", wsUrl);
                    const websocket = new WebSocket(wsUrl);
                    setWs(websocket);

                    websocket.onopen = () => {
                        console.log('WebSocket povezan');
                        websocket.send(JSON.stringify({
                            isLive: data.isLive,
                            takeFromHere: data.takeFromHere,
                            tradeAtNight: data.tradeAtNight,
                            leverage: data.leverage,
                            advancedMode: data.advancedMode,
                            tradeAmount: data.tradeAmount,
                            isRunning: data.isRunning
                        }));
                    };
                    websocket.onmessage = (event) => {
                        console.log('Podaci primljeni:', event.data);
                        const newData = JSON.parse(event.data);
                        setData(prevData => ({ ...prevData, ...newData }));
                        setChartUrl('/logs/orderbook.png?t=' + new Date().getTime());
                    };
                    websocket.onerror = (error) => {
                        console.error('WebSocket greška:', error);
                    };
                    websocket.onclose = () => {
                        console.log('WebSocket zatvoren');
                    };
                    return () => websocket.close();
                }, []);

                const toggleLiveMode = () => {
                    const newIsLive = !data.isLive;
                    setData(prevData => ({ ...prevData, isLive: newIsLive, takeFromHere: newIsLive ? prevData.takeFromHere : false }));
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ isLive: newIsLive }));
                    }
                };

                const toggleTakeFromHere = () => {
                    const newTakeFromHere = !data.takeFromHere;
                    setData(prevData => ({ ...prevData, takeFromHere: newTakeFromHere }));
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ takeFromHere: newTakeFromHere }));
                    }
                };

                const toggleTradeAtNight = () => {
                    const newTradeAtNight = !data.tradeAtNight;
                    setData(prevData => ({ ...prevData, tradeAtNight: newTradeAtNight }));
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ tradeAtNight: newTradeAtNight }));
                    }
                };

                const toggleAdvancedMode = () => {
                    const newAdvancedMode = !data.advancedMode;
                    setData(prevData => ({ ...prevData, advancedMode: newAdvancedMode }));
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ advancedMode: newAdvancedMode }));
                    }
                };

                const toggleBotRunning = () => {
                    const newIsRunning = !data.isRunning;
                    setData(prevData => ({ ...prevData, isRunning: newIsRunning }));
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ isRunning: newIsRunning }));
                    }
                };

                const handleLeverageChange = (event) => {
                    const newLeverage = parseInt(event.target.value);
                    if (newLeverage >= 1 && newLeverage <= 20) {
                        setData(prevData => ({ ...prevData, leverage: newLeverage }));
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ leverage: newLeverage }));
                        }
                    }
                };

                const handleTradeAmountChange = (event) => {
                    const newTradeAmount = parseFloat(event.target.value);
                    if (newTradeAmount >= 0.01 && newTradeAmount <= 1.0) {
                        setData(prevData => ({ ...prevData, tradeAmount: newTradeAmount }));
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ tradeAmount: newTradeAmount }));
                        }
                    }
                };

                const toggleDarkMode = () => {
                    setDarkMode(!darkMode);
                    document.body.classList.toggle('dark-mode');
                };

                return (
                    <div>
                        <h1 className={darkMode ? 'dark-mode' : ''}>PsyBot GUI</h1>
                        <div className="control-container">
                            <button onClick={toggleLiveMode}>
                                {data.isLive ? 'Prebaci na DEMO' : 'Prebaci na LIVE'}
                            </button>
                            {data.isLive && (
                                <button onClick={toggleTakeFromHere}>
                                    {data.takeFromHere ? 'Isključi Take From Here' : 'Uključi Take From Here'}
                                </button>
                            )}
                            <button onClick={toggleTradeAtNight}>
                                {data.tradeAtNight ? 'Isključi Trgovanje Noću' : 'Uključi Trgovanje Noću'}
                            </button>
                            <button onClick={toggleAdvancedMode}>
                                {data.advancedMode ? 'Isključi Poboljšanu Verziju' : 'Uključi Poboljšanu Verziju'}
                            </button>
                            <button onClick={toggleBotRunning}>
                                {data.isRunning ? 'STOP Bot' : 'START Bot'}
                            </button>
                            <button onClick={toggleDarkMode}>
                                {darkMode ? 'Isključi Noćni Mod' : 'Uključi Noćni Mod'}
                            </button>
                            <div>
                                <label>Leverage (1-20): </label>
                                <input
                                    type="number"
                                    className="leverage-input"
                                    value={data.leverage}
                                    min="1"
                                    max="20"
                                    onChange={handleLeverageChange}
                                />
                            </div>
                            <div>
                                <label>Količina za trgovanje (0.01-1.0 ETH): </label>
                                <input
                                    type="number"
                                    className="trade-amount-input"
                                    value={data.tradeAmount}
                                    min="0.01"
                                    max="1.0"
                                    step="0.01"
                                    onChange={handleTradeAmountChange}
                                />
                            </div>
                        </div>
                        <p>
                            <strong>Trenutna pozicija:</strong> {data.position}
                            {data.position !== 'None' && (
                                <span className="trade-indicator blink">⚡ Trejd u toku!</span>
                            )}
                        </p>
                        <p><strong>Trenutna cena:</strong> {data.price.toFixed(5)}</p>
                        <div className="levels">
                            <p><strong>Podrška:</strong> {data.support.toFixed(5)}</p>
                            <div className="level-bar support" style={{ width: `${(data.support / data.price * 100)}%` }}></div>
                            <p><strong>Otpor:</strong> {data.resistance.toFixed(5)}</p>
                            <div className="level-bar resistance" style={{ width: `${(data.resistance / data.price * 100)}%` }}></div>
                        </div>
                        <p><strong>Balans (BTC):</strong> {data.balance.toFixed(8)}</p>
                        <p><strong>UniMMR:</strong> {data.unimmr.toFixed(4)}</p>
                        <div className="chart-container">
                            <h3>Knjiga naloga</h3>
                            <img src={chartUrl} alt="Orderbook Chart" className="chart" />
                        </div>
                        <h3>Logovi:</h3>
                        <ul>
                            {data.logs.map((log, index) => (
                                <li key={index} className={darkMode ? 'dark-mode' : ''}>{log}</li>
                            ))}
                        </ul>
                    </div>
                );
            }

            ReactDOM.render(<App />, document.getElementById('root'));
        </script>
    </body>
</html>
"""

@app.get("/")
async def get():
    logging.info("GET / zahtev primljen, vraćam HTML")
    return HTMLResponse(html)

@app.get("/logs/orderbook.png")
async def get_orderbook_chart():
    chart_path = "/app/logs/orderbook.png"
    if os.path.exists(chart_path):
        return FileResponse(chart_path, media_type="image/png")
    else:
        return {"error": "Chart not found"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logging.info("WebSocket konekcija uspostavljena")
    await websocket.accept()
    last_data = None
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
        "isRunning": False
    }
    is_live = False
    take_from_here = False
    trade_at_night = False
    leverage = 3
    advanced_mode = False
    trade_amount = 0.06
    is_running = False

    try:
        while True:
            # Proveri poruke od klijenta
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                client_data = json.loads(message)
                if "isLive" in client_data:
                    is_live = client_data["isLive"]
                    logging.info(f"Mod: {'LIVE' if is_live else 'DEMO'}")
                if "takeFromHere" in client_data:
                    take_from_here = client_data["takeFromHere"]
                    logging.info(f"Take From Here: {'uključeno' if take_from_here else 'isključeno'}")
                if "tradeAtNight" in client_data:
                    trade_at_night = client_data["tradeAtNight"]
                    logging.info(f"Trgovanje noću: {'uključeno' if trade_at_night else 'isključeno'}")
                if "leverage" in client_data:
                    leverage = max(1, min(20, client_data["leverage"]))
                    logging.info(f"Leverage podešen na: {leverage}")
                if "advancedMode" in client_data:
                    advanced_mode = client_data["advancedMode"]
                    logging.info(f"Poboljšana verzija: {'uključena' if advanced_mode else 'isključena'}")
                if "tradeAmount" in client_data:
                    trade_amount = max(0.01, min(1.0, client_data["tradeAmount"]))
                    logging.info(f"Količina za trgovanje podešena na: {trade_amount} ETH")
                if "isRunning" in client_data:
                    is_running = client_data["isRunning"]
                    logging.info(f"Bot status: {'pokrenut' if is_running else 'zaustavljen'}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logging.error(f"Greška pri prijemu poruke: {e}")
                break

            # Provera /app/data.json
            data_path = "/app/data.json"
            if not os.path.exists(data_path) or os.path.getsize(data_path) == 0:
                logging.info("data.json ne postoji ili je prazan, kreiram novi fajl...")
                with open(data_path, "w") as f:
                    json.dump(default_data, f, indent=2)
                data = default_data
            else:
                try:
                    with open(data_path, "r") as f:
                        data = json.load(f)
                except json.JSONDecodeError as e:
                    logging.error(f"Greška pri parsiranju /app/data.json: {e}")
                    data = default_data
                    with open(data_path, "w") as f:
                        json.dump(data, f, indent=2)

            # Ažuriraj podatke
            data["isLive"] = is_live
            data["takeFromHere"] = take_from_here if is_live else False
            data["tradeAtNight"] = trade_at_night
            data["leverage"] = leverage
            data["advancedMode"] = advanced_mode
            data["tradeAmount"] = trade_amount
            data["isRunning"] = is_running

            # Ažuriraj data.json
            with open(data_path, "w") as f:
                json.dump(data, f, indent=2)

            if data != last_data:
                logging.info(f"WebSocket šalje podatke: {data}")
                try:
                    await websocket.send_text(json.dumps(data))
                    last_data = data
                except Exception as e:
                    logging.error(f"Greška pri slanju poruke preko WebSocket-a: {e}")
                    break

            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Greška u WebSocket-u: {e}")
    finally:
        logging.info("Zatvaram WebSocket konekciju")
        try:
            await websocket.close()
        except Exception as e:
            logging.error(f"Greška pri zatvaranju WebSocket-a: {e}")