import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Bot working! Test successful!')

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Analyze command received!')

def main():
    logger.info("Starting bot...")
    if not TOKEN:
        logger.error("NO TOKEN FOUND!")
        return
    logger.info(f"Token found: {TOKEN[:10]}...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    logger.info("Bot polling started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
