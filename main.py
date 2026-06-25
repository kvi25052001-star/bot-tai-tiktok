import os
import re
import time
import requests
import telebot
from flask import Flask
from threading import Thread

BOT_TOKEN = os.environ.get('BOT_TOKEN', 'AAE_a32hEqaLrXAn3KY_6met0ODG9zzY8yU')
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

app = Flask('')

@app.route('/')
def home():
    return "Bot TikTok dang hoat dong!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

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
        print(f"[API1-tikwm] Loi: {e}")

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
        print(f"[API2-ssstik] Loi: {e}")

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
        print(f"[API3-savetik] Loi: {e}")

    return None, None


def expand_short_url(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        return r.url
    except Exception:
        return url


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Xin chao! Gui link TikTok hoac Douyin, toi se tai video *khong logo* ve cho ban!\n\n"
        "Ho tro:\n"
        "• https://www.tiktok.com/@.../video/...\n"
        "• https://vm.tiktok.com/...\n"
        "• https://vt.tiktok.com/...\n"
        "• https://www.douyin.com/video/...",
        parse_mode="Markdown"
    )


def process_video(message, url):
    video_url = None
    status_msg = bot.reply_to(message, "🔄 Dang phan tich link...")

    try:
        if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
            bot.edit_message_text("🔗 Dang mo link rut gon...", message.chat.id, status_msg.message_id)
            url = expand_short_url(url)

        bot.edit_message_text("📡 Dang boc tach link video...", message.chat.id, status_msg.message_id)
        video_url, video_title = get_tiktok_video(url)

        if not video_url:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🌐 Thu tai thu cong", url="https://ssstik.io"))
            bot.edit_message_text(
                "❌ Khong lay duoc link video.\nVideo co the bi rieng tu hoac da bi xoa.",
                message.chat.id, status_msg.message_id,
                reply_markup=markup
            )
            return

        clean_title = re.sub(r'[^\w\s\-_]', '', video_title)[:40].strip()
        bot.edit_message_text("📥 Dang tai video len Telegram...", message.chat.id, status_msg.message_id)

        video_resp = requests.get(
            video_url,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"},
            stream=True
        )
        chunks = b""
        for chunk in video_resp.iter_content(chunk_size=524288):
            if chunk:
                chunks += chunk

        bot.send_video(
            chat_id=message.chat.id,
            video=chunks,
            caption=f"🎬 {clean_title}",
            reply_to_message_id=message.message_id,
            supports_streaming=True
        )
        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as error:
        print(f"[Upload] Loi: {error}")
        try:
            markup = telebot.types.InlineKeyboardMarkup()
            if video_url:
                markup.add(telebot.types.InlineKeyboardButton("👉 Bam vao day de tai video", url=video_url))
            bot.edit_message_text(
                "⚠️ File qua nang (>50MB) hoac mang Render bi nghen.\n"
                "Bam nut duoi de tai ve may:",
                message.chat.id, status_msg.message_id,
                reply_markup=markup
            )
        except Exception:
            pass


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
    t = Thread(target=process_video, args=(message, url))
    t.daemon = True
    t.start()


if __name__ == "__main__":
    Thread(target=run_flask).start()
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception:
        pass
    print("✅ Bot TikTok san sang!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
