import os
import html
import random
import requests
from flask import Flask, request
import json
import threading, time
import certifi
import logging
import schedule


# Thêm các import cần thiết từ telegram_daily.py
from dotenv import load_dotenv
from openai import OpenAI
from pixivpy3 import AppPixivAPI
from pymongo import MongoClient
from datetime import datetime, timedelta

# (Có thể import cloudinary, MongoClient nếu dự định dùng, nhưng nếu không dùng có thể bỏ)

# Nạp biến môi trường
load_dotenv()  # nếu bạn dùng file .env để lưu cấu hình
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")         # ID chat mặc định (có thể không cần nếu sẽ dùng chat_id động)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN")
PIXIV_USER_ID = int(os.getenv("PIXIV_USER_ID", "0"))
MONGO_URI = os.getenv("MONGODB_URI")    # Chuỗi kết nối MongoDB (đọc từ biến môi trường)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["lifeup-legend"]     # Tên database bạn đã tạo trên MongoDB
collection = db["characters"] 
tasks = db["tasks"]

print("🔗 Đang kết nối Mongo URI:", MONGO_URI)

logging.getLogger("pymongo").setLevel(logging.WARNING)

# Kiểm tra biến môi trường (tùy chọn, để đảm bảo không thiếu)
for key, value in {
    "BOT_TOKEN": BOT_TOKEN,
    "OPENAI_KEY": OPENAI_KEY,
    "PIXIV_REFRESH_TOKEN": PIXIV_REFRESH_TOKEN,
    "PIXIV_USER_ID": PIXIV_USER_ID,
    "MONGO_URI": MONGO_URI,
}.items():
    if not value:
        raise RuntimeError(f"⚠️ Thiếu biến môi trường: {key}")

# Khởi tạo các client cho OpenAI và Pixiv
openai_client = OpenAI(api_key=OPENAI_KEY)
pixiv_api = AppPixivAPI()
pixiv_api.auth(refresh_token=PIXIV_REFRESH_TOKEN)

# URL API Telegram để gửi tin nhắn/ảnh
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_SEND_MESSAGE = f"{TG_API}/sendMessage"
TG_SEND_PHOTO = f"{TG_API}/sendPhoto"

# Hàm tạo nhiệm vụ
def create_task(task):
    tasks.insert_one(task)

def get_today_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    return list(tasks.find({"date": today}))

def generate_daily_task():
    prompt = f"""
    Hãy tạo một nhiệm vụ ngắn gọn mang tính phát triển bản thân.
    Trả về JSON có các trường:
    - name: tên nhiệm vụ
    - short_desc: mô tả ngắn gọn
    - full_desc: mô tả đầy đủ
    - requirement: yêu cầu
    - reward: phần thưởng
    - penalty: hình phạt
    - deadline: thời hạn (vd: hôm nay 23:59)
    """
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content.strip()
    return text

def send_task():
    task_json = generate_daily_task()
    try:
        task = json.loads(task_json)
    except:
        print("❌ Lỗi JSON từ GPT, bỏ qua")
        return

    # lưu vào MongoDB
    create_task({
        "name": task["name"],
        "type": "Hàng ngày",
        "short_desc": task["short_desc"],
        "full_desc": task["full_desc"],
        "requirement": task["requirement"],
        "reward": task["reward"],
        "penalty": task["penalty"],
        "deadline": task["deadline"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "chưa hoàn thành",  # 🧩 trạng thái mặc định
        "difficulty": random.choice(["Dễ", "Trung bình", "Khó"])  # 🎯 độ khó ngẫu nhiên
    })

    # gửi tin nhắn tóm tắt lên Telegram
    message = (
        f"🧭 <b>Tên nhiệm vụ:</b> {task['name']}\n"
        f"📘 <b>Xếp loại:</b> Hàng ngày\n"
        f"📝 <b>Mô tả:</b> {task['short_desc']}\n"
        f"⏰ <b>Hết hạn:</b> {task['deadline']}\n"
        f"🔗 <b>Chi tiết:</b> https://lifeup-legend.vercel.app/tasks\n"
    )
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })

# Đặt lịch 7h sáng & 7h tối
schedule.every().day.at("07:00").do(send_task)
schedule.every().day.at("23:26").do(send_task)

# vòng lặp vô hạn
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Chạy song song với Flask
import threading
threading.Thread(target=run_scheduler, daemon=True).start()

# Hàm gửi tin nhắn văn bản (đã có sẵn trong main.py cũ)
def send_message(chat_id, text):
    requests.post(TG_SEND_MESSAGE, json={"chat_id": chat_id, "text": text})

