"""
SHON AI AUTOMATED TRADING BOT - COMPACT VERSION
5-Min Scalping Strategy | Angel One API | Full Automation
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime, time
import asyncio
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

# Trading Config
TRADING_ENABLED = os.environ.get('TRADING_ENABLED', 'false').lower() == 'true'
CAPITAL = float(os.environ.get('TRADING_CAPITAL', '8000'))
MAX_POSITIONS = int(os.environ.get('MAX_POSITIONS', '2'))
DAILY_LOSS_LIMIT = float(os.environ.get('DAILY_LOSS_LIMIT', '0.15'))
MAX_CAPITAL_PER_TRADE = float(os.environ.get('MAX_CAPITAL_PER_TRADE', '0.6'))

# Constants
NIFTY_LOT = 25
STRIKE_GAP = 50
TARGET = 0.20
STOP_LOSS = 0.25

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
    
    def login(self):
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json={'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp},
                headers={'X-PrivateKey': ANGEL_API_KEY, 'Content-Type': 'application/json'},
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                if data.get('status'):
                    self.token = data['data']['jwtToken']
                    logger.info('✅ Login success')
                    return True
            logger.error(f'❌ Login failed: {r.status_code}')
            return False
        except Exception as e:
            logger.error(f'Login error: {e}')
            return False
    
    def get_ltp(self):
        if not self.token:
            self.login()
        try:
            r = requests.post(
                f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json={'mode': 'LTP', 'exchangeTokens': {'NSE': ['99926000']}},
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json',
                    'X-PrivateKey': ANGEL_API_KEY,
                    'X-UserType': 'USER',
                    'X-SourceID': 'WEB'
                },
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                if data.get('status') and data.get('data', {}).get('fetched'):
                    return float(data['data']['fetched'][0]['ltp'])
        except Exception as e:
            logger.error(f'LTP error: {e}')
        return None

class TradingBot:
    def __init__(self):
        self.angel = AngelAPI()
        self.positions = []
        self.daily_pnl = 0.0
        self.capital = CAPITAL
        self.history = deque(maxlen=10)
        self.active = TRADING_ENABLED
    
    def is_market_open(self):
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.time()
        return time(9, 15) <= t <= time(15, 30)
    
    def update_price(self):
        ltp = self.angel.get_ltp()
        if ltp:
            self.history.append({'time': datetime.now(), 'price': ltp})
            logger.info(f'Price: Rs{ltp:,.2f}')
            return True
        return False
    
    def detect_signal(self):
        if len(self.history) < 3:
            return None
        candles = list(self.history)[-3:]
        move1 = candles[1]['price'] - candles[0]['price']
        move2 = candles[2]['price'] - candles[1]['price']
        total = candles[2]['price'] - candles[0]['price']
        
        if move1 > 0 and move2 > 0 and total >= 10:
            return {'type': 'CALL', 'price': candles[2]['price'], 'strength': 'STRONG' if total > 30 else 'MODERATE'}
        if move1 < 0 and move2 < 0 and abs(total) >= 10:
            return {'type': 'PUT', 'price': candles[2]['price'], 'strength': 'STRONG' if abs(total) > 30 else 'MODERATE'}
        return None
    
    def can_trade(self):
        if len(self.positions) >= MAX_POSITIONS:
            return False, 'Max positions'
        if self.daily_pnl < -(self.capital * DAILY_LOSS_LIMIT):
            return False, 'Daily loss limit'
        if not self.active:
            return False, 'Trading disabled'
        return True, 'OK'
    
    async def execute_trade(self, signal, bot, chat_id):
        can, reason = self.can_trade()
        if not can:
            logger.info(f'Trade skipped: {reason}')
            return
        
        try:
            spot = signal['price']
            direction = signal['type']
            strike = int(round(spot / STRIKE_GAP) * STRIKE_GAP)
            lots = min(2, max(1, int((self.capital * MAX_CAPITAL_PER_TRADE) / (400 * NIFTY_LOT))))
            qty = lots * NIFTY_LOT
            
            position = {
                'type': direction,
                'strike': strike,
                'spot_entry': spot,
                'entry_time': datetime.now(),
                'lots': lots,
                'qty': qty,
                'entry_premium': 400,
                'status': 'OPEN'
            }
            
            self.positions.append(position)
            logger.info(f'📊 Trade: {direction} @ {strike} | Lots: {lots}')
            
            if bot and chat_id:
                await bot.send_message(chat_id, f"""
🤖 TRADE EXECUTED

{direction} @ {strike}
Spot: Rs{spot:,.0f}
Lots: {lots} ({qty} qty)
Investment: ~Rs{400 * qty:,}

