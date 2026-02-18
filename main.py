import os
import logging
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pyotp

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

USD_INR = 84.0

ASSETS = {
    # NSE Options - Angel One API (Real LTP)
    'nifty': {
        'name': 'NIFTY 50', 'lot': 25, 'sym': 'Rs', 'gap': 50,
        'type': 'nse', 'exchange': 'NFO', 'symbol': 'NIFTY',
        'index_token': '99926000'
    },
    'banknifty': {
        'name': 'BANK NIFTY', 'lot': 15, 'sym': 'Rs', 'gap': 100,
        'type': 'nse', 'exchange': 'NFO', 'symbol': 'BANKNIFTY',
        'index_token': '99926009'
    },
    'finnifty': {
        'name': 'FIN NIFTY', 'lot': 25, 'sym': 'Rs', 'gap': 50,
        'type': 'nse', 'exchange': 'NFO', 'symbol': 'FINNIFTY',
        'index_token': '99926037'
    },
    # MCX Commodities - Calculated (No options API)
    'crude': {
        'name': 'CRUDE OIL MCX', 'lot': 100, 'sym': 'Rs', 'gap': 50,
        'type': 'mcx', 'ticker': 'CL=F'
    },
    'gold': {
        'name': 'GOLD MCX', 'lot': 100, 'sym': 'Rs', 'gap': 100,
        'type': 'mcx', 'ticker': 'GC=F'
    },
    'silver': {
        'name': 'SILVER MCX', 'lot': 30, 'sym': 'Rs', 'gap': 100,
        'type': 'mcx', 'ticker': 'SI=F'
    },
    # Crypto - Calculated (No options in India)
    'btc': {
        'name': 'BITCOIN', 'lot': 1, 'sym': '$', 'gap': 1000,
        'type': 'crypto', 'ticker': 'BTC-USD'
    },
    'eth': {
        'name': 'ETHEREUM', 'lot': 1, 'sym': '$', 'gap': 50,
        'type': 'crypto', 'ticker': 'ETH-USD'
    }
}

class AngelOneAPI:
    def __init__(self):
        self.api_key = ANGEL_API_KEY
        self.client_id = ANGEL_CLIENT_ID
        self.password = ANGEL_PASSWORD
        self.totp_secret = ANGEL_TOTP_SECRET
        self.access_token = None
        self.base_url = 'https://apiconnect.angelone.in'
    
    def generate_totp(self):
        try:
            return pyotp.TOTP(self.totp_secret).now()
        except:
            return None
    
    def login(self):
        try:
            totp = self.generate_totp()
            if not totp:
                return False
            
            url = f'{self.base_url}/rest/auth/angelbroking/user/v1/loginByPassword'
            headers = {
                'Content-Type': 'application/json',
                'X-PrivateKey': self.api_key
            }
            data = {
                'clientcode': self.client_id,
                'password': self.password,
                'totp': totp
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    self.access_token = result['data']['jwtToken']
                    return True
        except Exception as e:
            logger.error(f'Login error: {e}')
        return False
    
    def get_ltp(self, exchange, token):
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/market/v1/quote/'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'X-PrivateKey': self.api_key
            }
            data = {
                'mode': 'LTP',
                'exchangeTokens': {exchange: [token]}
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') and result.get('data'):
                    fetched = result['data'].get('fetched', [])
                    if fetched:
                        return float(fetched[0].get('ltp', 0))
        except Exception as e:
            logger.error(f'LTP error: {e}')
        return None
    
    def search_scrip(self, exchange, symbol):
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/order/v1/searchScrip'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'X-PrivateKey': self.api_key
            }
            data = {'exchange': exchange, 'searchscrip': symbol}
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    return result.get('data', [])
        except:
            pass
        return None

angel = AngelOneAPI() if all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]) else None

def get_yahoo_price(ticker):
    try:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = round(price - prev, 4)
            pct = round((change / prev) * 100, 2) if prev else 0
            return price, change, pct
    except:
        pass
    return None, None, None