# 🧠 Hàm dùng OpenAI để xếp hạng độ hiếm từ tiêu đề tranh
def get_rarity_rank(title: str) -> str:
    prompt = (
        f"Giả sử mỗi bức tranh có độ hiếm từ 1 đến 5 sao. "
        f"Phân tích tiêu đề '{title}' và trả về độ hiếm ngắn gọn (ví dụ: ⭐⭐⭐⭐ - Độ hiếm cao, khó gặp)."
    )
    try:
        res = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là hệ thống chấm độ hiếm tranh, chỉ trả lời ngắn gọn dạng sao."},
                {"role": "user", "content": prompt},
            ],
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ ChatGPT lỗi: {e}"

# 🎨 Hàm lấy ngẫu nhiên một ảnh Pixiv từ bookmark
def get_random_pixiv_image():
    print("🔍 Đang tải danh sách bookmark Pixiv...")
    res = pixiv_api.user_bookmarks_illust(user_id=PIXIV_USER_ID)
    all_illusts = res.illusts or []

    # Lấy tối đa ~200 tranh từ bookmark để random
    while res.next_url and len(all_illusts) < 200:
        next_qs = pixiv_api.parse_qs(res.next_url)
        res = pixiv_api.user_bookmarks_illust(**next_qs)
        all_illusts.extend(res.illusts or [])

    # Lọc bỏ các illust dạng ugoira (gif) vì không gửi được trực tiếp
    valid_illusts = [ill for ill in all_illusts if ill.type != "ugoira"]
    if not valid_illusts:
        raise Exception("❌ Không có ảnh hợp lệ trong bookmark.")

    # Chọn một tranh ngẫu nhiên từ danh sách hợp lệ
    illust = random.choice(valid_illusts)
    illust_id = illust.id
    title = illust.title

    # Lấy chi tiết tranh (để lấy link ảnh gốc)
    detail = pixiv_api.illust_detail(illust_id)
    illust_data = detail.illust

    # Xác định URL ảnh gốc (nếu tranh có nhiều trang thì chọn ngẫu nhiên một trang)
    if illust_data.meta_single_page and "original_image_url" in illust_data.meta_single_page:
        img_url = illust_data.meta_single_page["original_image_url"]
        page_info = "1/1"
    elif illust_data.meta_pages:
        page_data = random.choice(illust_data.meta_pages)
        img_url = page_data["image_urls"]["original"]
        idx = illust_data.meta_pages.index(page_data) + 1
        page_info = f"{idx}/{len(illust_data.meta_pages)}"
    else:
        raise Exception("❌ Không tìm thấy link ảnh hợp lệ cho tranh.")

    print(f"📥 Đang tải ảnh: {img_url} (Trang {page_info})")
    # Gửi request tải ảnh (kèm header referer cho Pixiv)
    headers = {
        "Referer": "https://www.pixiv.net/",
        "User-Agent": "Mozilla/5.0"
    }
    response = requests.get(img_url, headers=headers, timeout=15)
    if response.status_code != 200:
        raise Exception(f"❌ Lỗi tải ảnh (mã {response.status_code}).")

    # Lưu ảnh tạm ra file
    filename = f"pixiv_{illust_id}_p{page_info.replace('/', '-')}.jpg"
    with open(filename, "wb") as f:
        f.write(response.content)

    return filename, title, illust_id

# 💬 Hàm gửi ảnh Pixiv qua Telegram
def send_pixiv_image(chat_id: str):
    # Gọi hàm trên để lấy ảnh và thông tin
    img_path, title, illust_id = get_random_pixiv_image()
    # Gọi ChatGPT để lấy độ hiếm (tuỳ chọn, có thể bỏ qua nếu không cần)
    rarity_text = get_rarity_rank(title)

    # Tạo caption cho ảnh, bao gồm tiêu đề, độ hiếm và link Pixiv
    caption = (
        f"🎨 {html.escape(title)}\n\n"
        f"{rarity_text}\n\n"
        f"🔗 https://www.pixiv.net/artworks/{illust_id}"
    )

    print("📤 Đang gửi ảnh lên Telegram...")
    with open(img_path, "rb") as img_file:
        res = requests.post(
            TG_SEND_PHOTO,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": img_file}
        )
    if res.status_code == 200:
        print(f"✅ Đã gửi ảnh thành công - Tiêu đề: {title}")
    else:
        print(f"⚠️ Lỗi gửi ảnh Telegram (mã {res.status_code}): {res.text}")

