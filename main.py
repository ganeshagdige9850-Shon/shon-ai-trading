import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime
import math
import json
import time

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
            # Generate TOTP
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            details['totp_generated'] = totp
            details['totp_length'] = len(totp)
            
            # Prepare request
            payload = {
                'clientcode': ANGEL_CLIENT_ID,
                'password': ANGEL_PASSWORD,
                'totp': totp
            }
            
            headers = {
                'X-PrivateKey': ANGEL_API_KEY,
                'Content-Type': 'application/json'
            }
            
            details['request_url'] = f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword'
            details['request_payload'] = {
                'clientcode': ANGEL_CLIENT_ID,
                'password': '****',
                'totp': totp
            }
            details['api_key_length'] = len(ANGEL_API_KEY) if ANGEL_API_KEY else 0
            details['client_id_length'] = len(ANGEL_CLIENT_ID) if ANGEL_CLIENT_ID else 0
            details['totp_secret_length'] = len(ANGEL_TOTP_SECRET) if ANGEL_TOTP_SECRET else 0
            
            logger.info(f'Login attempt - Client: {ANGEL_CLIENT_ID}, TOTP: {totp}')
            
            # Make request
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json=payload,
                headers=headers,
                timeout=15
            )
            
            details['response_status'] = r.status_code
            details['response_headers'] = dict(r.headers)
            
            try:
                response_json = r.json()
                details['response_body'] = response_json
            except:
                details['response_body'] = r.text
            
            logger.info(f'Login response: {r.status_code} - {r.text[:200]}')
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status'):
                    self.token = data['data']['jwtToken']
                    logger.info('Login SUCCESS!')
                    if return_details:
                        return True, 'Success', details
                    return True, 'Success', {}
                else:
                    error = data.get('message', 'Unknown error')
                    logger.error(f'Login failed: {error}')
                    if return_details:
                        return False, error, details
                    return False, error, {}
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
                        return None, None, 'No data in response'
                else:
                    error = data.get('message', 'Unknown error')
                    return None, None, error
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

async def super_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super detailed debug with full API details"""
    msg = 'SUPER DEBUG\n' + '='*30 + '\n\n'
    
    # Credentials
    msg += 'CREDENTIALS:\n'
    msg += f'API_KEY: {ANGEL_API_KEY[:4]}...{ANGEL_API_KEY[-4:]} ({len(ANGEL_API_KEY)} chars)\n'
    msg += f'CLIENT_ID: {ANGEL_CLIENT_ID}\n'
    msg += f'PASSWORD: {len(ANGEL_PASSWORD)} chars\n'
    msg += f'TOTP_SECRET: {len(ANGEL_TOTP_SECRET)} chars\n\n'
    
    # TOTP Test
    msg += 'TOTP TEST:\n'
    totp1 = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
    msg += f'Generated: {totp1}\n'
    msg += f'Length: {len(totp1)}\n'
    msg += f'Format: {"OK" if len(totp1) == 6 and totp1.isdigit() else "ERROR"}\n\n'
    
    await update.message.reply_text(msg)
    
    # Login attempt with full details
    msg2 = 'LOGIN ATTEMPT:\n' + '='*30 + '\n\n'
    
    success, error, details = angel.login(return_details=True)
    
    msg2 += f'Status: {"✅ SUCCESS" if success else "❌ FAILED"}\n'
    msg2 += f'Error: {error}\n\n'
    
    if details:
        msg2 += 'REQUEST:\n'
        msg2 += f'URL: {details.get("request_url", "N/A")}\n'
        msg2 += f'Client: {ANGEL_CLIENT_ID}\n'
        msg2 += f'TOTP: {details.get("totp_generated", "N/A")}\n\n'
        
        msg2 += 'RESPONSE:\n'
        msg2 += f'Status: {details.get("response_status", "N/A")}\n'
        
        resp_body = details.get("response_body", {})
        if isinstance(resp_body, dict):
            msg2 += f'Message: {resp_body.get("message", "N/A")}\n'
            msg2 += f'Status: {resp_body.get("status", "N/A")}\n'
            if 'errorcode' in resp_body:
                msg2 += f'Error Code: {resp_body.get("errorcode")}\n'
        else:
            msg2 += f'Body: {str(resp_body)[:200]}\n'
    
    await update.message.reply_text(msg2)
    
    # Additional info
    msg3 = '\nPOSSIBLE ISSUES:\n'
    msg3 += '1. TOTP timing off (retry in 30sec)\n'
    msg3 += '2. Wrong password format\n'
    msg3 += '3. Account locked/disabled\n'
    msg3 += '4. API key expired\n\n'
    msg3 += 'Try logging in at:\nsmartapi.angelone.in'
    
    await update.message.reply_text(msg3)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Standard debug"""
    msg = 'DEBUG INFO\n' + '='*30 + '\n\n'
    
    msg += 'CREDENTIALS:\n'
    msg += f'API_KEY: {"✅" if ANGEL_API_KEY else "❌"}\n'
    msg += f'CLIENT_ID: {"✅" if ANGEL_CLIENT_ID else "❌"}\n'
    msg += f'PASSWORD: {"✅" if ANGEL_PASSWORD else "❌"}\n'
    msg += f'TOTP_SECRET: {"✅" if ANGEL_TOTP_SECRET else "❌"}\n\n'
    
    msg += 'LOGIN TEST:\n'
    success, error, _ = angel.login()
    if success:
        msg += '✅ Login SUCCESS!\n\n'
        
        msg += 'NSE TEST:\n'
        price, change, err = angel.get_price('99926000', 'NSE')
        if price:
            msg += f'✅ NIFTY: Rs{price:,.2f} ({change:+.2f}%)\n'
        else:
            msg += f'❌ Error: {err}\n'
    else:
        msg += f'❌ Login FAILED!\n'
        msg += f'Error: {error}\n\n'
        msg += 'Use /superdebug for details'
    
    await update.message.reply_text(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI Bot - SUPER DEBUG\n\n'
    msg += '/debug - Quick debug\n'
    msg += '/superdebug - Full details\n'
    msg += '/markets - Live prices\n'
    msg += '/recommend - Best trade\n\n'
    msg += 'Version: SUPER_DEBUG_v1'
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
    
    logger.info('='*50)
    logger.info('STARTING SUPER DEBUG BOT')
    logger.info('='*50)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('debug', debug))
    app.add_handler(CommandHandler('superdebug', super_debug))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('recommend', recommend))
    
    logger.info('Super debug bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
          
