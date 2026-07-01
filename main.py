import os
import re
import time
import requests
import telebot
from flask import Flask
from threading import Thread

# ============================================================
# 1. CẤU HÌNH BOT TELEGRAM
# QUAN TRỌNG: KHÔNG hardcode token thật ở đây.
# Vào BotFather -> /revoke để tạo token mới, rồi set biến môi trường
# BOT_TOKEN trên Render (Settings -> Environment).
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError("Chưa đặt biến môi trường BOT_TOKEN!")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
app = Flask('')


@app.route('/')
def home():
    return "Bot TikTok đang hoạt động!"


def run_flask():
    app.run(host='0.0.0.0', port=8080)


# ============================================================
# 2. HÀM BÓC TÁCH LINK TIKTOK
def get_tiktok_video(url):
    # API 1: tikwm.com
    try:
        resp = requests.post(
            "https://www.tikwm.com/api/",
            data={"url": url, "hd": 1},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        data = resp.json()
        if data.get("code") == 0:
            video_url = data["data"].get("hdplay") or data["data"].get("play")
            title = data["data"].get("title", "Video TikTok")
            if video_url:
                print("[API1-tikwm] OK")
                return video_url, title
    except Exception as e:
        print(f"[API1-tikwm] Lỗi: {e}")

    # API 2: ssstik.io
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        page = session.get("https://ssstik.io/en", timeout=10)
        token_match = re.search(r'name="tt"\s+value="([^"]+)"', page.text)
        if token_match:
            token = token_match.group(1)
            resp = session.post(
                "https://ssstik.io/abc?url=dl",
                data={"id": url, "locale": "en", "tt": token},
                headers={"Referer": "https://ssstik.io/en"},
                timeout=15
            )
            video_match = re.search(r'href="(https://[^"]+)"[^>]*>\s*Without watermark', resp.text)
            if video_match:
                video_url = video_match.group(1)
                title_match = re.search(r'<p class="maintext">(.*?)</p>', resp.text, re.DOTALL)
                title = title_match.group(1).strip() if title_match else "Video TikTok"
                print("[API2-ssstik] OK")
                return video_url, title
    except Exception as e:
        print(f"[API2-ssstik] Lỗi: {e}")

    # API 3: savetik.net
    try:
        resp = requests.post(
            "https://savetik.net/api/ajaxSearch",
            data={"q": url, "lang": "en"},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://savetik.net/en",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15
        )
        data = resp.json()
        if data.get("status") == "ok":
            html = data.get("data", "")
            video_match = re.search(r'href="(https://[^"]+)"[^>]*id="noWatermark"', html)
            if not video_match:
                video_match = re.search(r'href="(https://tikcdn[^"]+)"', html)
            if video_match:
                video_url = video_match.group(1)
                title_match = re.search(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "Video TikTok"
                print("[API3-savetik] OK")
                return video_url, title
    except Exception as e:
        print(f"[API3-savetik] Lỗi: {e}")

    return None, None


def expand_short_url(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        return r.url
    except Exception:
        return url


# ============================================================
# 3. XỬ LÝ TIN NHẮN TELEGRAM
# Lưu ý: xử lý TRỰC TIẾP trong handler (giống bot Xiaohongshu),
# KHÔNG tự tạo Thread() thủ công nữa — đây là nguyên nhân chính
# khiến bot bị đơ dần theo thời gian (thread tích tụ không kiểm soát).
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Xin chào! Gửi link TikTok hoặc Douyin, tôi sẽ tải video *không logo* về cho bạn!\n\n"
        "Hỗ trợ:\n"
        "• https://www.tiktok.com/@.../video/...\n"
        "• https://vm.tiktok.com/...\n"
        "• https://vt.tiktok.com/...\n"
        "• https://www.douyin.com/video/...",
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    url_match = re.search(
        r'https?://(?:www\.|vm\.|vt\.)?(?:tiktok\.com|douyin\.com)\S+',
        text
    )
    if not url_match:
        return

    url = url_match.group(0)
    status_msg = bot.reply_to(message, "🔄 Đang phân tích link...")
    video_url = None

    try:
        if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
            bot.edit_message_text("🔗 Đang mở link rút gọn...", message.chat.id, status_msg.message_id)
            url = expand_short_url(url)

        bot.edit_message_text("📡 Đang bóc tách link video...", message.chat.id, status_msg.message_id)
        video_url, video_title = get_tiktok_video(url)

        if not video_url:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🌐 Thử tải thủ công", url="https://ssstik.io"))
            bot.edit_message_text(
                "❌ Không lấy được link video.\nVideo có thể bị riêng tư hoặc đã bị xoá.",
                message.chat.id, status_msg.message_id,
                reply_markup=markup
            )
            return

        clean_title = re.sub(r'[^\w\s\-_]', '', video_title)[:40].strip()
        bot.edit_message_text("📥 Đang tải video lên Telegram...", message.chat.id, status_msg.message_id)

        # Tải video giống bot XHS: dùng .content trực tiếp với timeout rõ ràng,
        # tránh vòng lặp iter_content thủ công có thể bị treo khi mạng chập chờn.
        video_resp = requests.get(
            video_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"}
        )
        video_bytes = video_resp.content

        bot.send_video(
            chat_id=message.chat.id,
            video=video_bytes,
            caption=f"🎬 {clean_title}",
            reply_to_message_id=message.message_id,
            supports_streaming=True
        )
        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as error:
        print(f"[Upload] Lỗi: {error}")
        try:
            markup = telebot.types.InlineKeyboardMarkup()
            if video_url:
                markup.add(telebot.types.InlineKeyboardButton("👉 Bấm vào đây để tải video", url=video_url))
            bot.edit_message_text(
                "⚠️ File quá nặng (>50MB) hoặc mạng bị nghẽn.\n"
                "Bấm nút dưới để tải về máy:" if video_url else
                "⚠️ Có lỗi xảy ra, vui lòng thử lại sau.",
                message.chat.id, status_msg.message_id,
                reply_markup=markup if video_url else None
            )
        except Exception:
            pass


# ============================================================
# 4. KHỞI ĐỘNG
# Vòng lặp ngoài để tự khởi động lại polling nếu bị crash/mất kết nối,
# tránh tình trạng bot "đơ" vĩnh viễn cho tới khi có người restart thủ công.
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()

    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(1)
            print("✅ Bot TikTok sẵn sàng!")
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as e:
            print(f"[Polling] Lỗi, khởi động lại sau 5 giây: {e}")
            time.sleep(5)
