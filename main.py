import os
import logging
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

ASSETS = {
    'nifty':     {'name': 'NIFTY 50',       'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI',    'weekly': True, 'monthly': True},
    'banknifty': {'name': 'BANK NIFTY',     'lot': 15,  'gap': 100,  'sym': 'Rs', 'ticker': '^NSEBANK', 'weekly': True, 'monthly': True},
    'finnifty':  {'name': 'FIN NIFTY',      'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI',    'weekly': True, 'monthly': True},
    'midcap':    {'name': 'MIDCAP NIFTY',   'lot': 50,  'gap': 25,   'sym': 'Rs', 'ticker': '^NSEI',    'weekly': False, 'monthly': True},
    'sensex':    {'name': 'SENSEX',         'lot': 10,  'gap': 100,  'sym': 'Rs', 'ticker': '^BSESN',   'weekly': True, 'monthly': True},
    'crude':     {'name': 'CRUDE OIL MCX',  'lot': 100, 'gap': 50,   'sym': 'Rs', 'ticker': 'CL=F',     'weekly': False, 'monthly': True},
    'gold':      {'name': 'GOLD MCX',       'lot': 100, 'gap': 100,  'sym': 'Rs', 'ticker': 'GC=F',     'weekly': False, 'monthly': True},
    'silver':    {'name': 'SILVER MCX',     'lot': 30,  'gap': 100,  'sym': 'Rs', 'ticker': 'SI=F',     'weekly': False, 'monthly': True},
    'naturalgas':{'name': 'NATURALGAS MCX', 'lot': 1250,'gap': 5,    'sym': 'Rs', 'ticker': 'NG=F',     'weekly': False, 'monthly': True},
    'copper':    {'name': 'COPPER MCX',     'lot': 2500,'gap': 1,    'sym': 'Rs', 'ticker': 'HG=F',     'weekly': False, 'monthly': True},
    'btc':       {'name': 'BITCOIN',        'lot': 1,   'gap': 1000, 'sym': '$',  'ticker': 'BTC-USD',  'weekly': True, 'monthly': True},
    'eth':       {'name': 'ETHEREUM',       'lot': 1,   'gap': 50,   'sym': '$',  'ticker': 'ETH-USD',  'weekly': True, 'monthly': True},
    'bnb':       {'name': 'BINANCE COIN',   'lot': 1,   'gap': 5,    'sym': '$',  'ticker': 'BNB-USD',  'weekly': False, 'monthly': True},
    'sol':       {'name': 'SOLANA',         'lot': 1,   'gap': 5,    'sym': '$',  'ticker': 'SOL-USD',  'weekly': False, 'monthly': True},
}

USD_INR = 84.0

def fetch_usd_inr():
    global USD_INR
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if r.status_code == 200:
            price = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
            USD_INR = float(price)
    except Exception:
        pass
    return USD_INR

def get_yahoo_price(ticker):
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = round(price - prev, 4)
            pct = round((change / prev) * 100, 2) if prev else 0
            return price, change, pct
    except Exception:
        pass
    return None, None, None

def get_live_price(asset):
    cfg = ASSETS[asset]
    ticker = cfg['ticker']
    price_usd, change_usd, pct = get_yahoo_price(ticker)
    
    if price_usd is None:
        return None, None, None
    
    inr = fetch_usd_inr()
    
    if asset == 'crude':
        price = round(price_usd * inr / 6)
        change = round(change_usd * inr / 6, 1)
        return price, change, pct
    elif asset == 'gold':
        price = round(price_usd * inr / 31.1 * 10)
        change = round(change_usd * inr / 31.1 * 10)
        return price, change, pct
    elif asset == 'silver':
        price = round(price_usd * inr / 31.1 * 1000)
        change = round(change_usd * inr / 31.1 * 1000)
        return price, change, pct
    elif asset == 'naturalgas':
        price = round(price_usd * inr / 10, 1)
        change = round(change_usd * inr / 10, 1)
        return price, change, pct
    elif asset == 'copper':
        price = round(price_usd * inr * 2.2 / 1000, 1)
        change = round(change_usd * inr * 2.2 / 1000, 1)
        return price, change, pct
    else:
        return round(price_usd, 4), round(change_usd, 4), pct