Monitoring...
""")
        except Exception as e:
            logger.error(f'Execute error: {e}')
    
    async def monitor_positions(self, bot, chat_id):
        if not self.positions:
            return
        
        ltp = self.angel.get_ltp()
        if not ltp:
            return
        
        for pos in self.positions[:]:
            if pos['status'] != 'OPEN':
                continue
            
            move = ltp - pos['spot_entry']
            holding = (datetime.now() - pos['entry_time']).total_seconds() / 60
            should_exit = False
            reason = ''
            
            if pos['type'] == 'CALL':
                if move > 15:
                    should_exit, reason = True, 'TARGET'
                elif move < -10:
                    should_exit, reason = True, 'STOPLOSS'
            else:
                if move < -15:
                    should_exit, reason = True, 'TARGET'
                elif move > 10:
                    should_exit, reason = True, 'STOPLOSS'
            
            if holding > 30:
                should_exit, reason = True, 'TIME_EXIT'
            if not self.is_market_open():
                should_exit, reason = True, 'MARKET_CLOSE'
            
            if should_exit:
                await self.exit_position(pos, reason, bot, chat_id)
    
    async def exit_position(self, pos, reason, bot, chat_id):
        try:
            if reason == 'TARGET':
                pnl = pos['entry_premium'] * 0.20 * pos['qty']
            elif reason == 'STOPLOSS':
                pnl = pos['entry_premium'] * -0.25 * pos['qty']
            else:
                pnl = pos['entry_premium'] * 0.05 * pos['qty']
            
            self.daily_pnl += pnl
            self.capital += pnl
            pos['status'] = 'CLOSED'
            
            if pos in self.positions:
                self.positions.remove(pos)
            
            result = "✅ PROFIT" if pnl > 0 else "❌ LOSS"
            if bot and chat_id:
                await bot.send_message(chat_id, f"""
{result}

{pos['type']} @ {pos['strike']}
Reason: {reason}
P&L: Rs{pnl:+,.0f}

Capital: Rs{self.capital:,.0f}
Daily P&L: Rs{self.daily_pnl:+,.0f}
""")
            
            logger.info(f'Exit: {pos["type"]} @ {pos["strike"]} | P&L: Rs{pnl:+,.0f}')
        except Exception as e:
            logger.error(f'Exit error: {e}')

bot = TradingBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 SHON AI AUTO TRADING BOT

Strategy: 5-Min Scalping
Asset: NIFTY Options
Status: Automated

COMMANDS:
/status - Bot status
/enable - Enable trading
/disable - Disable trading
/positions - Active positions
/pnl - Daily P&L
/capital - Current capital
/help - All commands

⚠️ Use /enable to start
""")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
📊 STATUS

Trading: {'🟢 ON' if bot.active else '🔴 OFF'}
Market: {'🟢 OPEN' if bot.is_market_open() else '🔴 CLOSED'}

Capital: Rs{bot.capital:,.0f}
Daily P&L: Rs{bot.daily_pnl:+,.0f}

Active Positions: {len(bot.positions)}
Price Candles: {len(bot.history)}
""")

async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.active = True
    await update.message.reply_text('🟢 Trading ENABLED!')

async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.active = False
    await update.message.reply_text('🔴 Trading DISABLED!')

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot.positions:
        await update.message.reply_text('No active positions')
        return
    
    msg = '📋 POSITIONS\n\n'
    for i, p in enumerate(bot.positions, 1):
        holding = (datetime.now() - p['entry_time']).total_seconds() / 60
        msg += f"{i}. {p['type']} @ {p['strike']}\n   Entry: {p['entry_time'].strftime('%H:%M')} | {holding:.0f}min\n\n"
    await update.message.reply_text(msg)

async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
💰 DAILY P&L

Today: Rs{bot.daily_pnl:+,.0f}
Percent: {(bot.daily_pnl/CAPITAL*100):+.2f}%

Start: Rs{CAPITAL:,.0f}
Current: Rs{bot.capital:,.0f}

Loss Limit: Rs{-(CAPITAL*DAILY_LOSS_LIMIT):,.0f}
""")

async def capital_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
💼 CAPITAL

Starting: Rs{CAPITAL:,.0f}
Current: Rs{bot.capital:,.0f}
Change: Rs{bot.capital-CAPITAL:+,.0f}

Available: Rs{bot.capital*MAX_CAPITAL_PER_TRADE:,.0f}
Reserved: Rs{bot.capital*(1-MAX_CAPITAL_PER_TRADE):,.0f}
""")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📖 COMMANDS

CONTROL:
/enable - Start trading
/disable - Stop trading
/emergency - Emergency stop

MONITOR:
/status - Bot status
/positions - Active trades
/pnl - Today's P&L
/capital - Capital info

INFO:
/help - This message
/start - Welcome

⚠️ Bot trades automatically when enabled
""")

async def emergency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.active = False
    await update.message.reply_text("""
🚨 EMERGENCY STOP

✅ Trading disabled
⚠️ Open positions remain

Use /positions to check
Use /enable to resume
""")

async def trading_loop(app):
    logger.info('🚀 Trading loop started')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    while True:
        try:
            if not bot.is_market_open():
                await asyncio.sleep(300)
                continue
            
            if bot.update_price():
                signal = bot.detect_signal()
                if signal and bot.active:
                    logger.info(f'🎯 Signal: {signal}')
                    await bot.execute_trade(signal, app.bot, chat_id)
                await bot.monitor_positions(app.bot, chat_id)
            
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f'Loop error: {e}')
            await asyncio.sleep(60)

def main():
    if not TOKEN:
        print('❌ BOT_TOKEN missing!')
        return
    
    logger.info('='*50)
    logger.info('SHON AI AUTOMATED BOT')
    logger.info(f'Capital: Rs{CAPITAL:,.0f}')
    logger.info(f'Trading: {"ON" if TRADING_ENABLED else "OFF"}')
    logger.info('='*50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('enable', enable))
    app.add_handler(CommandHandler('disable', disable))
    app.add_handler(CommandHandler('positions', positions))
    app.add_handler(CommandHandler('pnl', pnl))
    app.add_handler(CommandHandler('capital', capital_cmd))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('emergency', emergency))
    
    logger.info('🤖 Bot running!')
    
    # Start trading loop in background
    async def post_init(application):
        asyncio.create_task(trading_loop(application))
    
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
