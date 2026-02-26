"""
Vercel Serverless Function - Dhan Webhook Trading
Deploy to Vercel (100% FREE, no credit card!)

File structure:
/api/webhook.py  (this file)
/requirements.txt
/vercel.json
"""

import os
import json
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

# Environment Variables (set in Vercel dashboard)
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Trading Configuration
NIFTY_LOT = 65
MAX_PREMIUM = 123
TARGET = 0.30
STOP_LOSS = 0.30

class DhanAPI:
    """Dhan API Integration"""
    
    def __init__(self):
        self.client_id = DHAN_CLIENT_ID
        self.token = DHAN_ACCESS_TOKEN
        self.base_url = 'https://api.dhan.co'
    
    def get_headers(self):
        return {
            'access-token': self.token,
            'Content-Type': 'application/json'
        }
    
    def get_ltp(self):
        """Get NIFTY spot price"""
        try:
            url = f'{self.base_url}/v2/quotes/ltp'
            payload = {'NSE_EQ': ['13']}
            r = requests.post(url, json=payload, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 'success':
                    return float(data['data']['NSE_EQ']['13']['last_price'])
            return None
        except Exception as e:
            print(f"LTP Error: {e}")
            return None
    
    def estimate_premium(self, spot, strike):
        """Estimate option premium based on distance"""
        distance = abs(strike - spot)
        if distance <= 50: return 350
        elif distance <= 100: return 200
        elif distance <= 150: return 120
        elif distance <= 200: return 80
        elif distance <= 250: return 50
        return 30
    
    def execute_trade(self, signal_type):
        """Execute trade based on TradingView signal"""
        try:
            spot = self.get_ltp()
            if not spot:
                return {'success': False, 'error': 'Could not get spot price'}
            
            # Find suitable option
            strike_gap = 50
            options = []
            
            for distance in [50, 100, 150, 200, 250, 300]:
                if signal_type == 'CALL':
                    strike = int(round((spot + distance) / strike_gap) * strike_gap)
                else:
                    strike = int(round((spot - distance) / strike_gap) * strike_gap)
                
                premium = self.estimate_premium(spot, strike)
                
                if premium <= MAX_PREMIUM:
                    options.append({
                        'strike': strike,
                        'premium': premium,
                        'distance': distance
                    })
            
            if not options:
                return {'success': False, 'error': 'No suitable options found'}
            
            # Select closest OTM
            selected = min(options, key=lambda x: x['distance'])
            strike = selected['strike']
            premium = selected['premium']
            investment = premium * NIFTY_LOT
            
            trade_details = {
                'success': True,
                'type': signal_type,
                'spot': spot,
                'strike': strike,
                'premium': premium,
                'qty': NIFTY_LOT,
                'investment': investment,
                'target_price': premium * (1 + TARGET),
                'sl_price': premium * (1 - STOP_LOSS)
            }
            
            return trade_details
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

def send_telegram(message):
    """Send Telegram notification"""
    if not BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Handle webhook POST request"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            # Parse JSON
            try:
                data = json.loads(body.decode('utf-8'))
            except:
                self.send_error(400, 'Invalid JSON')
                return
            
            # Extract signal
            signal_type = data.get('type')
            
            if not signal_type:
                self.send_error(400, 'Missing signal type')
                return
            
            print(f"Received signal: {signal_type}")
            
            # Execute trade
            dhan = DhanAPI()
            result = dhan.execute_trade(signal_type)
            
            if result.get('success'):
                # Send Telegram notification
                message = f"""
🤖 <b>WEBHOOK TRADE</b>

Signal: {signal_type}
Spot: Rs{result['spot']:,.0f}
Strike: {result['strike']}
Premium: Rs{result['premium']}
Qty: {result['qty']}
Investment: Rs{result['investment']:,.0f}

Target: Rs{result['target_price']:.0f}
SL: Rs{result['sl_price']:.0f}
"""
                send_telegram(message)
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            else:
                error_msg = f"❌ Trade failed: {result.get('error')}"
                send_telegram(error_msg)
                
                self.send_error(500, result.get('error'))
        
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            print(error_msg)
            send_telegram(error_msg)
            self.send_error(500, str(e))
    
    def do_GET(self):
        """Handle GET request (for testing)"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        html = """
        <html>
        <body>
        <h1>Dhan Webhook Trading - Vercel Function</h1>
        <p>Webhook is running! Send POST request with signal data.</p>
        <p>Client: 1109703036</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
          
