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

ASSETS = {
    'nifty': {
        'name': 'NIFTY 50',
        'lot': 25,
        'sym': 'Rs',
        'exchange': 'NFO',
        'symbol': 'NIFTY',
        'index_token': '99926000',
        'gap': 50
    },
    'banknifty': {
        'name': 'BANK NIFTY',
        'lot': 15,
        'sym': 'Rs',
        'exchange': 'NFO',
        'symbol': 'BANKNIFTY',
        'index_token': '99926009',
        'gap': 100
    },
    'finnifty': {
        'name': 'FIN NIFTY',
        'lot': 25,
        'sym': 'Rs',
        'exchange': 'NFO',
        'symbol': 'FINNIFTY',
        'index_token': '99926037',
        'gap': 50
    }
}

class AngelOneAPI:
    def __init__(self):
        self.api_key = ANGEL_API_KEY
        self.client_id = ANGEL_CLIENT_ID
        self.password = ANGEL_PASSWORD
        self.totp_secret = ANGEL_TOTP_SECRET
        self.access_token = None
        self.feed_token = None
        self.refresh_token = None
        self.base_url = 'https://apiconnect.angelone.in'
    
    def generate_totp(self):
        try:
            totp = pyotp.TOTP(self.totp_secret)
            return totp.now()
        except Exception as e:
            logger.error(f'TOTP error: {e}')
            return None
    
    def login(self):
        try:
            totp = self.generate_totp()
            if not totp:
                return False
            
            url = f'{self.base_url}/rest/auth/angelbroking/user/v1/loginByPassword'
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': '192.168.1.1',
                'X-ClientPublicIP': '106.193.147.98',
                'X-MACAddress': '00:00:00:00:00:00',
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
                    self.feed_token = result['data']['feedToken']
                    self.refresh_token = result['data']['refreshToken']
                    logger.info('Angel One login successful')
                    return True
                else:
                    logger.error(f'Login failed: {result.get("message")}')
            
        except Exception as e:
            logger.error(f'Login error: {e}')
        
        return False
    
    def get_ltp_data(self, exchange, symbol_token):
        """Get LTP for a single instrument"""
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/market/v1/quote/'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': '192.168.1.1',
                'X-ClientPublicIP': '106.193.147.98',
                'X-MACAddress': '00:00:00:00:00:00',
                'X-PrivateKey': self.api_key
            }
            data = {
                'mode': 'LTP',
                'exchangeTokens': {
                    exchange: [symbol_token]
                }
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') and result.get('data'):
                    fetched = result['data'].get('fetched', [])
                    if fetched:
                        return fetched[0]
            
        except Exception as e:
            logger.error(f'LTP error: {e}')
        
        return None
    
    def search_scrip(self, exchange, searchtext):
        """Search for instrument"""
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/order/v1/searchScrip'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': '192.168.1.1',
                'X-ClientPublicIP': '106.193.147.98',
                'X-MACAddress': '00:00:00:00:00:00',
                'X-PrivateKey': self.api_key
            }
            data = {
                'exchange': exchange,
                'searchscrip': searchtext
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    return result.get('data', [])
            
        except Exception as e:
            logger.error(f'Search error: {e}')
        
        return None

angel = AngelOneAPI() if all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]) else None

def get_next_thursday():
    """Get next weekly expiry (Thursday)"""
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)

def get_monthly_expiry():
    """Get monthly expiry (last Thursday)"""
    today = datetime.now()
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1)
    else:
        next_month = datetime(today.year, today.month + 1, 1)
    last_day = next_month - timedelta(days=1)
    days_back = (last_day.weekday() - 3) % 7
    expiry = last_day - timedelta(days=days_back)
    
    if expiry < today:
        if expiry.month == 12:
            next_next = datetime(expiry.year + 1, 1, 1)
        else:
            next_next = datetime(expiry.year, expiry.month + 1, 1)
        last_day = next_next - timedelta(days=1)
        days_back = (last_day.weekday() - 3) % 7
        expiry = last_day - timedelta(days=days_back)
    
    return expiry

def format_expiry_for_symbol(date):
    """Format date for option symbol: DDMMMYY"""
    return date.strftime('%d%b%y').upper()

def construct_option_symbol(base_symbol, strike, option_type, expiry_date):
    """Construct Angel One option symbol format"""
    expiry_str = format_expiry_for_symbol(expiry_date)
    strike_int = int(strike)
    return f'{base_symbol}{expiry_str}{strike_int}{option_type}'

def get_spot_price(asset_config):
    """Get spot price for index"""
    if not angel or not angel.access_token:
        if not angel.login():
            return None
    
    token = asset_config['index_token']
    data = angel.get_ltp_data('NSE', token)
    
    if data and 'ltp' in data:
        return float(data['ltp'])
    
    return None

