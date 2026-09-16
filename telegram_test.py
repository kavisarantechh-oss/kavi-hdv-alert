import os
import urllib.parse
import urllib.request

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

message = """🟢 KAVI HDV TEST

Telegram connection successful.

GitHub Actions → Telegram is working."""

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

data = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message
}).encode()

request = urllib.request.Request(url, data=data, method="POST")

with urllib.request.urlopen(request, timeout=20) as response:
    print(response.read().decode())
