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
        except:
            pass
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
        except:
            pass
        return None, None

angel = AngelAPI()

def get_yahoo_price(ticker):
    """FIXED CONVERSION - Force correct formulas"""
    try:
        r = requests.get(
            f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()['chart']['result'][0]['meta']
            price_usd = float(data.get('regularMarketPrice', 0))
            prev = float(data.get('previousClose', price_usd))
            change = round(((price_usd - prev) / prev) * 100, 2) if prev else 0
            
            # FORCE CORRECT CONVERSIONS
            if ticker == 'CL=F':
                # Crude: Direct USD to INR
                price_inr = int(price_usd * 84.0)
                logger.info(f'CRUDE CONVERSION: ${price_usd} x 84 = Rs{price_inr}')
                
            elif ticker == 'GC=F':
                # Gold: USD/oz to Rs/10g
                price_per_gram = (price_usd * 84.0) / 31.1035
                price_inr = int(price_per_gram * 10.0)
                logger.info(f'GOLD CONVERSION: ${price_usd}/oz = Rs{price_inr}/10g')
                
            elif ticker == 'SI=F':
                # Silver: USD/oz to Rs/kg
                price_inr = int(price_usd * 84.0 * 32.1507)
                logger.info(f'SILVER CONVERSION: ${price_usd}/oz = Rs{price_inr}/kg')
            else:
                price_inr = int(price_usd)
            
            return price_inr, change
    except Exception as e:
        logger.error(f'Yahoo error: {e}')
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
    pcr = 1.2 if change > 0.5 else 0.8 if change < -0.5 else 1.0
    
    return {
        'rsi': round(rsi, 1),
        'iv': round(iv, 1),
        'pcr': round(pcr, 2),
        'trend': 'BULLISH' if change > 0.3 else 'BEARISH' if change < -0.3 else 'NEUTRAL',
        'strength': 'STRONG' if abs(change) > 1.5 else 'MODERATE' if abs(change) > 0.5 else 'WEAK'
    }

def calculate_greeks(spot, strike, premium, days, iv, opt_type='CE'):
    dist = abs(strike - spot) / spot
    
    if opt_type == 'CE':
        if strike < spot:
            delta = 0.70
        elif dist < 0.02:
            delta = 0.50
        else:
            delta = 0.35
        delta = max(0.05, min(delta - dist * 0.3, 0.95))
    else:
        if strike > spot:
            delta = -0.70
        elif dist < 0.02:
            delta = -0.50
        else:
            delta = -0.35
        delta = min(-0.05, max(delta + dist * 0.3, -0.95))
    
    gamma = max(0.001, 0.02 * (1 - dist * 2) * (iv / 20))
    theta = -(premium * 0.003) * (iv / 20) * math.sqrt(30 / max(days, 1))
    vega = premium * 0.1 * math.sqrt(days / 30)
    
    return {
        'delta': round(delta, 3),
        'gamma': round(gamma, 4),
        'theta': round(theta, 2),
        'vega': round(vega, 2)
    }

def analyze_comprehensive(price, change, cfg, budget=15000):
    gap = cfg['gap']
    atm = int(round(price / gap) * gap)
    lot = cfg['lot']
    
    ind = calculate_indicators(price, change)
    
    if ind['trend'] == 'BULLISH':
        direction = 'CALL'
        strike = atm + gap
    elif ind['trend'] == 'BEARISH':
        direction = 'PUT'
        strike = atm - gap
    else:
        direction = 'WAIT'
        strike = atm
    
    premium = int(price * 0.02 * (1 + ind['iv'] / 100))
    investment = premium * lot
    greeks = calculate_greeks(price, strike, premium, 4, ind['iv'], direction)
    
    conf = 50
    if ind['strength'] == 'STRONG':
        conf += 20
    elif ind['strength'] == 'MODERATE':
        conf += 10
    if 30 < ind['rsi'] < 70:
        conf += 10
    if investment <= budget:
        conf += 10
    
    return {
        'direction': direction,
        'strike': strike,
        'premium': premium,
        'investment': investment,
        'fits_budget': investment <= budget,
        'indicators': ind,
        'greeks': greeks,
        'stop_loss': int(premium * 0.70),
        'target1': int(premium * 1.60),
        'target2': int(premium * 2.00),
        'confidence': min(conf, 95),
        'atm': atm
    }

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to show exact conversions"""
    msg = "DEBUG MCX CONVERSIONS\n" + "="*30 + "\n\n"
    
    try:
        r = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/CL=F',
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        price_usd = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
        price_inr = int(float(price_usd) * 84.0)
        msg += f"CRUDE:\nYahoo: ${price_usd}\nFormula: ${price_usd} x 84\nResult: Rs{price_inr}\n\n"
    except Exception as e:
        msg += f"Crude Error: {e}\n\n"
    
    try:
        r = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/GC=F',
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        price_usd = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
        price_inr = int((float(price_usd) * 84.0) / 31.1035 * 10.0)
        msg += f"GOLD:\nYahoo: ${price_usd}\nFormula: (${price_usd} x 84) / 31.1 x 10\nResult: Rs{price_inr}\n\n"
    except Exception as e:
        msg += f"Gold Error: {e}\n\n"
    
    msg += "Expected:\nCrude: Rs6,000 range\nGold: Rs72,000 range"
    await update.message.reply_text(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon Bot - DEBUG VERSION\n\n'
    msg += 'Fixed MCX conversions!\n\n'
    msg += '/debug - Show conversions\n'
    msg += '/markets - Live prices\n'
    msg += '/recommend - Best trade\n\n'
    msg += 'Version: FORCE_FIX_v2'
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
    
    msg += '\nMCX (FIXED CONVERSIONS):\n'
    for key in ['gold', 'silver', 'crude']:
        cfg = ASSETS[key]
        price, change = get_yahoo_price(cfg['ticker'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,} {arrow} {change:+.2f}%\n'
    
    msg += '\nExpected: Gold ~72k, Crude ~6k'
    await update.message.reply_text(msg)

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    budget = 15000
    if context.args:
        try:
            budget = int(context.args[0])
        except:
            pass
    
    await update.message.reply_text(f'🤖 Analyzing\nBudget: Rs{budget:,}')
    
    all_data = []
    
    for key, cfg in ASSETS.items():
        if cfg['type'] == 'mcx':
            price, change = get_yahoo_price(cfg['ticker'])
        else:
            price, change = angel.get_price(cfg['token'])
        
        if price:
            a = analyze_comprehensive(price, change, cfg, budget)
            all_data.append({
                'asset': cfg['name'],
                'price': price,
                'change': change,
                'analysis': a
            })
    
    if not all_data:
        await update.message.reply_text('❌ No data!')
        return
    
    best = max(all_data, key=lambda x: x['analysis']['confidence'] if x['analysis']['fits_budget'] else 0)
    a = best['analysis']
    
    if a['direction'] == 'WAIT':
        await update.message.reply_text('⏸️ No clear opportunity!')
        return
    
    ind = a['indicators']
    g = a['greeks']
    
    msg = '='*40 + '\n🤖 RECOMMENDATION\n' + '='*40 + '\n\n'
    msg += f'ASSET: {best["asset"]}\n'
    msg += f'Spot: Rs{best["price"]:,}\n'
    msg += f'Change: {best["change"]:+.2f}%\n\n'
    msg += f'BUY: {a["strike"]} {a["direction"]}\n'
    msg += f'Premium: Rs{a["premium"]}\n'
    msg += f'Investment: Rs{a["investment"]:,}\n\n'
    msg += f'INDICATORS:\nRSI: {ind["rsi"]}, Trend: {ind["trend"]}\n'
    msg += f'IV: {ind["iv"]}%, PCR: {ind["pcr"]}\n\n'
    msg += f'GREEKS:\nDelta: {g["delta"]:+.3f}\n'
    msg += f'Gamma: {g["gamma"]}\nTheta: {g["theta"]}\n\n'
    msg += f'RISK:\nEntry: Rs{a["premium"]}\n'
    msg += f'SL: Rs{a["stop_loss"]}\nTarget: Rs{a["target1"]}\n\n'
    msg += f'Confidence: {a["confidence"]}%\n\n'
    msg += 'VERSION: FORCE_FIX_v2'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('BOT_TOKEN missing!')
        return
    
    logger.info('='*50)
    logger.info('STARTING DEBUG BOT - FORCE FIXED CONVERSIONS')
    logger.info('='*50)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('debug', debug))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('recommend', recommend))
    
    logger.info('Bot running - Version: FORCE_FIX_v2')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