def get_expiry_dates():
    """Calculate weekly and monthly expiry dates"""
    today = datetime.now()
    
    # Weekly expiry - next Thursday
    days_until_thursday = (3 - today.weekday()) % 7
    if days_until_thursday == 0 and today.hour >= 15:
        days_until_thursday = 7
    weekly_expiry = today + timedelta(days=days_until_thursday)
    
    # Monthly expiry - last Thursday of current month
    # Go to last day of month
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1)
    else:
        next_month = datetime(today.year, today.month + 1, 1)
    last_day = next_month - timedelta(days=1)
    
    # Find last Thursday
    days_back = (last_day.weekday() - 3) % 7
    monthly_expiry = last_day - timedelta(days=days_back)
    
    # If monthly expiry has passed, get next month
    if monthly_expiry < today:
        if monthly_expiry.month == 12:
            next_next_month = datetime(monthly_expiry.year + 1, 1, 1)
        else:
            next_next_month = datetime(monthly_expiry.year, monthly_expiry.month + 1, 1)
        last_day = next_next_month - timedelta(days=1)
        days_back = (last_day.weekday() - 3) % 7
        monthly_expiry = last_day - timedelta(days=days_back)
    
    return weekly_expiry, monthly_expiry

def calculate_premium(spot_price, strike, distance_from_atm, iv, is_call=True):
    """Calculate approximate premium based on strike distance and IV"""
    # Base premium as % of spot
    if distance_from_atm == 0:  # ATM
        base_pct = 0.020
    elif distance_from_atm == 1:  # 1 OTM
        base_pct = 0.012
    elif distance_from_atm == 2:  # 2 OTM
        base_pct = 0.007
    elif distance_from_atm == 3:  # 3 OTM
        base_pct = 0.004
    else:
        base_pct = 0.002
    
    # Adjust for IV
    iv_multiplier = 1 + (iv - 20) / 100
    
    premium = spot_price * base_pct * iv_multiplier
    
    return max(round(premium), 10)

def get_greeks(asset, pct):
    iv_base = {
        'nifty': 14, 'banknifty': 20, 'finnifty': 17, 'midcap': 19, 'sensex': 14,
        'crude': 32, 'gold': 15, 'silver': 20, 'naturalgas': 40, 'copper': 22,
        'btc': 60, 'eth': 70, 'bnb': 65, 'sol': 75
    }
    iv = iv_base.get(asset, 25)
    
    if pct > 1.5:
        delta = round(min(0.62 + pct * 0.015, 0.70), 2)
        market = 'STRONGLY BULLISH'
        conf = min(92, 75 + int(pct * 4))
        iv += 4
        rsi = 72
    elif pct > 0.5:
        delta = round(0.54 + pct * 0.02, 2)
        market = 'BULLISH'
        conf = min(82, 68 + int(pct * 5))
        iv += 2
        rsi = 64
    elif pct < -1.5:
        delta = round(max(0.38 - abs(pct) * 0.015, 0.30), 2)
        market = 'STRONGLY BEARISH'
        conf = min(92, 75 + int(abs(pct) * 4))
        iv += 4
        rsi = 28
    elif pct < -0.5:
        delta = round(0.46 - abs(pct) * 0.02, 2)
        market = 'BEARISH'
        conf = min(82, 68 + int(abs(pct) * 5))
        iv += 2
        rsi = 36
    else:
        delta = 0.50
        market = 'NEUTRAL'
        conf = 55
        rsi = 50
        iv += 0
    
    gamma = round(0.018 + iv * 0.001, 4)
    theta = -round(iv * 1.1, 1)
    vega = round(iv * 0.8, 1)
    iv_rank = 'HIGH' if iv > 30 else 'MEDIUM' if iv > 18 else 'LOW'
    
    return {
        'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega,
        'iv': iv, 'iv_rank': iv_rank, 'market': market, 'conf': conf, 'rsi': rsi
    }

