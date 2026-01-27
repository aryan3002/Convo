#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/aryantripathi/Convo-main/Backend')

import httpx
from app.core.config import get_settings

settings = get_settings()
print(f"CLERK_FRONTEND_API={settings.clerk_frontend_api}")

url = 'https://api.clerk.com/v1/jwks'
client = httpx.Client(timeout=10)
resp = client.get(url, headers={'Authorization': f'Bearer {settings.clerk_secret_key}'})
print(f"Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Error: {resp.text[:500]}")
else:
    import json
    data = resp.json()
    keys = data.get('keys', [])
    print(f"Keys found: {len(keys)}")
    if keys:
        print(f"First key: {json.dumps({k: v for k,v in keys[0].items() if k!='x5c'}, indent=2)}")