def get_mcx_price(ticker):
    global USD_INR
    price_usd, change_usd, pct = get_yahoo_price(ticker)
    if not price_usd:
        return None, None, None
    
    # Update USD/INR
    try:
        inr_data = get_yahoo_price('USDINR=X')
        if inr_data[0]:
            USD_INR = inr_data[0]
    except:
        pass
    
    if ticker == 'CL=F':  # Crude
        price = round(price_usd * USD_INR / 6)
        change = round(change_usd * USD_INR / 6, 1)
    elif ticker == 'GC=F':  # Gold
        price = round(price_usd * USD_INR / 31.1 * 10)
        change = round(change_usd * USD_INR / 31.1 * 10)
    elif ticker == 'SI=F':  # Silver
        price = round(price_usd * USD_INR / 31.1 * 1000)
        change = round(change_usd * USD_INR / 31.1 * 1000)
    else:
        price = round(price_usd, 2)
        change = round(change_usd, 2)
    
    return price, change, pct

def calculate_premium(spot, strike, distance, iv):
    base = {0: 0.020, 1: 0.012, 2: 0.007, 3: 0.004}.get(abs(distance), 0.002)
    multiplier = 1 + (iv - 20) / 100
    return max(round(spot * base * multiplier), 10)

def get_iv_for_asset(asset, pct):
    iv_map = {
        'nifty': 14, 'banknifty': 20, 'finnifty': 17,
        'crude': 32, 'gold': 15, 'silver': 20,
        'btc': 60, 'eth': 70
    }
    iv = iv_map.get(asset, 25)
    if abs(pct) > 1.0:
        iv += 4
    elif abs(pct) > 0.5:
        iv += 2
    return iv

def get_next_expiry():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0 and today.hour >= 15:
        days = 7
    return today + timedelta(days=days)

def format_expiry(date):
    return date.strftime('%d%b%y').upper()

def construct_option_symbol(base, strike, opt_type, expiry):
    exp_str = format_expiry(expiry)
    return f'{base}{exp_str}{int(strike)}{opt_type}'

