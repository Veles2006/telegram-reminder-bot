import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Update từ Telegram:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Ví dụ: người dùng gõ /start
        if text == "/start":
            send_message(chat_id, "Bot đang hoạt động ✅")
        elif text == "/pixiv":
            send_message(chat_id, "Đang xử lý hình từ Pixiv...")

            # Gọi lại hàm send_pixiv_image() của bro
            os.system("python pixiv_bot.py")  # hoặc gọi trực tiếp nếu gộp chung file

        else:
            send_message(chat_id, "Câu lệnh không hợp lệ 🫠")

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
