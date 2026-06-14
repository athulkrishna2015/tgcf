from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = input("Enter your API_ID: ").strip()
API_HASH = input("Enter your API_HASH: ").strip()

if not API_ID or not API_HASH:
    print("Error: API_ID and API_HASH are required.")
    exit(1)
print("Starting Telegram session generation...")
print("Please enter your phone number and the login code you receive on Telegram.")
print("-" * 50)

import asyncio

async def main():
    # Create a new client and authenticate
    client = TelegramClient(StringSession(), int(API_ID), API_HASH)
    await client.start()
    
    print("-" * 50)
    print("Authentication successful!")
    print("\nHere is your new SESSION_STRING:\n")
    print(client.session.save())
    print("\n" + "-" * 50)
    print("Copy the string above and paste it into your .env file as SESSION_STRING_2, SESSION_STRING_3, etc.")
    print("Keep this string safe! Anyone with it can access your Telegram account.")
    await client.disconnect()

asyncio.run(main())
