import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime
import math
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

ASSETS = {
    'nifty': {'name': 'NIFTY 50', 'lot': 25, 'token': '99926000', 'exchange': 'NSE', 'gap': 50},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'token': '99926009', 'exchange': 'NSE', 'gap': 100},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'token': '99926037', 'exchange': 'NSE', 'gap': 50},
    'sensex': {'name': 'SENSEX', 'lot': 10, 'token': '99919000', 'exchange': 'NSE', 'gap': 100},
    'midcap': {'name': 'MIDCAP NIFTY', 'lot': 50, 'token': '99926074', 'exchange': 'NSE', 'gap': 25},
    'gold': {'name': 'GOLD MCX', 'lot': 100, 'token': '234690', 'exchange': 'MCX', 'gap': 1000},
    'silver': {'name': 'SILVER MCX', 'lot': 30, 'token': '234694', 'exchange': 'MCX', 'gap': 1000},
    'crude': {'name': 'CRUDE OIL MCX', 'lot': 100, 'token': '234677', 'exchange': 'MCX', 'gap': 50}
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
        self.configured = all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET])
    
    def login(self):
        if not self.configured:
            logger.error('Angel One not configured!')
            return False, 'Credentials missing'
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            logger.info(f'Login attempt for {ANGEL_CLIENT_ID}')
            
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json={'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp},
                headers={'X-PrivateKey': ANGEL_API_KEY, 'Content-Type': 'application/json'},
                timeout=15
            )
            
            logger.info(f'Login response status: {r.status_code}')
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status'):
                    self.token = data['data']['jwtToken']
                    logger.info('Login SUCCESS!')
                    return True, 'Success'
                else:
                    error = data.get('message', 'Unknown error')
                    logger.error(f'Login failed: {error}')
                    return False, error
            else:
                logger.error(f'Login HTTP error: {r.status_code} - {r.text}')
                return False, f'HTTP {r.status_code}'
        except Exception as e:
            logger.error(f'Login exception: {e}')
            return False, str(e)
    
    def get_price(self, token_id, exchange='NSE'):
        if not self.token:
            success, msg = self.login()
            if not success:
                return None, None, msg
        
        try:
            logger.info(f'Fetching price for {exchange} {token_id}')
            
            r = requests.post(
                f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json={'mode': 'LTP', 'exchangeTokens': {exchange: [token_id]}},
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-UserType': 'USER',
                    'X-SourceID': 'WEB',
                    'X-ClientLocalIP': '192.168.1.1',
                    'X-ClientPublicIP': '106.193.147.98',
                    'X-MACAddress': '00:00:00:00:00:00',
                    'X-PrivateKey': ANGEL_API_KEY
                },
                timeout=10
            )
            
            logger.info(f'Price response status: {r.status_code}')
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status'):
                    fetched = data.get('data', {}).get('fetched', [])
                    if fetched and len(fetched) > 0:
                        price = float(fetched[0]['ltp'])
                        change = float(fetched[0].get('pChange', 0))
                        logger.info(f'{exchange} {token_id}: Rs{price} ({change:+.2f}%)')
                        return price, change, 'Success'
                    else:
                        return None, None, 'No data in response'
                else:
                    error = data.get('message', 'Unknown error')
                    return None, None, error
            else:
                return None, None, f'HTTP {r.status_code}'
        except Exception as e:
            logger.error(f'Price exception: {e}')
            return None, None, str(e)

