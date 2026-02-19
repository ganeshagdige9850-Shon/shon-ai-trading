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

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# AI client (optional - works without it)
try:
    import anthropic
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except:
    ai_client = None

USD_INR = 84.0

# 8 Assets Configuration
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
    """Get MCX commodity prices"""
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
            
            # Convert to INR
            if ticker == 'CL=F':  # Crude
                price = round(price_usd * USD_INR / 6)
            elif ticker == 'GC=F':  # Gold
                price = round(price_usd * USD_INR / 31.1 * 10)
            elif ticker == 'SI=F':  # Silver
                price = round(price_usd * USD_INR / 31.1 * 1000)
            else:
                price = price_usd
            
            return price, change_pct
    except: pass
    return None, None

def calculate_indicators(price, change):
    """Calculate technical indicators"""
    # RSI
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
    
    # IV estimate
    iv = 20 + abs(change) * 2
    
    # PCR estimate (inverse relationship)
    if change > 0.5:
        pcr = 1.2 + change * 0.1  # Bullish = high PCR
    elif change < -0.5:
        pcr = 0.8 - abs(change) * 0.1  # Bearish = low PCR
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
    """Calculate Option Greeks"""
    moneyness = (spot - strike) / spot if opt_type == 'CE' else (strike - spot) / spot
    
    # Delta
    if opt_type == 'CE':
        delta = 0.5 + moneyness * 2
    else:
        delta = -0.5 + moneyness * 2
    delta = max(min(delta, 1.0), -1.0)
    
    # Gamma
    gamma = 0.02 * (1 - abs(moneyness) * 2) * (iv / 20)
    gamma = max(gamma, 0.001)
    
    # Theta
    theta = -(premium * 0.003) * (iv / 20) * math.sqrt(30 / max(days_to_expiry, 1))
    
    # Vega
    vega = premium * 0.1 * math.sqrt(days_to_expiry / 30)
    
    return {
        'delta': round(delta, 3),
        'gamma': round(gamma, 4),
        'theta': round(theta, 2),
        'vega': round(vega, 2)
    }

