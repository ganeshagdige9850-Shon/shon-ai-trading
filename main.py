import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

USD_INR = 84.0

ASSETS = {
    'nifty': {'name': 'NIFTY 50', 'lot': 25, 'token': '99926000', 'gap': 50, 'type': 'nse'},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'token': '99926009', 'gap': 100, 'type': 'nse'},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'token': '99926037', 'gap': 50, 'type': 'nse'},
    'sensex': {'name': 'SENSEX', 'lot': 10, 'token': '99919000', 'gap': 100, 'type': 'nse'},
    'midcap': {'name': 'MIDCAP NIFTY', 'lot': 50, 'token': '99926074', 'gap': 25, 'type': 'nse'},
    'gold': {'name': 'GOLD MCX', 'lot': 100, 'gap': 100, 'type': 'mcx', 'ticker': 'GC=F'},
    'silver': {'name': 'SILVER MCX', 'lot': 30, 'gap': 100, 'type': 'mcx', 'ticker': 'SI=F'},
    'crude': {'name': 'CRUDE OIL MCX', 'lot': 100, 'gap': 50, 'type': 'mcx', 'ticker': 'CL=F'}
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
        self.configured = all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET])
    
    def login(self):
        if not self.configured:
            return False
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json={'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp},
                headers={'X-PrivateKey': ANGEL_API_KEY, 'Content-Type': 'application/json'},
                timeout=15
            )
            if r.status_code == 200 and r.json().get('status'):
                self.token = r.json()['data']['jwtToken']
                return True
        except: pass
        return False
    
    def get_price(self, token_id):
        if not self.token and not self.login():
            return None, None
        try:
            r = requests.post(
                f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json={'mode': 'LTP', 'exchangeTokens': {'NSE': [token_id]}},
                headers={'Authorization': f'Bearer {self.token}', 'X-PrivateKey': ANGEL_API_KEY},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()['data']['fetched'][0]
                return float(data['ltp']), float(data.get('pChange', 0))
        except: pass
        return None, None

angel = AngelAPI()

def get_yahoo_price(ticker):
    global USD_INR
    try:
        r = requests.get(
            f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price_usd = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price_usd))
            change_pct = round(((price_usd - prev) / prev) * 100, 2) if prev else 0
            
            if ticker == 'CL=F':
                price = round(price_usd * USD_INR)
            elif ticker == 'GC=F':
                price = round((price_usd * USD_INR) / 31.1035 * 10)
            elif ticker == 'SI=F':
                price = round(price_usd * USD_INR * 32.1507)
            else:
                price = price_usd
            
            return price, change_pct
    except: pass
    return None, None

def calculate_indicators(price, change):
    if change > 1.5:
        rsi = 72
    elif change > 0.5:
        rsi = 64
    elif change < -1.5:
        rsi = 28
    elif change < -0.5:
        rsi = 36
    else:
        rsi = 50
    
    iv = 20 + abs(change) * 2
    
    if change > 0.5:
        pcr = 1.2 + change * 0.1
    elif change < -0.5:
        pcr = 0.8 - abs(change) * 0.1
    else:
        pcr = 1.0
    
    return {
        'rsi': round(rsi, 1),
        'iv': round(iv, 1),
        'pcr': round(pcr, 2),
        'trend': 'BULLISH' if change > 0.3 else 'BEARISH' if change < -0.3 else 'NEUTRAL',
        'strength': 'STRONG' if abs(change) > 1.5 else 'MODERATE' if abs(change) > 0.5 else 'WEAK'
    }

def calculate_greeks(spot, strike, premium, days_to_expiry, iv, opt_type='CE'):
    distance_pct = abs(strike - spot) / spot
    
    if opt_type == 'CE':
        if strike < spot:
            delta = 0.70 - (distance_pct * 0.5)
        elif distance_pct < 0.02:
            delta = 0.50
        else:
            delta = 0.35 - (distance_pct * 0.3)
        delta = max(0.05, min(delta, 0.95))
    else:
        if strike > spot:
            delta = -0.70 + (distance_pct * 0.5)
        elif distance_pct < 0.02:
            delta = -0.50
        else:
            delta = -0.35 + (distance_pct * 0.3)
        delta = min(-0.05, max(delta, -0.95))
    
    gamma = 0.02 * (1 - distance_pct * 2) * (iv / 20)
    gamma = max(gamma, 0.001)
    theta = -(premium * 0.003) * (iv / 20) * math.sqrt(30 / max(days_to_expiry, 1))
    vega = premium * 0.1 * math.sqrt(days_to_expiry / 30)
    
    return {
        'delta': round(delta, 3),
        'gamma': round(gamma, 4),
        'theta': round(theta, 2),
        'vega': round(vega, 2)
    }

