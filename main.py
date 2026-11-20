import asyncio
import math
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.responses import FileResponse
from typing import Literal

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

BASE = 'https://fapi.binance.com'
cache = {}
client = None
sem = asyncio.Semaphore(5)

@asynccontextmanager
async def lifespan(app):
    global client
    client = httpx.AsyncClient(timeout=12, limits=httpx.Limits(max_connections=10))
    yield
    await client.aclose()

app = FastAPI(title='Futures AI Scanner', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173','http://127.0.0.1:5173'], allow_methods=['GET'], allow_headers=['*'])

async def get(path, params=None, ttl=10):
    key = (path, tuple(sorted((params or {}).items())))
    now = time.monotonic()
    if key in cache and now-cache[key][0] < ttl:
        return cache[key][1]
    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(BASE+path, params=params)
                if r.status_code in (418,429):
                    raise HTTPException(503, 'Binance rate limit; try later')
                r.raise_for_status()
                data = r.json()
                cache[key] = (time.monotonic(), data)
                return data
            except httpx.HTTPError:
                if attempt == 2:
                    raise HTTPException(503, 'Binance unavailable')
                await asyncio.sleep(0.5 * (2 ** attempt))

@app.get('/api/health')
async def health():
    return {'status':'ok','source':'Binance USDT-M Futures','mode':'signals-only'}

@app.get('/api/symbols')
async def symbols():
    info = await get('/fapi/v1/exchangeInfo', ttl=3600)
    return [s['symbol'] for s in info['symbols'] if s['status']=='TRADING' and s['contractType']=='PERPETUAL' and s['quoteAsset']=='USDT']

@app.get('/api/tickers')
async def tickers():
    allowed = set(await symbols())
    data = await get('/fapi/v1/ticker/24hr', ttl=30)
    return [{'symbol':t['symbol'],'lastPrice':t['lastPrice'],'quoteVolume':t['quoteVolume'],'priceChangePercent':t['priceChangePercent']} for t in data if t['symbol'] in allowed]

@app.get('/api/klines/{symbol}')
async def klines(symbol:str, interval:Literal['1m','5m','15m']='5m', limit:int=Query(200,ge=50,le=500)):
    symbol=symbol.upper()
    if symbol not in await symbols():
        raise HTTPException(400,'Unsupported symbol')
    return await get('/fapi/v1/klines',{'symbol':symbol,'interval':interval,'limit':limit},ttl=15)

def indicators(rows):
    # The final candle can still be forming; exclude it unconditionally.
    closed = rows[:-1]
    if len(closed)<100: return None
    df=pd.DataFrame(closed)
    close=df[4].astype(float)
    high=df[2].astype(float)
    low=df[3].astype(float)
    volume=df[5].astype(float)
    ema20=close.ewm(span=20,adjust=False).mean()
    ema50=close.ewm(span=50,adjust=False).mean()
    delta=close.diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+up/(down.replace(0,np.nan)))
    rsi=rsi.fillna(100)
    tr=pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False).mean()
    macd=close.ewm(span=12,adjust=False).mean()-close.ewm(span=26,adjust=False).mean()
    hist=macd-macd.ewm(span=9,adjust=False).mean()
    vol_ratio=float(volume.iloc[-1]/max(volume.iloc[-21:-1].mean(),1e-12))
    return {'price':float(close.iloc[-1]),'ema20':float(ema20.iloc[-1]),'ema50':float(ema50.iloc[-1]),'rsi':float(rsi.iloc[-1]),'atr':float(atr.iloc[-1]),'macdHist':float(hist.iloc[-1]),'volumeRatio':vol_ratio,'candleClose':int(closed[-1][6])}

async def analyze(symbol):
    try:
        candles=await asyncio.gather(*[get('/fapi/v1/klines',{'symbol':symbol,'interval':tf,'limit':130},ttl=45) for tf in ['1m','5m','15m']])
        a,b,c=[indicators(x) for x in candles]
        if not all([a,b,c]): return None
        up=c['price']>c['ema20']>c['ema50'] and b['price']>b['ema20']
        down=c['price']<c['ema20']<c['ema50'] and b['price']<b['ema20']
        side='LONG' if up else 'SHORT' if down else 'NO TRADE'
        if side=='NO TRADE':return None
        momentum=(b['macdHist']>0 and 48<=b['rsi']<=72) if side=='LONG' else (b['macdHist']<0 and 28<=b['rsi']<=52)
        entry=a['price']
        atr=b['atr']
        if not math.isfinite(atr) or atr<=0:return None
        stop=entry-1.5*atr if side=='LONG' else entry+1.5*atr
        tp=entry+3*atr if side=='LONG' else entry-3*atr
        score=25+ (20 if momentum else 0)+ (20 if b['volumeRatio']>=1.2 else 8) + (15 if ((a['macdHist']>0)==(side=='LONG')) else 0)+ (10 if 0.0008<=atr/entry<=0.03 else 0)+10
        if score<75 or not momentum or stop<=0 or tp<=0:return None
        return {'symbol':symbol,'side':side,'score':score,'entry':entry,'stop':stop,'takeProfit':tp,'rrGross':2.0,'time':a['candleClose'],'reason':'15m trend + 5m momentum + 1m timing','volumeRatio':round(b['volumeRatio'],2),'rsi':round(b['rsi'],1),'status':'candidate','disclaimer':'Indicative setup, not a verified executable signal. Fees, spread, funding and slippage not included.'}
    except (HTTPException,ValueError,KeyError,TypeError,IndexError):
        return None

@app.get('/api/opportunities')
async def opportunities(limit:int=Query(10,ge=1,le=30),min_quote_volume:float=Query(10000000,ge=0),universe_limit:int=Query(0,ge=0,le=500)):
    tick=await tickers()
    eligible=sorted((t for t in tick if float(t['quoteVolume'])>=min_quote_volume),key=lambda x:float(x['quoteVolume']),reverse=True)
    # universe_limit=0 scans every liquid USDT perpetual contract, in batches.
    if universe_limit: eligible=eligible[:universe_limit]
    results=[]
    for i in range(0,len(eligible),10):
        chunk=await asyncio.gather(*(analyze(t['symbol']) for t in eligible[i:i+10]))
        results.extend(x for x in chunk if x)
    results.sort(key=lambda x:(x['score'],x['volumeRatio']),reverse=True)
    return {'opportunities':results[:limit],'scanned':len(eligible),'matched':len(results),'timestamp':int(time.time()*1000),'note':'Candidate setups only. No backtested profitability or execution-cost validation.'}


# Serve the web interface from the same HTTPS origin as the API.
FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(FRONTEND_FILE)
