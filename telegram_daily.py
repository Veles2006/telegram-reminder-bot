import os
import random
import html
import requests
from openai import OpenAI
from pixivpy3 import AppPixivAPI
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from pymongo import MongoClient


# --- Nạp biến môi trường ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN")
PIXIV_USER_ID = int(os.getenv("PIXIV_USER_ID", "0"))

for key, value in {
    "BOT_TOKEN": BOT_TOKEN,
    "CHAT_ID": CHAT_ID,
    "OPENAI_KEY": OPENAI_KEY,
    "PIXIV_REFRESH_TOKEN": PIXIV_REFRESH_TOKEN,
    "PIXIV_USER_ID": PIXIV_USER_ID,
}.items():
    if not value:
        raise RuntimeError(f"⚠️ Thiếu biến môi trường: {key}")

# --- Khởi tạo ---
client = OpenAI(api_key=OPENAI_KEY)
pixiv = AppPixivAPI()
pixiv.auth(refresh_token=PIXIV_REFRESH_TOKEN)

TG_SEND_PHOTO = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

# ==========================================================
# 🧠 ChatGPT: Xếp hạng độ hiếm
# ==========================================================
def get_rarity_rank(title: str) -> str:
    prompt = (
        f"Giả sử mỗi bức tranh có độ hiếm từ 1 đến 5 sao. "
        f"Phân tích tiêu đề '{title}' và trả về độ hiếm ngẫu nhiên, "
        f"ngắn gọn, ví dụ: ⭐⭐⭐⭐ - Độ hiếm cao, khó gặp."
    )
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là hệ thống chấm độ hiếm tranh, chỉ trả lời ngắn gọn dạng sao."},
                {"role": "user", "content": prompt},
            ],
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ ChatGPT lỗi: {e}"

# ==========================================================
# 🎨 Lấy ảnh hợp lệ và tải gốc từ Pixiv
# ==========================================================
def get_random_pixiv_image():
    print("🔍 Đang tải danh sách bookmark...")
    res = pixiv.user_bookmarks_illust(user_id=PIXIV_USER_ID)
    all_illusts = res.illusts

    while res.next_url and len(all_illusts) < 200:
        next_qs = pixiv.parse_qs(res.next_url)
        res = pixiv.user_bookmarks_illust(**next_qs)
        all_illusts.extend(res.illusts)

    valid = [i for i in all_illusts if i.type != "ugoira"]
    if not valid:
        raise Exception("❌ Không có ảnh hợp lệ trong bookmark")

    illust = random.choice(valid)
    illust_id = illust.id
    title = illust.title

    # Lấy chi tiết ảnh chính xác
    detail = pixiv.illust_detail(illust_id)
    illust_data = detail.illust

    if illust_data.meta_single_page and "original_image_url" in illust_data.meta_single_page:
        img_url = illust_data.meta_single_page["original_image_url"]
        page_info = "1/1"
    elif illust_data.meta_pages:
        page_data = random.choice(illust_data.meta_pages)
        img_url = page_data["image_urls"]["original"]
        idx = illust_data.meta_pages.index(page_data) + 1
        page_info = f"{idx}/{len(illust_data.meta_pages)}"
    else:
        raise Exception("❌ Không tìm thấy link ảnh hợp lệ")

    print(f"📥 Ảnh: {img_url} (Trang {page_info})")

    headers = {
        "Referer": "https://www.pixiv.net/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    img = requests.get(img_url, headers=headers, timeout=15)
    if img.status_code != 200:
        raise Exception(f"❌ Lỗi tải ảnh (status {img.status_code})")

    filename = f"pixiv_{illust_id}_p{page_info.replace('/', '-')}.jpg"
    with open(filename, "wb") as f:
        f.write(img.content)

    return filename, title, illust_id

# ==========================================================
# 💬 Gửi ảnh lên Telegram
# ==========================================================
def send_pixiv_image():
    try:
        img_path, title, illust_id = get_random_pixiv_image()
        rarity = get_rarity_rank(title)

        caption = (
            f"🎨 {html.escape(title)}\n\n"
            f"{rarity}\n\n"
            f"🔗 https://www.pixiv.net/artworks/{illust_id}"
        )

        print("📤 Gửi ảnh lên Telegram...")
        r = requests.post(
            TG_SEND_PHOTO,
            data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"photo": open(img_path, "rb")},
        )

        if r.status_code == 200:
            print(f"✅ Gửi thành công ({r.status_code}) - {title}")
        else:
            print(f"⚠️ Telegram trả về lỗi ({r.status_code}): {r.text}")

    except Exception as e:
        print(f"❌ Lỗi khi gửi ảnh: {e}")

# ==========================================================
# 🚀 Chạy ngay
# ==========================================================
if __name__ == "__main__":
    send_pixiv_image()