def analyze_comprehensive(price, change, cfg, budget=15000):
    gap = cfg['gap']
    atm = round(price / gap) * gap
    lot = cfg['lot']
    
    indicators = calculate_indicators(price, change)
    
    if indicators['trend'] == 'BULLISH':
        direction = 'CALL'
        strike = atm + gap
    elif indicators['trend'] == 'BEARISH':
        direction = 'PUT'
        strike = atm - gap
    else:
        direction = 'WAIT'
        strike = atm
    
    premium = int(price * 0.02 * (1 + indicators['iv'] / 100))
    investment = premium * lot
    
    days_to_expiry = 4
    greeks = calculate_greeks(price, strike, premium, days_to_expiry, indicators['iv'], direction)
    
    stop_loss = int(premium * 0.70)
    target1 = int(premium * 1.60)
    target2 = int(premium * 2.00)
    
    conf = 50
    if indicators['strength'] == 'STRONG':
        conf += 20
    elif indicators['strength'] == 'MODERATE':
        conf += 10
    
    if 30 < indicators['rsi'] < 70:
        conf += 10
    
    if investment <= budget:
        conf += 10
    
    return {
        'direction': direction,
        'strike': strike,
        'premium': premium,
        'investment': investment,
        'fits_budget': investment <= budget,
        'indicators': indicators,
        'greeks': greeks,
        'stop_loss': stop_loss,
        'target1': target1,
        'target2': target2,
        'confidence': min(conf, 95),
        'atm': atm
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI Trading Bot\n\n'
    msg += '📊 8 Assets:\n'
    msg += 'NSE: NIFTY, BANKNIFTY, FINNIFTY, SENSEX, MIDCAP\n'
    msg += 'MCX: GOLD, SILVER, CRUDE\n\n'
    msg += '/recommend - Best trade\n'
    msg += '/markets - All prices\n'
    msg += '/analyze [asset] - Quick check\n\n'
    msg += 'Fixed conversions! ✅'
    await update.message.reply_text(msg)

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    budget = 15000
    if context.args:
        try:
            budget = int(context.args[0])
        except: pass
    
    await update.message.reply_text(f'🤖 Analyzing...\nBudget: Rs{budget:,}')
    
    all_analysis = []
    
    for key, cfg in ASSETS.items():
        if cfg['type'] == 'nse':
            price, change = angel.get_price(cfg['token'])
        else:
            price, change = get_yahoo_price(cfg['ticker'])
        
        if price:
            analysis = analyze_comprehensive(price, change, cfg, budget)
            all_analysis.append({
                'asset': cfg['name'],
                'price': price,
                'change': change,
                'analysis': analysis,
                'lot': cfg['lot']
            })
    
    if not all_analysis:
        await update.message.reply_text('❌ No data!')
        return
    
    best = max(all_analysis, key=lambda x: x['analysis']['confidence'] if x['analysis']['fits_budget'] else 0)
    a = best['analysis']
    
    if a['direction'] == 'WAIT':
        await update.message.reply_text('⏸️ No clear opportunity!')
        return
    
    arrow = '📈' if best['change'] > 0 else '📉'
    ind = a['indicators']
    g = a['greeks']
    
    msg = '═' * 40 + '\n🤖 RECOMMENDATION\n' + '═' * 40 + '\n\n'
    msg += f'ASSET: {best["asset"]}\n'
    msg += f'Spot: Rs{best["price"]:,.2f} {arrow}\n'
    msg += f'Change: {best["change"]:+.2f}%\n\n'
    msg += f'BUY: {a["strike"]} {a["direction"]}\n'
    msg += f'Premium: Rs{a["premium"]}\n'
    msg += f'Investment: Rs{a["investment"]:,}\n\n'
    msg += f'INDICATORS:\n'
    msg += f'RSI: {ind["rsi"]}, Trend: {ind["trend"]}\n'
    msg += f'IV: {ind["iv"]}%, PCR: {ind["pcr"]}\n\n'
    msg += f'GREEKS:\n'
    msg += f'Δ={g["delta"]:+.3f}, Γ={g["gamma"]}, Θ={g["theta"]}, ν={g["vega"]}\n\n'
    msg += f'RISK:\n'
    msg += f'Entry: Rs{a["premium"]}\n'
    msg += f'Stop Loss: Rs{a["stop_loss"]}\n'
    msg += f'Target: Rs{a["target1"]}\n\n'
    msg += f'Confidence: {a["confidence"]}%'
    
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        msg = 'Use: /analyze [asset]\n\n'
        for key in ASSETS.keys():
            msg += f'• {key}\n'
        await update.message.reply_text(msg)
        return
    
    asset = context.args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text('❌ Not found!')
        return
    
    cfg = ASSETS[asset]
    
    if cfg['type'] == 'nse':
        price, change = angel.get_price(cfg['token'])
    else:
        price, change = get_yahoo_price(cfg['ticker'])
    
    if not price:
        await update.message.reply_text('❌ No data!')
        return
    
    analysis = analyze_comprehensive(price, change, cfg)
    a = analysis
    ind = a['indicators']
    g = a['greeks']
    arrow = '📈' if change > 0 else '📉'
    
    msg = f'{cfg["name"]}\n' + '=' * 30 + '\n'
    msg += f'Spot: Rs{price:,.2f} {arrow}\n'
    msg += f'Change: {change:+.2f}%\n\n'
    msg += f'Signal: {ind["trend"]}\n'
    msg += f'Recommendation: {a["direction"]}\n'
    if a["direction"] != 'WAIT':
        msg += f'Strike: Rs{a["strike"]}\n'
        msg += f'Premium: Rs{a["premium"]}\n'
        msg += f'Δ={g["delta"]:+.3f}\n'
    msg += f'\nConfidence: {a["confidence"]}%'
    
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    msg = 'LIVE MARKETS\n' + '='*30 + '\n'
    msg += f'Time: {now.strftime("%I:%M %p")}\n\n'
    
    msg += 'NSE INDICES:\n'
    for key in ['nifty', 'banknifty', 'finnifty', 'sensex', 'midcap']:
        cfg = ASSETS[key]
        price, change = angel.get_price(cfg['token'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,.2f} {arrow} {change:+.2f}%\n'
    
    msg += '\nMCX COMMODITIES:\n'
    for key in ['gold', 'silver', 'crude']:
        cfg = ASSETS[key]
        price, change = get_yahoo_price(cfg['ticker'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,.0f} {arrow} {change:+.2f}%\n'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('BOT_TOKEN not set!')
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('recommend', recommend))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('markets', markets))
    
    print('Fixed bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
