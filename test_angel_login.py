#!/usr/bin/env python3
"""
Angel One API Login Test
Run this on your PC/laptop to test credentials directly
"""

import requests
import pyotp
import json

# YOUR NEW CREDENTIALS (from ShonTradingBot2 app)
API_KEY = "YOUR_NEW_API_KEY"  # 8 characters from new app
CLIENT_ID = "G208449"
PASSWORD = "Brand@12345"
TOTP_SECRET = "YOUR_NEW_TOTP_SECRET"  # Long string from new app

print("="*50)
print("ANGEL ONE API LOGIN TEST")
print("="*50)
print()

# Step 1: Check credentials format
print("STEP 1: Checking credentials...")
print(f"API_KEY length: {len(API_KEY)} chars")
print(f"CLIENT_ID: {CLIENT_ID}")
print(f"PASSWORD length: {len(PASSWORD)} chars")
print(f"PASSWORD value: {PASSWORD}")
print(f"TOTP_SECRET length: {len(TOTP_SECRET)} chars")
print()

# Step 2: Generate TOTP
print("STEP 2: Generating TOTP...")
try:
    totp = pyotp.TOTP(TOTP_SECRET).now()
    print(f"TOTP Generated: {totp}")
    print(f"TOTP Length: {len(totp)}")
    print()
except Exception as e:
    print(f"ERROR generating TOTP: {e}")
    print("Check TOTP_SECRET is correct!")
    exit(1)

# Step 3: Prepare login request
print("STEP 3: Preparing login request...")
url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"

headers = {
    'X-PrivateKey': API_KEY,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

payload = {
    'clientcode': CLIENT_ID,
    'password': PASSWORD,
    'totp': totp
}

print(f"URL: {url}")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

# Step 4: Make request
print("STEP 4: Making login request...")
print("Sending request to Angel One...")
print()

try:
    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=15
    )
    
    print("="*50)
    print("RESPONSE RECEIVED")
    print("="*50)
    print()
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Length: {len(response.text)} bytes")
    print()
    
    print("Response Headers:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")
    print()
    
    print("Response Body:")
    if response.text:
        print(response.text)
        print()
        
        # Try to parse JSON
        try:
            data = response.json()
            print("Parsed JSON:")
            print(json.dumps(data, indent=2))
            print()
            
            if response.status_code == 200 and data.get('status'):
                print("✅ SUCCESS! Login worked!")
                print(f"JWT Token: {data['data']['jwtToken'][:50]}...")
            else:
                print("❌ FAILED!")
                print(f"Error Message: {data.get('message', 'Unknown')}")
                if 'errorcode' in data:
                    print(f"Error Code: {data['errorcode']}")
        except:
            print("Response is not valid JSON")
    else:
        print("(EMPTY - This is the problem!)")
        print()
        print("❌ EMPTY RESPONSE means:")
        print("1. Angel One rejecting at gateway level")
        print("2. API Key or Client ID invalid")
        print("3. New app not fully activated")
        print("4. Account issue")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    print()
    print("Check your internet connection!")

print()
print("="*50)
print("TEST COMPLETE")
print("="*50)
print()
print("If you see ✅ SUCCESS - credentials work!")
print("Copy them to Railway and bot will work.")
print()
print("If you see ❌ FAILED - contact Angel One support")
print("Email: support@angelbroking.com")
print("They'll check why your app credentials aren't working.")
  