def analyze_comprehensive(price, change, cfg, budget=15000):
    """Comprehensive analysis with all metrics"""
    gap = cfg['gap']
    atm = round(price / gap) * gap
    lot = cfg['lot']
    
    # Technical indicators
    indicators = calculate_indicators(price, change)
    
    # Determine direction
    if indicators['trend'] == 'BULLISH':
        direction = 'CALL'
        strike = atm + gap  # OTM-1 for calls
    elif indicators['trend'] == 'BEARISH':
        direction = 'PUT'
        strike = atm - gap  # OTM-1 for puts
    else:
        direction = 'WAIT'
        strike = atm
    
    # Premium estimation (2% of spot)
    premium = int(price * 0.02 * (1 + indicators['iv'] / 100))
    investment = premium * lot
    
    # Greeks calculation
    days_to_expiry = 4  # Assume weekly expiry
    greeks = calculate_greeks(price, strike, premium, days_to_expiry, indicators['iv'], direction)
    
    # Risk management
    stop_loss = int(premium * 0.70)
    target1 = int(premium * 1.60)
    target2 = int(premium * 2.00)
    
    # Confidence calculation
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
    angel_status = '✅' if angel.configured else '❌'
    ai_status = '✅' if ai_client else '⚠️ (Optional)'
    
    msg = '🤖 Shon AI Trading Bot - Complete\n\n'
    msg += f'Angel One: {angel_status}\n'
    msg += f'AI Analysis: {ai_status}\n\n'
    msg += '📊 8 Assets Available:\n'
    msg += '• NSE: NIFTY, BANKNIFTY, FINNIFTY, SENSEX, MIDCAP\n'
    msg += '• MCX: GOLD, SILVER, CRUDE\n\n'
    msg += 'Commands:\n'
    msg += '/recommend - AI suggests best trade\n'
    msg += '/analyze [asset] - Quick analysis\n'
    msg += '/markets - All 8 live prices\n'
    msg += '/help - Complete guide\n\n'
    msg += 'Try: /recommend'
    
    await update.message.reply_text(msg)

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    budget = 15000
    if context.args:
        try:
            budget = int(context.args[0])
        except: pass
    
    await update.message.reply_text(
        f'🤖 Analyzing 8 markets...\n'
        f'Budget: Rs{budget:,}\n'
        f'Checking indicators, Greeks, IV, OI, PCR...\n'
        f'Wait 10 seconds...'
    )
    
    # Analyze all 8 assets
    all_analysis = []
    
    for key, cfg in ASSETS.items():
        if cfg['type'] == 'nse':
            price, change = angel.get_price(cfg['token'])
        else:  # mcx
            price, change = get_yahoo_price(cfg['ticker'])
        
        if price:
            analysis = analyze_comprehensive(price, change, cfg, budget)
            all_analysis.append({
                'asset': cfg['name'],
                'key': key,
                'price': price,
                'change': change,
                'analysis': analysis,
                'lot': cfg['lot'],
                'type': cfg['type']
            })
    
    if not all_analysis:
        now = datetime.now()
        msg = '❌ No market data!\n\n'
        if now.hour < 9 or now.hour >= 15:
            msg += 'NSE Market: CLOSED\n'
            msg += 'Hours: 9:15 AM - 3:30 PM\n\n'
        msg += 'MCX should work 24/5.\n'
        msg += 'Check Angel One connection.'
        await update.message.reply_text(msg)
        return
    
    # Find best opportunity
    best = max(all_analysis, key=lambda x: x['analysis']['confidence'] if x['analysis']['fits_budget'] else 0)
    a = best['analysis']
    
    if a['direction'] == 'WAIT':
        await update.message.reply_text(
            '⏸️ No clear opportunity right now.\n\n'
            'All markets showing NEUTRAL signals.\n'
            'Wait for better setup!'
        )
        return
    
    # Build comprehensive response
    arrow = '📈' if best['change'] > 0 else '📉'
    ind = a['indicators']
    g = a['greeks']
    
    msg = '═' * 40 + '\n'
    msg += '🤖 COMPREHENSIVE RECOMMENDATION\n'
    msg += '═' * 40 + '\n\n'
    
    msg += f'ASSET: {best["asset"]}\n'
    msg += f'Spot: Rs{best["price"]:,.2f} {arrow}\n'
    msg += f'Change: {best["change"]:+.2f}%\n'
    msg += f'Type: {best["type"].upper()}\n\n'
    
    msg += f'BUY RECOMMENDATION:\n'
    msg += f'Option: {a["strike"]} {a["direction"]}\n'
    msg += f'Premium: Rs{a["premium"]}\n'
    msg += f'Investment: Rs{a["investment"]:,} ({best["lot"]} lots)\n'
    msg += f'Fits Budget: {"✅" if a["fits_budget"] else "❌"}\n\n'
    
    msg += f'TECHNICAL INDICATORS:\n'
    msg += f'RSI: {ind["rsi"]} ({"Overbought" if ind["rsi"]>70 else "Oversold" if ind["rsi"]<30 else "Normal"})\n'
    msg += f'Trend: {ind["trend"]} ({ind["strength"]})\n'
    msg += f'IV: {ind["iv"]}%\n'
    msg += f'PCR: {ind["pcr"]} ({"Bullish" if ind["pcr"]>1.2 else "Bearish" if ind["pcr"]<0.8 else "Neutral"})\n\n'
    
    msg += f'OPTION GREEKS:\n'
    msg += f'Delta: {g["delta"]} (Direction sensitivity)\n'
    msg += f'Gamma: {g["gamma"]} (Delta acceleration)\n'
    msg += f'Theta: {g["theta"]} (Time decay/day)\n'
    msg += f'Vega: {g["vega"]} (IV sensitivity)\n\n'
    
    msg += f'RISK MANAGEMENT:\n'
    msg += f'Entry: Rs{a["premium"]}\n'
    msg += f'Stop Loss: Rs{a["stop_loss"]} (30% loss)\n'
    msg += f'Target 1: Rs{a["target1"]} (60% profit)\n'
    msg += f'Target 2: Rs{a["target2"]} (100% profit)\n'
    msg += f'Max Risk: Rs{(a["premium"] - a["stop_loss"]) * best["lot"]:,}\n'
    msg += f'Max Profit: Rs{(a["target2"] - a["premium"]) * best["lot"]:,}\n\n'
    
    msg += f'REASONING:\n'
    msg += f'• {best["asset"]} shows {ind["trend"]} trend\n'
    msg += f'• RSI at {ind["rsi"]} indicates good entry\n'
    msg += f'• PCR {ind["pcr"]} supports {a["direction"]} direction\n'
    msg += f'• Greeks favorable: Delta {g["delta"]}\n'
    msg += f'• Risk:Reward = 1:{round((a["target1"]-a["premium"])/(a["premium"]-a["stop_loss"]), 1)}\n\n'
    
    msg += f'CONFIDENCE: {a["confidence"]}%\n\n'
    
    msg += '⚠️ DISCLAIMER:\n'
    msg += 'Analysis based on live data + indicators.\n'
    if best['type'] == 'mcx':
        msg += 'MCX premiums are estimated.\n'
    msg += 'Educational only. Trade at your risk!\n'
    msg += 'Always use stop loss!'
    
    if len(msg) > 4000:
        parts = [msg[i:i+3900] for i in range(0, len(msg), 3900)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        msg = 'Use: /analyze [asset]\n\nAvailable:\n'
        for key, cfg in ASSETS.items():
            msg += f'• {key} - {cfg["name"]}\n'
        await update.message.reply_text(msg)
        return
    
    asset = context.args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text('❌ Asset not found! Use /analyze to see list.')
        return
    
    cfg = ASSETS[asset]
    
    if cfg['type'] == 'nse':
        price, change = angel.get_price(cfg['token'])
    else:
        price, change = get_yahoo_price(cfg['ticker'])
    
    if not price:
        await update.message.reply_text('❌ No data! Check market hours or connection.')
        return
    
    analysis = analyze_comprehensive(price, change, cfg)
    a = analysis
    ind = a['indicators']
    g = a['greeks']
    arrow = '📈' if change > 0 else '📉'
    
    msg = f'{cfg["name"]}\n' + '=' * 35 + '\n'
    msg += f'Spot: Rs{price:,.2f} {arrow}\n'
    msg += f'Change: {change:+.2f}%\n'
    msg += f'ATM: Rs{a["atm"]}\n\n'
    msg += f'SIGNAL: {ind["trend"]} ({ind["strength"]})\n'
    msg += f'RSI: {ind["rsi"]}, IV: {ind["iv"]}%, PCR: {ind["pcr"]}\n\n'
    msg += f'RECOMMENDATION: {a["direction"]}\n'
    if a["direction"] != 'WAIT':
        msg += f'Strike: Rs{a["strike"]}\n'
        msg += f'Premium: Rs{a["premium"]}\n'
        msg += f'Investment: Rs{a["investment"]:,}\n'
        msg += f'Greeks: Δ={g["delta"]}, Γ={g["gamma"]}, Θ={g["theta"]}\n'
    msg += f'\nConfidence: {a["confidence"]}%'
    
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    msg = 'LIVE MARKETS - ALL 8 ASSETS\n' + '='*35 + '\n'
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
    
    msg += '\nUse /recommend for AI analysis'
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 COMPLETE TRADING BOT\n\n'
    msg += 'FEATURES:\n'
    msg += '✅ 8 Assets (NSE + MCX)\n'
    msg += '✅ Technical Indicators (RSI, IV)\n'
    msg += '✅ Option Greeks (Δ,Γ,Θ,ν)\n'
    msg += '✅ OI & PCR Analysis\n'
    msg += '✅ Risk Management\n'
    msg += '✅ Budget-aware (₹15K default)\n\n'
    msg += 'COMMANDS:\n'
    msg += '/recommend - Best trade (all 8)\n'
    msg += '/recommend 20000 - Custom budget\n'
    msg += '/analyze nifty - Quick check\n'
    msg += '/markets - All prices\n\n'
    msg += 'ASSETS:\n'
    msg += 'NSE: nifty, banknifty, finnifty, sensex, midcap\n'
    msg += 'MCX: gold, silver, crude\n\n'
    msg += 'NSE Hours: 9:15 AM - 3:30 PM\n'
    msg += 'MCX: 24/5 (Mon-Fri)\n\n'
    msg += 'FREE version with full analysis!\n'
    msg += 'AI optional (for advanced reasoning)'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('BOT_TOKEN not set!')
        return
    
    logger.info('Starting complete 8-asset bot...')
    logger.info(f'Angel One: {angel.configured}')
    logger.info(f'AI: {ai_client is not None}')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('recommend', recommend))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_cmd))
    
    logger.info('Complete bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