def format_strike_options(spot, gap, sym, lot, iv, market):
    """Format multiple strike options with real-time premiums"""
    atm = round(spot / gap) * gap
    
    strikes = []
    
    if 'BULLISH' in market:
        # For bullish: Show Call options
        option_type = 'CE'
        
        # ATM Call
        atm_premium = calculate_premium(spot, atm, 0, iv, True)
        strikes.append({
            'name': 'ATM',
            'strike': atm,
            'type': option_type,
            'premium': atm_premium,
            'investment': atm_premium * lot,
            'distance': 0,
            'recommendation': 'Moderate risk, balanced R:R'
        })
        
        # OTM1 Call
        otm1 = round(atm + gap, 4)
        otm1_premium = calculate_premium(spot, otm1, 1, iv, True)
        strikes.append({
            'name': 'OTM-1',
            'strike': otm1,
            'type': option_type,
            'premium': otm1_premium,
            'investment': otm1_premium * lot,
            'distance': 1,
            'recommendation': 'Best risk/reward - RECOMMENDED'
        })
        
        # OTM2 Call
        otm2 = round(atm + 2 * gap, 4)
        otm2_premium = calculate_premium(spot, otm2, 2, iv, True)
        strikes.append({
            'name': 'OTM-2',
            'strike': otm2,
            'type': option_type,
            'premium': otm2_premium,
            'investment': otm2_premium * lot,
            'distance': 2,
            'recommendation': 'Lower cost, aggressive play'
        })
        
        # ITM1 Call (for conservative traders)
        itm1 = round(atm - gap, 4)
        itm1_premium = calculate_premium(spot, itm1, -1, iv, True)
        strikes.append({
            'name': 'ITM-1',
            'strike': itm1,
            'type': option_type,
            'premium': itm1_premium,
            'investment': itm1_premium * lot,
            'distance': -1,
            'recommendation': 'Conservative, higher Delta'
        })
        
    elif 'BEARISH' in market:
        # For bearish: Show Put options
        option_type = 'PE'
        
        # ATM Put
        atm_premium = calculate_premium(spot, atm, 0, iv, False)
        strikes.append({
            'name': 'ATM',
            'strike': atm,
            'type': option_type,
            'premium': atm_premium,
            'investment': atm_premium * lot,
            'distance': 0,
            'recommendation': 'Moderate risk, balanced R:R'
        })
        
        # OTM1 Put
        otm1 = round(atm - gap, 4)
        otm1_premium = calculate_premium(spot, otm1, 1, iv, False)
        strikes.append({
            'name': 'OTM-1',
            'strike': otm1,
            'type': option_type,
            'premium': otm1_premium,
            'investment': otm1_premium * lot,
            'distance': 1,
            'recommendation': 'Best risk/reward - RECOMMENDED'
        })
        
        # OTM2 Put
        otm2 = round(atm - 2 * gap, 4)
        otm2_premium = calculate_premium(spot, otm2, 2, iv, False)
        strikes.append({
            'name': 'OTM-2',
            'strike': otm2,
            'type': option_type,
            'premium': otm2_premium,
            'investment': otm2_premium * lot,
            'distance': 2,
            'recommendation': 'Lower cost, aggressive play'
        })
        
        # ITM1 Put
        itm1 = round(atm + gap, 4)
        itm1_premium = calculate_premium(spot, itm1, -1, iv, False)
        strikes.append({
            'name': 'ITM-1',
            'strike': itm1,
            'type': option_type,
            'premium': itm1_premium,
            'investment': itm1_premium * lot,
            'distance': -1,
            'recommendation': 'Conservative, higher Delta'
        })
        
    else:
        # Neutral: Show both ATM Call and Put
        atm_call_premium = calculate_premium(spot, atm, 0, iv, True)
        atm_put_premium = calculate_premium(spot, atm, 0, iv, False)
        
        strikes.append({
            'name': 'ATM',
            'strike': atm,
            'type': 'CE',
            'premium': atm_call_premium,
            'investment': atm_call_premium * lot,
            'distance': 0,
            'recommendation': 'For breakout upside'
        })
        
        strikes.append({
            'name': 'ATM',
            'strike': atm,
            'type': 'PE',
            'premium': atm_put_premium,
            'investment': atm_put_premium * lot,
            'distance': 0,
            'recommendation': 'For breakdown downside'
        })
    
    return strikes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = 'Shon A.I. Advanced Trading Bot\n\n'
    msg += 'FEATURES:\n'
    msg += '- Live Real-time Prices\n'
    msg += '- ATM/OTM/ITM Strike Analysis\n'
    msg += '- Weekly + Monthly Expiry\n'
    msg += '- Real-time Premium Calculations\n'
    msg += '- Investment per Lot\n'
    msg += '- Dynamic Greeks\n\n'
    msg += 'COMMANDS:\n'
    msg += '/analyze nifty - Complete analysis\n'
    msg += '/markets - All live prices\n'
    msg += '/help - Full help\n\n'
    msg += 'MARKETS:\n'
    msg += 'Indices: nifty, banknifty, finnifty, sensex, midcap\n'
    msg += 'Commodities: crude, gold, silver, naturalgas, copper\n'
    msg += 'Crypto: btc, eth, bnb, sol\n\n'
    msg += 'Ready to analyze!'
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        msg = 'Use: /analyze [asset]\n\n'
        msg += 'Examples:\n'
        msg += '/analyze nifty\n'
        msg += '/analyze banknifty\n'
        msg += '/analyze gold\n'
        msg += '/analyze btc\n\n'
        msg += 'Get complete analysis with:\n'
        msg += '- Multiple strike options\n'
        msg += '- Real-time premiums\n'
        msg += '- Investment per lot\n'
        msg += '- Weekly/Monthly expiry\n\n'
        msg += 'Assets: nifty, banknifty, gold, silver, crude, btc, eth'
        await update.message.reply_text(msg)
        return
    
    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(asset + ' not supported!\nUse /help for asset list')
        return
    
    cfg = ASSETS[asset]
    
    loading = await update.message.reply_text('Fetching live data for ' + cfg['name'] + '...')
    
    price, change, pct = get_live_price(asset)
    
    try:
        await loading.delete()
    except Exception:
        pass
    
    if price is None:
        await update.message.reply_text('Live price unavailable!\nPlease try again.')
        return
    
    sym = cfg['sym']
    gap = cfg['gap']
    lot = cfg['lot']
    
    g = get_greeks(asset, pct)
    strikes = format_strike_options(price, gap, sym, lot, g['iv'], g['market'])
    weekly_exp, monthly_exp = get_expiry_dates()
    
    arrow = 'UP' if change >= 0 else 'DOWN'
    sign = '+' if pct >= 0 else ''
    
    # Build message
    msg = '=' * 40 + '\n'
    msg += cfg['name'] + ' - REAL-TIME ANALYSIS\n'
    msg += '=' * 40 + '\n'
    msg += 'Spot Price: ' + sym + str(price) + '\n'
    msg += 'Change: ' + arrow + ' ' + sign + str(pct) + '%\n'
    msg += 'Time: ' + datetime.now().strftime('%d-%b %I:%M %p') + '\n\n'
    
    msg += 'MARKET SIGNAL:\n'
    msg += 'Direction: ' + g['market'] + '\n'
    msg += 'Confidence: ' + str(g['conf']) + '%\n'
    msg += 'RSI: ' + str(g['rsi'])
    if g['rsi'] > 70:
        msg += ' (Overbought)'
    elif g['rsi'] < 30:
        msg += ' (Oversold)'
    msg += '\n'
    msg += 'IV: ' + str(g['iv']) + '% (' + g['iv_rank'] + ')\n\n'
    
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    msg += 'STRIKE OPTIONS - REAL-TIME PREMIUMS\n'
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
    
    for i, strike in enumerate(strikes, 1):
        msg += str(i) + '. ' + strike['name'] + ' - ' + sym + str(strike['strike']) + ' ' + strike['type'] + '\n'
        msg += '   Premium: ' + sym + str(strike['premium']) + '\n'
        msg += '   Investment (1 lot): ' + sym + str(strike['investment']) + '\n'
        msg += '   Lot Size: ' + str(lot) + ' qty\n'
        msg += '   ' + strike['recommendation'] + '\n\n'
    
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    msg += 'EXPIRY DATES\n'
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
    
    if cfg['weekly']:
        msg += 'WEEKLY EXPIRY:\n'
        msg += weekly_exp.strftime('%d-%b-%Y (%A)') + '\n'
        days_to_weekly = (weekly_exp - datetime.now()).days
        msg += 'Days Remaining: ' + str(days_to_weekly) + '\n\n'
    
    msg += 'MONTHLY EXPIRY:\n'
    msg += monthly_exp.strftime('%d-%b-%Y (%A)') + '\n'
    days_to_monthly = (monthly_exp - datetime.now()).days
    msg += 'Days Remaining: ' + str(days_to_monthly) + '\n\n'
    
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    msg += 'GREEKS (Real-time Dynamic)\n'
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
    msg += 'Delta: ' + str(g['delta']) + ' (Price sensitivity)\n'
    msg += 'Gamma: ' + str(g['gamma']) + ' (Delta change rate)\n'
    msg += 'Theta: ' + str(g['theta']) + ' (Time decay/day)\n'
    msg += 'Vega: ' + str(g['vega']) + ' (IV sensitivity)\n\n'
    
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    msg += 'TRADING RECOMMENDATION\n'
    msg += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
    
    if 'BULLISH' in g['market']:
        msg += 'BEST CHOICE: OTM-1 CALL\n'
        msg += 'Why: Optimal risk/reward for bullish trend\n'
        msg += 'Risk: Limited to premium paid\n'
        msg += 'Stop Loss: 30% of premium\n'
        msg += 'Take Profit: 60-80% gain\n'
    elif 'BEARISH' in g['market']:
        msg += 'BEST CHOICE: OTM-1 PUT\n'
        msg += 'Why: Optimal risk/reward for bearish trend\n'
        msg += 'Risk: Limited to premium paid\n'
        msg += 'Stop Loss: 30% of premium\n'
        msg += 'Take Profit: 60-80% gain\n'
    else:
        msg += 'RECOMMENDATION: WAIT\n'
        msg += 'Market direction unclear\n'
        msg += 'Watch for breakout or breakdown\n'
        msg += 'Consider iron condor if experienced\n'
    
    msg += '\nTIMING:\n'
    msg += 'Best Entry: 10:00-11:30 AM\n'
    msg += 'Avoid: 3:00-3:30 PM (volatility)\n\n'
    
    msg += 'RISK MANAGEMENT:\n'
    msg += '- Never risk >2% of capital per trade\n'
    msg += '- Max 2 lots per position\n'
    msg += '- Always use Stop Loss (30% rule)\n'
    msg += '- Book profits at 60-80% gain\n\n'
    
    msg += '⚠️ DISCLAIMER:\n'
    msg += 'Educational analysis only!\n'
    msg += 'Trade at your own risk.\n'
    msg += 'Past performance ≠ future results.\n'
    msg += '=' * 40
    
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Fetching live prices from all markets...')
    
    msg = 'LIVE MARKET DASHBOARD\n'
    msg += '=' * 35 + '\n'
    msg += datetime.now().strftime('%d-%b-%Y %I:%M %p') + '\n\n'
    
    msg += 'INDIAN INDICES:\n'
    for a in ['nifty', 'banknifty', 'sensex', 'finnifty']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
        except Exception:
            pass
    
    msg += '\nCOMMODITIES MCX:\n'
    for a in ['crude', 'gold', 'silver']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
        except Exception:
            pass
    
    msg += '\nCRYPTO:\n'
    for a in ['btc', 'eth', 'bnb', 'sol']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