def get_option_data(asset, strike, option_type, expiry):
    """Get option LTP and details"""
    if not angel:
        return None
    
    cfg = ASSETS[asset]
    symbol = construct_option_symbol(cfg['symbol'], strike, option_type, expiry)
    
    # Search for the option
    results = angel.search_scrip(cfg['exchange'], symbol)
    
    if results:
        for item in results:
            if item.get('tradingsymbol') == symbol:
                token = item.get('symboltoken')
                if token:
                    # Get LTP
                    ltp_data = angel.get_ltp_data(cfg['exchange'], token)
                    if ltp_data:
                        return {
                            'symbol': symbol,
                            'token': token,
                            'ltp': float(ltp_data.get('ltp', 0)),
                            'strike': strike,
                            'type': option_type
                        }
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if angel and angel.access_token:
        status = '✅ Angel One - LIVE DATA'
    elif angel:
        if angel.login():
            status = '✅ Angel One - LIVE DATA'
        else:
            status = '⚠️ Angel One login failed'
    else:
        status = '❌ Not configured'
    
    msg = f'🤖 Shon A.I. Real-time Bot\n\n'
    msg += f'Status: {status}\n\n'
    msg += 'Features:\n'
    msg += '✅ Real NSE Spot Price\n'
    msg += '✅ Live CE/PE LTP\n'
    msg += '✅ Multiple Strike Options\n'
    msg += '✅ Investment per Lot\n'
    msg += '✅ Weekly/Monthly Expiry\n\n'
    msg += 'Commands:\n'
    msg += '/analyze nifty\n'
    msg += '/analyze banknifty\n'
    msg += '/analyze finnifty\n'
    msg += '/test\n'
    msg += '/help\n\n'
    msg += 'Data: Angel One SmartAPI'
    
    await update.message.reply_text(msg)

