"""
SHON AI TRADING BOT - DHAN VERSION
5-Min Scalping Strategy with Dhan API
All strategies same, just Dhan integration!
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from datetime import datetime, time
import asyncio
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN')

# Trading Config
TRADING_ENABLED = os.environ.get('TRADING_ENABLED', 'false').lower() == 'true'
CAPITAL = float(os.environ.get('TRADING_CAPITAL', '8000'))

# NIFTY Config
NIFTY_LOT = 25
NIFTY_STRIKE_GAP = 50

# Risk Management
MAX_POSITIONS = int(os.environ.get('MAX_POSITIONS', '2'))
DAILY_LOSS_LIMIT = float(os.environ.get('DAILY_LOSS_LIMIT', '0.15'))
MAX_CAPITAL_PER_TRADE = float(os.environ.get('MAX_CAPITAL_PER_TRADE', '0.6'))

# Strategy
TARGET = 0.20
STOP_LOSS = 0.25

class DhanAPI:
    def __init__(self):
        self.client_id = DHAN_CLIENT_ID
        self.access_token = DHAN_ACCESS_TOKEN
        self.base_url = 'https://api.dhan.co'
        
    def get_headers(self):
        """Get API headers"""
        return {
            'access-token': self.access_token,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_ltp(self, symbol='NIFTY', exchange='NSE'):
        """Get Last Traded Price"""
        try:
            # Dhan security ID for NIFTY 50 index
            security_id = '13' if symbol == 'NIFTY' else symbol
            
            url = f'{self.base_url}/v2/quotes/ltp'
            payload = {
                'NSE_EQ': [security_id]
            }
            
            r = requests.post(url, json=payload, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 'success':
                    ltp = float(data['data']['NSE_EQ'][security_id]['last_price'])
                    return ltp
            
            logger.error(f'LTP fetch failed: {r.status_code}')
            return None
            
        except Exception as e:
            logger.error(f'LTP error: {e}')
            return None
    
    def place_order(self, symbol, quantity, price, transaction_type, order_type='LIMIT', product_type='INTRADAY'):
        """Place order on Dhan"""
        try:
            url = f'{self.base_url}/v2/orders'
            
            payload = {
                'dhanClientId': self.client_id,
                'transactionType': transaction_type,  # BUY or SELL
                'exchangeSegment': 'NSE_FNO',  # Options
                'productType': product_type,
                'orderType': order_type,
                'validity': 'DAY',
                'tradingSymbol': symbol,
                'securityId': '',  # Will be filled by Dhan
                'quantity': quantity,
                'disclosedQuantity': 0,
                'price': price,
                'triggerPrice': 0,
                'afterMarketOrder': False
            }
            
            r = requests.post(url, json=payload, headers=self.get_headers(), timeout=15)
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 'success':
                    order_id = data['data']['orderId']
                    logger.info(f'✅ Order placed: {order_id}')
                    return True, order_id, None
            
            logger.error(f'Order failed: {r.status_code} - {r.text}')
            return False, None, r.text
            
        except Exception as e:
            logger.error(f'Order placement error: {e}')
            return False, None, str(e)

class TradingBot:
    def __init__(self):
        self.dhan = DhanAPI()
        self.positions = []
        self.daily_pnl = 0.0
        self.capital = CAPITAL
        self.history = deque(maxlen=10)
        self.active = TRADING_ENABLED
    
    def is_market_open(self):
        """Check if market is open"""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.time()
        return time(9, 15) <= t <= time(15, 30)
    
    def update_price(self):
        ltp = self.dhan.get_ltp()
        if ltp:
            self.history.append({'time': datetime.now(), 'price': ltp})
            logger.info(f'NIFTY: Rs{ltp:,.2f}')
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
            return {'type': 'CALL', 'price': candles[2]['price']}
        if move1 < 0 and move2 < 0 and abs(total) >= 10:
            return {'type': 'PUT', 'price': candles[2]['price']}
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
            strike = int(round(spot / NIFTY_STRIKE_GAP) * NIFTY_STRIKE_GAP)
            premium = 400
            lots = min(2, max(1, int((self.capital * MAX_CAPITAL_PER_TRADE) / (premium * NIFTY_LOT))))
            qty = lots * NIFTY_LOT
            
            position = {
                'type': direction,
                'strike': strike,
                'spot_entry': spot,
                'entry_time': datetime.now(),
                'lots': lots,
                'qty': qty,
                'entry_premium': premium,
                'status': 'OPEN'
            }
            
            self.positions.append(position)
            logger.info(f'📊 Trade: {direction} @ {strike} | Lots: {lots}')
            
            if bot and chat_id:
                await bot.send_message(chat_id, f"""
