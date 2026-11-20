# Futures AI Scanner — MVP

Signals-only, no trading API keys, no real orders. Educational / research prototype.

## Requirements
Python 3.10+ and internet access to Binance Futures public API.

## Start backend (Windows PowerShell)
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```
If PowerShell blocks activation, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` then `.venv\Scripts\python.exe -m uvicorn main:app --port 8000`.

## Start frontend
Open `frontend/index.html` in your browser. Click "فحص السوق".

## API
- http://127.0.0.1:8000/docs
- /api/health
- /api/symbols
- /api/tickers
- /api/klines/BTCUSDT?interval=5m&limit=200
- /api/opportunities?limit=10

## Important limitations
- Scanner processes the full *liquid* active USDT perpetual universe by default (24h quote volume >= 10m USDT). This is a tunable liquidity filter, not a fixed top-N restriction.
- 3 timeframes and EMA/RSI/MACD/ATR/volume are calculated on closed candles. This is a heuristic, not AI predictive modeling.
- Signals are indicative candidates, NOT validated executable trade recommendations. No spread, fees, slippage, funding or order-book checks; gross R:R is theoretical.
- No persistent history, backtesting, alerts, or auto refresh yet.
- Scanning all symbols can be slow and may hit Binance rate limits. For development use `/api/opportunities?universe_limit=20`.
- Some networks/regions may restrict access to Binance endpoints.


## Online deployment
See [DEPLOY.md](DEPLOY.md). The FastAPI service now serves the frontend at `/`, so the app works under a single HTTPS origin.
