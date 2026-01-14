#!/usr/bin/env python3
"""
Simple script to get your Telegram Chat ID.
Usage: python get_chat_id.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file")
    exit(1)

print(f"🤖 Using bot token: {TELEGRAM_BOT_TOKEN[:10]}...")
print("\n" + "="*60)
print("📱 INSTRUCTIONS:")
print("="*60)
print("1. Open Telegram and find your bot")
print("2. Send /start or any message to the bot")
print("3. Run this script again")
print("="*60 + "\n")

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

try:
    response = requests.get(url, timeout=10)
    data = response.json()
    
    if not data.get("ok"):
        print(f"❌ API Error: {data}")
        exit(1)
    
    results = data.get("result", [])
    
    if not results:
        print("⚠️  No messages found!")
        print("\n💡 Make sure you:")
        print("   1. Started a conversation with the bot in Telegram")
        print("   2. Sent at least one message (/start)")
        print("   3. The bot token is correct")
        exit(0)
    
    print(f"✅ Found {len(results)} message(s)!\n")
    
    chat_ids = set()
    
    for update in results:
        message = update.get("message", {})
        if message:
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            first_name = chat.get("first_name", "Unknown")
            username = chat.get("username", "N/A")
            chat_type = chat.get("type", "unknown")
            
            if chat_id:
                chat_ids.add(str(chat_id))
                print(f"👤 User: {first_name} (@{username})")
                print(f"   Chat ID: {chat_id}")
                print(f"   Type: {chat_type}")
                print(f"   Message: {message.get('text', 'N/A')}")
                print()
    
    if chat_ids:
        print("="*60)
        print("📋 COPY THIS TO YOUR .env FILE:")
        print("="*60)
        print(f"TELEGRAM_ADMIN_CHAT_IDS={','.join(chat_ids)}")
        print("="*60)
    
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    exit(1)
