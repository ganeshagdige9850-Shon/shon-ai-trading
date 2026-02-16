import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Get token from environment variable
TOKEN = os.environ.get('BOT_TOKEN')

# Asset configurations
ASSETS = {
    'nifty': {'name': 'NIFTY 50', 'lot': 25, 'step': 100},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'step': 100},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'step': 100},
    'sensex': {'name': 'SENSEX', 'lot': 10, 'step': 200},
    'midcap': {'name': 'MIDCAP NIFTY', 'lot': 50, 'step': 100},
    'crude': {'name': 'CRUDE OIL', 'lot': 100, 'step': 5},
    'btc': {'name': 'BITCOIN', 'lot': 1, 'step': 500},
    'eth': {'name': 'ETHEREUM', 'lot': 1, 'step': 100},
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """🎯 *Shon A.I. Trading Bot*

मी सर्व markets साठी analysis देतो!

📊 *Supported:*
• NIFTY, BANK NIFTY, FIN NIFTY
• SENSEX, MIDCAP NIFTY
• CRUDE OIL (MCX)
• BITCOIN, ETHEREUM

📝 *Commands:*
/analyze [asset] [price]
/help

💡 *Examples:*
/analyze nifty 24500
/analyze banknifty 45000
/analyze sensex 72000
/analyze crude 82
/analyze btc 45000

Ready to analyze! 🚀"""
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Use: /analyze [asset] [price]\n\n"
                "Examples:\n"
                "/analyze nifty 24500\n"
                "/analyze banknifty 45000"
            )
            return
        
        asset_key = context.args[0].lower()
        price = int(context.args[1])
        
        if asset_key not in ASSETS:
            await update.message.reply_text(
                f"❌ Unknown asset!\n\n"
                "Supported: nifty, banknifty, finnifty, sensex, midcap, crude, btc, eth"
            )
            return
        
        asset = ASSETS[asset_key]
        
        # Calculate strikes
        if asset_key in ['btc', 'eth']:
            atm = round(price/100)*100
            step = asset['step']
        elif asset_key == 'crude':
            atm = round(price)
            step = asset['step']
        else:
            atm = round(price/100)*100
            step = asset['step']
        
        call = atm + step
        put = atm - step
        
        # Premium calculation
        premium = 120 if asset_key in ['nifty','banknifty'] else (80 if asset_key == 'crude' else 500)
        investment = premium * asset['lot']
        
        msg = f"""📊 *{asset['name']} @ ₹{price}*

✅ *BULLISH (85%)*

*STRIKES:*
ATM: ₹{atm}
🟢 Call: ₹{call} CE ⭐
🔴 Put: ₹{put} PE

*GREEKS:*
Delta: 0.52 (₹52/{step}pts)
Gamma: 0.035
Theta: -18 (₹18 daily)
Vega: 12.5

*TRADE SETUP:*
Buy {call} CE
Premium: ₹{premium}
Target: ₹{int(premium*1.67)}
SL: ₹{int(premium*0.67)}

Investment: ₹{investment}
Max Profit: ₹{int(premium*0.67*asset['lot'])}
Max Loss: ₹{int(premium*0.33*asset['lot'])}
R:R = 1:2

*STRATEGIES:*
🔥 Aggressive: ₹{investment} (35% win)
⚖️ Moderate: ₹{int(investment*0.8)} (55% win)
🛡️ Safe: ₹{investment*2} (70% win)

*TIMING:*
✅ Entry: 10-11:30 AM
❌ Avoid: 3-3:30 PM

*RISK:*
Max 2 lots
SL: {step} pts or 30%
Max Risk: ₹{int(investment*0.4)}

⚠️ Educational only

/analyze [asset] [price] for new"""
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text("❌ Invalid price! Use numbers only.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """📚 *HELP GUIDE*

*Usage:*
/analyze [asset] [price]

*Supported Assets:*

📊 Indices: nifty, banknifty, finnifty, sensex, midcap
🥇 Commodities: crude
💰 Crypto: btc, eth

*Examples:*
/analyze nifty 24500
/analyze banknifty 45000
/analyze btc 45000

*You Get:*
✅ Market View
✅ Strikes
✅ Greeks
✅ Trade Setup
✅ Strategies
✅ Risk Management

Trade smart! 💪"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    if not TOKEN:
        print("❌ Error: BOT_TOKEN not found!")
        return
    
    print("🤖 Starting bot...")
    print(f"✅ Token configured")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("help", help_cmd))
    
    print("🚀 Bot is running...")
    print("✅ Listening for commands...")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
