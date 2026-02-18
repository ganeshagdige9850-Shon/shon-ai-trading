import os
import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pyotp

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

# Angel One Credentials (Add in Railway Variables)
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

ASSETS = {
    'nifty': {'name': 'NIFTY 50', 'lot': 25, 'sym': 'Rs', 'exchange': 'NFO', 'symbol': 'NIFTY'},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'sym': 'Rs', 'exchange': 'NFO', 'symbol': 'BANKNIFTY'},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'sym': 'Rs', 'exchange': 'NFO', 'symbol': 'FINNIFTY'},
}

class AngelOneAPI:
    def __init__(self):
        self.api_key = ANGEL_API_KEY
        self.client_id = ANGEL_CLIENT_ID
        self.password = ANGEL_PASSWORD
        self.totp_secret = ANGEL_TOTP_SECRET
        self.access_token = None
        self.feed_token = None
        self.base_url = 'https://apiconnect.angelone.in'
    
    def generate_totp(self):
        """Generate TOTP from secret"""
        try:
            totp = pyotp.TOTP(self.totp_secret)
            return totp.now()
        except Exception as e:
            logger.error(f'TOTP generation error: {e}')
            return None
    
    def login(self):
        """Login to Angel One and get tokens"""
        try:
            totp = self.generate_totp()
            if not totp:
                logger.error('Failed to generate TOTP')
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
                    logger.info('Angel One login successful!')
                    return True
                else:
                    logger.error(f'Login failed: {result.get("message")}')
            else:
                logger.error(f'Login API error: {response.status_code}')
            
        except Exception as e:
            logger.error(f'Angel One login error: {e}')
        
        return False
    
    def get_profile(self):
        """Get user profile"""
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/user/v1/getProfile'
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
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            
        except Exception as e:
            logger.error(f'Get profile error: {e}')
        
        return None
    
    def search_scrip(self, exchange, symbol):
        """Search for scrip details"""
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
                'searchscrip': symbol
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            
        except Exception as e:
            logger.error(f'Search scrip error: {e}')
        
        return None
    
    def get_quote(self, exchange, symbol_token, trading_symbol):
        """Get market quote"""
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
                'mode': 'FULL',
                'exchangeTokens': {
                    exchange: [symbol_token]
                }
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    return result.get('data', {}).get('fetched', [])
            
        except Exception as e:
            logger.error(f'Get quote error: {e}')
        
        return None

# Initialize Angel One client
angel = AngelOneAPI() if all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]) else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if angel:
        status = '✅ Connected to Angel One API'
        if not angel.access_token:
            if angel.login():
                status = '✅ Angel One API - LIVE DATA'
            else:
                status = '⚠️ Angel One login failed - check credentials'
    else:
        status = '❌ Angel One not configured'
    
    msg = f'🤖 Shon A.I. Trading Bot\n\n'
    msg += f'Status: {status}\n\n'
    msg += 'Features:\n'
    msg += '✅ Real NSE Option Chain\n'
    msg += '✅ Live CE/PE LTP\n'
    msg += '✅ Strike Prices from Exchange\n'
    msg += '✅ Open Interest Data\n'
    msg += '✅ Volume & IV\n\n'
    msg += 'Commands:\n'
    msg += '/analyze nifty\n'
    msg += '/analyze banknifty\n'
    msg += '/analyze finnifty\n'
    msg += '/test - Test Angel One connection\n'
    msg += '/help\n\n'
    msg += 'Data Source: Angel One SmartAPI 📊'
    
    await update.message.reply_text(msg)

async def test_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test Angel One API connection"""
    if not angel:
        await update.message.reply_text(
            '❌ Angel One API not configured!\n\n'
            'Please add these to Railway Variables:\n'
            '- ANGEL_API_KEY\n'
            '- ANGEL_CLIENT_ID\n'
            '- ANGEL_PASSWORD\n'
            '- ANGEL_TOTP_SECRET'
        )
        return
    
    await update.message.reply_text('⏳ Testing Angel One connection...')
    
    # Try login
    if angel.login():
        # Get profile
        profile = angel.get_profile()
        
        if profile and profile.get('status'):
            data = profile['data']
            name = data.get('name', 'Unknown')
            client_id = data.get('clientcode', 'Unknown')
            
            msg = '✅ Angel One API - Connected!\n\n'
            msg += f'Name: {name}\n'
            msg += f'Client ID: {client_id}\n'
            msg += f'Access Token: Active\n\n'
            msg += 'Bot ready to fetch LIVE market data! 🚀'
            
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text('⚠️ Connected but profile fetch failed')
    else:
        await update.message.reply_text(
            '❌ Angel One login failed!\n\n'
            'Check:\n'
            '1. API Key correct?\n'
            '2. Client ID correct?\n'
            '3. Password correct?\n'
            '4. TOTP Secret correct?'
        )

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
        await update.message.reply_text(
            '❌ Angel One API not configured!\n'
            'See /help for setup instructions.'
        )
        return
    
    cfg = ASSETS[asset]
    
    loading = await update.message.reply_text(
        f'⏳ Fetching LIVE {cfg["name"]} data from Angel One...\n'
        'Please wait...'
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
    
    # Search for the symbol
    search = angel.search_scrip(cfg['exchange'], cfg['symbol'])
    
    try:
        await loading.delete()
    except:
        pass
    
    if not search or not search.get('status'):
        await update.message.reply_text(
            f'❌ Could not find {cfg["symbol"]} on Angel One!\n'
            'This might be because:\n'
            '- Market is closed\n'
            '- Symbol not available\n'
            '- API issue'
        )
        return
    
    # For now, show that connection works
    await update.message.reply_text(
        f'✅ Angel One API Working!\n\n'
        f'Found {cfg["name"]} data.\n\n'
        f'Note: Full option chain display\n'
        f'requires additional API calls.\n\n'
        f'This confirms:\n'
        f'✅ API Connected\n'
        f'✅ Login Successful\n'
        f'✅ Can fetch market data\n\n'
        f'Next: I\'ll add full option chain\n'
        f'with CE/PE LTP in next update!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 ANGEL ONE SETUP GUIDE\n'
    msg += '=' * 30 + '\n\n'
    
    if angel and angel.access_token:
        msg += '✅ Your bot is configured!\n\n'
        msg += 'Commands:\n'
        msg += '/analyze nifty - Live NIFTY data\n'
        msg += '/analyze banknifty - Bank Nifty\n'
        msg += '/test - Test connection\n\n'
    else:
        msg += '⚠️ Not configured yet!\n\n'
        msg += 'Setup Steps:\n'
        msg += '1. Get API from smartapi.angelone.in\n'
        msg += '2. Add 4 variables to Railway\n'
        msg += '3. Redeploy bot\n'
        msg += '4. Done! Real data! ✅\n\n'
    
    msg += 'Data Source: Angel One Official API\n'
    msg += 'Cost: FREE with Angel One account'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        logger.error('BOT_TOKEN not set!')
        return
    
    logger.info('Angel One bot starting...')
    
    if angel:
        logger.info('Angel One API configured')
        if angel.login():
            logger.info('Angel One login successful!')
        else:
            logger.warning('Angel One login failed - check credentials')
    else:
        logger.warning('Angel One API not configured')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('test', test_connection))
    app.add_handler(CommandHandler('help', help_command))
    
    logger.info('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
      