async def test_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not angel:
        await update.message.reply_text('❌ Angel One not configured!')
        return
    
    await update.message.reply_text('⏳ Testing connection...')
    
    if angel.login():
        # Test spot price fetch
        spot = get_spot_price(ASSETS['nifty'])
        
        if spot:
            msg = '✅ Angel One API - Fully Working!\n\n'
            msg += f'Test: NIFTY Spot = Rs{spot:,.2f}\n'
            msg += f'Login: Success\n'
            msg += f'Token: Active\n\n'
            msg += 'Ready for full option chain! 🚀'
        else:
            msg = '⚠️ Login OK but data fetch issue'
        
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text('❌ Login failed!')

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            'Use: /analyze [asset]\n\n'
            'Examples:\n'
            '/analyze nifty\n'
            '/analyze banknifty\n'
            '/analyze finnifty'
        )
        return
    
    asset = args[0].lower()
    
    if asset not in ASSETS:
        await update.message.reply_text(f'{asset} not supported!')
        return
    
    if not angel:
        await update.message.reply_text('❌ Angel One not configured!')
        return
    
    cfg = ASSETS[asset]
    
    loading = await update.message.reply_text(
        f'⏳ Fetching LIVE {cfg["name"]} option chain...\n'
        f'This may take 10-15 seconds...'
    )
    
    # Login if needed
    if not angel.access_token:
        if not angel.login():
            try:
                await loading.delete()
            except:
                pass
            await update.message.reply_text('❌ Angel One login failed!')
            return
    
    # Get spot price
    spot = get_spot_price(cfg)
    
    if not spot:
        try:
            await loading.delete()
        except:
            pass
        await update.message.reply_text('❌ Could not fetch spot price!')
        return
    
    # Calculate ATM and nearby strikes
    gap = cfg['gap']
    atm = round(spot / gap) * gap
    
    # Get weekly expiry
    expiry = get_next_thursday()
    
    # Define strikes to fetch
    strikes = [
        atm - gap,      # ITM-1
        atm,            # ATM
        atm + gap,      # OTM-1
        atm + 2 * gap   # OTM-2
    ]
    
    # Fetch option data for each strike
    option_data = []
    
    for strike in strikes:
        # Get CE data
        ce_data = get_option_data(asset, strike, 'CE', expiry)
        
        # Get PE data
        pe_data = get_option_data(asset, strike, 'PE', expiry)
        
        if ce_data or pe_data:
            option_data.append({
                'strike': strike,
                'ce': ce_data,
                'pe': pe_data
            })
    
    try:
        await loading.delete()
    except:
        pass
    
    if not option_data:
        await update.message.reply_text(
            '⚠️ Could not fetch option chain!\n\n'
            'Possible reasons:\n'
            '- Market closed\n'
            '- Expiry mismatch\n'
            '- Symbol format issue\n\n'
            f'Spot: Rs{spot:,.2f} (fetched OK)'
        )
        return
    
    # Build response
    sym = cfg['sym']
    lot = cfg['lot']
    now = datetime.now().strftime('%d-%b %I:%M%p')
    expiry_str = expiry.strftime('%d-%b-%Y')
    
    lines = []
    lines.append('═' * 40)
    lines.append(f'📊 {cfg["name"]} OPTION CHAIN')
    lines.append('═' * 40)
    lines.append(f'Spot: {sym}{spot:,.2f}')
    lines.append(f'Time: {now}')
    lines.append(f'Expiry: {expiry_str}')
    lines.append(f'Data: Angel One (LIVE)')
    lines.append('')
    
    # Determine signal
    if spot > atm:
        signal = 'BULLISH'
        conf = 70
    elif spot < atm:
        signal = 'BEARISH'
        conf = 70
    else:
        signal = 'NEUTRAL'
        conf = 55
    
    lines.append(f'🎯 SIGNAL: {signal} ({conf}%)')
    lines.append('')
    lines.append('━' * 40)
    lines.append('LIVE OPTIONS DATA')
    lines.append('━' * 40)
    
    # Display each strike
    for item in option_data:
        strike = item['strike']
        ce = item.get('ce')
        pe = item.get('pe')
        
        # Determine position
        if strike < atm:
            pos = 'ITM'
        elif strike == atm:
            pos = 'ATM'
        else:
            pos = f'OTM-{int((strike - atm) / gap)}'
        
        lines.append('')
        lines.append(f'{pos} - Strike: {sym}{strike}')
        lines.append('')
        
        # CE data
        if ce:
            ce_ltp = ce['ltp']
            ce_inv = ce_ltp * lot
            lines.append(f'  📈 CALL (CE):')
            lines.append(f'     LTP: {sym}{ce_ltp:,.2f}')
            lines.append(f'     Investment: {sym}{ce_inv:,.0f} (1 lot)')
            lines.append(f'     Symbol: {ce["symbol"]}')
        else:
            lines.append(f'  📈 CALL (CE): No data')
        
        lines.append('')
        
        # PE data
        if pe:
            pe_ltp = pe['ltp']
            pe_inv = pe_ltp * lot
            lines.append(f'  📉 PUT (PE):')
            lines.append(f'     LTP: {sym}{pe_ltp:,.2f}')
            lines.append(f'     Investment: {sym}{pe_inv:,.0f} (1 lot)')
            lines.append(f'     Symbol: {pe["symbol"]}')
        else:
            lines.append(f'  📉 PUT (PE): No data')
    
    lines.append('')
    lines.append('━' * 40)
    lines.append('RECOMMENDATION')
    lines.append('━' * 40)
    lines.append('')
    
    if signal == 'BULLISH':
        lines.append('✅ BUY CALL (CE) OPTIONS')
        lines.append(f'Best: ATM ({sym}{atm}) or OTM-1 CE')
        lines.append('Reason: Spot above ATM - Bullish')
    elif signal == 'BEARISH':
        lines.append('✅ BUY PUT (PE) OPTIONS')
        lines.append(f'Best: ATM ({sym}{atm}) or OTM-1 PE')
        lines.append('Reason: Spot below ATM - Bearish')
    else:
        lines.append('⏸️ WAIT FOR CLEAR DIRECTION')
        lines.append('Spot at ATM - Market neutral')
    
    lines.append('')
    lines.append(f'Lot Size: {lot} qty')
    lines.append('Stop Loss: 30% of LTP')
    lines.append('Target: 60-80% profit')
    lines.append('')
    lines.append('⚠️ Educational only!')
    lines.append('All prices LIVE from NSE via Angel One')
    lines.append('═' * 40)
    
    msg = '\n'.join(lines)
    
    # Split if too long
    if len(msg) > 4000:
        await update.message.reply_text(msg[:4000])
        await update.message.reply_text(msg[4000:])
    else:
        await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 HELP\n'
    msg += '═' * 30 + '\n\n'
    msg += 'Commands:\n'
    msg += '/analyze nifty - Full option chain\n'
    msg += '/analyze banknifty - Bank Nifty\n'
    msg += '/analyze finnifty - Fin Nifty\n'
    msg += '/test - Test connection\n\n'
    msg += 'Features:\n'
    msg += '✅ Real spot price from NSE\n'
    msg += '✅ Live CE/PE LTP\n'
    msg += '✅ Multiple strikes (ITM/ATM/OTM)\n'
    msg += '✅ Investment per lot\n'
    msg += '✅ Weekly expiry auto-detect\n\n'
    msg += 'Data: Angel One SmartAPI\n'
    msg += 'Update: Every command (live)\n'
    msg += 'Cost: FREE'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        logger.error('BOT_TOKEN not set!')
        return
    
    logger.info('Starting Angel One full option chain bot...')
    
    if angel:
        logger.info('Angel One configured')
    else:
        logger.warning('Angel One not configured')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('test', test_connection))
    app.add_handler(CommandHandler('help', help_command))
    
    logger.info('Bot running with full option chain!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