angel = AngelAPI()

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
    """Detailed debug information"""
    msg = 'DEBUG INFO\n' + '='*30 + '\n\n'
    
    # Check credentials
    msg += 'CREDENTIALS:\n'
    msg += f'API_KEY: {"✅" if ANGEL_API_KEY else "❌"}\n'
    msg += f'CLIENT_ID: {"✅" if ANGEL_CLIENT_ID else "❌"}\n'
    msg += f'PASSWORD: {"✅" if ANGEL_PASSWORD else "❌"}\n'
    msg += f'TOTP_SECRET: {"✅" if ANGEL_TOTP_SECRET else "❌"}\n\n'
    
    # Try login
    msg += 'LOGIN TEST:\n'
    success, error = angel.login()
    if success:
        msg += '✅ Login SUCCESS!\n'
        msg += f'Token: {angel.token[:20]}...\n\n'
    else:
        msg += f'❌ Login FAILED!\n'
        msg += f'Error: {error}\n\n'
        await update.message.reply_text(msg)
        return
    
    # Try NSE
    msg += 'NSE TEST (NIFTY):\n'
    price, change, error = angel.get_price('99926000', 'NSE')
    if price:
        msg += f'✅ SUCCESS!\n'
        msg += f'Price: Rs{price:,.2f}\n'
        msg += f'Change: {change:+.2f}%\n\n'
    else:
        msg += f'❌ FAILED!\n'
        msg += f'Error: {error}\n\n'
    
    # Try MCX
    msg += 'MCX TEST (GOLD):\n'
    price, change, error = angel.get_price('234690', 'MCX')
    if price:
        msg += f'✅ SUCCESS!\n'
        msg += f'Price: Rs{price:,.2f}\n'
        msg += f'Change: {change:+.2f}%\n'
    else:
        msg += f'❌ FAILED!\n'
        msg += f'Error: {error}\n'
    
    await update.message.reply_text(msg)

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick test"""
    msg = 'ANGEL ONE TEST\n' + '='*30 + '\n\n'
    
    # Test NSE
    price, change, error = angel.get_price('99926000', 'NSE')
    if price:
        msg += f'NSE Test: ✅\nNIFTY: Rs{price:,.2f} ({change:+.2f}%)\n\n'
    else:
        msg += f'NSE Test: ❌\nError: {error}\n\n'
    
    # Test MCX
    price, change, error = angel.get_price('234690', 'MCX')
    if price:
        msg += f'MCX Test: ✅\nGOLD: Rs{price:,.2f} ({change:+.2f}%)\n\n'
    else:
        msg += f'MCX Test: ❌\nError: {error}\n\n'
    
    msg += 'Use /debug for detailed info'
    await update.message.reply_text(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI Bot - DEBUG\n\n'
    msg += '/test - Quick test\n'
    msg += '/debug - Detailed debug\n'
    msg += '/markets - Live prices\n'
    msg += '/recommend - Best trade\n\n'
    msg += 'Version: DEBUG_v3'
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    msg = 'LIVE MARKETS\n' + '='*30 + '\n'
    msg += f'Time: {now.strftime("%I:%M %p")}\n\n'
    
    msg += 'NSE INDICES:\n'
    for key in ['nifty', 'banknifty', 'finnifty', 'sensex', 'midcap']:
        cfg = ASSETS[key]
        price, change, error = angel.get_price(cfg['token'], cfg['exchange'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,.2f} {arrow} {change:+.2f}%\n'
    
    msg += '\nMCX COMMODITIES:\n'
    for key in ['gold', 'silver', 'crude']:
        cfg = ASSETS[key]
        price, change, error = angel.get_price(cfg['token'], cfg['exchange'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,.0f} {arrow} {change:+.2f}%\n'
    
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
        price, change, error = angel.get_price(cfg['token'], cfg['exchange'])
        
        if price:
            a = analyze_comprehensive(price, change, cfg, budget)
            all_data.append({
                'asset': cfg['name'],
                'price': price,
                'change': change,
                'analysis': a
            })
    
    if not all_data:
        await update.message.reply_text('❌ No data! Use /debug')
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
    msg += f'BUY: {a["strike"]:,} {a["direction"]}\n'
    msg += f'Premium: Rs{a["premium"]:,}\n'
    msg += f'Investment: Rs{a["investment"]:,}\n\n'
    msg += f'INDICATORS:\nRSI: {ind["rsi"]}, Trend: {ind["trend"]}\n'
    msg += f'IV: {ind["iv"]}%, PCR: {ind["pcr"]}\n\n'
    msg += f'GREEKS:\nDelta: {g["delta"]:+.3f}\n'
    msg += f'Gamma: {g["gamma"]}\nTheta: {g["theta"]}\n\n'
    msg += f'RISK:\nEntry: Rs{a["premium"]:,}\n'
    msg += f'SL: Rs{a["stop_loss"]:,}\nTarget: Rs{a["target1"]:,}\n\n'
    msg += f'Confidence: {a["confidence"]}%'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('BOT_TOKEN missing!')
        return
    
    logger.info('='*50)
    logger.info('STARTING DEBUG BOT')
    logger.info('='*50)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('test', test))
    app.add_handler(CommandHandler('debug', debug))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('recommend', recommend))
    
    logger.info('Debug bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
