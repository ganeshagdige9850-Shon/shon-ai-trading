import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime
import math
import json
import urllib.parse

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
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
        self.configured = all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET])
    
    def login(self, return_details=False):
        if not self.configured:
            return False, 'Credentials missing', {}
        
        details = {}
        
        try:
            # Clean password - remove any leading/trailing spaces
            clean_password = ANGEL_PASSWORD.strip() if ANGEL_PASSWORD else ''
            
            # Generate TOTP
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            
            details['password_length'] = len(clean_password)
            details['password_has_spaces'] = ' ' in clean_password
            details['password_starts_with_space'] = clean_password != clean_password.lstrip()
            details['password_ends_with_space'] = clean_password != clean_password.rstrip()
            details['totp'] = totp
            
            # Check for problematic characters
            special_chars = set(clean_password) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            details['special_chars'] = ''.join(sorted(special_chars)) if special_chars else 'None'
            
            # Prepare payload
            payload = {
                'clientcode': ANGEL_CLIENT_ID,
                'password': clean_password,
                'totp': totp
            }
            
            headers = {
                'X-PrivateKey': ANGEL_API_KEY,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            logger.info(f'Login attempt - Client: {ANGEL_CLIENT_ID}')
            logger.info(f'Password length: {len(clean_password)}')
            logger.info(f'Special chars: {details["special_chars"]}')
            
            # Make request
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json=payload,
                headers=headers,
                timeout=15
            )
            
            details['status_code'] = r.status_code
            details['response_headers'] = dict(r.headers)
            details['response_text'] = r.text
            details['response_length'] = len(r.text)
            
            logger.info(f'Response status: {r.status_code}')
            logger.info(f'Response length: {len(r.text)}')
            logger.info(f'Response text: {r.text[:500]}')
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    if data.get('status'):
                        self.token = data['data']['jwtToken']
                        logger.info('Login SUCCESS!')
                        if return_details:
                            return True, 'Success', details
                        return True, 'Success', {}
                    else:
                        error = data.get('message', 'Unknown error')
                        if return_details:
                            return False, error, details
                        return False, error, {}
                except json.JSONDecodeError as e:
                    if return_details:
                        details['json_error'] = str(e)
                        return False, 'Invalid JSON response', details
                    return False, 'Invalid JSON response', {}
            else:
                if return_details:
                    return False, f'HTTP {r.status_code}', details
                return False, f'HTTP {r.status_code}', {}
                
        except Exception as e:
            logger.error(f'Login exception: {e}')
            details['exception'] = str(e)
            if return_details:
                return False, str(e), details
            return False, str(e), {}
    
    def get_price(self, token_id, exchange='NSE'):
        if not self.token:
            success, msg, _ = self.login()
            if not success:
                return None, None, msg
        
        try:
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
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status'):
                    fetched = data.get('data', {}).get('fetched', [])
                    if fetched and len(fetched) > 0:
                        price = float(fetched[0]['ltp'])
                        change = float(fetched[0].get('pChange', 0))
                        return price, change, 'Success'
                    else:
                        return None, None, 'No data'
                else:
                    return None, None, data.get('message', 'Error')
            else:
                return None, None, f'HTTP {r.status_code}'
        except Exception as e:
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

async def superdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced debug with password analysis"""
    msg = 'PASSWORD ANALYSIS\n' + '='*30 + '\n\n'
    
    if ANGEL_PASSWORD:
        clean_pwd = ANGEL_PASSWORD.strip()
        msg += f'Length: {len(ANGEL_PASSWORD)} chars\n'
        msg += f'After trim: {len(clean_pwd)} chars\n'
        msg += f'Has spaces: {"Yes" if " " in ANGEL_PASSWORD else "No"}\n'
        msg += f'Starts space: {"Yes" if ANGEL_PASSWORD != ANGEL_PASSWORD.lstrip() else "No"}\n'
        msg += f'Ends space: {"Yes" if ANGEL_PASSWORD != ANGEL_PASSWORD.rstrip() else "No"}\n\n'
        
        special = set(clean_pwd) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        msg += f'Special chars: {", ".join(sorted(special)) if special else "None"}\n\n'
    
    await update.message.reply_text(msg)
    
    msg2 = 'LOGIN ATTEMPT\n' + '='*30 + '\n\n'
    success, error, details = angel.login(return_details=True)
    
    msg2 += f'Status: {"✅" if success else "❌"}\n'
    msg2 += f'Error: {error}\n\n'
    
    if details:
        msg2 += f'Response code: {details.get("status_code")}\n'
        msg2 += f'Response length: {details.get("response_length")} bytes\n\n'
        
        resp_text = details.get('response_text', '')
        if resp_text:
            msg2 += f'Response:\n{resp_text[:300]}\n'
        else:
            msg2 += 'Response: EMPTY (This is the problem!)\n'
    
    await update.message.reply_text(msg2)
    
    if not success and details.get('response_length', 0) == 0:
        msg3 = '\n⚠️ EMPTY RESPONSE MEANS:\n'
        msg3 += '1. Angel One rejecting immediately\n'
        msg3 += '2. Password has invalid chars\n'
        msg3 += '3. OR API endpoint changed\n\n'
        msg3 += 'SOLUTION:\n'
        msg3 += '- Contact Angel One support\n'
        msg3 += '- OR create NEW API app\n'
        msg3 += '- support@angelbroking.com'
        await update.message.reply_text(msg3)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick debug"""
    msg = 'DEBUG\n' + '='*30 + '\n\n'
    
    msg += 'CREDENTIALS:\n'
    msg += f'API_KEY: {"✅" if ANGEL_API_KEY else "❌"}\n'
    msg += f'CLIENT_ID: {"✅" if ANGEL_CLIENT_ID else "❌"}\n'
    msg += f'PASSWORD: {"✅" if ANGEL_PASSWORD else "❌"} ({len(ANGEL_PASSWORD) if ANGEL_PASSWORD else 0} chars)\n'
    msg += f'TOTP_SECRET: {"✅" if ANGEL_TOTP_SECRET else "❌"}\n\n'
    
    msg += 'APP STATUS: ACTIVE ✅\n\n'
    
    msg += 'LOGIN TEST:\n'
    success, error, _ = angel.login()
    if success:
        msg += '✅ SUCCESS!\n\n'
        
        price, change, err = angel.get_price('99926000', 'NSE')
        if price:
            msg += f'NSE: ✅ Rs{price:,.2f} ({change:+.2f}%)\n'
        else:
            msg += f'NSE: ❌ {err}\n'
    else:
        msg += f'❌ FAILED: {error}\n'
        msg += '\nUse /superdebug for details'
    
    await update.message.reply_text(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI Bot - DEBUG v2\n\n'
    msg += 'App Status: ACTIVE ✅\n\n'
    msg += '/debug - Quick test\n'
    msg += '/superdebug - Full analysis\n'
    msg += '/markets - Live prices\n'
    msg += '/recommend - Trade\n'
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
        await update.message.reply_text('❌ No data! Use /superdebug')
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
    
    logger.info('Starting debug bot v2 - password analysis')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('debug', debug))
    app.add_handler(CommandHandler('superdebug', superdebug))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('recommend', recommend))
    
    logger.info('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