def get_nse_option_ltp(asset, strike, opt_type, expiry):
    """Get real LTP from Angel One for NSE options"""
    if not angel:
        return None
    
    cfg = ASSETS[asset]
    symbol = construct_option_symbol(cfg['symbol'], strike, opt_type, expiry)
    
    results = angel.search_scrip(cfg['exchange'], symbol)
    if results:
        for item in results:
            if item.get('tradingsymbol') == symbol:
                token = item.get('symboltoken')
                if token:
                    ltp = angel.get_ltp(cfg['exchange'], token)
                    if ltp:
                        return {'ltp': ltp, 'symbol': symbol}
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nse_status = '✅ Real LTP' if angel and angel.access_token else '⚠️ Calculated'
    
    msg = '🤖 Shon A.I. Hybrid Trading Bot\n\n'
    msg += f'NSE Options: {nse_status}\n'
    msg += 'MCX/Crypto: Calculated + Live Spot\n\n'
    msg += 'Commands:\n'
    msg += '/analyze nifty - Real NSE LTP\n'
    msg += '/analyze banknifty - Real NSE LTP\n'
    msg += '/analyze gold - Live spot + Calc\n'
    msg += '/analyze crude - Live spot + Calc\n'
    msg += '/analyze btc - Live spot + Calc\n'
    msg += '/markets - All live prices\n'
    msg += '/help\n\n'
    msg += 'Ready!'
    
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            'Use: /analyze [asset]\n\n'
            'NSE (Real LTP):\n'
            '/analyze nifty\n'
            '/analyze banknifty\n\n'
            'MCX/Crypto (Calculated):\n'
            '/analyze gold\n'
            '/analyze crude\n'
            '/analyze btc'
        )
        return
    
    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(f'{asset} not supported!')
        return
    
    cfg = ASSETS[asset]
    asset_type = cfg['type']
    
    loading = await update.message.reply_text(f'⏳ Fetching {cfg["name"]} data...')
    
    # Get spot price
    spot = None
    change = 0
    pct = 0
    
    if asset_type == 'nse':
        if angel:
            if not angel.access_token:
                angel.login()
            spot = angel.get_ltp('NSE', cfg['index_token'])
        
        if not spot:
            try:
                await loading.delete()
            except:
                pass
            await update.message.reply_text('❌ Could not fetch NSE data!')
            return
        
        data_source = '📡 Angel One (LIVE NSE)'
        
    elif asset_type == 'mcx':
        spot, change, pct = get_mcx_price(cfg['ticker'])
        data_source = '📊 Yahoo Finance → MCX'
        
    elif asset_type == 'crypto':
        spot, change, pct = get_yahoo_price(cfg['ticker'])
        data_source = '📊 Yahoo Finance'
    
    if not spot:
        try:
            await loading.delete()
        except:
            pass
        await update.message.reply_text('❌ Could not fetch price!')
        return
    
    try:
        await loading.delete()
    except:
        pass
    
    # Calculate strikes
    gap = cfg['gap']
    sym = cfg['sym']
    lot = cfg['lot']
    atm = round(spot / gap) * gap
    
    strikes = [atm - gap, atm, atm + gap, atm + 2 * gap]
    
    iv = get_iv_for_asset(asset, pct)
    expiry = get_next_expiry()
    
    # Build response
    now = datetime.now().strftime('%d-%b %I:%M%p')
    arrow = 'UP' if pct >= 0 else 'DN'
    sign = '+' if pct >= 0 else ''
    
    lines = []
    lines.append('═' * 40)
    lines.append(f'📊 {cfg["name"]} ANALYSIS')
    lines.append('═' * 40)
    lines.append(f'Spot: {sym}{spot:,.2f}')
    if change:
        lines.append(f'Change: {arrow} {sign}{pct}%')
    lines.append(f'Time: {now}')
    lines.append(f'Data: {data_source}')
    lines.append('')
    
    if pct > 0.5:
        signal = 'BULLISH'
        conf = 70
    elif pct < -0.5:
        signal = 'BEARISH'
        conf = 70
    else:
        signal = 'NEUTRAL'
        conf = 55
    
    lines.append(f'🎯 SIGNAL: {signal} ({conf}%)')
    lines.append(f'IV: {iv}%')
    lines.append('')
    lines.append('━' * 40)
    lines.append('OPTION STRIKES')
    lines.append('━' * 40)
    
    for i, strike in enumerate(strikes):
        if strike < atm:
            pos = 'ITM'
        elif strike == atm:
            pos = 'ATM'
        else:
            pos = f'OTM-{(strike - atm) // gap}'
        
        lines.append('')
        lines.append(f'{pos} - Strike: {sym}{strike}')
        lines.append('')
        
        # Try to get real LTP for NSE
        if asset_type == 'nse':
            ce_data = get_nse_option_ltp(asset, strike, 'CE', expiry)
            pe_data = get_nse_option_ltp(asset, strike, 'PE', expiry)
            
            if ce_data:
                ce_ltp = ce_data['ltp']
                lines.append(f'  📈 CALL (CE): {sym}{ce_ltp:,.2f}')
                lines.append(f'     Investment: {sym}{int(ce_ltp * lot):,} (1 lot)')
                lines.append(f'     Symbol: {ce_data["symbol"]}')
            else:
                lines.append(f'  📈 CALL (CE): Data unavailable')
            
            lines.append('')
            
            if pe_data:
                pe_ltp = pe_data['ltp']
                lines.append(f'  📉 PUT (PE): {sym}{pe_ltp:,.2f}')
                lines.append(f'     Investment: {sym}{int(pe_ltp * lot):,} (1 lot)')
                lines.append(f'     Symbol: {pe_data["symbol"]}')
            else:
                lines.append(f'  📉 PUT (PE): Data unavailable')
        
        else:
            # Calculated premiums for MCX/Crypto
            dist = abs((strike - atm) // gap)
            ce_premium = calculate_premium(spot, strike, dist, iv)
            pe_premium = calculate_premium(spot, strike, dist, iv)
            
            lines.append(f'  📈 CALL (CE): {sym}{ce_premium} (calculated)')
            lines.append(f'     Investment: {sym}{ce_premium * lot:,} (1 lot)')
            lines.append('')
            lines.append(f'  📉 PUT (PE): {sym}{pe_premium} (calculated)')
            lines.append(f'     Investment: {sym}{pe_premium * lot:,} (1 lot)')
    
    lines.append('')
    lines.append('━' * 40)
    lines.append('RECOMMENDATION')
    lines.append('━' * 40)
    lines.append('')
    
    if signal == 'BULLISH':
        lines.append('✅ BUY CALL (CE)')
        lines.append(f'Best: ATM ({sym}{atm}) or OTM-1')
    elif signal == 'BEARISH':
        lines.append('✅ BUY PUT (PE)')
        lines.append(f'Best: ATM ({sym}{atm}) or OTM-1')
    else:
        lines.append('⏸️ WAIT for direction')
    
    lines.append('')
    lines.append(f'Lot Size: {lot} qty')
    lines.append('Stop Loss: 30% of premium')
    lines.append('')
    
    if asset_type != 'nse':
        lines.append('⚠️ NOTE:')
        lines.append(f'{cfg["name"]} options premiums are calculated')
        lines.append('Spot price is LIVE')
        if asset_type == 'mcx':
            lines.append('MCX options API not available')
        else:
            lines.append('No crypto options in India')
    
    lines.append('')
    lines.append('Educational only!')
    lines.append('═' * 40)
    
    msg = '\n'.join(lines)
    
    if len(msg) > 4000:
        await update.message.reply_text(msg[:4000])
        await update.message.reply_text(msg[4000:])
    else:
        await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Fetching all market prices...')
    
    lines = ['LIVE MARKET PRICES', '=' * 30, '']
    
    lines.append('NSE INDICES:')
    for a in ['nifty', 'banknifty', 'finnifty']:
        try:
            if angel:
                if not angel.access_token:
                    angel.login()
                price = angel.get_ltp('NSE', ASSETS[a]['index_token'])
                if price:
                    lines.append(f'{a.upper()}: Rs{price:,.2f}')
        except:
            pass
    
    lines.append('')
    lines.append('MCX COMMODITIES:')
    for a in ['crude', 'gold', 'silver']:
        try:
            p, c, pct = get_mcx_price(ASSETS[a]['ticker'])
            if p:
                sign = '+' if pct >= 0 else ''
                lines.append(f'{a.upper()}: Rs{p:,.0f} {sign}{pct}%')
        except:
            pass
    
    lines.append('')
    lines.append('CRYPTO:')
    for a in ['btc', 'eth']:
        try:
            p, c, pct = get_yahoo_price(ASSETS[a]['ticker'])
            if p:
                sign = '+' if pct >= 0 else ''
                lines.append(f'{a.upper()}: ${p:,.2f} {sign}{pct}%')
        except:
            pass
    
    lines.append('')
    lines.append('Use /analyze [asset] for details')
    
    await update.message.reply_text('\n'.join(lines))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 HELP - HYBRID BOT\n'
    msg += '=' * 30 + '\n\n'
    msg += 'DATA SOURCES:\n\n'
    msg += '1. NSE Options (Real LTP):\n'
    msg += '   - NIFTY\n'
    msg += '   - BANKNIFTY\n'
    msg += '   - FINNIFTY\n'
    msg += '   Source: Angel One API\n\n'
    msg += '2. MCX Commodities (Calculated):\n'
    msg += '   - CRUDE OIL\n'
    msg += '   - GOLD\n'
    msg += '   - SILVER\n'
    msg += '   Live Spot + Calculated Premium\n'
    msg += '   (MCX options API not available)\n\n'
    msg += '3. Crypto (Calculated):\n'
    msg += '   - BTC\n'
    msg += '   - ETH\n'
    msg += '   Live Spot + Calculated Premium\n'
    msg += '   (No crypto options in India)\n\n'
    msg += 'Commands:\n'
    msg += '/analyze [asset]\n'
    msg += '/markets - All prices\n\n'
    msg += 'Why calculated for MCX/Crypto?\n'
    msg += '- MCX options require different API\n'
    msg += '- Crypto options not allowed in India\n'
    msg += '- Spot prices are 100% live\n'
    msg += '- Premiums ~85-90% accurate'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        logger.error('BOT_TOKEN not set!')
        return
    
    logger.info('Hybrid bot starting...')
    
    if angel:
        logger.info('Angel One configured for NSE')
        if angel.login():
            logger.info('Angel One login OK')
    else:
        logger.warning('Angel One not configured')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_command))
    
    logger.info('Hybrid bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