# Hàm gọi ChatGPT để tạo mô tả
def parse_character_description(description: str) -> dict:
    prompt = (
        f"Hãy phân tích mô tả nhân vật sau và trích xuất thông tin dưới dạng JSON với các trường đã cho.\n"
        f"Mô tả nhân vật: '''{description}'''\n"
        f"Lưu ý: Nếu mô tả không nhắc đến trường nào, có thể bỏ qua trường đó."
    )
    try:
        res = openai_client.chat.completions.create(
            model="gpt-4",  # hoặc model phù hợp (gpt-3.5-turbo,...)
            messages=[
                {"role": "system", "content": "Bạn là trợ lý phân tích nhân vật."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = res.choices[0].message.content.strip()
        data = json.loads(answer)  # parse chuỗi JSON thành dict
        return data
    except Exception as e:
        print(f"❌ Lỗi GPT parse: {e}")
        return {}

# Khởi tạo Flask app sau khi đã cấu hình mọi thứ
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Cập nhật từ Telegram:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send_message(chat_id, "Bot đang hoạt động ✅")
        elif text == "/pixiv":
            send_message(chat_id, "Đang xử lý hình từ Pixiv...")
            # Gọi trực tiếp hàm gửi ảnh (thay vì os.system)
            try:
                send_pixiv_image(chat_id)
            except Exception as e:
                # Nếu có lỗi, thông báo về chat
                send_message(chat_id, f"Đã xảy ra lỗi: {e}")
        elif text.startswith("/createCharacter"):
            parts = text.split(" ", 1)
            if len(parts) < 2:
                send_message(chat_id, "Hãy nhập mô tả nhân vật sau lệnh /createCharacter.")
            else:
                description = parts[1]
                # Gọi GPT phân tích mô tả nhân vật
                char_data = parse_character_description(description)
                if not char_data:
                    send_message(chat_id, "❌ Không trích xuất được thông tin từ mô tả.")
                else:
                    # Thêm trường hệ thống
                    char_data["created_at"] = time.time()  # hoặc datetime.now().isoformat()
                    char_data["status"] = "active"
                    result = collection.insert_one(char_data)
                    new_id = str(result.inserted_id)
                    send_message(chat_id, f"✅ Đã tạo nhân vật mới với ID: {new_id}")
                    print(f"Đã thêm nhân vật ID {new_id}: {char_data}")
        
        #Tạo người chơi /createPlayer Veles Nữ 18
        elif text.startswith("/createPlayer"):
            parts = text.split(" ", 3)
            # Cấu trúc: /createPlayer <tên> [giới tính] [tuổi]
            name = parts[1] if len(parts) > 1 else "Vô danh"
            gender = parts[2] if len(parts) > 2 else "?"
            age = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else "?"

            import random
            # Tạo thông tin người chơi mặc định
            player_data = {
                "name": name,
                "gender": gender,
                "age": age,
                "stats": {
                    "strength": random.randint(1, 10),
                    "intelligence": random.randint(1, 10),
                    "stamina": random.randint(1, 10),
                    "speed": random.randint(1, 10),
                    "charm": random.randint(1, 10)
                },
                "skills": [],
                "titles": [],
                "occupation": "",
                "created_at": time.time(),
                "status": "active",
                "type": "player"
            }

            result = collection.insert_one(player_data)
            new_id = str(result.inserted_id)

            summary = (
                f"🎮 <b>Người chơi mới được tạo!</b>\n"
                f"🆔 ID: {new_id}\n"
                f"👤 Tên: {player_data['name']}\n"
                f"⚧ Giới tính: {player_data['gender']}\n"
                f"🎂 Tuổi: {player_data['age']}\n\n"
                f"📊 Chỉ số:\n"
                f"💪 Sức mạnh: {player_data['stats']['strength']}\n"
                f"🧠 Trí tuệ: {player_data['stats']['intelligence']}\n"
                f"❤️ Thể lực: {player_data['stats']['stamina']}\n"
                f"⚡ Tốc độ: {player_data['stats']['speed']}\n"
                f"✨ Mỹ lực: {player_data['stats']['charm']}"
            )

            send_message(chat_id, summary)
            print(f"✅ Đã tạo người chơi ID {new_id}: {player_data}")
            print("🔗 Đang kết nối Mongo URI:", MONGO_URI)
            print("🧠 MongoDB info:", client.server_info().get("version", "Không lấy được"))



        #Hiện bảng trạng thái người chơi /playerStatus Veles
        elif text.startswith("/playerStatus"):
            parts = text.split(" ", 1)
            if len(parts) < 2:
                send_message(chat_id, "⚠️ Vui lòng nhập tên nhân vật. Ví dụ:\n/playerStatus Veles")
            else:
                name = parts[1].strip()
                player = collection.find_one({"name": name, "type": "player"})

                if not player:
                    send_message(chat_id, f"❌ Không tìm thấy người chơi tên '{name}'.")
                else:
                    stats = player.get("stats", {})
                    summary = (
                        f"📜 <b>BẢNG TRẠNG THÁI</b>\n"
                        f"👤 Tên: {player.get('name', '?')}\n"
                        f"⚧ Giới tính: {player.get('gender', '?')}\n"
                        f"🎂 Tuổi: {player.get('age', '?')}\n"
                        f"🆔 ID: {player.get('_id')}\n\n"
                        f"📊 <b>Chỉ số:</b>\n"
                        f"💪 Sức mạnh: {stats.get('strength', '?')}\n"
                        f"🧠 Trí tuệ: {stats.get('intelligence', '?')}\n"
                        f"❤️ Thể lực: {stats.get('stamina', '?')}\n"
                        f"⚡ Tốc độ: {stats.get('speed', '?')}\n"
                        f"✨ Mỹ lực: {stats.get('charm', '?')}\n\n"
                        f"🎯 Nghề nghiệp: {player.get('occupation', '(Chưa có)')}\n"
                        f"🏅 Danh hiệu: {', '.join(player.get('titles', [])) if player.get('titles') else '(Trống)'}\n"
                        f"🪄 Kỹ năng: {', '.join(player.get('skills', [])) if player.get('skills') else '(Chưa học kỹ năng nào)'}"
                    )
                    send_message(chat_id, summary)

        #Lệnh sửa người chơi /editPlayer <tên> <trường> <giá trị mới>
        elif text.startswith("/editPlayer"):
            parts = text.split(" ", 3)
            if len(parts) < 4:
                send_message(chat_id,
                    "⚠️ Cú pháp sai. Hãy dùng dạng:\n"
                    "/editPlayer <tên> <trường> <giá trị>\n\n"
                    "Ví dụ:\n"
                    "/editPlayer Veles age 25\n"
                    "/editPlayer Veles gender Nam\n"
                    "/editPlayer Veles strength 8"
                )
            else:
                name = parts[1].strip()
                field = parts[2].strip().lower()
                value = parts[3].strip()

                player = collection.find_one({"name": name, "type": "player"})
                if not player:
                    send_message(chat_id, f"❌ Không tìm thấy người chơi tên '{name}'.")
                    return "ok", 200

                # Map tên trường trong lệnh sang key thực tế
                valid_fields = {
                    "name": "name",
                    "gender": "gender",
                    "age": "age",
                    "strength": "stats.strength",
                    "intelligence": "stats.intelligence",
                    "stamina": "stats.stamina",
                    "speed": "stats.speed",
                    "charm": "stats.charm"
                }

                if field not in valid_fields:
                    send_message(chat_id, f"⚠️ Trường '{field}' không hợp lệ. Có thể sửa: {', '.join(valid_fields.keys())}")
                    return "ok", 200

                # Nếu là số, ép kiểu
                if value.isdigit():
                    value = int(value)

                # Tạo key MongoDB động (vd: "stats.strength")
                update_field = valid_fields[field]
                result = collection.update_one(
                    {"_id": player["_id"]},
                    {"$set": {update_field: value}}
                )

                if result.modified_count > 0:
                    send_message(chat_id, f"✅ Đã cập nhật {field} của '{name}' thành: {value}")
                    print(f"✏️ Đã sửa {field} cho {name}: {value}")
                else:
                    send_message(chat_id, f"⚠️ Không có thay đổi (có thể giá trị mới trùng giá trị cũ).")


        #Lệnh xoá người chơi /deletePlayer Veles
        elif text.startswith("/deletePlayer"):
            parts = text.split(" ", 1)
            if len(parts) < 2:
                send_message(chat_id, "⚠️ Vui lòng nhập tên nhân vật cần xóa. Ví dụ:\n/deletePlayer Veles")
            else:
                name = parts[1].strip()
                player = collection.find_one({"name": name, "type": "player"})

                if not player:
                    send_message(chat_id, f"❌ Không tìm thấy người chơi tên '{name}'.")
                else:
                    result = collection.delete_one({"_id": player["_id"]})
                    if result.deleted_count > 0:
                        send_message(chat_id, f"🗑️ Đã xóa người chơi '{name}' thành công.")
                        print(f"🗑️ Đã xóa player: {player}")
                    else:
                        send_message(chat_id, f"⚠️ Không thể xóa '{name}'. Có thể đã bị xóa trước đó.")

        

        else:
            send_message(chat_id, "Câu lệnh không hợp lệ 🫠")

    return "ok", 200


def heartbeat():
    while True:
        print("💓 Bot vẫn đang hoạt động...")
        time.sleep(60 * 5)  # mỗi 5 phút in 1 lần

threading.Thread(target=heartbeat, daemon=True).start()

if __name__ == "__main__":
    import sys
    import logging

    # Cho phép Flask in log ra console Render
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    app.logger.addHandler(logging.StreamHandler(sys.stdout))
    app.logger.setLevel(logging.DEBUG)

    # Bật debug để log chi tiết request
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=True)