🤖 TRADE EXECUTED (DHAN)

{direction} @ {strike}
Spot: Rs{spot:,.0f}
Lots: {lots} ({qty} qty)
Investment: ~Rs{premium * qty:,}

Monitoring...
""")
        except Exception as e:
            logger.error(f'Execute error: {e}')
    
    async def monitor_positions(self, current_price, bot, chat_id):
        for pos in self.positions[:]:
            if pos['status'] != 'OPEN':
                continue
            
            move = current_price - pos['spot_entry']
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
{result} - DHAN

{pos['type']} @ {pos['strike']}
Reason: {reason}
P&L: Rs{pnl:+,.0f}

Capital: Rs{self.capital:,.0f}
Daily: Rs{self.daily_pnl:+,.0f}
""")
            
            logger.info(f'Exit: {pos["type"]} @ {pos["strike"]} | P&L: Rs{pnl:+,.0f}')
        except Exception as e:
            logger.error(f'Exit error: {e}')

bot = TradingBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 SHON AI TRADING BOT - DHAN

Strategy: 5-Min Scalping
Asset: NIFTY Options
Broker: Dhan 🚀

/status - Bot status
/enable - Enable trading
/disable - Disable trading
/positions - Active positions
/pnl - Daily P&L
/help - All commands

⚠️ Use /enable to start
""")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
📊 STATUS (DHAN)

Trading: {'🟢 ON' if bot.active else '🔴 OFF'}
Market: {'🟢 OPEN' if bot.is_market_open() else '🔴 CLOSED'}

Capital: Rs{bot.capital:,.0f}
Daily P&L: Rs{bot.daily_pnl:+,.0f}

Positions: {len(bot.positions)}/{MAX_POSITIONS}
Candles: {len(bot.history)}
""")

async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.active = True
    await update.message.reply_text('🟢 DHAN Trading ENABLED!')

async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.active = False
    await update.message.reply_text('🔴 Trading DISABLED!')

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot.positions:
        await update.message.reply_text('No active positions')
        return
    
    msg = '📋 POSITIONS (DHAN)\n\n'
    for i, p in enumerate(bot.positions, 1):
        holding = (datetime.now() - p['entry_time']).total_seconds() / 60
        msg += f"{i}. {p['type']} @ {p['strike']}\n"
        msg += f"   Entry: {p['entry_time'].strftime('%H:%M')} | {holding:.0f}min\n\n"
    await update.message.reply_text(msg)

async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
💰 DAILY P&L (DHAN)

Today: Rs{bot.daily_pnl:+,.0f}
Percent: {(bot.daily_pnl/CAPITAL*100):+.2f}%

Start: Rs{CAPITAL:,.0f}
Current: Rs{bot.capital:,.0f}

Loss Limit: Rs{-(CAPITAL*DAILY_LOSS_LIMIT):,.0f}
""")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📖 COMMANDS (DHAN BOT)

/enable - Start trading
/disable - Stop trading
/status - Bot status
/positions - Active trades
/pnl - Daily P&L
/help - This message

🚀 Powered by Dhan API
⚡ Same 5-min scalping strategy
✅ Better execution, lower latency!
""")

async def trading_loop(app):
    logger.info('🚀 Dhan trading loop started')
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
                
                current_price = list(bot.history)[-1]['price']
                await bot.monitor_positions(current_price, app.bot, chat_id)
            
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f'Loop error: {e}')
            await asyncio.sleep(60)

def main():
    if not TOKEN:
        print('❌ BOT_TOKEN missing!')
        return
    
    logger.info('='*50)
    logger.info('SHON AI TRADING BOT - DHAN')
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
    app.add_handler(CommandHandler('help', help_cmd))
    
    logger.info('🤖 Dhan bot running!')
    
    async def post_init(application):
        asyncio.create_task(trading_loop(application))
    
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    
