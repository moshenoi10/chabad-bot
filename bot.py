import os
import json
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WP_URL = "https://chabadupdates.com/wp-json/wp/v2"
WP_USER = os.environ["WP_USER"]
WP_PASSWORD = os.environ["WP_PASSWORD"]
CHANNEL_ID = "-1003967710127"
VIMEO_TOKEN = os.environ.get("VIMEO_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "UCXhNK4F73hySVUj66u5GFjg")
GOOGLE_DRIVE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY", "")
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET", "")
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# ─── מערכת מייל ────────────────────────────────────────
email_system = {
    "active": True,              # האם המערכת פעילה
    "interval": 1800,            # כל כמה שניות לבדוק (ברירת מחדל: 30 דקות)
    "allowed_senders": ["mnoishtat@gmail.com"],  # כתובות מורשות
    "last_check": 0,             # זמן הבדיקה האחרונה
    "seen_ids": set(),           # מיילים שכבר טופלו
    "pending_email": {}          # מייל ממתין לאישור
}
youtube_tokens = {}

# ─── מילים עם גרש ─────────────────────────────────────────
GERESH_WORDS = ['חב״ד', 'ל״ג', 'ת״ת', 'ע״י', 'ע״ה', 'ז״ל', 'ב״ה',
                'כ״ק', 'רשב״י', 'שליט״א', 'אדמו״ר', 'נשיא״נו',
                'יבלחט״א', 'משב״ק', 'לנצ״נ', 'נ״ע', 'ז״י', 'הי״ד',
                'בל״נ', 'כ״ה', 'י״ב', 'י״ג', 'י״ד', 'ט״ו', 'ט״ז',
                'נ״י', 'ב״ב', 'ת״ח', 'ר״מ', 'ר״י', 'ר״ח', 'ר״ת',
                'ד״ת', 'ב״ד', 'כ״ד', 'ט״ז', 'מ״מ', 'א״א', 'ל״ע']

# ─── הגדרות ווטרמארק ────────────────────────────────────────
watermark_settings = {
    "enabled": True,
    "text": "עדכוני חב״ד",
    "font_size": 40,           # גודל פיקסלים
    "text_color": "#FFFFFF",   # hex color
    "bg_color": "#000000",     # hex color
    "bg_opacity": 140,         # 0-255
    "pos_x": 95,               # אחוז מרוחב (0-100), מימין
    "pos_y": 95,               # אחוז מגובה (0-100), מלמטה
    "font": "default",         # default / bold / serif
    "logo_bytes": None,        # תמונת לוגו במקום טקסט
    "mode": "text"             # text / logo
}

# ─── מערכת הרשאות ────────────────────────────────────────
SUPER_ADMIN_ID = "1798097090"

# רמות הרשאה: "admin", "senior_editor", "editor", "blocked"
users_permissions = {
    SUPER_ADMIN_ID: "admin"
}

def get_permission(user_id):
    uid = str(user_id)
    if uid == SUPER_ADMIN_ID:
        return "admin"
    return users_permissions.get(uid, None)

def is_admin(user_id):
    return get_permission(str(user_id)) == "admin"

def is_senior_editor(user_id):
    return get_permission(str(user_id)) in ("admin", "senior_editor")

def is_editor(user_id):
    return get_permission(str(user_id)) in ("admin", "senior_editor", "editor")

# לוג פעולות
activity_log = []

def log_action(user_id, username, action):
    entry = {
        "time": time.strftime("%d/%m/%Y %H:%M"),
        "user_id": user_id,
        "username": username,
        "action": action
    }
    activity_log.append(entry)
    if len(activity_log) > 100:
        activity_log.pop(0)
    print(f"📋 לוג: {entry['time']} | {username} | {action}", flush=True)

def send_image(chat_id, image_bytes, caption=""):
    """שולח תמונה לטלגרם"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=30
        )
    except Exception as e:
        print(f"שגיאה שליחת תמונה: {e}", flush=True)

def notify_admin_error(error_msg):
    # סנן שגיאות רשת זמניות – לא צריך להודיע על ניתוקים רגילים
    ignore_patterns = [
        "Connection aborted",
        "Connection reset by peer",
        "Network is unreachable",
        "Failed to establish a new connection",
        "Max retries exceeded",
        "Read timed out",
        "Connection refused",
        "RemoteDisconnected",
        "ConnectionResetError",
        "NewConnectionError",
        "TimeoutError",
        "HTTPSConnectionPool",
    ]
    for pattern in ignore_patterns:
        if pattern in str(error_msg):
            print(f"ניתוק רגיל – לא מודיע: {error_msg[:100]}", flush=True)
            return
    # שגיאה אמיתית – שלח הודעה בעברית
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": SUPER_ADMIN_ID, "text": f"⚠️ <b>שגיאה בבוט:</b>\n\n{error_msg[:500]}", "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as _e:
        print(f"שגיאה בשליחת התראה: {_e}", flush=True)

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/youtube/callback"):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            code = query.get("code", [None])[0]
            if code:
                tokens = get_youtube_token(code)
                if tokens:
                    youtube_tokens["access_token"] = tokens.get("access_token")
                    youtube_tokens["refresh_token"] = tokens.get("refresh_token")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write("✅ YouTube מחובר! חזור לטלגרם.".encode())
                    return
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

import pickle

drafts = {}
DRAFTS_FILE = "/tmp/drafts.pkl"

def save_drafts():
    try:
        with open(DRAFTS_FILE, "wb") as f:
            safe_drafts = {}
            for uid, d in drafts.items():
                safe = {k: v for k, v in d.items() 
                       if k not in ("main_image", "gallery", "mazaltov_images", "pending_group_files")}
                safe_drafts[uid] = safe
            pickle.dump(safe_drafts, f)
    except Exception as _e:
        print(f"שגיאה: {_e}", flush=True)

def load_drafts():
    global drafts
    try:
        with open(DRAFTS_FILE, "rb") as f:
            drafts = pickle.load(f)
    except:
        drafts = {}
offset = 0

ADMIN_MENU = {
    "keyboard": [
        [{"text": "✍️ כתבה חדשה"}, {"text": "🤖 העלאה חכמה"}],
        [{"text": "🎉 מזל טוב"}, {"text": "🎬 העלאה ליוטיוב"}],
        [{"text": "✏️ עריכת כתבה"}, {"text": "🗑️ מחיקת כתבה"}],
        [{"text": "📋 כתבות אחרונות"}, {"text": "📝 טיוטות"}],
        [{"text": "👥 ניהול משתמשים"}, {"text": "📊 לוג פעולות"}],
        [{"text": "📧 ניהול מייל"}, {"text": "📈 אנליטיקס"}],
        [{"text": "📢 הפצת תוכן"}, {"text": "🎥 הפצת וידאו"}],
        [{"text": "🌐 ניהול רשתות"}, {"text": "⚙️ הגדרות מערכת"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

SENIOR_EDITOR_MENU = {
    "keyboard": [
        [{"text": "✍️ כתבה חדשה"}, {"text": "🤖 העלאה חכמה"}],
        [{"text": "🎉 מזל טוב"}, {"text": "🎬 העלאה ליוטיוב"}],
        [{"text": "✏️ עריכת כתבה"}, {"text": "🗑️ מחיקת כתבה"}],
        [{"text": "📋 כתבות אחרונות"}, {"text": "📝 טיוטות"}],
        [{"text": "📧 ניהול מייל"}, {"text": "📈 אנליטיקס"}],
        [{"text": "📢 הפצת תוכן"}, {"text": "🎥 הפצת וידאו"}],
        [{"text": "🌐 ניהול רשתות"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

EDITOR_MENU = {
    "keyboard": [
        [{"text": "✍️ כתבה חדשה"}, {"text": "🎉 מזל טוב"}],
        [{"text": "✏️ עריכת כתבה"}, {"text": "🎬 העלאה ליוטיוב"}],
        [{"text": "📢 הפצת תוכן"}, {"text": "🎥 הפצת וידאו"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

# לשמור תאימות אחורה
MAIN_MENU = SENIOR_EDITOR_MENU

def edit_message(chat_id, message_id, text, reply_markup=None):
    """עורך הודעה קיימת במקום לשלוח חדשה"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"שגיאה edit_message: {e}", flush=True)

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(url, json=data, timeout=10)
        if not resp.ok:
            # נסה בלי parse_mode
            data2 = {"chat_id": chat_id, "text": text}
            if reply_markup:
                data2["reply_markup"] = json.dumps(reply_markup)
            requests.post(url, json=data2, timeout=10)
    except Exception as e:
        print(f"שגיאה שליחה: {e}")

def get_youtube_auth_url():
    params = {
        "client_id": YOUTUBE_CLIENT_ID,
        "redirect_uri": "https://chabad-bot.onrender.com/youtube/callback",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube",
        "access_type": "offline",
        "prompt": "consent"
    }
    from urllib.parse import urlencode
    return "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)

def get_youtube_token(code):
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "redirect_uri": "https://chabad-bot.onrender.com/youtube/callback",
        "grant_type": "authorization_code"
    })
    if resp.status_code == 200:
        return resp.json()
    return None

def refresh_youtube_token(refresh_token):
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "refresh_token": refresh_token,
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "grant_type": "refresh_token"
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None

def upload_to_youtube(video_bytes, title, description="", tags=[]):
    if not youtube_tokens.get("access_token"):
        return None, "לא מחובר ל-YouTube"
    try:
        access_token = youtube_tokens["access_token"]
        if youtube_tokens.get("refresh_token"):
            new_token = refresh_youtube_token(youtube_tokens["refresh_token"])
            if new_token:
                youtube_tokens["access_token"] = new_token
                access_token = new_token

        headers = {"Authorization": f"Bearer {access_token}"}
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",
                "channelId": YOUTUBE_CHANNEL_ID
            },
            "status": {"privacyStatus": "public"}
        }
        import json as json_lib
        from requests_toolbelt import MultipartEncoder
        
        init_resp = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={**headers, "Content-Type": "application/json", "X-Upload-Content-Type": "video/*"},
            json=metadata
        )
        if init_resp.status_code != 200:
            return None, f"שגיאה: {init_resp.text[:200]}"
        
        upload_url = init_resp.headers.get("Location")
        upload_resp = requests.put(upload_url, headers={**headers, "Content-Type": "video/*"}, data=video_bytes, timeout=300)
        
        if upload_resp.status_code in (200, 201):
            video_id = upload_resp.json()["id"]
            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            # בדוק אם הסרטון קצר מ-60 שניות – אם כן הוסף #Shorts
            if len(video_bytes) < 50_000_000:  # סרטון קטן מ-50MB כנראה קצר
                yt_url = f"https://www.youtube.com/shorts/{video_id}"
            return yt_url, None
        return None, f"שגיאה: {upload_resp.status_code}"
    except Exception as e:
        return None, str(e)

def wait_for_vimeo(video_id, max_wait=300):
    headers = {
        "Authorization": f"bearer {VIMEO_TOKEN}",
        "Accept": "application/vnd.vimeo.*+json;version=3.4"
    }
    for _ in range(max_wait // 10):
        try:
            r = requests.get(f"https://api.vimeo.com/videos/{video_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                status = r.json().get("transcode", {}).get("status", "")
                if status == "complete":
                    return True
        except Exception as _e:
            print(f"שגיאה: {_e}", flush=True)
        time.sleep(10)
    return False

def upload_to_vimeo(video_bytes, title="סרטון חדש", chat_id=None):
    if not VIMEO_TOKEN:
        return None, None
    try:
        headers = {
            "Authorization": f"bearer {VIMEO_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.vimeo.*+json;version=3.4"
        }
        size = len(video_bytes)
        size_mb = size // 1024 // 1024
        print(f"מתחיל העלאה ל-Vimeo: {size_mb}MB", flush=True)

        if chat_id and size_mb > 10:
            send_message(chat_id, f"⏳ מעלה סרטון ל-Vimeo ({size_mb}MB)...\nזה עשוי לקחת כמה דקות.")

        create_resp = requests.post(
            "https://api.vimeo.com/me/videos",
            headers=headers,
            json={
                "upload": {"approach": "tus", "size": size},
                "name": title,
                "privacy": {"view": "anybody"}
            },
            timeout=30
        )
        if create_resp.status_code != 200:
            print(f"שגיאה יצירת Vimeo: {create_resp.text[:200]}", flush=True)
            return None, None

        upload_link = create_resp.json()["upload"]["upload_link"]
        video_uri = create_resp.json()["uri"]
        video_id = video_uri.split("/")[-1]

        chunk_size = 5 * 1024 * 1024  # 5MB chunks
        offset = 0
        start_time = time.time()
        last_update = 0

        while offset < size:
            chunk = video_bytes[offset:offset + chunk_size]
            chunk_resp = requests.patch(
                upload_link,
                headers={
                    "Tus-Resumable": "1.0.0",
                    "Upload-Offset": str(offset),
                    "Content-Type": "application/offset+octet-stream",
                    "Content-Length": str(len(chunk))
                },
                data=chunk,
                timeout=120
            )
            if chunk_resp.status_code not in (204, 200):
                print(f"שגיאה chunk Vimeo: {chunk_resp.status_code}", flush=True)
                return None, None

            offset += len(chunk)
            elapsed = time.time() - start_time
            progress = offset / size
            
            # שלח עדכון כל 20% או כל 30 שניות
            if chat_id and size_mb > 10:
                should_update = (progress - last_update >= 0.2) or (elapsed - last_update * elapsed >= 30)
                if progress - last_update >= 0.19:
                    last_update = progress
                    remaining = (elapsed / progress * (1 - progress)) if progress > 0 else 0
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    time_str = f"{mins}:{secs:02d} דקות" if mins > 0 else f"{secs} שניות"
                    pct = int(progress * 100)
                    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                    send_message(chat_id, f"📤 מעלה ל-Vimeo: {pct}%\n{bar}\n⏱ זמן משוער: {time_str}")

            print(f"Vimeo: {offset//1024//1024}MB / {size_mb}MB ({int(progress*100)}%)", flush=True)

        total_time = int(time.time() - start_time)
        mins = total_time // 60
        secs = total_time % 60
        time_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs} שניות"
        print(f"✅ Vimeo {video_id} הועלה ב-{time_str}!", flush=True)
        return f"https://vimeo.com/{video_id}", video_id

    except Exception as e:
        print(f"שגיאה Vimeo: {e}", flush=True)
        return None, None

def notify_channel(title, subtitle, url):
    text = f"*עדכוני חב״ד - {title}*\n{subtitle}\n\n*לכתבה המלאה לחצו ⬇️*\n{url}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"שגיאה שליחה לערוץ: {e}")

def post_to_twitter(text, url=""):
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return False, "מפתחות Twitter חסרים"
    try:
        import hmac, hashlib, base64, urllib.parse, time as time_mod

        tweet_text = f"{text}\n\n{url}" if url else text
        if len(tweet_text) > 280:
            tweet_text = f"{text[:270 - len(url)]}...\n\n{url}"

        endpoint = "https://api.twitter.com/2/tweets"
        timestamp = str(int(time_mod.time()))
        nonce = base64.b64encode(os.urandom(16)).decode().strip("=+/")

        oauth_params = {
            "oauth_consumer_key": TWITTER_API_KEY,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_token": TWITTER_ACCESS_TOKEN,
            "oauth_version": "1.0"
        }

        param_string = "&".join([
            f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(oauth_params.items())
        ])
        base_string = "&".join([
            "POST",
            urllib.parse.quote(endpoint, safe=''),
            urllib.parse.quote(param_string, safe='')
        ])
        signing_key = f"{urllib.parse.quote(TWITTER_API_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_SECRET, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature
        auth_header = "OAuth " + ", ".join([
            f'{urllib.parse.quote(str(k), safe="")}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        ])

        resp = requests.post(
            endpoint,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"text": tweet_text},
            timeout=15
        )
        if resp.status_code in (200, 201):
            return True, resp.json().get("data", {}).get("id", "")
        return False, resp.text[:300]
    except Exception as e:
        return False, str(e)




    """מפרסם טוויט עם כותרת ולינק"""
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return False, "מפתחות Twitter חסרים"
    try:
        import hmac
        import hashlib
        import base64
        import urllib.parse
        import time as time_mod

        tweet_text = f"{text}\n\n{url}" if url else text
        # קצר ל-280 תווים
        if len(tweet_text) > 280:
            max_title = 280 - len(url) - 5
            tweet_text = f"{text[:max_title]}...\n\n{url}"

        # OAuth 1.0a signature
        endpoint = "https://api.twitter.com/2/tweets"
        timestamp = str(int(time_mod.time()))
        nonce = base64.b64encode(os.urandom(16)).decode().strip("=+/")

        oauth_params = {
            "oauth_consumer_key": TWITTER_API_KEY,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_token": TWITTER_ACCESS_TOKEN,
            "oauth_version": "1.0"
        }

        # בנה signature
        param_string = "&".join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
                                  for k, v in sorted(oauth_params.items())])
        base_string = f"POST&{urllib.parse.quote(endpoint, safe='')}&{urllib.parse.quote(param_string, safe='')}"
        signing_key = f"{urllib.parse.quote(TWITTER_API_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_SECRET, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature
        auth_header = "OAuth " + ", ".join([f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
                                             for k, v in sorted(oauth_params.items())])

        resp = requests.post(
            endpoint,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"text": tweet_text},
            timeout=15
        )
        if resp.status_code in (200, 201):
            return True, resp.json().get("data", {}).get("id", "")
        return False, resp.text[:200]
    except Exception as e:
        return False, str(e)


    text = f"*עדכוני חב\"ד - {title}*\n{subtitle}\n{url}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"שגיאה שליחה לערוץ: {e}")

def get_menu(user_id):
    perm = get_permission(str(user_id))
    if perm == "admin":
        return ADMIN_MENU
    elif perm == "senior_editor":
        return SENIOR_EDITOR_MENU
    return EDITOR_MENU

def get_wp_categories():
    try:
        resp = requests.get(f"{WP_URL}/categories?per_page=100",
                           auth=(WP_USER, WP_PASSWORD), timeout=10)
        if resp.status_code == 200:
            return {cat["name"]: cat["id"] for cat in resp.json()}
    except Exception as e:
        print(f"שגיאה קטגוריות: {e}")
    return {}

def upload_image_to_wp(image_bytes, filename):
    try:
        url = f"{WP_URL}/media"
        headers = {"Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": "image/jpeg"}
        resp = requests.post(url, headers=headers, data=image_bytes,
                            auth=(WP_USER, WP_PASSWORD), timeout=30)
        if resp.status_code == 201:
            return resp.json()["id"], resp.json()["source_url"]
    except Exception as e:
        print(f"שגיאה העלאת תמונה: {e}")
    return None, None

def publish_to_wp(draft, status="publish", schedule_date=None):
    vimeo_ids = draft.get("vimeo_ids", [])
    if vimeo_ids:
        print(f"ממתין לעיבוד {len(vimeo_ids)} סרטוני Vimeo...", flush=True)
        for vid_id in vimeo_ids:
            wait_for_vimeo(vid_id, max_wait=120)
        print("כל הסרטונים מוכנים!", flush=True)
    featured_id = None
    if draft.get("main_image"):
        featured_id, _ = upload_image_to_wp(draft["main_image"], "main.jpg")

    gallery_content = ""
    for i, img in enumerate(draft.get("gallery", [])):
        img_id, img_url = upload_image_to_wp(img, f"gallery_{i}.jpg")
        if img_url:
            gallery_content += f'\n<figure class="wp-block-image size-full"><img src="{img_url}" /></figure>\n'

    body_text = convert_whatsapp_format(draft.get("body", ""))
    import re
    paragraphs = [p.strip() for p in re.split(r'\n{1,}', body_text) if p.strip()]
    if paragraphs:
        content = "\n\n".join([f"<!-- wp:paragraph -->\n<p>{p}</p>\n<!-- /wp:paragraph -->" for p in paragraphs])
    else:
        content = f"<!-- wp:paragraph -->\n<p>{body_text}</p>\n<!-- /wp:paragraph -->"
    if gallery_content:
        content += "\n\n" + gallery_content

    if draft.get("video_url"):
        url = draft["video_url"]
        content += f'\n\n<!-- wp:embed {{"url":"{url}","type":"video","providerNameSlug":"vimeo","responsive":true}} -->\n<figure class="wp-block-embed is-type-video is-provider-vimeo"><div class="wp-block-embed__wrapper">\n{url}\n</div></figure>\n<!-- /wp:embed -->'

    for url in draft.get("videos", []):
        if "vimeo.com" in url:
            video_id = url.split("/")[-1].split("?")[0]
            content += f'\n\n<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="https://player.vimeo.com/video/{video_id}" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>\n'
        elif "youtube.com" in url or "youtu.be" in url:
            content += f'\n\n<!-- wp:embed {{"url":"{url}","type":"video","providerNameSlug":"youtube","responsive":true}} -->\n<figure class="wp-block-embed is-type-video is-provider-youtube"><div class="wp-block-embed__wrapper">\n{url}\n</div></figure>\n<!-- /wp:embed -->'

    # העלאת PDF לוורדפרס
    # הוספת PDF שכבר הועלו לאתר
    for pdf in draft.get("pdf_embeds", []):
        pdf_url = pdf["url"]
        pdf_name = pdf["name"]
        content += f'\n\n<div class="wp-block-file"><object data="{pdf_url}" type="application/pdf" width="100%" height="600px"><a href="{pdf_url}">{pdf_name}</a></object></div>'

    # העלאת PDF ישן (גיבוי)
    for pdf in draft.get("pdf_files", []):
        try:
            print(f"מעלה PDF: {pdf['name']} ({len(pdf['bytes'])} bytes)", flush=True)
            url = f"{WP_URL}/media"
            headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(pdf['name'])}",
                      "Content-Type": "application/pdf"}
            resp = requests.post(url, headers=headers, data=pdf["bytes"],
                               auth=(WP_USER, WP_PASSWORD), timeout=60)
            print(f"PDF upload status: {resp.status_code}", flush=True)
            if resp.status_code == 201:
                pdf_url = resp.json()["source_url"]
                pdf_name = pdf["name"]
                content += f'\n\n<div class="wp-block-file"><object data="{pdf_url}" type="application/pdf" width="100%" height="600px"><a href="{pdf_url}">{pdf_name}</a></object></div>'
            else:
                print(f"PDF error: {resp.text[:200]}", flush=True)
        except Exception as e:
            print(f"שגיאה העלאת PDF: {e}", flush=True)

    # העלאת קבצי שמע לוורדפרס
    for audio in draft.get("audio_files", []):
        try:
            url = f"{WP_URL}/media"
            headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(audio['name'])}",
                      "Content-Type": "audio/mpeg"}
            resp = requests.post(url, headers=headers, data=audio["bytes"],
                               auth=(WP_USER, WP_PASSWORD), timeout=30)
            if resp.status_code == 201:
                audio_url = resp.json()["source_url"]
                content += f'\n\n<!-- wp:audio -->\n<figure class="wp-block-audio"><audio controls src="{audio_url}"></audio></figure>\n<!-- /wp:audio -->'
        except Exception as e:
            print(f"שגיאה העלאת שמע: {e}", flush=True)

    tag_ids = []
    for tag in draft.get("tags", []):
        try:
            r = requests.post(f"{WP_URL}/tags", json={"name": tag},
                            auth=(WP_USER, WP_PASSWORD), timeout=10)
            if r.status_code in (200, 201):
                tag_ids.append(r.json()["id"])
        except Exception as _e:
            print(f"שגיאה: {_e}", flush=True)

    post_data = {
        "title": draft.get("title", ""),
        "content": content,
        "excerpt": draft.get("subtitle", ""),
        "status": status,
        "categories": draft.get("categories", []),
        "tags": tag_ids,
    }
    # הוסף ACF רק אם יש ערך לא ריק
    red_title = draft.get("red_title", "").strip()
    print(f"red_title: '{red_title}'", flush=True)
    if red_title:
        post_data["meta"] = {"tag_label": red_title}
    if schedule_date:
        post_data["date"] = schedule_date
    if featured_id:
        post_data["featured_media"] = featured_id

    resp = requests.post(f"{WP_URL}/posts", json=post_data,
                        auth=(WP_USER, WP_PASSWORD), timeout=30)
    return resp

def get_file(file_id):
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}", timeout=10)
        file_path = r.json()["result"]["file_path"]
        img = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=30)
        return img.content
    except Exception as e:
        print(f"שגיאה קבלת קובץ: {e}")
    return None

def add_images_to_post(post_id, image_urls):
    try:
        r = requests.get(
            f"{WP_URL}/posts/{post_id}?context=edit",
            auth=(WP_USER, WP_PASSWORD), timeout=10
        )
        if r.status_code != 200:
            return False
        
        post_data = r.json()
        existing_content = post_data.get("content", {}).get("raw", "") or post_data.get("content", {}).get("rendered", "")
        
        new_images = ""
        for img_url in image_urls:
            new_images += f'\n<figure class="wp-block-image size-full"><img src="{img_url}" /></figure>\n'
        
        new_content = existing_content + new_images
        
        update = requests.post(
            f"{WP_URL}/posts/{post_id}",
            json={"content": new_content},
            auth=(WP_USER, WP_PASSWORD), timeout=10
        )
        return update.status_code == 200
    except Exception as e:
        print(f"שגיאה הוספת תמונות: {e}", flush=True)
        return False

def convert_whatsapp_format(text):
    import re
    text = re.sub(r'\*([^*]+)\*', r'<strong>\1</strong>', text)
    text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)
    text = re.sub(r'~([^~]+)~', r'<s>\1</s>', text)
    return text

def process_with_groq(text, prompt=None):
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return None
    if prompt is None:
        prompt = build_groq_prompt(text)
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=60
        )
        if resp.status_code == 200:
            result = resp.json()["choices"][0]["message"]["content"]
            return clean_json_string(result)
        if resp.status_code == 429:
            print(f"Groq 429, ממתין 30 שניות...", flush=True)
            time.sleep(30)
            # נסיון שני
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 2000},
                timeout=60
            )
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"]
                return clean_json_string(result)
        print(f"שגיאה Groq: {resp.status_code} | {resp.text[:300]}", flush=True)
    except Exception as e:
        print(f"שגיאה Groq: {e}", flush=True)
    return None

def clean_json_string(result):
    import re
    result = result.strip().replace("```json", "").replace("```", "").strip()
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', result)
    first_brace = result.find("{")
    last_brace = result.rfind("}")
    if first_brace == -1 or last_brace == -1:
        print(f"שגיאה JSON: לא נמצאו סוגריים\nתשובה: {result[:300]}", flush=True)
        return None
    result = result[first_brace:last_brace+1]

    def fix_quotes(s):
        """מתקן גרשיים כפולים שנמצאים בתוך ערכי JSON"""
        output = []
        in_string = False
        i = 0
        while i < len(s):
            c = s[i]
            if c == '\\' and i + 1 < len(s):
                output.append(c)
                output.append(s[i+1])
                i += 2
                continue
            if c == '"':
                if not in_string:
                    in_string = True
                    output.append(c)
                else:
                    j = i + 1
                    while j < len(s) and s[j] in (' ', '\t'):
                        j += 1
                    if j >= len(s) or s[j] in (':', ',', '}', ']', '\n', '\r'):
                        in_string = False
                        output.append(c)
                    else:
                        output.append('\u05f4')
            else:
                output.append(c)
            i += 1
        return ''.join(output)

    # ניסיון ראשון – ישיר
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        pass
    # תיקון newlines לפני fix_quotes
    result_nl = result.replace('\n', '\\n').replace('\r', '')
    try:
        return json.loads(result_nl)
    except json.JSONDecodeError:
        pass
    # תיקון גרשיים
    fixed = fix_quotes(result)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # תיקון גרשיים + newlines
    fixed2 = fix_quotes(result_nl)
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError as e:
        print(f"שגיאה JSON סופית: {e}\nתשובה: {result[:500]}", flush=True)
        return None

def prepare_text_for_ai(text):
    """מכין טקסט לשליחה ל-AI – מחליף גרשיים עבריים בתו בטוח"""
    import re
    # החלף " בין אותיות עבריות (כמו ת"ת, ל"ג, אדמו"ר)
    text = re.sub(r'(?<=[א-ת])"(?=[א-ת])', '״', text)
    # החלף " אחרי אות עברית ולפני רווח (כמו כ"ק )
    text = re.sub(r'(?<=[א-ת])"(?=\s)', '״', text)
    # החלף " אחרי אות עברית בסוף מילה
    text = re.sub(r'(?<=[א-ת])"(?=[,\.!?\s\n])', '״', text)
    return text

def restore_geresh(text):
    """מחזיר גרשיים עבריים למילים נפוצות"""
    if not text:
        return text
    common = {
        'חב ד': 'חב״ד', 'ל ג': 'ל״ג', 'אדמו ר': 'אדמו״ר',
        'כ ק': 'כ״ק', 'ע ה': 'ע״ה', 'ז ל': 'ז״ל',
        'שליט א': 'שליט״א', 'ת ת': 'ת״ת', 'ע י': 'ע״י',
        'רשב י': 'רשב״י', 'ב ה': 'ב״ה',
    }
    for wrong, right in common.items():
        text = text.replace(wrong, right)
    return text

def auto_detect_geresh(text):
    """סורק טקסט גולמי ומוסיף מילים עם גרש לרשימה אוטומטית"""
    import re
    if not text:
        return
    found = re.findall(r'[א-ת]+"[א-ת]+', text)
    for word in found:
        normalized = word.replace('"', '״')
        if normalized not in GERESH_WORDS:
            GERESH_WORDS.append(normalized)
            print(f"📝 נוסף לרשימת גרשיים: {normalized}", flush=True)

def fix_geresh(text):
    """מנקה בעיות גרשיים בטקסט שהגיע מ-AI"""
    import re
    if not text:
        return text
    # שלב 1: תקן ״" לפני אות → רווח
    text = re.sub(r'״"([א-ת])', r'״ \1', text)
    # שלב 2: החלף " רגיל בין אותיות עבריות ב-״
    text = re.sub(r'([א-ת])"([א-ת])', r'\1״\2', text)
    text = re.sub(r'([א-ת])"([\s,.\-:!?•]|$)', r'\1״\2', text)
    # שלב 3: נקה ״״ כפול
    text = text.replace('״״', '״')
    # שלב 4: שמור מילים מוכרות עם placeholder
    pre_placeholders = {}
    for i, word in enumerate(GERESH_WORDS):
        pattern = r'(?<![א-ת])' + re.escape(word) + r'(?![א-ת])'
        if re.search(pattern, text):
            ph = f"__PRE{i}__"
            pre_placeholders[ph] = word
            text = re.sub(pattern, ph, text)
    # שלב 5: כל ״ שדבוק לאות הבאה – הוסף רווח
    text = re.sub(r'(״)([א-ת])', r'״ \2', text)
    # שלב 6: שחזר מילים מוכרות
    for ph, word in pre_placeholders.items():
        text = text.replace(ph, word)
    return text

def build_groq_prompt(text):
    """פרומפט קצר יותר לGroq שמוגבל ב-tokens"""
    if len(text) > 800:
        text = text[:800] + "..."
    return f"""אתה עורך חדשות. החזר JSON בלבד ללא שום טקסט אחר.
פורמט מדויק:
{{"title":"כותרת עד 10 מילים עם נקודתיים","subtitle":"משפט1 7-9 מילים • משפט2 7-9 מילים • משפט3 7-9 מילים","red_title":"2-4 מילים","body":"גוף הטקסט בפסקאות","tags":["תגית1","תגית2","תגית3","תגית4","תגית5"]}}

טקסט: {text}"""

def build_prompt(text):
    return f"""אתה עורך חדשות חרדי מקצועי. קרא את הטקסט וצור ממנו כתבה עיתונאית.

כותרת ראשית:
- עד 8 מילים
- פורמט: נושא + נקודתיים + פרט. לדוגמה: "פטירת רבנית בירושלים: קהילה שרויה באבל"
- אסור להתחיל בשם האתר
- אסור להשתמש בכוכביות * או סימני עיצוב אחרים
- נקודתיים פעם אחת בלבד

כותרת משנה:
- 2-3 משפטים מופרדים ב-•
- כל משפט 7-9 מילים
- לא להתחיל ב-• ולא לסיים ב-•
- אסור כוכביות * או סימני עיצוב
- אסור מרכאות או גרשיים על מילים רגילות

כותרת אדומה:
- 2-4 מילים בלבד
- אסור כוכביות או סימני עיצוב

גוף הכתבה:
- העתק את הטקסט המקורי מילה במילה
- חלק לפסקאות של 2-4 משפטים
- הסר * _ ~ אבל שמור על תוכן המילים
- אסור להוסיף או להמציא

תגיות:
- 5-8 מילות מפתח מהטקסט

גרשיים – כלל ברזל:
- גרש עברי ״ מותר רק במילים שבטקסט המקורי כתובות עם " כמו חב"ד, ל"ג, משב"ק
- אסור לשים ״ על שמות, ציטוטים, כותרות ספרים, שמות מקומות
- ציטוטים: כתוב בלי מרכאות בכלל

החזר JSON בלבד ללא שום טקסט נוסף:
{{"title":"...","subtitle":"...","red_title":"...","body":"...","tags":["...","...","...","...","..."]}}

טקסט:
{text}"""



def process_with_gemini(text):
    if not GEMINI_API_KEY:
        return None
    # סרוק את הטקסט הגולמי ומצא מילים עם גרש
    auto_detect_geresh(text)
    text = prepare_text_for_ai(text)
    prompt = build_prompt(text)
    try:
        for attempt in range(2):
            print(f"Gemini ניסיון {attempt+1}...", flush=True)
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60
            )
            if resp.status_code in (429, 503):
                if attempt == 0:
                    print(f"Gemini 429, ממתין 20 שניות...", flush=True)
                    time.sleep(20)
                    continue
                print(f"Gemini 429 שוב, עובר ל-Groq...", flush=True)
                break
            if resp.status_code == 200:
                result = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = clean_json_string(result)
                if parsed:
                    for field in ["title", "subtitle", "red_title", "body"]:
                        if field in parsed and parsed[field]:
                            parsed[field] = fix_geresh(restore_geresh(parsed[field]))
                    return parsed
                return None
            print(f"שגיאה Gemini: {resp.status_code} {resp.text[:100]}", flush=True)
            break
    except Exception as e:
        print(f"שגיאה Gemini exception: {e}", flush=True)
    
    # גיבוי – Groq
    print("עובר ל-Groq כגיבוי...", flush=True)
    return process_with_groq(text)

def improve_titles_with_ai(draft):
    text = draft.get("body", "")
    prompt = f"""אתה עורך ראשי של אתר חדשות חרדי. הכותרות הבאות חיוורות מדי – שפר אותן לרמה עיתונאית גבוהה.

כותרת נוכחית: {draft.get('title','')}
כותרת משנה נוכחית: {draft.get('subtitle','')}
כותרת אדומה נוכחית: {draft.get('red_title','')}

גוף הכתבה לעיון:
{text[:500]}

כללים:
- כותרת ראשית: שילוב רגש + עובדה + שם מרכזי, עם נקודתיים (:) ליצירת מתח. לפחות 8 מילים.
- כותרת משנה: פרטים עשירים מופרדים ב-•. לפחות 20 מילים.
- כותרת אדומה: 2-4 מילים עוצמתיות.
- גרשיים כפולים " החלף ב-'

החזר JSON בלבד:
{{"title": "...", "subtitle": "...", "red_title": "..."}}"""

    # נסה Gemini קודם
    try:
        if GEMINI_API_KEY:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                result = result.strip().replace("```json", "").replace("```", "").strip()
                import re
                result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', result)
                last_brace = result.rfind("}")
                if last_brace != -1:
                    result = result[:last_brace+1]
                return json.loads(result)
    except Exception as e:
        print(f"שגיאה שיפור כותרות Gemini: {e}", flush=True)

    # גיבוי Groq
    try:
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.5},
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"]
                result = result.strip().replace("```json", "").replace("```", "").strip()
                import re
                result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', result)
                last_brace = result.rfind("}")
                if last_brace != -1:
                    result = result[:last_brace+1]
                return json.loads(result)
    except Exception as e:
        print(f"שגיאה שיפור כותרות Groq: {e}", flush=True)
    return None


    summary = f"""📋 <b>סיכום:</b>

<b>כותרת:</b> {draft.get('title','')}
<b>כותרת משנה:</b> {draft.get('subtitle','')}
<b>כותרת אדומה:</b> {draft.get('red_title','')}
<b>תגיות:</b> {', '.join(draft.get('tags',[]))}
<b>קטגוריות:</b> {', '.join(draft.get('cat_names',[]))}
<b>תמונה ראשית:</b> {'✅' if draft.get('main_image') else '❌'}
<b>גלריה:</b> {len(draft.get('gallery',[]))} תמונות
<b>וידאו:</b> {draft.get('video_url') or 'אין'}"""
    send_message(chat_id, summary, {
        "inline_keyboard": [
            [{"text": "🚀 פרסם עכשיו", "callback_data": "publish_now"},
             {"text": "⏰ תזמן פרסום", "callback_data": "publish_schedule"}],
            [{"text": "💾 שמור כטיוטה", "callback_data": "publish_draft"},
             {"text": "❌ ביטול", "callback_data": "publish_cancel"}]
        ]
    })

processed_updates = set()

def extract_drive_id(url):
    """מחלץ ID של קובץ או תיקייה מלינק Google Drive"""
    import re
    # תיקייה: /folders/ID
    folder = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if folder:
        return folder.group(1), "folder"
    # קובץ: /file/d/ID
    file = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if file:
        return file.group(1), "file"
    # id= בפרמטר
    param = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if param:
        return param.group(1), "file"
    return None, None

def download_drive_file(file_id):
    """מוריד קובץ בודד מ-Google Drive"""
    try:
        # שימוש בלינק הורדה ישיר – עובד לקבצים ציבוריים
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        resp = requests.get(url, timeout=15, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
        # נסיון שני – export דרך API
        url2 = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={GOOGLE_DRIVE_API_KEY}"
        resp2 = requests.get(url2, timeout=15)
        if resp2.status_code == 200:
            return resp2.content
        print(f"שגיאה Drive file: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"שגיאה הורדת Drive: {e}", flush=True)
    return None

def list_drive_folder(folder_id):
    """מחזיר רשימת קבצים בתיקייה"""
    try:
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&key={GOOGLE_DRIVE_API_KEY}&fields=files(id,name,mimeType)&pageSize=100"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            files = resp.json().get("files", [])
            images = [f for f in files if f["mimeType"].startswith("image/")]
            videos = [f for f in files if f["mimeType"].startswith("video/")]
            return images, videos
        print(f"שגיאה Drive folder: {resp.status_code} {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"שגיאה Drive folder: {e}", flush=True)
    return [], []

def handle_drive_link(chat_id, user_id, url, draft):
    """מטפל בלינק Drive בthread נפרד"""
    def _download():
        drive_id, drive_type = extract_drive_id(url)
        if not drive_id:
            send_message(chat_id, "❌ לא זיהיתי לינק Google Drive תקין.")
            return

        if drive_type == "file":
            send_message(chat_id, "⏳ מוריד קובץ מ-Drive...")
            content = download_drive_file(drive_id)
            if content:
                draft.setdefault("gallery", []).append(content)
                send_message(chat_id, f"✅ קובץ הורד! ({len(draft['gallery'])} תמונות)\n\nשלח עוד או /done:")
            else:
                send_message(chat_id, "❌ לא הצלחתי להוריד. וודא שהקובץ פתוח לצפייה.")

        elif drive_type == "folder":
            send_message(chat_id, "⏳ סורק תיקייה ב-Drive...")
            images, videos = list_drive_folder(drive_id)
            if not images:
                send_message(chat_id, "❌ לא נמצאו תמונות בתיקייה.")
                return
            send_message(chat_id, f"📁 נמצאו {len(images)} תמונות. מוריד...")
            count = 0
            for i, img in enumerate(images):
                content = download_drive_file(img["id"])
                if content:
                    draft.setdefault("gallery", []).append(content)
                    count += 1
                # הודעת התקדמות כל 10 תמונות
                if (i + 1) % 10 == 0:
                    send_message(chat_id, f"⏳ הורדתי {count}/{len(images)} תמונות...")
            send_message(chat_id, f"✅ {count} תמונות הורדו!\n\nשלח עוד או /done:")

    t = threading.Thread(target=_download, daemon=True)
    t.start()

def _show_summary(chat_id, draft):
    summary = f"""📋 <b>סיכום:</b>

<b>כותרת:</b> {draft.get('title','')}
<b>כותרת משנה:</b> {draft.get('subtitle','')}
<b>כותרת אדומה:</b> {draft.get('red_title','')}
<b>תגיות:</b> {', '.join(draft.get('tags',[]))}
<b>קטגוריות:</b> {', '.join(draft.get('cat_names',[]))}
<b>תמונה ראשית:</b> {'✅' if draft.get('main_image') else '❌'}
<b>גלריה:</b> {len(draft.get('gallery',[]))} תמונות
<b>וידאו:</b> {draft.get('video_url') or 'אין'}"""
    send_message(chat_id, summary, {
        "inline_keyboard": [
            [{"text": "🚀 פרסם עכשיו", "callback_data": "publish_now"},
             {"text": "⏰ תזמן פרסום", "callback_data": "publish_schedule"}],
            [{"text": "💾 שמור כטיוטה", "callback_data": "publish_draft"},
             {"text": "❌ ביטול", "callback_data": "publish_cancel"}]
        ]
    })

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    username = msg["from"].get("username", msg["from"].get("first_name", "לא ידוע"))
    text = msg.get("text", "")

    perm = get_permission(user_id)

    if perm == "blocked":
        send_message(chat_id, "❌ הגישה שלך חסומה.")
        return

    if perm is None:
        send_message(chat_id, "⛔ אין לך הרשאה להשתמש בבוט.\n\nפנה למנהל לקבלת גישה.")
        notify_admin_error(f"משתמש חדש ביקש גישה:\nשם: {username}\nID: {user_id}\n\nלאשר: /approve_{user_id}\nלחסום: /block_{user_id}")
        return

    if user_id not in drafts:
        drafts[user_id] = {"step": "idle", "gallery": []}

    draft = drafts[user_id]
    step = draft.get("step", "idle")

    if text.startswith("/approve_") and is_admin(user_id):
        target_id = text.replace("/approve_", "")
        users_permissions[target_id] = "editor"
        send_message(chat_id, f"✅ משתמש {target_id} אושר כעורך!")
        send_message(int(target_id), "✅ הגישה שלך אושרה! שלח /start להתחיל.", EDITOR_MENU)
        log_action(user_id, username, f"אישור עורך {target_id}")
        return

    if text.startswith("/approvesenior_") and is_admin(user_id):
        target_id = text.replace("/approvesenior_", "")
        users_permissions[target_id] = "senior_editor"
        send_message(chat_id, f"✅ משתמש {target_id} אושר כעורך ראשי!")
        send_message(int(target_id), "✅ הגישה שלך אושרה כעורך ראשי! שלח /start להתחיל.", SENIOR_EDITOR_MENU)
        log_action(user_id, username, f"אישור עורך ראשי {target_id}")
        return

    if text.startswith("/block_") and is_admin(user_id):
        target_id = text.replace("/block_", "")
        users_permissions[target_id] = "blocked"
        send_message(chat_id, f"🚫 משתמש {target_id} נחסם!")
        log_action(user_id, username, f"חסימת משתמש {target_id}")
        return

    if text.startswith("/makeadmin_") and user_id == SUPER_ADMIN_ID:
        target_id = text.replace("/makeadmin_", "")
        users_permissions[target_id] = "admin"
        send_message(chat_id, f"✅ משתמש {target_id} הוגדר כמנהל!")
        return

    if text == "👥 ניהול משתמשים" and is_admin(user_id):
        total = len(users_permissions)
        by_role = {}
        for uid, perm in users_permissions.items():
            by_role.setdefault(perm, []).append(uid)
        
        users_text = f"👥 <b>משתמשים מורשים ({total}):</b>\n\n"
        role_names = {"admin": "🔴 מנהל", "senior_editor": "🟡 עורך ראשי", "editor": "🟢 עורך", "blocked": "⛔ חסום"}
        for role, uids in by_role.items():
            users_text += f"<b>{role_names.get(role, role)}:</b>\n"
            for uid in uids:
                users_text += f"  • {uid}\n"
            users_text += "\n"
        
        users_text += "פקודות:\n/approve_[ID] → עורך\n/approvesenior_[ID] → עורך ראשי\n/makeadmin_[ID] → מנהל\n/block_[ID] → חסום"
        send_message(chat_id, users_text)
        return

    if text == "📊 לוג פעולות" and is_admin(user_id):
        if activity_log:
            log_text = "\n".join([f"• {e['time']} | {e['username']} | {e['action']}" for e in activity_log[-20:]])
            send_message(chat_id, f"📊 <b>20 פעולות אחרונות:</b>\n\n{log_text}")
        else:
            send_message(chat_id, "אין פעולות בלוג עדיין.")
        return

    if text and not text.startswith("/"):
        log_action(user_id, username, f"הודעה: {text[:50]}")

    if text == "📈 אנליטיקס" and is_senior_editor(user_id):
        send_message(chat_id, "📈 <b>אנליטיקס</b>\n\nמה תרצה לבדוק?", {
            "inline_keyboard": [
                [{"text": "🏆 5 הכתבות הנצפות ביותר", "callback_data": "analytics_top"}],
                [{"text": "👥 כניסות לאתר", "callback_data": "analytics_visits"}],
                [{"text": "🔍 בדוק כתבה ספציפית", "callback_data": "analytics_page"}]
            ]
        })
        return

    if step == "analytics_page_input" and is_senior_editor(user_id):
        send_message(chat_id, "⏳ מושך נתונים...")
        send_message(chat_id, "לאיזה תקופה?", {
            "inline_keyboard": [
                [{"text": "24 שעות", "callback_data": f"analytics_page_1_{text}"},
                 {"text": "שבוע", "callback_data": f"analytics_page_7_{text}"}],
                [{"text": "חודש", "callback_data": f"analytics_page_30_{text}"}]
            ]
        })
        draft["step"] = "idle"
        return

    if text == "🌐 ניהול רשתות" and is_senior_editor(user_id):
        fb_ok = "✅" if os.environ.get("FB_PAGE_TOKEN") else "❌"
        ig_ok = "✅" if os.environ.get("IG_USER_ID") else "❌"
        wm_status = "✅ פעיל" if watermark_settings["enabled"] else "❌ כבוי"
        send_message(chat_id, f"""🌐 <b>ניהול רשתות חברתיות</b>

{fb_ok} פייסבוק
{ig_ok} אינסטגרם
🖼 ווטרמארק: {wm_status}""", {
            "inline_keyboard": [
                [{"text": "📊 סטטיסטיקות פייסבוק", "callback_data": "social_stats_fb"},
                 {"text": "📊 סטטיסטיקות אינסטגרם", "callback_data": "social_stats_ig"}],
                [{"text": "🗑️ מחק פוסט פייסבוק", "callback_data": "social_delete_fb"},
                 {"text": "🗑️ מחק פוסט אינסטגרם", "callback_data": "social_delete_ig"}],
                [{"text": "📋 פוסטים אחרונים", "callback_data": "social_recent_posts"}],
                [{"text": "🖼 הגדרות ווטרמארק", "callback_data": "watermark_settings"}]
            ]
        })
        return

    if text == "⚙️ הגדרות מערכת" and is_admin(user_id):
        words_list = "\n".join([f"• {w}" for w in GERESH_WORDS])
        send_message(chat_id, f"⚙️ <b>הגדרות מערכת</b>\n\n<b>מילים עם גרש:</b>\n{words_list}", {
            "inline_keyboard": [
                [{"text": "➕ הוסף מילה", "callback_data": "geresh_add"},
                 {"text": "➖ הסר מילה", "callback_data": "geresh_remove"}],
                [{"text": "✏️ ערוך פרומפט Gemini", "callback_data": "edit_prompt"}]
            ]
        })
        return

    if text == "📢 הפצת תוכן" and is_editor(user_id):
        drafts[user_id]["step"] = "social_content"
        drafts[user_id]["social_data"] = {}
        send_message(chat_id, "📢 <b>הפצת תוכן</b>\n\nשלח את הטקסט שתרצה להפיץ:", {
            "inline_keyboard": [[{"text": "❌ ביטול", "callback_data": "publish_cancel"}]]
        })
        return

    if text == "🎥 הפצת וידאו" and is_editor(user_id):
        drafts[user_id]["step"] = "social_video"
        drafts[user_id]["social_data"] = {}
        send_message(chat_id, "🎥 <b>הפצת וידאו</b>\n\nשלח את קובץ הסרטון (עד 20MB) או לינק Drive:", {
            "inline_keyboard": [[{"text": "❌ ביטול", "callback_data": "publish_cancel"}]]
        })
        return

    if text == "📧 ניהול מייל" and is_senior_editor(user_id):
        send_message(chat_id, get_email_status(), {
            "inline_keyboard": [
                [{"text": "⏸️ השהה" if email_system["active"] else "▶️ הפעל", "callback_data": "email_toggle"},
                 {"text": "🔄 בדוק עכשיו", "callback_data": "email_check_now"}],
                [{"text": "⏱️ שנה תדירות", "callback_data": "email_change_interval"}],
                [{"text": "➕ הוסף כתובת", "callback_data": "email_add_sender"},
                 {"text": "➖ הסר כתובת", "callback_data": "email_remove_sender"}]
            ]
        })
        return

    if step == "email_remove_sender_input" and is_senior_editor(user_id):
        if text in email_system["allowed_senders"]:
            email_system["allowed_senders"].remove(text)
            send_message(chat_id, f"✅ כתובת {text} הוסרה!", get_menu(user_id))
        else:
            send_message(chat_id, "⚠️ כתובת לא נמצאה.")
        draft["step"] = "idle"
        return

    if step == "email_interval_input" and is_senior_editor(user_id):
        try:
            minutes = int(text)
            email_system["interval"] = minutes * 60
            send_message(chat_id, f"✅ תדירות עודכנה ל-{minutes} דקות!", get_menu(user_id))
        except:
            send_message(chat_id, "⚠️ שלח מספר בדקות (לדוגמה: 30)")
        draft["step"] = "idle"
        return

    if step == "email_pending_url" and is_admin(user_id):
        # קיבל URL לכתבה עבור הוספת תמונות/סרטון
        pending = email_system.get("pending_email", {})
        if pending.get("type") == "add_images" and text.startswith("http"):
            part = text.rstrip("/").split("/")[-1]
            post_id = part if part.isdigit() else None
            if not post_id:
                r = requests.get(f"{WP_URL}/posts?slug={part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                posts = r.json()
                post_id = str(posts[0]["id"]) if posts else None
            if post_id:
                send_message(chat_id, "⏳ מעלה תמונות...")
                image_urls = []
                for img_bytes in pending.get("images", []):
                    img_id, img_url = upload_image_to_wp(img_bytes, "email_img.jpg")
                    if img_url:
                        image_urls.append(img_url)
                if image_urls:
                    add_images_to_post(post_id, image_urls)
                    send_message(chat_id, f"✅ {len(image_urls)} תמונות נוספו!", get_menu(user_id))
                else:
                    send_message(chat_id, "❌ לא הצלחתי להעלות תמונות.")
            email_system["pending_email"] = {}
        draft["step"] = "idle"
        return

    if text in ("/start", "/new", "✍️ כתבה חדשה"):
        if text == "/start":
            menu = get_menu(user_id)
            send_message(chat_id, "שלום! 👋 בחר פעולה:", menu)
            return
        if not is_editor(user_id):
            send_message(chat_id, "❌ אין לך הרשאה.")
            return
        drafts[user_id] = {"step": "title", "gallery": []}
        send_message(chat_id, "📝 <b>כתבה חדשה</b>\n\nשלח את <b>כותרת</b> הכתבה:")
        return

    if text in ("/smart", "🤖 העלאה חכמה"):
        if not is_senior_editor(user_id):
            send_message(chat_id, "❌ אין לך הרשאה להעלאה חכמה.")
            return
        drafts[user_id] = {"step": "smart_text", "gallery": []}
        send_message(chat_id, "🤖 <b>העלאה חכמה</b>\n\nשלח את הטקסט הגולמי של הכתבה:")
        return

    if text == "🎬 העלאה ליוטיוב":
        if not youtube_tokens.get("access_token"):
            auth_url = get_youtube_auth_url()
            send_message(chat_id, f"🔑 צריך להתחבר ל-YouTube פעם אחת:\n\n<a href='{auth_url}'>לחץ כאן להתחברות</a>")
        else:
            send_message(chat_id, "🎬 <b>העלאה ליוטיוב</b>\n\nבחר סוג העלאה:", {
                "inline_keyboard": [[
                    {"text": "✍️ העלאה רגילה", "callback_data": "yt_manual"},
                    {"text": "🤖 העלאה חכמה", "callback_data": "yt_smart"}
                ]]
            })
        return

    if text == "/youtube_auth":
        auth_url = get_youtube_auth_url()
        send_message(chat_id, f"🔑 <a href='{auth_url}'>לחץ כאן להתחברות ל-YouTube</a>")
        return

    if text == "📋 כתבות אחרונות":
        posts = get_recent_posts("publish")
        if posts:
            msg_text = "📋 <b>5 הכתבות האחרונות:</b>\n\n"
            for p in posts:
                msg_text += f"• <a href='{p['link']}'>{p['title']['rendered']}</a>\n"
            send_message(chat_id, msg_text, get_menu(user_id))
        else:
            send_message(chat_id, "❌ לא נמצאו כתבות.", get_menu(user_id))
        return

    if text == "📝 טיוטות":
        posts = get_recent_posts("draft")
        if posts:
            msg_text = "📝 <b>הטיוטות שלך:</b>\n\n"
            for p in posts:
                msg_text += f"• <a href='{p['link']}'>{p['title']['rendered']}</a>\n"
            send_message(chat_id, msg_text, get_menu(user_id))
        else:
            send_message(chat_id, "אין טיוטות שמורות.", get_menu(user_id))
        return

    if text in ("/mazaltov", "🎉 מזל טוב"):
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "🎉 <b>מזל טוב</b>\n\nבחר סוג העלאה:", {
            "inline_keyboard": [[
                {"text": "📸 תמונה אחת", "callback_data": "mazaltov_single"},
                {"text": "📸📸 כמה תמונות", "callback_data": "mazaltov_multi"}
            ]]
        })
        return

    if text in ("/edit", "✏️ עריכת כתבה"):
        if not is_admin(user_id):
            send_message(chat_id, "❌ אין לך הרשאה לערוך כתבות.")
            return
        drafts[user_id] = {"step": "edit_url", "gallery": []}
        send_message(chat_id, "✏️ <b>עריכת כתבה</b>\n\nשלח את ה-URL של הכתבה:")
        return

    if text in ("/delete", "🗑️ מחיקת כתבה"):
        if not is_senior_editor(user_id):
            send_message(chat_id, "❌ אין לך הרשאה למחוק כתבות.")
            return
        drafts[user_id] = {"step": "delete_url", "gallery": []}
        send_message(chat_id, "🗑️ <b>מחיקת כתבה</b>\n\nשלח את ה-URL של הכתבה למחיקה:")
        return

    if text in ("/cancel", "❌ ביטול"):
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ הפעולה בוטלה.", get_menu(user_id))
        return

    # טיפול בעריכות חכמות
    if handle_smart_edit_inputs(chat_id, user_id, step, text, draft, drafts):
        return

    # טיפול בשלבי העלאה
    if handle_message_steps(chat_id, user_id, text, msg, draft, drafts):
        return

    # טיפול בשלבי העלאת כתבה רגילה
    if step == "title":
        draft["title"] = text
        draft["step"] = "subtitle"
        send_message(chat_id, "✅ כותרת נשמרה!\n\nשלח את <b>כותרת המשנה</b>:")

    elif step == "subtitle":
        draft["subtitle"] = text
        draft["step"] = "red_title"
        send_message(chat_id, "✅ כותרת משנה נשמרה!\n\nשלח את <b>הכותרת האדומה</b> (קצרה):")

    elif step == "red_title":
        draft["red_title"] = text
        draft["step"] = "body"
        send_message(chat_id, "✅ כותרת אדומה נשמרה!\n\nשלח את <b>גוף הכתבה</b>:")

    elif step == "body":
        draft["body"] = text
        draft["step"] = "tags"
        send_message(chat_id, "✅ גוף הכתבה נשמר!\n\nשלח <b>תגיות</b> מופרדות בפסיק:")

    elif step == "tags":
        draft["tags"] = [t.strip() for t in text.split(",")]
        draft["step"] = "categories"
        try:
            cats = get_wp_categories()
        except Exception as e:
            print(f"שגיאה קטגוריות: {e}", flush=True)
            cats = {}
        keyboard = {"inline_keyboard": []}
        row = []
        relevant_ids = [11, 26, 25, 52, 45, 50, 51, 49, 48, 1087, 1090, 1091, 1089, 1088, 47, 46, 62, 1083, 63, 1084, 1085, 1086, 24]
        for cat_name, cat_id in cats.items():
            if cat_id in relevant_ids:
                row.append({"text": cat_name, "callback_data": f"cat_{cat_id}_{cat_name}"})
                if len(row) == 2:
                    keyboard["inline_keyboard"].append(row)
                    row = []
        if row:
            keyboard["inline_keyboard"].append(row)
        keyboard["inline_keyboard"].append([{"text": "✅ סיימתי", "callback_data": "cat_done"}])
        draft["categories"] = []
        draft["cat_names"] = []
        send_message(chat_id, "✅ תגיות נשמרו!\n\nבחר <b>קטגוריות</b>:", keyboard)

    elif step == "yt_edit_title_input":
        draft["yt_title"] = text
        draft["step"] = "youtube_smart_confirm"
        send_message(chat_id, f"✅ כותרת עודכנה!\n\nשלח סרטון או ערוך עוד:", {
            "inline_keyboard": [
                [{"text": "✅ שלח סרטון", "callback_data": "yt_smart_approve"}],
                [{"text": "✏️ ערוך תיאור", "callback_data": "yt_edit_desc"}]
            ]
        })

    elif step == "yt_edit_desc_input":
        draft["yt_desc"] = text
        draft["step"] = "youtube_smart_confirm"
        send_message(chat_id, f"✅ תיאור עודכן!\n\nשלח סרטון או ערוך עוד:", {
            "inline_keyboard": [
                [{"text": "✅ שלח סרטון", "callback_data": "yt_smart_approve"}],
                [{"text": "✏️ ערוך כותרת", "callback_data": "yt_edit_title"}]
            ]
        })

    elif step == "article_yt_smart_text":
        send_message(chat_id, "⏳ Gemini מעבד...")
        result = process_with_gemini(text)
        if result:
            draft["yt_title"] = result.get("title", draft.get("title", "סרטון"))
            draft["yt_tags"] = result.get("tags", [])
            file_id = draft.get("pending_video_file_id")
            if file_id:
                if not youtube_tokens.get("access_token"):
                    auth_url = get_youtube_auth_url()
                    send_message(chat_id, f"🔑 צריך להתחבר ל-YouTube:\n<a href='{auth_url}'>לחץ כאן</a>")
                else:
                    send_message(chat_id, f"⏳ מעלה ל-YouTube עם כותרת:\n<b>{draft['yt_title']}</b>")
                    video_bytes = get_file(file_id)
                    if video_bytes:
                        url, error = upload_to_youtube(video_bytes, draft["yt_title"], "", draft["yt_tags"])
                        if url:
                            draft.setdefault("videos", []).append(url)
                            send_message(chat_id, f"✅ עלה ל-YouTube!\n🔗 {url}\n\nשלח סרטון נוסף או /done:")
                        else:
                            send_message(chat_id, f"❌ שגיאה: {error}")
        else:
            send_message(chat_id, "❌ שגיאה בעיבוד. שלח שוב.")

    elif step == "youtube_smart_text":
        send_message(chat_id, "⏳ Gemini מעבד...")
        result = process_with_gemini(text)
        if result:
            draft["yt_title"] = result.get("title", "")
            draft["yt_desc"] = result.get("subtitle", "")
            draft["yt_tags"] = result.get("tags", [])
            draft["step"] = "youtube_smart_confirm"
            preview = f"""🤖 <b>תצוגה מקדימה:</b>

<b>כותרת:</b> {draft['yt_title']}
<b>תיאור:</b> {draft['yt_desc']}
<b>תגיות:</b> {', '.join(draft['yt_tags'])}"""
            send_message(chat_id, preview, {
                "inline_keyboard": [
                    [{"text": "✅ מאשר, שלח סרטון", "callback_data": "yt_smart_approve"}],
                    [{"text": "✏️ ערוך כותרת", "callback_data": "yt_edit_title"},
                     {"text": "✏️ ערוך תיאור", "callback_data": "yt_edit_desc"}],
                    [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                ]
            })
        else:
            send_message(chat_id, "❌ שגיאה בעיבוד. נסה שוב.", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}

    elif step == "youtube_title":
        draft["yt_title"] = text
        draft["step"] = "youtube_desc"
        send_message(chat_id, "שלח <b>תיאור הסרטון</b> (או /skip):")

    elif step == "youtube_desc":
        draft["yt_desc"] = "" if text == "/skip" else text
        draft["step"] = "youtube_tags"
        send_message(chat_id, "שלח <b>תגיות</b> מופרדות בפסיק (או /skip):")

    elif step == "youtube_tags":
        draft["yt_tags"] = [] if text == "/skip" else [t.strip() for t in text.split(",")]
        draft["step"] = "youtube_video"
        send_message(chat_id, "שלח את <b>קובץ הסרטון</b>:")

    elif step == "youtube_video":
        if "video" in msg or "document" in msg:
            send_message(chat_id, "⏳ מעלה סרטון ל-YouTube...")
            file_id = msg.get("video", msg.get("document", {})).get("file_id")
            if file_id:
                video_bytes = get_file(file_id)
                if video_bytes:
                    url, error = upload_to_youtube(
                        video_bytes,
                        draft.get("yt_title", "סרטון"),
                        draft.get("yt_desc", ""),
                        draft.get("yt_tags", [])
                    )
                    if url:
                        send_message(chat_id, f"✅ <b>הסרטון עלה ל-YouTube!</b>\n🔗 {url}", get_menu(user_id))
                    else:
                        send_message(chat_id, f"❌ שגיאה: {error}", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "⚠️ שלח קובץ סרטון:")

    elif step == "smart_text":
        send_message(chat_id, "⏳ Gemini מעבד את הטקסט...")
        result = process_with_gemini(text)
        if result:
            body_clean = convert_whatsapp_format(result.get("body", text))
            draft.update({
                "title": result.get("title", ""),
                "subtitle": result.get("subtitle", ""),
                "red_title": result.get("red_title", ""),
                "body": body_clean,
                "tags": result.get("tags", []),
                "step": "smart_preview"
            })
            import re
            body_preview = re.sub(r'<[^>]+>', '', body_clean)[:300]
            # escape תווים מיוחדים של HTML
            def escape_html(s):
                return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            preview = f"""🤖 <b>תצוגה מקדימה:</b>

<b>כותרת:</b> {escape_html(draft['title'])}
<b>כותרת משנה:</b> {escape_html(draft['subtitle'])}
<b>כותרת אדומה:</b> {escape_html(draft['red_title'])}
<b>תגיות:</b> {escape_html(', '.join(draft['tags']))}

<b>גוף:</b>
{escape_html(body_preview)}{'...' if len(body_clean) > 300 else ''}"""
            send_message(chat_id, preview, {
                "inline_keyboard": [
                    [{"text": "✅ מאשר, המשך", "callback_data": "smart_approve"}],
                    [{"text": "✨ שפר כותרות", "callback_data": "smart_improve_titles"}],
                    [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
                     {"text": "✏️ ערוך כותרת משנה", "callback_data": "smart_edit_subtitle"}],
                    [{"text": "✏️ ערוך גוף", "callback_data": "smart_edit_body"},
                     {"text": "✏️ ערוך תגיות", "callback_data": "smart_edit_tags"}],
                    [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                ]
            })
        else:
            # AI נכשל – שמור את הטקסט ושאל מה לעשות
            draft["body"] = text
            draft["step"] = "smart_text"
            send_message(chat_id, "❌ ה-AI לא הצליח לעבד כרגע.\n\nמה תרצה לעשות?", {
                "inline_keyboard": [
                    [{"text": "🔄 נסה שוב", "callback_data": "smart_retry"}],
                    [{"text": "✍️ המשך ידנית", "callback_data": "smart_manual_fallback"}],
                    [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                ]
            })

def show_smart_preview(chat_id, draft):
    """מציג תצוגה מקדימה מלאה עם קטגוריות שכבר נבחרו"""
    import re as _re
    body_preview = _re.sub(r'<[^>]+>', '', draft.get("body",""))[:300]
    def esc(s): return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

    # בחר קטגוריות אוטומטית אם עדיין לא נבחרו
    if not draft.get("categories"):
        cats, cat_names = auto_select_categories(draft.get("title",""), draft.get("body",""))
        draft["categories"] = cats
        draft["cat_names"] = cat_names

    cat_display = esc(', '.join(draft.get('cat_names',[])) or 'טרם נבחרו')
    preview = f"""🤖 <b>תצוגה מקדימה:</b>

<b>כותרת:</b> {esc(draft.get('title',''))}
<b>כותרת משנה:</b> {esc(draft.get('subtitle',''))}
<b>כותרת אדומה:</b> {esc(draft.get('red_title',''))}
<b>תגיות:</b> {esc(', '.join(draft.get('tags',[])))}
<b>קטגוריות:</b> {cat_display}

<b>גוף:</b>
{esc(body_preview)}{'...' if len(draft.get('body','')) > 300 else ''}"""
    send_message(chat_id, preview, {
        "inline_keyboard": [
            [{"text": "✅ מאשר, המשך", "callback_data": "smart_approve"}],
            [{"text": "✨ שפר כותרות", "callback_data": "smart_improve_titles"}],
            [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
             {"text": "✏️ ערוך כותרת משנה", "callback_data": "smart_edit_subtitle"}],
            [{"text": "✏️ ערוך כותרת אדומה", "callback_data": "smart_edit_red_title"},
             {"text": "✏️ ערוך תגיות", "callback_data": "smart_edit_tags"}],
            [{"text": "✏️ ערוך גוף", "callback_data": "smart_edit_body"},
             {"text": "🔄 שנה קטגוריות", "callback_data": "change_categories"}],
            [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
        ]
    })

def handle_smart_edit_inputs(chat_id, user_id, step, text, draft, drafts):
    """מטפל בכניסות עריכה חכמה - נקרא מתוך handle_message"""
    if step == "smart_edit_subtitle_input":
        draft["subtitle"] = text
        draft["step"] = "smart_preview"
        show_smart_preview(chat_id, draft)
        return True
    elif step == "smart_edit_title_input":
        draft["title"] = text
        draft["step"] = "smart_preview"
        show_smart_preview(chat_id, draft)
        return True
    elif step == "smart_edit_red_title_input":
        draft["red_title"] = text
        draft["step"] = "smart_preview"
        show_smart_preview(chat_id, draft)
        return True
    elif step == "smart_edit_body_input":
        draft["body"] = text
        draft["step"] = "smart_preview"
        show_smart_preview(chat_id, draft)
        return True
    elif step == "smart_edit_tags_input":
        draft["tags"] = [t.strip() for t in text.split(",")]
        draft["step"] = "smart_preview"
        show_smart_preview(chat_id, draft)
        return True
    return False

def handle_message_steps(chat_id, user_id, text, msg, draft, drafts):
    """מטפל בשלבי העלאת כתבה"""
    step = draft.get("step", "idle")

    if step == "schedule_time":
        try:
            from datetime import datetime
            dt = datetime.strptime(text.strip(), "%d/%m/%Y %H:%M")
            iso_date = dt.strftime("%Y-%m-%dT%H:%M:00")
            draft["schedule_date"] = iso_date
            send_message(chat_id, "⏳ מתזמן פרסום...")
            try:
                resp = publish_to_wp(draft, "future", iso_date)
            except Exception as e:
                send_message(chat_id, f"❌ שגיאה בפרסום: {e}")
                return True
            if resp.status_code == 201:
                send_message(chat_id, f"✅ <b>הכתבה מתוזמנת לפרסום ב-{text}!</b>", get_menu(user_id))
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
            drafts[user_id] = {"step": "idle", "gallery": []}
        except ValueError:
            send_message(chat_id, "⚠️ פורמט שגוי. נסה שוב:\n<code>DD/MM/YYYY HH:MM</code>")
        return True

    elif step == "main_image":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft["main_image"] = content
                draft["step"] = "gallery"
                send_message(chat_id, "✅ תמונה ראשית נשמרה!\n\nשלח תמונות, PDF, קובץ שמע, או לינק Google Drive. כשסיימת שלח /done:")
        else:
            send_message(chat_id, "⚠️ שלח תמונה:")
        return True

    elif step == "gallery":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft.setdefault("gallery", []).append(content)
                if len(draft["gallery"]) == 1:
                    send_message(chat_id, "📥 מקבל קבצים... שלח תמונות, PDF, קובץ שמע, או /done כשסיימת")
        elif "document" in msg:
            doc = msg["document"]
            mime = doc.get("mime_type", "")
            file_id = doc["file_id"]
            file_size = doc.get("file_size", 0)
            file_name = doc.get("file_name", "document")
            print(f"📄 קובץ התקבל: {file_name} | mime: {mime} | size: {file_size} bytes", flush=True)
            if mime == "application/pdf":
                print(f"📄 מנסה להוריד PDF: {file_id}", flush=True)
                # בדוק כפילות לפי file_id וגם לפי שם+גודל
                uploaded_ids = draft.get("uploaded_file_ids", set())
                file_key = f"{file_id}_{file_size}_{file_name}"
                if file_id in uploaded_ids or file_key in uploaded_ids:
                    print(f"📄 כפול – מדלג", flush=True)
                    return True
                content = get_file(file_id)
                print(f"📄 הורדה: {'הצלחה ' + str(len(content)) + ' bytes' if content else 'נכשל'}", flush=True)
                if content:
                    send_message(chat_id, "⏳ מעלה PDF לאתר...")
                    fname = file_name if file_name.endswith('.pdf') else file_name + '.pdf'
                    # שם בטוח לוורדפרס (ASCII בלבד)
                    safe_fname = f"doc_{int(time.time())}.pdf"
                    import base64
                    credentials = base64.b64encode(f"{WP_USER}:{WP_PASSWORD}".encode()).decode()
                    headers_wp = {
                        "Content-Disposition": f'attachment; filename="{safe_fname}"',
                        "Content-Type": "application/pdf",
                        "Authorization": f"Basic {credentials}"
                    }
                    resp = requests.post(f"{WP_URL}/media", headers=headers_wp, data=content, timeout=60)
                    print(f"📄 WordPress upload: {resp.status_code}", flush=True)
                    if resp.status_code == 201:
                        pdf_url = resp.json()["source_url"]
                        media_id = resp.json()["id"]
                        requests.post(f"{WP_URL}/media/{media_id}",
                                     json={"title": fname.replace('.pdf',''), "caption": fname},
                                     headers={"Authorization": f"Basic {credentials}"},
                                     timeout=10)
                        draft.setdefault("pdf_embeds", []).append({"url": pdf_url, "name": fname})
                        draft.setdefault("uploaded_file_ids", set()).add(file_id)
                        draft["uploaded_file_ids"].add(file_key)
                        send_message(chat_id, f"✅ PDF הועלה! ({len(draft.get('pdf_embeds',[]))} קבצים)\n\nשלח עוד או /done:")
                    else:
                        print(f"📄 שגיאה: {resp.text[:300]}", flush=True)
                        send_message(chat_id, f"❌ שגיאה בהעלאת PDF ({resp.status_code}). נסה שוב.")
                    if resp.status_code == 201:
                        pdf_url = resp.json()["source_url"]
                        draft.setdefault("pdf_embeds", []).append({"url": pdf_url, "name": fname})
                        send_message(chat_id, f"✅ PDF הועלה לאתר! ({len(draft.get('pdf_embeds',[]))} קבצים)\n\nשלח עוד או /done:")
                    else:
                        print(f"📄 שגיאה: {resp.text[:200]}", flush=True)
                        send_message(chat_id, f"❌ שגיאה בהעלאת PDF: {resp.status_code}\nנסה שוב.")
                else:
                    send_message(chat_id, "❌ לא הצלחתי להוריד את ה-PDF. נסה שוב.")
            elif mime and mime.startswith("audio/"):
                content = get_file(file_id)
                if content:
                    draft.setdefault("audio_files", []).append({"bytes": content, "name": doc.get("file_name", "audio.mp3")})
                    send_message(chat_id, f"✅ קובץ שמע נוסף!\n\nשלח עוד או /done:")
        elif "audio" in msg:
            content = get_file(msg["audio"]["file_id"])
            if content:
                draft.setdefault("audio_files", []).append({"bytes": content, "name": msg["audio"].get("file_name", "audio.mp3")})
                send_message(chat_id, f"✅ קובץ שמע נוסף!\n\nשלח עוד או /done:")
        elif text and text.startswith("http") and "drive.google.com" in text:
            drive_id, drive_type = extract_drive_id(text)
            if drive_id:
                send_message(chat_id, "⏳ מוריד תמונות מ-Drive...")
                if drive_type == "folder":
                    images, _ = list_drive_folder(drive_id)
                    count = 0
                    for i, img in enumerate(images):
                        content = download_drive_file(img["id"])
                        if content:
                            draft.setdefault("gallery", []).append(content)
                            count += 1
                        if (i + 1) % 10 == 0:
                            send_message(chat_id, f"⏳ הורדתי {count}/{len(images)} תמונות...")
                    send_message(chat_id, f"✅ {count} תמונות הורדו!\n\nשלח עוד או /done:")
                elif drive_type == "file":
                    content = download_drive_file(drive_id)
                    if content:
                        draft.setdefault("gallery", []).append(content)
                        send_message(chat_id, f"✅ תמונה הורדה! ({len(draft['gallery'])} סה\"כ)\n\nשלח עוד או /done:")
            else:
                send_message(chat_id, "❌ לינק Drive לא תקין.")
        elif text == "/done":
            draft["step"] = "video"
            count = len(draft.get('gallery', []))
            send_message(chat_id, f"✅ התקבלו {count} תמונות!\n\nשלח <b>קובץ סרטון</b> להעלאה ל-Vimeo, <b>לינק</b> ידני, או /skip:")
        else:
            send_message(chat_id, "שלח תמונות, PDF, קובץ שמע, לינק Drive, או /done:")
        return True

    elif step == "video":
        if text == "/skip" or text == "/done":
            draft["step"] = "confirm"
            _show_summary(chat_id, draft)
        elif "video" in msg or "document" in msg:
            file_id = msg.get("video", msg.get("document", {})).get("file_id")
            media_group_id = msg.get("media_group_id")
            if media_group_id:
                if draft.get("current_media_group") != media_group_id:
                    draft["current_media_group"] = media_group_id
                    draft["pending_group_files"] = []
                if file_id not in draft.get("pending_group_files", []):
                    draft.setdefault("pending_group_files", []).append(file_id)
                if len(draft["pending_group_files"]) == 1:
                    send_message(chat_id, f"📥 מקבל סרטונים... שלח /upload_all כשסיימת לשלוח הכל")
            else:
                draft["pending_video_file_id"] = file_id
                send_message(chat_id, "לאן להעלות את הסרטון?", {
                    "inline_keyboard": [
                        [{"text": "🎬 YouTube", "callback_data": "upload_youtube"},
                         {"text": "🎥 Vimeo", "callback_data": "upload_vimeo"}],
                        [{"text": "🤖 YouTube חכם", "callback_data": "upload_youtube_smart"}]
                    ]
                })
        elif text == "/upload_all":
            files = draft.get("pending_group_files", [])
            if files:
                send_message(chat_id, f"📥 התקבלו {len(files)} סרטונים. לאן להעלות?", {
                    "inline_keyboard": [
                        [{"text": "🎬 YouTube", "callback_data": "upload_group_youtube"},
                         {"text": "🎥 Vimeo", "callback_data": "upload_group_vimeo"}]
                    ]
                })
        elif text and text.startswith("http"):
            draft.setdefault("videos", []).append(text)
            send_message(chat_id, f"✅ לינק {len(draft['videos'])} נוסף!\n\nשלח סרטון נוסף או /done לסיום:")
        else:
            send_message(chat_id, "שלח קובץ סרטון, לינק, /upload_all לכמה סרטונים, או /skip:")
        return True

    elif step == "confirm":
        if text == "/publish":
            send_message(chat_id, "⏳ מפרסם לוורדפרס...")
            resp = publish_to_wp(draft)
            if resp.status_code == 201:
                post_url = resp.json().get("link", "")
                send_message(chat_id, f"✅ <b>הכתבה פורסמה!</b>\n🔗 {post_url}", get_menu(user_id))
                notify_channel(draft.get("title", ""), draft.get("subtitle", ""), post_url)
                drafts[user_id] = {"step": "idle", "gallery": []}
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        else:
            send_message(chat_id, "שלח /publish לפרסום או /cancel לביטול")
        return True

    elif step == "edit_url":
        try:
            part = text.rstrip("/").split("/")[-1]
            if part.isdigit():
                r = requests.get(f"{WP_URL}/posts/{part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                post = r.json() if r.status_code == 200 else None
            else:
                r = requests.get(f"{WP_URL}/posts?slug={part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                posts = r.json()
                post = posts[0] if posts else None
            if not post:
                send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                return True
            draft["edit_id"] = post["id"]
            draft["step"] = "edit_field"
            send_message(chat_id, f"""✏️ <b>עורך כתבה:</b>
<b>{post['title']['rendered']}</b>

מה תרצה לערוך?""", {
                "inline_keyboard": [
                    [{"text": "כותרת", "callback_data": "edit_title"},
                     {"text": "כותרת משנה", "callback_data": "edit_subtitle"}],
                    [{"text": "כותרת אדומה", "callback_data": "edit_red_title"},
                     {"text": "תמונה ראשית", "callback_data": "edit_image"}],
                    [{"text": "הוספת תמונות", "callback_data": "edit_gallery"},
                     {"text": "הוספת סרטון", "callback_data": "edit_video"}]
                ]
            })
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")
        return True

    elif step == "edit_field_value":
        field = draft.get("edit_field")
        post_id = draft.get("edit_id")
        update_data = {}
        if field == "title":
            update_data["title"] = text
        elif field == "subtitle":
            update_data["excerpt"] = text
        elif field == "red_title":
            update_data["meta"] = {"tag_label": text}
        r = requests.post(f"{WP_URL}/posts/{post_id}", json=update_data,
                         auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code == 200:
            send_message(chat_id, "✅ הכתבה עודכנה!", get_menu(user_id))
        else:
            send_message(chat_id, f"❌ שגיאה: {r.text[:200]}")
        drafts[user_id] = {"step": "idle", "gallery": []}
        return True

    elif step == "edit_image_upload":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                post_id = draft.get("edit_id")
                featured_id, _ = upload_image_to_wp(content, "edit_main.jpg")
                if featured_id:
                    r = requests.post(f"{WP_URL}/posts/{post_id}",
                                     json={"featured_media": featured_id},
                                     auth=(WP_USER, WP_PASSWORD), timeout=10)
                    if r.status_code == 200:
                        send_message(chat_id, "✅ תמונה ראשית עודכנה!", get_menu(user_id))
                    else:
                        send_message(chat_id, f"❌ שגיאה: {r.text[:200]}")
                drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "⚠️ שלח תמונה:")
        return True

    elif step == "edit_video_input":
        pending = draft.setdefault("edit_videos_pending", [])
        if "video" in msg or ("document" in msg and msg["document"].get("mime_type", "").startswith("video/")):
            obj = msg.get("video") or msg.get("document", {})
            file_id = obj.get("file_id")
            if file_id:
                video_bytes = get_file(file_id)
                if video_bytes:
                    pending.append({"type": "file", "bytes": video_bytes})
                    send_message(chat_id, f"✅ סרטון {len(pending)} התקבל! שלח עוד או /done:")
                else:
                    send_message(chat_id, "❌ לא הצלחתי להוריד. נסה שוב.")
        elif text and text.startswith("http"):
            pending.append({"type": "url", "url": text})
            send_message(chat_id, f"✅ לינק {len(pending)} נוסף! שלח עוד או /done:")
        elif text == "/done":
            if not pending:
                send_message(chat_id, "⚠️ לא התקבלו סרטונים.")
                return True
            if len(pending) == 1 and pending[0]["type"] == "file":
                # שאל לאיזה שירות להעלות
                draft["edit_videos_pending"] = pending
                draft["step"] = "edit_video_service"
                send_message(chat_id, "לאיזה שירות להעלות את הסרטון?", {
                    "inline_keyboard": [
                        [{"text": "🎬 Vimeo", "callback_data": "edit_video_to_vimeo"},
                         {"text": "▶️ YouTube", "callback_data": "edit_video_to_youtube"}]
                    ]
                })
            elif any(v["type"] == "file" for v in pending):
                draft["edit_videos_pending"] = pending
                draft["step"] = "edit_video_service"
                send_message(chat_id, f"לאיזה שירות להעלות את {len([v for v in pending if v['type']=='file'])} הסרטונים?", {
                    "inline_keyboard": [
                        [{"text": "🎬 Vimeo", "callback_data": "edit_video_to_vimeo"},
                         {"text": "▶️ YouTube", "callback_data": "edit_video_to_youtube"}],
                        [{"text": "🌐 הכל", "callback_data": "edit_video_to_all"}]
                    ]
                })
            else:
                # רק לינקים – הוסף ישירות
                _add_videos_to_post(chat_id, user_id, draft, drafts, pending)
        else:
            send_message(chat_id, "שלח קובץ וידאו, לינק, או /done:")
        return True

    elif step == "edit_video_service":
        pass
        return True

    elif step == "edit_video_url":
        post_id = draft.get("edit_id")
        r = requests.get(f"{WP_URL}/posts/{post_id}?context=edit", auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code == 200:
            existing_content = r.json().get("content", {}).get("raw", "") or r.json().get("content", {}).get("rendered", "")
            video_id = text.split("/")[-1].split("?")[0]
            new_video = f'\n\n<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="https://player.vimeo.com/video/{video_id}" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>\n'
            new_content = existing_content + new_video
            requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content},
                        auth=(WP_USER, WP_PASSWORD), timeout=10)
            send_message(chat_id, "✅ סרטון נוסף לכתבה!", get_menu(user_id))
        else:
            send_message(chat_id, "❌ שגיאה בעדכון")
        drafts[user_id] = {"step": "idle", "gallery": []}
        return True

    elif step == "delete_url":
        try:
            part = text.rstrip("/").split("/")[-1]
            if part.isdigit():
                r = requests.get(f"{WP_URL}/posts/{part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                post = r.json() if r.status_code == 200 else None
            else:
                r = requests.get(f"{WP_URL}/posts?slug={part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                posts = r.json()
                post = posts[0] if posts else None
            if not post:
                send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                return True
            draft["delete_id"] = post["id"]
            draft["delete_title"] = post["title"]["rendered"]
            draft["step"] = "delete_confirm"
            send_message(chat_id, f"⚠️ האם למחוק את הכתבה:\n<b>{post['title']['rendered']}</b>?", {
                "inline_keyboard": [[
                    {"text": "✅ כן, מחק", "callback_data": "delete_yes"},
                    {"text": "❌ ביטול", "callback_data": "delete_no"}
                ]]
            })
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")
        return True

    elif step == "mazaltov_image":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                send_message(chat_id, "⏳ מעלה לאתר...")
                featured_id, _ = upload_image_to_wp(content, "mazaltov.jpg")
                post_data = {
                    "title": "מזל טוב",
                    "content": "",
                    "status": "publish",
                    "categories": [18, 103]
                }
                if featured_id:
                    post_data["featured_media"] = featured_id
                resp = requests.post(f"{WP_URL}/posts", json=post_data,
                                    auth=(WP_USER, WP_PASSWORD), timeout=30)
                if resp.status_code == 201:
                    post_url = resp.json().get("link", "")
                    send_message(chat_id, f"✅ <b>מזל טוב פורסם!</b>\n🔗 {post_url}")
                else:
                    send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
                drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "⚠️ שלח תמונה:")
        return True

    elif step == "mazaltov_multi":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft.setdefault("mazaltov_images", []).append(content)
                if len(draft["mazaltov_images"]) == 1:
                    send_message(chat_id, "📸 מקבל תמונות... שלח /done כשסיימת")
        elif text == "/done":
            images = draft.get("mazaltov_images", [])
            if not images:
                send_message(chat_id, "⚠️ לא התקבלו תמונות.")
                return True
            send_message(chat_id, f"⏳ מעלה {len(images)} כתבות מזל טוב...")
            success = 0
            for i, img in enumerate(images):
                featured_id, _ = upload_image_to_wp(img, f"mazaltov_{i}.jpg")
                post_data = {
                    "title": "מזל טוב",
                    "content": "",
                    "status": "publish",
                    "categories": [18, 103]
                }
                if featured_id:
                    post_data["featured_media"] = featured_id
                resp = requests.post(f"{WP_URL}/posts", json=post_data,
                                    auth=(WP_USER, WP_PASSWORD), timeout=30)
                if resp.status_code == 201:
                    success += 1
            send_message(chat_id, f"✅ פורסמו {success}/{len(images)} כתבות מזל טוב!", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "שלח תמונות או /done לסיום:")
        return True

    elif step == "categories":
        pass
        return True

    elif step == "smart_preview":
        pass
        return True

    elif step == "delete_confirm":
        pass
        return True

    elif step == "youtube_smart_confirm":
        pass
        return True

    elif step == "drive_link_input":
        if text and "drive.google.com" in text:
            def _drive_thread():
                drive_id, drive_type = extract_drive_id(text)
                if not drive_id:
                    send_message(chat_id, "❌ לינק Drive לא תקין.")
                    return
                if drive_type == "folder":
                    send_message(chat_id, "⏳ סורק תיקייה ב-Drive...")
                    images, _ = list_drive_folder(drive_id)
                    if not images:
                        send_message(chat_id, "❌ לא נמצאו תמונות.")
                        return
                    count = 0
                    for i, img in enumerate(images):
                        img_bytes = download_drive_file(img["id"])
                        if img_bytes:
                            draft.setdefault("gallery", []).append(img_bytes)
                            count += 1
                        if (i + 1) % 10 == 0:
                            send_message(chat_id, f"⏳ {count}/{len(images)} תמונות...")
                    draft["step"] = "gallery"
                    send_message(chat_id, f"✅ {count} תמונות הורדו! שלח עוד או /done:")
                elif drive_type == "file":
                    img_bytes = download_drive_file(drive_id)
                    if img_bytes:
                        draft.setdefault("gallery", []).append(img_bytes)
                        draft["step"] = "gallery"
                        send_message(chat_id, "✅ קובץ הורד! שלח עוד או /done:")
            threading.Thread(target=_drive_thread, daemon=True).start()
        else:
            send_message(chat_id, "⚠️ שלח לינק תקין מ-Google Drive:")
        return True

    elif step == "edit_gallery_upload":
        if "photo" in msg:
            media_group_id = msg.get("media_group_id")
            file_id = msg["photo"][-1]["file_id"]
            if "edit_gallery_pending" not in draft:
                draft["edit_gallery_pending"] = []
            if media_group_id:
                if draft.get("edit_gallery_group") != media_group_id:
                    draft["edit_gallery_group"] = media_group_id
                if file_id not in draft["edit_gallery_pending"]:
                    draft["edit_gallery_pending"].append(file_id)
                if len(draft["edit_gallery_pending"]) == 1:
                    send_message(chat_id, "📥 מקבל קבצים... שלח /done כשסיימת")
            else:
                draft["edit_gallery_pending"].append(file_id)
                send_message(chat_id, f"📥 {len(draft['edit_gallery_pending'])} קבצים. שלח עוד או /done:")
        elif "document" in msg:
            doc = msg["document"]
            mime = doc.get("mime_type", "")
            file_id = doc["file_id"]
            post_id = draft.get("edit_id")
            content_bytes = get_file(file_id)
            if content_bytes:
                if mime == "application/pdf":
                    url = f"{WP_URL}/media"
                    fname = doc.get('file_name', 'doc.pdf')
                    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(fname)}",
                              "Content-Type": "application/pdf"}
                    resp = requests.post(url, headers=headers, data=content_bytes,
                                       auth=(WP_USER, WP_PASSWORD), timeout=30)
                    if resp.status_code == 201:
                        pdf_url = resp.json()["source_url"]
                        r = requests.get(f"{WP_URL}/posts/{post_id}?context=edit", auth=(WP_USER, WP_PASSWORD), timeout=10)
                        if r.status_code == 200:
                            existing = r.json().get("content", {}).get("raw", "")
                            new_content = existing + f'\n\n<div class="wp-block-file"><object data="{pdf_url}" type="application/pdf" width="100%" height="600px"><a href="{pdf_url}">{fname}</a></object></div>'
                            requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content}, auth=(WP_USER, WP_PASSWORD), timeout=10)
                        send_message(chat_id, "✅ PDF נוסף! שלח עוד או /done:")
                elif mime and mime.startswith("audio/"):
                    url = f"{WP_URL}/media"
                    fname = doc.get('file_name', 'audio.mp3')
                    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(fname)}",
                              "Content-Type": mime}
                    resp = requests.post(url, headers=headers, data=content_bytes,
                                       auth=(WP_USER, WP_PASSWORD), timeout=30)
                    if resp.status_code == 201:
                        audio_url = resp.json()["source_url"]
                        r = requests.get(f"{WP_URL}/posts/{post_id}?context=edit", auth=(WP_USER, WP_PASSWORD), timeout=10)
                        if r.status_code == 200:
                            existing = r.json().get("content", {}).get("raw", "")
                            new_content = existing + f'\n\n<figure class="wp-block-audio"><audio controls src="{audio_url}"></audio></figure>'
                            requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content}, auth=(WP_USER, WP_PASSWORD), timeout=10)
                        send_message(chat_id, "✅ קובץ שמע נוסף! שלח עוד או /done:")
        elif text == "/done":
            post_id = draft.get("edit_id")
            pending = draft.get("edit_gallery_pending", [])
            if pending:
                send_message(chat_id, f"⏳ מעלה {len(pending)} תמונות...")
                image_urls = []
                for fid in pending:
                    img_bytes = get_file(fid)
                    if img_bytes:
                        img_id, img_url = upload_image_to_wp(img_bytes, "gallery_add.jpg")
                        if img_url:
                            image_urls.append(img_url)
                if image_urls:
                    add_images_to_post(post_id, image_urls)
                    send_message(chat_id, f"✅ {len(image_urls)} תמונות נוספו!", get_menu(user_id))
                draft["edit_gallery_pending"] = []
            drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "שלח תמונות, PDF, קובץ שמע, או /done:")
        return True

    elif step == "social_content":
        social = draft.get("social_data", {})
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            social["image"] = content
            draft["social_data"] = social
            draft["step"] = "social_content_caption"
            send_message(chat_id, "✅ תמונה התקבלה!\n\nשלח כיתוב/טקסט (או /skip לדלג):")
        elif text and text != "/skip":
            social["text_content"] = text
            draft["social_data"] = social
            draft["step"] = "social_content_platforms"
            _show_social_platforms(chat_id, social, "content")
        elif text == "/skip":
            draft["step"] = "social_content_platforms"
            _show_social_platforms(chat_id, social, "content")
        return True

    elif step == "social_content_caption":
        social = draft.get("social_data", {})
        if text != "/skip":
            social["text_content"] = text
        draft["social_data"] = social
        draft["step"] = "social_content_platforms"
        _show_social_platforms(chat_id, social, "content")
        return True

    elif step == "social_video":
        social = draft.get("social_data", {})
        if "video" in msg or "document" in msg:
            obj = msg.get("video") or msg.get("document", {})
            file_id = obj.get("file_id")
            if file_id:
                video_bytes = get_file(file_id)
                if video_bytes:
                    social["video_bytes"] = video_bytes
                    draft["social_data"] = social
                    draft["step"] = "social_video_platforms"
                    _show_social_video_platforms(chat_id)
                else:
                    send_message(chat_id, "❌ לא הצלחתי להוריד את הסרטון.")
        elif text and "drive.google.com" in text:
            send_message(chat_id, "⏳ מוריד מ-Drive...")
            def _dl_social():
                drive_id, drive_type = extract_drive_id(text)
                if drive_id and drive_type == "file":
                    vb = download_drive_file(drive_id)
                    if vb:
                        social["video_bytes"] = vb
                        draft["social_data"] = social
                        draft["step"] = "social_video_platforms"
                        _show_social_video_platforms(chat_id)
                    else:
                        send_message(chat_id, "❌ לא הצלחתי להוריד.")
                else:
                    send_message(chat_id, "❌ שלח לינק לקובץ בודד מ-Drive.")
            threading.Thread(target=_dl_social, daemon=True).start()
        else:
            send_message(chat_id, "⚠️ שלח קובץ וידאו או לינק Drive:")
        return True

    elif step == "wm_text_input":
        watermark_settings["text"] = text.strip()
        send_message(chat_id, f"✅ טקסט עודכן: <b>{text.strip()}</b>")
        draft["step"] = "idle"
        return True

    elif step == "wm_fontsize_input":
        try:
            size = int(text.strip())
            if 10 <= size <= 200:
                watermark_settings["font_size"] = size
                send_message(chat_id, f"✅ גודל עודכן: {size}px")
            else:
                send_message(chat_id, "⚠️ הכנס מספר בין 10 ל-200")
        except:
            send_message(chat_id, "⚠️ הכנס מספר תקין")
        draft["step"] = "idle"
        return True

    elif step == "wm_textcolor_input":
        color = text.strip()
        if not color.startswith("#"):
            color = "#" + color
        if len(color) in (4, 7):
            watermark_settings["text_color"] = color
            send_message(chat_id, f"✅ צבע טקסט עודכן: {color}")
        else:
            send_message(chat_id, "⚠️ פורמט לא תקין. דוגמה: #FFFFFF")
        draft["step"] = "idle"
        return True

    elif step == "wm_bgcolor_input":
        color = text.strip()
        if not color.startswith("#"):
            color = "#" + color
        if len(color) in (4, 7):
            watermark_settings["bg_color"] = color
            send_message(chat_id, f"✅ צבע רקע עודכן: {color}")
        else:
            send_message(chat_id, "⚠️ פורמט לא תקין. דוגמה: #000000")
        draft["step"] = "idle"
        return True

    elif step == "wm_opacity_input":
        try:
            opacity = int(text.strip())
            if 0 <= opacity <= 255:
                watermark_settings["bg_opacity"] = opacity
                send_message(chat_id, f"✅ שקיפות עודכנה: {opacity}")
            else:
                send_message(chat_id, "⚠️ הכנס מספר בין 0 ל-255")
        except:
            send_message(chat_id, "⚠️ הכנס מספר תקין")
        draft["step"] = "idle"
        return True

    elif step == "wm_posx_input":
        try:
            val = int(text.strip())
            if 0 <= val <= 100:
                watermark_settings["pos_x"] = val
                send_message(chat_id, f"✅ מיקום X עודכן: {val}%")
            else:
                send_message(chat_id, "⚠️ הכנס מספר בין 0 ל-100")
        except:
            send_message(chat_id, "⚠️ הכנס מספר תקין")
        draft["step"] = "idle"
        return True

    elif step == "wm_posy_input":
        try:
            val = int(text.strip())
            if 0 <= val <= 100:
                watermark_settings["pos_y"] = val
                send_message(chat_id, f"✅ מיקום Y עודכן: {val}%")
            else:
                send_message(chat_id, "⚠️ הכנס מספר בין 0 ל-100")
        except:
            send_message(chat_id, "⚠️ הכנס מספר תקין")
        draft["step"] = "idle"
        return True

    elif step == "wm_logo_input":
        if "photo" in msg or "document" in msg:
            obj = msg.get("photo", [])
            file_id = obj[-1]["file_id"] if obj else msg.get("document", {}).get("file_id")
            if file_id:
                logo_bytes = get_file(file_id)
                if logo_bytes:
                    watermark_settings["logo_bytes"] = logo_bytes
                    watermark_settings["mode"] = "logo"
                    send_message(chat_id, "✅ לוגו הועלה! מצב לוגו פעיל.")
        draft["step"] = "idle"
        return True

    elif step == "wm_preview_input":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                watermarked = add_watermark(content)
                send_image(chat_id, watermarked, "🖼 תצוגה מקדימה ווטרמארק")
        draft["step"] = "idle"
        return True

    elif step == "wm_text_input":
        email = text.strip().lower()
        import re
        if re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
            if email not in email_system["allowed_senders"]:
                email_system["allowed_senders"].append(email)
                send_message(chat_id, f"✅ הכתובת <b>{email}</b> נוספה!", get_menu(user_id))
            else:
                send_message(chat_id, "הכתובת כבר קיימת ברשימה.")
        else:
            send_message(chat_id, "❌ כתובת מייל לא תקינה. נסה שוב:")
            return True
        draft["step"] = "idle"
        return True

    elif step == "social_content_platforms":
        # מטופל דרך callbacks
        pass
        return True

    elif step == "geresh_add_input":
        word = text.strip()
        if word and '״' in word:
            if word not in GERESH_WORDS:
                GERESH_WORDS.append(word)
                send_message(chat_id, f"✅ המילה <b>{word}</b> נוספה לרשימה!")
            else:
                send_message(chat_id, "המילה כבר קיימת ברשימה.")
        else:
            send_message(chat_id, "⚠️ המילה חייבת לכלול ״ (גרש עברי). נסה שוב.")
        draft["step"] = "idle"
        return True

    elif step == "edit_prompt_input":
        if "{text}" in text:
            # שמור פרומפט מותאם אישית
            draft["custom_prompt"] = text
            # שמור גלובלית
            import builtins
            builtins.CUSTOM_PROMPT = text
            send_message(chat_id, "✅ פרומפט עודכן! ישפיע על ההעלאה הבאה.")
        else:
            send_message(chat_id, "❌ הפרומפט חייב לכלול {text} בסוף כדי לקבל את הטקסט.")
        draft["step"] = "idle"
        return True

    elif step == "social_delete_fb_input":
        import re
        fb_token = os.environ.get("FB_PAGE_TOKEN","")
        fb_page_id = os.environ.get("FB_PAGE_ID","")
        # נסה לחלץ post ID מלינק
        post_id = text.strip()
        # פורמט: facebook.com/permalink/123 או /posts/123
        for pattern in [
            r'permalink/(\d+)',
            r'/posts/(\d+)',
            r'story_fbid=(\d+)',
            r'pfbid[\w]+',
        ]:
            match = re.search(pattern, text)
            if match:
                post_id = match.group(1) if '(' in pattern else match.group(0)
                break
        # אם זה pfbid צריך לחפש ב-feed
        if post_id.startswith("pfbid") or "facebook.com" in text:
            try:
                resp = requests.get(
                    f"https://graph.facebook.com/v18.0/{fb_page_id}/posts",
                    params={"fields": "id,permalink_url", "limit": 20, "access_token": fb_token},
                    timeout=15
                )
                if resp.status_code == 200:
                    for post in resp.json().get("data", []):
                        if post.get("permalink_url", "") in text or text in post.get("permalink_url", ""):
                            post_id = post["id"]
                            break
            except Exception as e:
                print(f"שגיאה חיפוש פוסט: {e}", flush=True)
        print(f"מוחק FB post_id: {post_id}", flush=True)
        try:
            resp = requests.delete(
                f"https://graph.facebook.com/v18.0/{post_id}",
                params={"access_token": fb_token},
                timeout=15
            )
            print(f"FB delete: {resp.status_code} {resp.text[:100]}", flush=True)
            if resp.status_code == 200:
                send_message(chat_id, "✅ פוסט נמחק מפייסבוק!", get_menu(user_id))
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        except Exception as e:
            send_message(chat_id, f"❌ {e}")
        draft["step"] = "idle"
        return True

    elif step == "social_delete_ig_input":
        send_message(chat_id, """⚠️ <b>אינסטגרם לא מאפשר מחיקה דרך API</b>

למחיקת הפוסט:
1. כנס ל-Creator Studio:
https://business.facebook.com/creatorstudio

2. בחר את חשבון האינסטגרם
3. מצא את הפוסט ומחק

או ישירות באפליקציית אינסטגרם → הפוסט → ⋯ → מחק""", get_menu(user_id))
        draft["step"] = "idle"
        return True

    elif step == "social_video_platforms":
        pass
        return True

    elif step == "social_yt_title":
        draft["social_data"]["yt_title"] = text
        draft["step"] = "social_yt_desc"
        send_message(chat_id, "✍️ שלח תיאור לYouTube (או /skip):")
        return True

    elif step == "social_yt_desc":
        if text != "/skip":
            draft["social_data"]["yt_desc"] = text
        draft["step"] = "social_yt_tags"
        send_message(chat_id, "🏷️ שלח תגיות מופרדות בפסיק (או /skip):")
        return True

    elif step == "social_yt_tags":
        if text != "/skip":
            draft["social_data"]["yt_tags"] = [t.strip() for t in text.split(",")]
        _process_next_social_platform(chat_id, user_id, draft, drafts)
        return True

    elif step == "social_tiktok_caption":
        if text != "/skip":
            draft["social_data"]["tiktok_caption"] = text
        _process_next_social_platform(chat_id, user_id, draft, drafts)
        return True

    return False

def _show_social_platforms(chat_id, social, mode="content"):
    """מציג בחירת פלטפורמות להפצת תוכן"""
    send_message(chat_id, "📢 <b>לאיזה פלטפורמות להפיץ?</b>", {
        "inline_keyboard": [
            [{"text": "📘 פייסבוק", "callback_data": "social_fb"},
             {"text": "📸 אינסטגרם", "callback_data": "social_ig"}],
            [{"text": "📱 טלגרם ערוץ", "callback_data": "social_tg"},
             {"text": "🐦 טוויטר", "callback_data": "social_tw"}],
            [{"text": "💬 וואטסאפ", "callback_data": "social_wa"}],
            [{"text": "🌐 הכל", "callback_data": "social_all_content"}],
            [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
        ]
    })

def _show_social_video_platforms(chat_id):
    """מציג בחירת פלטפורמות לוידאו"""
    send_message(chat_id, "🎥 <b>לאיזה פלטפורמות להעלות?</b>", {
        "inline_keyboard": [
            [{"text": "▶️ YouTube", "callback_data": "social_video_yt"},
             {"text": "🎬 Vimeo", "callback_data": "social_video_vimeo"}],
            [{"text": "🎵 TikTok", "callback_data": "social_video_tiktok"}],
            [{"text": "🌐 הכל", "callback_data": "social_video_all"}],
            [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
        ]
    })

def _process_next_social_platform(chat_id, user_id, draft, drafts):
    """מעבד פלטפורמה הבאה בתור"""
    social = draft.get("social_data", {})
    queue = social.get("platforms_queue", [])

    if not queue:
        # סיים הכל
        send_message(chat_id, "✅ <b>הפצה הושלמה!</b>", get_menu(user_id))
        drafts[user_id] = {"step": "idle", "gallery": []}
        return

    platform = queue.pop(0)
    social["platforms_queue"] = queue
    draft["social_data"] = social

    if platform == "youtube":
        draft["step"] = "social_yt_title"
        send_message(chat_id, "▶️ <b>YouTube</b>\n\nשלח כותרת לסרטון:")

    elif platform == "vimeo":
        send_message(chat_id, "⏳ מעלה ל-Vimeo...")
        def _upload_vimeo():
            vb = social.get("video_bytes")
            if vb:
                url, vid_id = upload_to_vimeo(vb, social.get("yt_title", "סרטון"), chat_id)
                if url:
                    send_message(chat_id, f"✅ Vimeo: {url}")
                else:
                    send_message(chat_id, "❌ שגיאה ב-Vimeo")
            _process_next_social_platform(chat_id, user_id, draft, drafts)
        threading.Thread(target=_upload_vimeo, daemon=True).start()

    elif platform == "tiktok":
        draft["step"] = "social_tiktok_caption"
        send_message(chat_id, "🎵 <b>TikTok</b>\n\nשלח כותרת ו-hashtags (או /skip):")

    elif platform == "facebook":
        send_message(chat_id, "⏳ מפרסם לפייסבוק...")
        text_content = social.get("text_content", "")
        link = social.get("link", "")
        msg_text = f"{text_content}\n{link}" if link else text_content
        img = social.get("image")
        if img:
            img = add_watermark(img)
        ok, result = post_to_facebook(msg_text, img)
        send_message(chat_id, f"✅ פורסם בפייסבוק!" if ok else f"❌ פייסבוק: {result}")
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif platform == "instagram":
        send_message(chat_id, "⏳ מפרסם לאינסטגרם...")
        img = social.get("image")
        if img:
            img = add_watermark(resize_for_instagram(img))
        caption = social.get("text_content", "")
        ok, result = post_to_instagram(caption, img)
        if ok:
            # שמור כותרת גלובלית לשימוש בסטורי
            import builtins
            builtins.LAST_POST_TITLE = caption.split('\n')[0][:50] if caption else ""
            send_message(chat_id, "✅ פורסם באינסטגרם!", {
                "inline_keyboard": [[{"text": "📱 שתף לסטורי", "callback_data": f"ig_story_{result}"}]]
            })
        else:
            send_message(chat_id, f"❌ אינסטגרם: {result}")
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif platform == "telegram":
        send_message(chat_id, "⏳ שולח לערוץ...")
        text_content = social.get("text_content", "")
        link = social.get("link", "")
        msg_text = f"{text_content}\n{link}" if link else text_content
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": msg_text},
                timeout=10
            )
            send_message(chat_id, "✅ נשלח לערוץ טלגרם!")
        except:
            send_message(chat_id, "❌ שגיאה בשליחה לערוץ")
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif platform == "twitter":
        send_message(chat_id, "⏳ מפרסם לטוויטר...")
        text_content = social.get("text_content", "")
        link = social.get("link", "")
        ok, result = post_to_twitter(text_content, link)
        send_message(chat_id, f"✅ פורסם בטוויטר!" if ok else f"❌ טוויטר: {result}")
        _process_next_social_platform(chat_id, user_id, draft, drafts)

def _add_videos_to_post(chat_id, user_id, draft, drafts, videos, service="vimeo"):
    """מוסיף סרטונים לכתבה קיימת"""
    post_id = draft.get("edit_id")
    
    def _do_upload():
        r = requests.get(f"{WP_URL}/posts/{post_id}?context=edit", auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code != 200:
            send_message(chat_id, "❌ לא מצאתי את הכתבה.")
            return
        existing_content = r.json().get("content", {}).get("raw", "")
        new_content = existing_content
        count = 0
        
        for vid in videos:
            if vid["type"] == "url":
                url = vid["url"]
                if "vimeo.com" in url:
                    vid_id = url.split("/")[-1].split("?")[0]
                    new_content += f'\n\n<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="https://player.vimeo.com/video/{vid_id}" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>\n'
                elif "youtube.com" in url or "youtu.be" in url:
                    new_content += f'\n\n<!-- wp:embed {{"url":"{url}"}} -->\n<figure class="wp-block-embed"><div class="wp-block-embed__wrapper">\n{url}\n</div></figure>\n<!-- /wp:embed -->'
                count += 1
            elif vid["type"] == "file":
                send_message(chat_id, f"⏳ מעלה סרטון ל-{service}...")
                if service in ("vimeo", "all"):
                    vimeo_url, _ = upload_to_vimeo(vid["bytes"], draft.get("edit_title", "סרטון"), chat_id)
                    if vimeo_url:
                        vid_id = vimeo_url.split("/")[-1]
                        new_content += f'\n\n<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="https://player.vimeo.com/video/{vid_id}" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>\n'
                        count += 1
                if service in ("youtube", "all"):
                    # YouTube דורש כותרת
                    send_message(chat_id, f"✅ Vimeo הועלה! מעלה גם ל-YouTube...")
        
        requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content},
                     auth=(WP_USER, WP_PASSWORD), timeout=10)
        send_message(chat_id, f"✅ {count} סרטונים נוספו לכתבה!", get_menu(user_id))
        drafts[user_id] = {"step": "idle", "gallery": []}
    
    threading.Thread(target=_do_upload, daemon=True).start()

def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    user_id = str(cb["from"]["id"])
    cb_data = cb["data"]

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                 json={"callback_query_id": cb["id"]}, timeout=5)

    draft = drafts.get(user_id, {})
    if not draft:
        draft = {"step": "idle", "gallery": []}
    drafts[user_id] = draft

    if cb_data.startswith("cat_") and cb_data != "cat_done":
        parts = cb_data.split("_", 2)
        cat_id = int(parts[1])
        cat_name = parts[2]
        if cat_id not in draft.get("categories", []):
            draft.setdefault("categories", []).append(cat_id)
            draft.setdefault("cat_names", []).append(cat_name)
            send_message(chat_id, f"✅ <b>{cat_name}</b> נוספה!\nנבחרו: {', '.join(draft['cat_names'])}\n\nבחר עוד או לחץ סיימתי")
        else:
            send_message(chat_id, f"⚠️ {cat_name} כבר נבחרה.")

    elif cb_data == "yt_smart_approve":
        draft["step"] = "youtube_video"
        send_message(chat_id, "✅ מעולה! עכשיו שלח את <b>קובץ הסרטון</b>:")

    elif cb_data == "yt_edit_title":
        draft["step"] = "yt_edit_title_input"
        send_message(chat_id, f"כותרת נוכחית:\n<b>{draft.get('yt_title','')}</b>\n\nשלח כותרת חדשה:")

    elif cb_data == "yt_edit_desc":
        draft["step"] = "yt_edit_desc_input"
        send_message(chat_id, f"תיאור נוכחי:\n{draft.get('yt_desc','')}\n\nשלח תיאור חדש:")

    elif cb_data == "yt_manual":
        draft["step"] = "youtube_title"
        send_message(chat_id, "🎬 שלח את <b>כותרת הסרטון</b>:")

    elif cb_data == "yt_smart":
        draft["step"] = "youtube_smart_text"
        send_message(chat_id, "🤖 שלח טקסט גולמי ו-Gemini יכין כותרת, תיאור ותגיות:")

    elif cb_data == "mazaltov_single":
        draft["step"] = "mazaltov_image"
        send_message(chat_id, "🎉 שלח את <b>התמונה</b>:")

    elif cb_data == "mazaltov_multi":
        draft["step"] = "mazaltov_multi"
        draft["mazaltov_images"] = []
        send_message(chat_id, "🎉 שלח את כל התמונות (אפשר כמה ביחד).\nכשסיימת שלח /done:")

    elif cb_data == "upload_group_vimeo":
        files = draft.get("pending_group_files", [])
        send_message(chat_id, f"⏳ מעלה {len(files)} סרטונים ל-Vimeo...")
        success = 0
        for i, fid in enumerate(files):
            video_bytes = get_file(fid)
            if video_bytes:
                url, vid_id = upload_to_vimeo(video_bytes, f"{draft.get('title', 'סרטון')} {i+1}", chat_id)
                if url:
                    draft.setdefault("videos", []).append(url)
                    draft.setdefault("vimeo_ids", []).append(vid_id)
                    success += 1
        draft["pending_group_files"] = []
        send_message(chat_id, f"✅ הועלו {success}/{len(files)} סרטונים ל-Vimeo!\n\nשלח /done לסיום או סרטון נוסף:")

    elif cb_data == "upload_group_youtube":
        files = draft.get("pending_group_files", [])
        if not youtube_tokens.get("access_token"):
            auth_url = get_youtube_auth_url()
            send_message(chat_id, f"🔑 צריך להתחבר ל-YouTube:\n<a href='{auth_url}'>לחץ כאן</a>")
        else:
            send_message(chat_id, f"⏳ מעלה {len(files)} סרטונים ל-YouTube...")
            success = 0
            for i, fid in enumerate(files):
                video_bytes = get_file(fid)
                if video_bytes:
                    url, error = upload_to_youtube(video_bytes, f"{draft.get('title', 'סרטון')} {i+1}")
                    if url:
                        draft.setdefault("videos", []).append(url)
                        success += 1
            draft["pending_group_files"] = []
            send_message(chat_id, f"✅ הועלו {success}/{len(files)} סרטונים ל-YouTube!\n\nשלח /done לסיום או סרטון נוסף:")

    elif cb_data == "upload_vimeo":
        file_id = draft.get("pending_video_file_id")
        if file_id:
            send_message(chat_id, "⏳ מעלה ל-Vimeo...")
            video_bytes = get_file(file_id)
            if video_bytes:
                vimeo_url, vid_id = upload_to_vimeo(video_bytes, draft.get("title", "סרטון"), chat_id)
                if vimeo_url:
                    draft.setdefault("videos", []).append(vimeo_url)
                    draft.setdefault("vimeo_ids", []).append(vid_id)
                    send_message(chat_id, f"✅ עלה ל-Vimeo!\n\nשלח סרטון נוסף או /done:")
                else:
                    send_message(chat_id, "❌ שגיאה בהעלאה ל-Vimeo")

    elif cb_data == "upload_youtube_smart":
        draft["step"] = "article_yt_smart_text"
        send_message(chat_id, "🤖 שלח טקסט גולמי ו-Gemini יכין כותרת ותגיות לסרטון:")

    elif cb_data == "upload_youtube":
        file_id = draft.get("pending_video_file_id")
        if file_id:
            if not youtube_tokens.get("access_token"):
                auth_url = get_youtube_auth_url()
                send_message(chat_id, f"🔑 צריך להתחבר ל-YouTube קודם:\n<a href='{auth_url}'>לחץ כאן</a>")
            else:
                send_message(chat_id, "⏳ מעלה ל-YouTube...")
                video_bytes = get_file(file_id)
                if video_bytes:
                    url, error = upload_to_youtube(video_bytes, draft.get("title", "סרטון"))
                    if url:
                        draft.setdefault("videos", []).append(url)
                        send_message(chat_id, f"✅ עלה ל-YouTube!\n🔗 {url}\n\nשלח סרטון נוסף או /done:")
                    else:
                        send_message(chat_id, f"❌ שגיאה: {error}")

    elif cb_data == "smart_approve":
        # קטגוריות כבר נבחרו בתצוגה המקדימה
        if not draft.get("categories"):
            cats, cat_names = auto_select_categories(draft.get("title",""), draft.get("body",""))
            draft["categories"] = cats
            draft["cat_names"] = cat_names
        if draft.get("from_email"):
            draft["step"] = "confirm"
            _show_summary(chat_id, draft)
        else:
            draft["step"] = "main_image"
            send_message(chat_id, "שלח את <b>התמונה הראשית</b>:", {
                "inline_keyboard": [[{"text": "🔄 שנה קטגוריות", "callback_data": "change_categories"},
                                     {"text": "⏭️ דלג", "callback_data": "skip_main_image"}]]
            })

    elif cb_data == "smart_retry":
        draft["step"] = "smart_text"
        saved_text = draft.get("body", "")
        if saved_text:
            send_message(chat_id, "⏳ מנסה שוב...")
            result = process_with_gemini(saved_text)
            if result:
                body_clean = convert_whatsapp_format(result.get("body", saved_text))
                draft.update({
                    "title": result.get("title", ""),
                    "subtitle": result.get("subtitle", ""),
                    "red_title": result.get("red_title", ""),
                    "body": body_clean,
                    "tags": result.get("tags", []),
                    "step": "smart_preview"
                })
                import re
                body_preview = re.sub(r'<[^>]+>', '', body_clean)[:300]
                preview = f"""🤖 <b>תצוגה מקדימה:</b>

<b>כותרת:</b> {draft['title']}
<b>כותרת משנה:</b> {draft['subtitle']}
<b>כותרת אדומה:</b> {draft['red_title']}
<b>תגיות:</b> {', '.join(draft['tags'])}

<b>גוף:</b>
{body_preview}{'...' if len(body_clean) > 300 else ''}"""
                send_message(chat_id, preview, {
                    "inline_keyboard": [
                        [{"text": "✅ מאשר, המשך", "callback_data": "smart_approve"}],
                        [{"text": "✨ שפר כותרות", "callback_data": "smart_improve_titles"}],
                        [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
                         {"text": "✏️ ערוך כותרת משנה", "callback_data": "smart_edit_subtitle"}],
                        [{"text": "✏️ ערוך גוף", "callback_data": "smart_edit_body"},
                         {"text": "✏️ ערוך תגיות", "callback_data": "smart_edit_tags"}],
                        [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                    ]
                })
            else:
                send_message(chat_id, "❌ ה-AI עדיין לא זמין. נסה שוב בעוד דקה.", {
                    "inline_keyboard": [
                        [{"text": "🔄 נסה שוב", "callback_data": "smart_retry"}],
                        [{"text": "✍️ המשך ידנית", "callback_data": "smart_manual_fallback"}],
                        [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                    ]
                })
        else:
            send_message(chat_id, "שלח את הטקסט מחדש:")

    elif cb_data == "smart_manual_fallback":
        # עבור להעלאה ידנית עם הגוף שנשמר
        draft["step"] = "title"
        draft["title"] = ""
        send_message(chat_id, "✍️ נעבור להעלאה ידנית.\n\nשלח את <b>הכותרת</b>:")

    elif cb_data == "smart_improve_titles":
        send_message(chat_id, "✨ משפר כותרות...")
        improved = improve_titles_with_ai(draft)
        if improved:
            draft["title"] = improved.get("title", draft["title"])
            draft["subtitle"] = improved.get("subtitle", draft["subtitle"])
            draft["red_title"] = improved.get("red_title", draft["red_title"])
            import re
            body_preview = re.sub(r'<[^>]+>', '', draft.get("body",""))[:300]
            preview = f"""✨ <b>כותרות משופרות:</b>

<b>כותרת:</b> {draft['title']}
<b>כותרת משנה:</b> {draft['subtitle']}
<b>כותרת אדומה:</b> {draft['red_title']}
<b>תגיות:</b> {', '.join(draft.get('tags',[]))}

<b>גוף:</b>
{body_preview}{'...' if len(draft.get('body','')) > 300 else ''}"""
            send_message(chat_id, preview, {
                "inline_keyboard": [
                    [{"text": "✅ מאשר, המשך", "callback_data": "smart_approve"}],
                    [{"text": "✨ שפר שוב", "callback_data": "smart_improve_titles"}],
                    [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
                     {"text": "✏️ ערוך כותרת משנה", "callback_data": "smart_edit_subtitle"}],
                    [{"text": "✏️ ערוך גוף", "callback_data": "smart_edit_body"},
                     {"text": "✏️ ערוך תגיות", "callback_data": "smart_edit_tags"}],
                    [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                ]
            })
        else:
            send_message(chat_id, "❌ שגיאה בשיפור כותרות. נסה שוב.")

    elif cb_data == "smart_edit_red_title":
        draft["step"] = "smart_edit_red_title_input"
        send_message(chat_id, f"כותרת אדומה נוכחית:\n<b>{draft.get('red_title','')}</b>\n\nשלח כותרת אדומה חדשה (2-4 מילים):")

    elif cb_data == "smart_edit_subtitle":
        draft["step"] = "smart_edit_subtitle_input"
        send_message(chat_id, f"כותרת משנה נוכחית:\n{draft.get('subtitle','')}\n\nשלח כותרת משנה חדשה:")

    elif cb_data == "smart_edit_title":
        draft["step"] = "smart_edit_title_input"
        send_message(chat_id, f"כותרת נוכחית:\n<b>{draft.get('title','')}</b>\n\nשלח כותרת חדשה:")

    elif cb_data == "smart_edit_body":
        draft["step"] = "smart_edit_body_input"
        send_message(chat_id, "שלח גוף כתבה חדש:")

    elif cb_data == "smart_edit_tags":
        draft["step"] = "smart_edit_tags_input"
        send_message(chat_id, f"תגיות נוכחיות: {', '.join(draft.get('tags',[]))}\n\nשלח תגיות חדשות מופרדות בפסיק:")

    elif cb_data == "publish_now":
        send_message(chat_id, "⏳ מפרסם לוורדפרס...")
        try:
            resp = publish_to_wp(draft, "publish")
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בפרסום: {e}", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}
            return
        if resp.status_code == 201:
            post_url = resp.json().get("link", "")
            post_title = draft.get("title", "")
            notify_channel(post_title, draft.get("subtitle", ""), post_url)
            draft["last_post_url"] = post_url
            draft["last_post_title"] = post_title
            # שמור גלובלית לשימוש בסטורי
            import builtins
            builtins.LAST_POST_TITLE = post_title
            builtins.LAST_POST_URL = post_url
            send_message(chat_id, f"✅ <b>הכתבה פורסמה ונשלחה לערוץ!</b>\n🔗 {post_url}", {
                "inline_keyboard": [
                    [{"text": "📘 פרסם בפייסבוק", "callback_data": "auto_share_fb"},
                     {"text": "📸 פרסם באינסטגרם", "callback_data": "auto_share_ig"}],
                    [{"text": "🌐 פרסם בכולם", "callback_data": "auto_share_all"}],
                    [{"text": "🐦 טוויטר", "callback_data": "share_twitter"},
                     {"text": "✅ סיום", "callback_data": "publish_done"}]
                ]
            })
        else:
            send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
            drafts[user_id] = {"step": "idle", "gallery": []}

    elif cb_data == "publish_draft":
        send_message(chat_id, "⏳ שומר כטיוטה...")
        resp = publish_to_wp(draft, "draft")
        if resp.status_code == 201:
            send_message(chat_id, "✅ <b>נשמר כטיוטה!</b>", get_menu(user_id))
        else:
            send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        drafts[user_id] = {"step": "idle", "gallery": []}

    elif cb_data == "publish_schedule":
        from datetime import datetime, timedelta
        now = datetime.now()
        times = [
            ("בעוד שעה", now + timedelta(hours=1)),
            ("מחר בבוקר 08:00", now.replace(hour=8, minute=0) + timedelta(days=1)),
            ("מחר בצהריים 12:00", now.replace(hour=12, minute=0) + timedelta(days=1)),
            ("מחר בערב 20:00", now.replace(hour=20, minute=0) + timedelta(days=1)),
        ]
        keyboard = {"inline_keyboard": [
            [{"text": label, "callback_data": f"sched_{dt.strftime('%d/%m/%Y_%H:%M')}"}]
            for label, dt in times
        ] + [[{"text": "⌨️ הזן זמן ידנית", "callback_data": "schedule_manual"}]]}
        send_message(chat_id, "⏰ <b>מתי לפרסם?</b>", keyboard)

    elif cb_data == "schedule_manual":
        draft["step"] = "schedule_time"
        send_message(chat_id, "⏰ שלח תאריך ושעה:\n<code>DD/MM/YYYY HH:MM</code>\n\nלדוגמה: <code>20/05/2026 09:00</code>")

    elif cb_data.startswith("sched_"):
        time_str = cb_data.replace("sched_", "").replace("_", " ")
        try:
            from datetime import datetime
            dt = datetime.strptime(time_str, "%d/%m/%Y %H:%M")
            iso_date = dt.strftime("%Y-%m-%dT%H:%M:00")
            send_message(chat_id, "⏳ מתזמן פרסום...")
            try:
                resp = publish_to_wp(draft, "future", iso_date)
            except Exception as e:
                send_message(chat_id, f"❌ שגיאה: {e}", get_menu(user_id))
                return
            if resp.status_code == 201:
                send_message(chat_id, f"✅ <b>הכתבה מתוזמנת לפרסום ב-{time_str}!</b>", get_menu(user_id))
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
            drafts[user_id] = {"step": "idle", "gallery": []}
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")

    elif cb_data == "publish_cancel":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ הפעולה בוטלה.", get_menu(user_id))

    elif cb_data == "cat_done":
        draft["step"] = "main_image"
        send_message(chat_id, f"✅ קטגוריות: {', '.join(draft.get('cat_names',[]))}\n\nשלח את <b>התמונה הראשית</b>:")

    elif cb_data == "drive_link":
        draft["step"] = "drive_link_input"
        send_message(chat_id, "🔗 שלח את לינק Google Drive (תיקייה או קובץ):")

    elif cb_data == "change_categories":
        draft["step"] = "categories"
        cats = get_wp_categories()
        keyboard = {"inline_keyboard": []}
        row = []
        # הצג רק קטגוריות רלוונטיות
        relevant_ids = [11, 26, 25, 52, 45, 50, 51, 49, 48, 1087, 1090, 1091, 1089, 1088, 47, 46, 62, 1083, 63, 1084, 1085, 1086, 24]
        for cat_name, cat_id in cats.items():
            if cat_id in relevant_ids:
                row.append({"text": cat_name, "callback_data": f"cat_{cat_id}_{cat_name}"})
                if len(row) == 2:
                    keyboard["inline_keyboard"].append(row)
                    row = []
        if row:
            keyboard["inline_keyboard"].append(row)
        keyboard["inline_keyboard"].append([{"text": "✅ סיימתי", "callback_data": "cat_done"}])
        draft["categories"] = []
        draft["cat_names"] = []
        send_message(chat_id, "בחר קטגוריות:", keyboard)

    elif cb_data == "analytics_top":
        send_message(chat_id, "לאיזה תקופה?", {
            "inline_keyboard": [
                [{"text": "24 שעות אחרונות", "callback_data": "analytics_top_1"},
                 {"text": "שבוע אחרון", "callback_data": "analytics_top_7"}],
                [{"text": "חודש אחרון", "callback_data": "analytics_top_30"}]
            ]
        })

    elif cb_data.startswith("analytics_top_"):
        days = cb_data.replace("analytics_top_", "")
        period = f"{days}daysAgo"
        period_name = {"1": "24 השעות האחרונות", "7": "7 הימים האחרונים", "30": "30 הימים האחרונים"}.get(days, "")
        send_message(chat_id, "⏳ מושך נתונים...")
        data = get_analytics_data(period)
        if data and data.get("rows"):
            msg = f"🏆 <b>חמש הכתבות הנצפות ביותר באתר ״עדכוני חב״ד״</b>\n<b>{period_name}:</b>\n\n"
            for i, row in enumerate(data["rows"][:5], 1):
                title = row["dimensionValues"][0]["value"]
                path = row["dimensionValues"][1]["value"]
                url = f"https://chabadupdates.com{path}"
                msg += f"<b>{i}. {title}</b>\n{url}\n\n"
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "❌ לא נמצאו נתונים.")

    elif cb_data == "analytics_visits":
        send_message(chat_id, "לאיזה תקופה?", {
            "inline_keyboard": [
                [{"text": "24 שעות אחרונות", "callback_data": "analytics_visits_1"}],
                [{"text": "7 ימים אחרונים", "callback_data": "analytics_visits_7"}],
                [{"text": "30 ימים אחרונים", "callback_data": "analytics_visits_30"}]
            ]
        })

    elif cb_data.startswith("analytics_visits_"):
        days = cb_data.replace("analytics_visits_", "")
        period = f"{days}daysAgo"
        period_name = {"1": "24 השעות האחרונות", "7": "7 הימים האחרונים", "30": "30 הימים האחרונים"}.get(days, "")
        send_message(chat_id, "⏳ מושך נתונים...")
        data = get_analytics_totals(period)
        if data:
            msg = f"""📊 <b>סטטיסטיקות אתר ״עדכוני חב״ד״</b>
<b>{period_name}:</b>

👥 משתמשים: <b>{data['users']}</b>
🔗 סשנים: <b>{data['sessions']}</b>
👁 צפיות בדפים: <b>{data['pageviews']}</b>"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "❌ לא נמצאו נתונים.")

    elif cb_data == "analytics_page":
        draft["step"] = "analytics_page_input"
        send_message(chat_id, "🔍 שלח לינק לכתבה שתרצה לבדוק:")

    elif cb_data.startswith("analytics_page_"):
        parts = cb_data.split("_", 3)
        days = parts[2]
        url = parts[3]
        period = f"{days}daysAgo"
        period_name = {"1": "24 שעות", "7": "שבוע", "30": "חודש"}.get(days, "")
        data = get_analytics_page(url, period)
        if data:
            msg = f"""🔍 <b>{data['title']}</b>

<b>תקופה:</b> {period_name}
👁 צפיות: <b>{data['pageviews']}</b>
👥 משתמשים: <b>{data['users']}</b>

🔗 {url}"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "❌ לא נמצאו נתונים לכתבה זו.")

    elif cb_data == "email_toggle":
        email_system["active"] = not email_system["active"]
        status = "✅ הופעלה" if email_system["active"] else "⏸️ הושהתה"
        send_message(chat_id, f"מערכת המייל {status}!", get_menu(user_id))

    elif cb_data == "email_check_now":
        send_message(chat_id, "⏳ בודק מיילים...")
        threading.Thread(target=check_emails, daemon=True).start()
        send_message(chat_id, "✅ בדיקה הופעלה! תקבל הודעה אם יש מיילים חדשים.")

    elif cb_data == "email_change_interval":
        draft["step"] = "email_interval_input"
        send_message(chat_id, f"⏱️ תדירות נוכחית: {email_system['interval']//60} דקות\n\nשלח מספר דקות חדש:")

    elif cb_data == "email_add_sender":
        draft["step"] = "email_add_sender_input"
        send_message(chat_id, "➕ שלח את כתובת המייל להוספה:")

    elif cb_data == "email_remove_sender":
        senders = email_system["allowed_senders"]
        if not senders:
            send_message(chat_id, "אין כתובות מורשות.")
        else:
            keyboard = {"inline_keyboard": [[{"text": f"🗑 {s}", "callback_data": f"email_rm_{s}"}] for s in senders]}
            keyboard["inline_keyboard"].append([{"text": "❌ ביטול", "callback_data": "publish_cancel"}])
            send_message(chat_id, "בחר כתובת להסרה:", keyboard)

    elif cb_data.startswith("email_rm_"):
        addr = cb_data.replace("email_rm_", "")
        if addr in email_system["allowed_senders"]:
            email_system["allowed_senders"].remove(addr)
            send_message(chat_id, f"✅ {addr} הוסרה!", get_menu(user_id))

    elif cb_data == "email_approve":
        pending = email_system.get("pending_email", {})
        if pending.get("type") == "article":
            send_message(chat_id, "⏳ Gemini מעבד את המייל...")
            body = pending.get("body", "")
            result = process_with_gemini(body)
            if result:
                new_draft = {
                    "step": "smart_preview",
                    "title": result.get("title", ""),
                    "subtitle": result.get("subtitle", ""),
                    "red_title": result.get("red_title", ""),
                    "body": convert_whatsapp_format(result.get("body", body)),
                    "tags": result.get("tags", []),
                    "gallery": [],
                    "categories": [],
                    "cat_names": [],
                    "from_email": True
                }
                # בחר קטגוריות אוטומטית
                cats, cat_names = auto_select_categories(new_draft["title"], new_draft["body"])
                new_draft["categories"] = cats
                new_draft["cat_names"] = cat_names
                # הוסף תמונות מהמייל
                images = pending.get("images", [])
                if images:
                    new_draft["main_image"] = images[0]
                    new_draft["gallery"] = images[1:]
                # העלה סרטונים ל-Vimeo
                videos = pending.get("videos", [])
                if videos:
                    send_message(chat_id, f"⏳ מעלה {len(videos)} סרטונים ל-Vimeo...")
                    vimeo_urls = []
                    vimeo_ids = []
                    for i, vid_bytes in enumerate(videos):
                        result_v = upload_to_vimeo(vid_bytes, new_draft.get("title", f"סרטון {i+1}"), chat_id)
                        if result_v and isinstance(result_v, tuple):
                            url, vid_id = result_v
                            if url:
                                vimeo_urls.append(url)
                                vimeo_ids.append(vid_id)
                    if vimeo_urls:
                        new_draft["videos"] = vimeo_urls
                        new_draft["vimeo_ids"] = vimeo_ids
                        send_message(chat_id, f"✅ {len(vimeo_urls)} סרטונים עלו ל-Vimeo!")
                drafts[user_id] = new_draft
                import re
                body_preview = re.sub(r'<[^>]+>', '', new_draft["body"])[:300]
                preview = f"""📧 <b>כתבה ממייל – תצוגה מקדימה:</b>

<b>כותרת:</b> {new_draft['title']}
<b>כותרת משנה:</b> {new_draft['subtitle']}
<b>כותרת אדומה:</b> {new_draft['red_title']}
<b>תגיות:</b> {', '.join(new_draft['tags'])}
<b>תמונות:</b> {len(images)}

<b>גוף:</b>
{body_preview}{'...' if len(new_draft['body']) > 300 else ''}"""
                send_message(chat_id, preview, {
                    "inline_keyboard": [
                        [{"text": "✅ מאשר, המשך", "callback_data": "smart_approve"}],
                        [{"text": "✨ שפר כותרות", "callback_data": "smart_improve_titles"}],
                        [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
                         {"text": "✏️ ערוך כותרת משנה", "callback_data": "smart_edit_subtitle"}],
                        [{"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                    ]
                })
            else:
                send_message(chat_id, "❌ שגיאה בעיבוד. נסה שוב.", get_menu(user_id))
            email_system["pending_email"] = {}

    elif cb_data == "email_reject":
        email_system["pending_email"] = {}
        send_message(chat_id, "❌ המייל נדחה.", get_menu(user_id))

    elif cb_data == "email_cancel":
        email_system["pending_email"] = {}
        drafts[user_id]["step"] = "idle"
        send_message(chat_id, "❌ בוטל.", get_menu(user_id))

    elif cb_data == "social_fb":
        draft["social_data"]["platforms_queue"] = ["facebook"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_ig":
        draft["social_data"]["platforms_queue"] = ["instagram"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_tg":
        draft["social_data"]["platforms_queue"] = ["telegram"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_tw":
        draft["social_data"]["platforms_queue"] = ["twitter"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_wa":
        send_message(chat_id, "⚠️ WhatsApp Business API דורש הגדרה נוספת.\n\nנוסיף בהמשך 🙂", get_menu(user_id))

    elif cb_data == "social_all_content":
        draft["social_data"]["platforms_queue"] = ["facebook", "instagram", "telegram", "twitter"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_video_yt":
        draft["social_data"]["platforms_queue"] = ["youtube"]
        draft["step"] = "social_yt_title"
        send_message(chat_id, "▶️ <b>YouTube</b>\n\nשלח כותרת לסרטון:")

    elif cb_data == "social_video_vimeo":
        draft["social_data"]["platforms_queue"] = ["vimeo"]
        _process_next_social_platform(chat_id, user_id, draft, drafts)

    elif cb_data == "social_video_tiktok":
        draft["social_data"]["platforms_queue"] = ["tiktok"]
        draft["step"] = "social_tiktok_caption"
        send_message(chat_id, "🎵 <b>TikTok</b>\n\nשלח כותרת ו-hashtags (או /skip):")

    elif cb_data == "social_video_all":
        draft["social_data"]["platforms_queue"] = ["youtube", "vimeo", "tiktok"]
        draft["step"] = "social_yt_title"
        send_message(chat_id, "▶️ <b>YouTube ראשון</b>\n\nשלח כותרת לסרטון:")

    elif cb_data.startswith("ig_story_"):
        media_id = cb_data.replace("ig_story_", "")
        ig_user_id = os.environ.get("IG_USER_ID","")
        fb_token = os.environ.get("FB_PAGE_TOKEN","")
        # קח כותרת מה-draft או מהמשתנה הגלובלי
        import builtins
        post_title = (draft.get("last_post_title") or 
                     draft.get("title") or 
                     getattr(builtins, 'LAST_POST_TITLE', "") or
                     draft.get("social_data", {}).get("text_content", ""))

        status_resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": "⏳ מכין סטורי...", "parse_mode": "HTML"},
            timeout=10
        )
        msg_id = status_resp.json().get("result", {}).get("message_id") if status_resp.ok else None

        def _post_story():
            try:
                # מצא URL של התמונה מהפוסט
                edit_message(chat_id, msg_id, "⏳ מושך תמונה מהפוסט...")
                media_resp = requests.get(
                    f"https://graph.facebook.com/v18.0/{media_id}",
                    params={"fields": "media_url,thumbnail_url", "access_token": fb_token},
                    timeout=15
                )
                img_url = None
                if media_resp.status_code == 200:
                    data = media_resp.json()
                    img_url = data.get("media_url") or data.get("thumbnail_url")
                print(f"Story image URL: {img_url}", flush=True)

                if not img_url:
                    edit_message(chat_id, msg_id, "❌ לא מצאתי תמונה בפוסט")
                    return

                # הורד את התמונה
                img_resp = requests.get(img_url, timeout=30)
                if img_resp.status_code != 200:
                    edit_message(chat_id, msg_id, "❌ לא הצלחתי להוריד תמונה")
                    return

                # בנה תמונת סטורי עם תבנית
                edit_message(chat_id, msg_id, "⏳ בונה תבנית סטורי...")
                story_img = create_story_template(img_resp.content, post_title)

                # העלה לוורדפרס
                edit_message(chat_id, msg_id, "⏳ מעלה סטורי...")
                _, story_url = upload_image_to_wp(story_img, "story.jpg")
                if not story_url:
                    edit_message(chat_id, msg_id, "❌ שגיאה בהעלאת תמונה")
                    return

                # פרסם לסטורי
                resp = requests.post(
                    f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
                    data={"image_url": story_url, "media_type": "STORIES", "access_token": fb_token},
                    timeout=30
                )
                print(f"Story container: {resp.status_code} {resp.text[:150]}", flush=True)
                if resp.status_code != 200:
                    edit_message(chat_id, msg_id, f"❌ שגיאה: {resp.text[:200]}")
                    return

                container_id = resp.json().get("id")
                time.sleep(3)
                pub = requests.post(
                    f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
                    data={"creation_id": container_id, "access_token": fb_token},
                    timeout=15
                )
                print(f"Story publish: {pub.status_code} {pub.text[:100]}", flush=True)
                if pub.status_code == 200:
                    edit_message(chat_id, msg_id, "✅ סטורי פורסם!")
                else:
                    edit_message(chat_id, msg_id, f"❌ שגיאה: {pub.text[:200]}")
            except Exception as e:
                edit_message(chat_id, msg_id, f"❌ שגיאה: {e}")

        threading.Thread(target=_post_story, daemon=True).start()

    elif cb_data == "watermark_settings":
        wm = watermark_settings
        send_message(chat_id, f"""🖼 <b>הגדרות ווטרמארק</b>

<b>סטטוס:</b> {'✅ פעיל' if wm['enabled'] else '❌ כבוי'}
<b>מצב:</b> {'🖼 לוגו' if wm['mode']=='logo' else '✏️ טקסט'}
<b>טקסט:</b> {wm['text']}
<b>גופן:</b> {wm.get('font','bold')}
<b>גודל:</b> {wm['font_size']}px
<b>צבע טקסט:</b> {wm['text_color']}
<b>צבע רקע:</b> {wm['bg_color']}
<b>שקיפות רקע:</b> {wm['bg_opacity']}/255
<b>מיקום X:</b> {wm['pos_x']}% (מימין)
<b>מיקום Y:</b> {wm['pos_y']}% (מלמטה)""", {
            "inline_keyboard": [
                [{"text": "✅ הפעל" if not wm['enabled'] else "❌ כבה", "callback_data": "wm_toggle"}],
                [{"text": "✏️ מצב טקסט", "callback_data": "wm_mode_text"},
                 {"text": "🖼 מצב לוגו", "callback_data": "wm_mode_logo"}],
                [{"text": "📝 שנה טקסט", "callback_data": "wm_text"}],
                [{"text": "🔤 גופן רגיל", "callback_data": "wm_font_default"},
                 {"text": "🔤 גופן מודגש", "callback_data": "wm_font_bold"},
                 {"text": "🔤 גופן קלאסי", "callback_data": "wm_font_serif"}],
                [{"text": "📏 שנה גודל (px)", "callback_data": "wm_fontsize"}],
                [{"text": "🎨 צבע טקסט (hex)", "callback_data": "wm_textcolor"}],
                [{"text": "🎨 צבע רקע (hex)", "callback_data": "wm_bgcolor"},
                 {"text": "🚫 ללא רקע", "callback_data": "wm_bg_none"}],
                [{"text": "💧 שקיפות רקע", "callback_data": "wm_opacity"}],
                [{"text": "↔️ מיקום X%", "callback_data": "wm_posx"},
                 {"text": "↕️ מיקום Y%", "callback_data": "wm_posy"}],
                [{"text": "🖼 תצוגה מקדימה", "callback_data": "wm_preview"}]
            ]
        })

    elif cb_data == "wm_toggle":
        watermark_settings["enabled"] = not watermark_settings["enabled"]
        send_message(chat_id, f"✅ ווטרמארק {'הופעל' if watermark_settings['enabled'] else 'כובה'}!")

    elif cb_data == "wm_mode_text":
        watermark_settings["mode"] = "text"
        send_message(chat_id, "✅ מצב טקסט פעיל")

    elif cb_data == "wm_mode_logo":
        draft["step"] = "wm_logo_input"
        send_message(chat_id, "🖼 שלח תמונת לוגו (PNG עם רקע שקוף מומלץ):")

    elif cb_data == "wm_text":
        draft["step"] = "wm_text_input"
        send_message(chat_id, f"✏️ שלח טקסט חדש:\n(נוכחי: {watermark_settings['text']})")

    elif cb_data.startswith("wm_font_"):
        font = cb_data.replace("wm_font_", "")
        watermark_settings["font"] = font
        send_message(chat_id, f"✅ גופן עודכן: {font}")

    elif cb_data == "wm_fontsize":
        draft["step"] = "wm_fontsize_input"
        send_message(chat_id, f"📏 שלח גודל גופן בפיקסלים (10-200):\n(נוכחי: {watermark_settings['font_size']})")

    elif cb_data == "wm_textcolor":
        draft["step"] = "wm_textcolor_input"
        send_message(chat_id, f"🎨 שלח צבע טקסט בפורמט hex:\nלדוגמה: #FFFFFF (לבן), #000000 (שחור), #FFD700 (זהב), #FF0000 (אדום)\n(נוכחי: {watermark_settings['text_color']})")

    elif cb_data == "wm_bgcolor":
        draft["step"] = "wm_bgcolor_input"
        send_message(chat_id, f"🎨 שלח צבע רקע בפורמט hex:\n(נוכחי: {watermark_settings['bg_color']})")

    elif cb_data == "wm_bg_none":
        watermark_settings["bg_color"] = "none"
        send_message(chat_id, "✅ רקע הוסר!")

    elif cb_data == "wm_opacity":
        draft["step"] = "wm_opacity_input"
        send_message(chat_id, f"💧 שלח שקיפות רקע (0=שקוף לגמרי, 255=אטום לגמרי):\n(נוכחי: {watermark_settings['bg_opacity']})")

    elif cb_data == "wm_posx":
        draft["step"] = "wm_posx_input"
        send_message(chat_id, f"↔️ שלח מיקום אופקי (0=שמאל קצה, 100=ימין קצה):\n(נוכחי: {watermark_settings['pos_x']}%)")

    elif cb_data == "wm_posy":
        draft["step"] = "wm_posy_input"
        send_message(chat_id, f"↕️ שלח מיקום אנכי (0=עליון קצה, 100=תחתון קצה):\n(נוכחי: {watermark_settings['pos_y']}%)")

    elif cb_data == "wm_preview":
        draft["step"] = "wm_preview_input"
        send_message(chat_id, "📸 שלח תמונה לבדיקת הווטרמארק:")

    elif cb_data == "social_stats_fb":
        fb_token = os.environ.get("FB_PAGE_TOKEN","")
        fb_page_id = os.environ.get("FB_PAGE_ID","")
        if not fb_token:
            send_message(chat_id, "❌ FB_PAGE_TOKEN חסר")
            return
        send_message(chat_id, "⏳ מושך נתונים...")
        try:
            # משוך נתוני דף בסיסיים
            resp = requests.get(
                f"https://graph.facebook.com/v18.0/{fb_page_id}",
                params={
                    "fields": "name,fan_count,followers_count",
                    "access_token": fb_token
                },
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = f"""📊 <b>סטטיסטיקות פייסבוק:</b>

📄 דף: <b>{data.get('name','')}</b>
👍 לייקים: <b>{data.get('fan_count', 'N/A')}</b>
👥 עוקבים: <b>{data.get('followers_count', 'N/A')}</b>"""
                send_message(chat_id, msg)
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")

    elif cb_data == "social_stats_ig":
        ig_user_id = os.environ.get("IG_USER_ID","")
        fb_token = os.environ.get("FB_PAGE_TOKEN","")
        if not ig_user_id:
            send_message(chat_id, "❌ IG_USER_ID חסר")
            return
        send_message(chat_id, "⏳ מושך נתונים...")
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v18.0/{ig_user_id}",
                params={"fields": "followers_count,media_count,name", "access_token": fb_token},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = f"""📊 <b>סטטיסטיקות אינסטגרם:</b>

👤 חשבון: <b>{data.get('name','')}</b>
👥 עוקבים: <b>{data.get('followers_count', 'N/A')}</b>
📸 פוסטים: <b>{data.get('media_count', 'N/A')}</b>"""
                send_message(chat_id, msg)
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")

    elif cb_data == "social_delete_fb":
        draft["step"] = "social_delete_fb_input"
        send_message(chat_id, "🗑️ שלח לינק לפוסט בפייסבוק למחיקה:")

    elif cb_data == "social_delete_ig":
        send_message(chat_id, """⚠️ <b>אינסטגרם לא מאפשר מחיקה דרך API</b>

למחיקת הפוסט:
1. כנס ל-Creator Studio:
https://business.facebook.com/creatorstudio

2. בחר את חשבון האינסטגרם
3. מצא את הפוסט ומחק

או ישירות באפליקציית אינסטגרם → הפוסט → ⋯ → מחק""")

    elif cb_data == "social_recent_posts":
        fb_token = os.environ.get("FB_PAGE_TOKEN","")
        fb_page_id = os.environ.get("FB_PAGE_ID","")
        ig_user_id = os.environ.get("IG_USER_ID","")
        send_message(chat_id, "⏳ מושך פוסטים אחרונים...")
        msg = ""
        # פייסבוק
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v18.0/{fb_page_id}/posts",
                params={"fields": "id,message,created_time", "limit": 3, "access_token": fb_token},
                timeout=15
            )
            if resp.status_code == 200:
                posts = resp.json().get("data", [])
                if posts:
                    msg += "📘 <b>פייסבוק:</b>\n"
                    for p in posts:
                        msg += f"🆔 <code>{p['id']}</code>\n{p.get('message','')[:40]}...\n\n"
        except Exception as e:
            msg += f"❌ פייסבוק: {e}\n"
        # אינסטגרם
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
                params={"fields": "id,caption,timestamp", "limit": 3, "access_token": fb_token},
                timeout=15
            )
            if resp.status_code == 200:
                posts = resp.json().get("data", [])
                if posts:
                    msg += "📸 <b>אינסטגרם:</b>\n"
                    for p in posts:
                        msg += f"🆔 <code>{p['id']}</code>\n{p.get('caption','')[:40]}...\n\n"
        except Exception as e:
            msg += f"❌ אינסטגרם: {e}\n"
        send_message(chat_id, msg or "אין פוסטים.")

    elif cb_data in ("auto_share_fb", "auto_share_ig", "auto_share_all"):
        post_url = draft.get("last_post_url", "")
        post_title = draft.get("last_post_title", "")
        post_body = draft.get("body", "")
        post_images = [draft.get("main_image")] + draft.get("gallery", [])
        post_images = [img for img in post_images if img]  # הסר None
        
        import re
        # נקה HTML tags מהגוף
        clean_body = re.sub(r'<[^>]+>', '', post_body).strip()
        
        # פורמט: שורה ראשונה מודגשת (בפייסבוק) + גוף
        fb_text = f"{post_title}\n\n{clean_body}"
        ig_text = f"{post_title}\n\n{clean_body}"
        
        def _auto_share():
            # שלח הודעה אחת ועדכן אותה
            status_resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": "⏳ מפרסם ברשתות...", "parse_mode": "HTML"},
                timeout=10
            )
            msg_id = status_resp.json().get("result", {}).get("message_id") if status_resp.ok else None

            def update(text, markup=None):
                if msg_id:
                    edit_message(chat_id, msg_id, text, markup)
                else:
                    send_message(chat_id, text, markup)

            status_lines = []

            if cb_data in ("auto_share_fb", "auto_share_all"):
                update("⏳ מעלה לפייסבוק...")
                wm_images = [add_watermark(img) for img in post_images] if post_images else []
                if len(wm_images) > 1:
                    photo_ids = []
                    for img in wm_images[:10]:
                        resp = requests.post(
                            f"https://graph.facebook.com/v18.0/{os.environ.get('FB_PAGE_ID')}/photos",
                            data={"published": "false", "access_token": os.environ.get("FB_PAGE_TOKEN")},
                            files={"source": ("image.jpg", img, "image/jpeg")},
                            timeout=30
                        )
                        if resp.status_code == 200:
                            photo_ids.append({"media_fbid": resp.json()["id"]})
                    if photo_ids:
                        resp = requests.post(
                            f"https://graph.facebook.com/v18.0/{os.environ.get('FB_PAGE_ID')}/feed",
                            data={
                                "message": fb_text,
                                "access_token": os.environ.get("FB_PAGE_TOKEN"),
                                **{f"attached_media[{i}]": f'{{"media_fbid":"{pid["media_fbid"]}"}}' for i, pid in enumerate(photo_ids)}
                            },
                            timeout=30
                        )
                        ok = resp.status_code == 200
                        result = resp.json().get("id","") if ok else resp.text[:200]
                    else:
                        ok, result = post_to_facebook(fb_text)
                elif post_images:
                    ok, result = post_to_facebook(fb_text, wm_images[0] if wm_images else None)
                else:
                    ok, result = post_to_facebook(fb_text)

                if ok:
                    draft["last_fb_post_id"] = result
                    status_lines.append("✅ פייסבוק")
                else:
                    status_lines.append(f"❌ פייסבוק נכשל")
                update("\n".join(status_lines) or "⏳")

                if cb_data == "auto_share_fb":
                    return

            if cb_data in ("auto_share_ig", "auto_share_all"):
                update(("\n".join(status_lines) + "\n" if status_lines else "") + "⏳ מעלה לאינסטגרם...")
                if not post_images:
                    status_lines.append("⚠️ אינסטגרם – אין תמונה")
                    update("\n".join(status_lines))
                elif len(post_images) > 1:
                    ok, result = post_to_instagram_carousel(ig_text, [add_watermark(img) for img in post_images[:10]])
                else:
                    ok, result = post_to_instagram(ig_text, add_watermark(post_images[0]))

                if post_images:
                    print(f"IG ok={ok}, result={result}", flush=True)
                    if ok:
                        draft["last_ig_post_id"] = result
                        status_lines.append("✅ אינסטגרם")
                        update("\n".join(status_lines), {
                            "inline_keyboard": [[{"text": "📱 שתף לסטורי", "callback_data": f"ig_story_{result}"}]]
                        })
                    else:
                        status_lines.append(f"❌ אינסטגרם נכשל")
                        update("\n".join(status_lines), {
                            "inline_keyboard": [[{"text": "🔄 נסה שוב", "callback_data": "auto_share_ig"}]]
                        })
                    return

            update("\n".join(status_lines) if status_lines else "✅ הושלם")

        threading.Thread(target=_auto_share, daemon=True).start()

    elif cb_data == "share_social_post":
        post_url = draft.get("last_post_url", "")
        post_title = draft.get("last_post_title", "")
        draft["social_data"] = {
            "text_content": post_title,
            "link": post_url
        }
        draft["step"] = "social_content_platforms"
        _show_social_platforms(chat_id, draft["social_data"], "content")

    elif cb_data == "geresh_add":
        draft["step"] = "geresh_add_input"
        send_message(chat_id, f"➕ שלח מילה חדשה להוספה לרשימת הגרשיים\n(לדוגמה: נ״ך)")

    elif cb_data == "geresh_remove":
        keyboard = {"inline_keyboard": [[{"text": w, "callback_data": f"geresh_rm_{w}"}] for w in GERESH_WORDS]}
        keyboard["inline_keyboard"].append([{"text": "❌ ביטול", "callback_data": "publish_cancel"}])
        send_message(chat_id, "➖ בחר מילה להסרה:", keyboard)

    elif cb_data.startswith("geresh_rm_"):
        word = cb_data.replace("geresh_rm_", "")
        if word in GERESH_WORDS:
            GERESH_WORDS.remove(word)
            send_message(chat_id, f"✅ המילה <b>{word}</b> הוסרה!")
        else:
            send_message(chat_id, "❌ מילה לא נמצאה.")

    elif cb_data == "edit_prompt":
        from bot import build_prompt
        send_message(chat_id, "✏️ <b>עריכת פרומפט Gemini</b>\n\nשלח את הפרומפט החדש (טקסט ארוך).\n\n⚠️ שים לב: הפרומפט חייב לכלול {text} בסוף!\n\nהפרומפט הנוכחי מוגדר בקוד.")
        draft["step"] = "edit_prompt_input"

    elif cb_data == "share_twitter":
        post_url = draft.get("last_post_url", "")
        post_title = draft.get("last_post_title", "")
        send_message(chat_id, "⏳ מפרסם בטוויטר...")
        success, result = post_to_twitter(post_title, post_url)
        if success:
            send_message(chat_id, f"✅ פורסם בטוויטר!", get_menu(user_id))
        else:
            send_message(chat_id, f"❌ שגיאה בטוויטר: {result}", get_menu(user_id))
        drafts[user_id] = {"step": "idle", "gallery": []}

    elif cb_data == "publish_done":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "✅ סיום!", get_menu(user_id))

    elif cb_data == "edit_done":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "✅ הכתבה עודכנה בהצלחה!", get_menu(user_id))

    elif cb_data == "edit_title":
        draft["step"] = "edit_field_value"
        draft["edit_field"] = "title"
        send_message(chat_id, "שלח את הכותרת החדשה:")

    elif cb_data == "edit_subtitle":
        draft["step"] = "edit_field_value"
        draft["edit_field"] = "subtitle"
        send_message(chat_id, "שלח את כותרת המשנה החדשה:")

    elif cb_data == "edit_red_title":
        draft["step"] = "edit_field_value"
        draft["edit_field"] = "red_title"
        send_message(chat_id, "שלח את הכותרת האדומה החדשה:")

    elif cb_data == "edit_content":
        draft["step"] = "edit_field_value"
        draft["edit_field"] = "content"
        send_message(chat_id, "שלח את התוכן החדש:")

    elif cb_data == "edit_image":
        draft["step"] = "edit_image_upload"
        send_message(chat_id, "שלח את התמונה הראשית החדשה:")

    elif cb_data == "edit_gallery":
        draft["step"] = "edit_gallery_upload"
        send_message(chat_id, "שלח תמונות, PDF, או קובץ שמע להוספה.\nכשסיימת שלח /done:")

    elif cb_data == "edit_video_to_vimeo":
        pending = draft.get("edit_videos_pending", [])
        _add_videos_to_post(chat_id, user_id, draft, drafts, pending, "vimeo")

    elif cb_data == "edit_video_to_youtube":
        pending = draft.get("edit_videos_pending", [])
        _add_videos_to_post(chat_id, user_id, draft, drafts, pending, "youtube")

    elif cb_data == "edit_video_to_all":
        pending = draft.get("edit_videos_pending", [])
        _add_videos_to_post(chat_id, user_id, draft, drafts, pending, "all")

    elif cb_data == "edit_video":
        draft["step"] = "edit_video_input"
        draft["edit_videos_pending"] = []
        send_message(chat_id, "🎬 <b>הוספת סרטון לכתבה</b>\n\nשלח קובץ וידאו, לינק Vimeo, או לינק YouTube.\nשלח /done כשסיימת לשלוח:", {
            "inline_keyboard": [[{"text": "❌ ביטול", "callback_data": "edit_done"}]]
        })

    elif cb_data == "delete_yes":
        post_id = draft.get("delete_id")
        r = requests.delete(f"{WP_URL}/posts/{post_id}",
                           auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code in (200, 201):
            send_message(chat_id, "✅ הכתבה נמחקה!", get_menu(user_id))
        else:
            send_message(chat_id, f"❌ שגיאה: {r.text[:200]}")
        drafts[user_id] = {"step": "idle", "gallery": []}

    elif cb_data == "delete_no":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ המחיקה בוטלה.", get_menu(user_id))

def get_recent_posts(status="publish"):
    try:
        resp = requests.get(
            f"{WP_URL}/posts?per_page=5&status={status}&orderby=date&order=desc",
            auth=(WP_USER, WP_PASSWORD), timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"שגיאה כתבות אחרונות: {e}")
    return []

def keep_alive():
    """שולח ping לבוט כל 10 דקות כדי שלא יירדם ב-Render"""
    while True:
        time.sleep(600)
        try:
            requests.get("https://chabad-bot.onrender.com", timeout=10)
            print("✅ Keep-alive ping", flush=True)
        except Exception as _e:
            print(f"שגיאה: {_e}", flush=True)

GA_PROPERTY_ID = os.environ.get("GA_PROPERTY_ID", "")
GA_SERVICE_ACCOUNT_JSON = os.environ.get("GA_SERVICE_ACCOUNT_JSON", "")

def get_analytics_token():
    """מקבל token לגישה ל-Google Analytics"""
    if not GA_SERVICE_ACCOUNT_JSON:
        return None
    try:
        import json as json_lib
        import time as time_mod
        import base64
        import hashlib
        import hmac as hmac_lib

        sa = json_lib.loads(GA_SERVICE_ACCOUNT_JSON)
        
        # בנה JWT
        header = base64.urlsafe_b64encode(json_lib.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
        now = int(time_mod.time())
        payload = base64.urlsafe_b64encode(json_lib.dumps({
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/analytics.readonly",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": now + 3600,
            "iat": now
        }).encode()).rstrip(b'=').decode()
        
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        
        private_key = serialization.load_pem_private_key(
            sa["private_key"].encode(),
            password=None,
            backend=default_backend()
        )
        
        signing_input = f"{header}.{payload}".encode()
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        sig = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
        
        jwt = f"{header}.{payload}.{sig}"
        
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt
        }, timeout=10)
        
        if resp.status_code == 200:
            return resp.json()["access_token"]
    except Exception as e:
        print(f"שגיאה Analytics token: {e}", flush=True)
    return None

def get_analytics_data(period="7daysAgo", limit=5):
    """מושך נתוני Analytics"""
    token = get_analytics_token()
    if not token:
        return None
    try:
        resp = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{GA_PROPERTY_ID}:runReport",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "dateRanges": [{"startDate": period, "endDate": "today"}],
                "metrics": [{"name": "screenPageViews"}],
                "dimensions": [{"name": "pageTitle"}, {"name": "pagePath"}],
                "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
                "limit": limit,
                "dimensionFilter": {
                    "filter": {
                        "fieldName": "pagePath",
                        "stringFilter": {"matchType": "CONTAINS", "value": "/archives/"}
                    }
                }
            },
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"שגיאה Analytics: {resp.status_code} {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"שגיאה Analytics data: {e}", flush=True)
    return None

def get_analytics_totals(period="7daysAgo"):
    """מושך סה"כ כניסות לאתר"""
    token = get_analytics_token()
    if not token:
        return None
    try:
        resp = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{GA_PROPERTY_ID}:runReport",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "dateRanges": [{"startDate": period, "endDate": "today"}],
                "metrics": [
                    {"name": "sessions"},
                    {"name": "screenPageViews"},
                    {"name": "activeUsers"}
                ]
            },
            timeout=15
        )
        if resp.status_code == 200:
            rows = resp.json().get("rows", [])
            if rows:
                vals = rows[0]["metricValues"]
                return {
                    "sessions": vals[0]["value"],
                    "pageviews": vals[1]["value"],
                    "users": vals[2]["value"]
                }
    except Exception as e:
        print(f"שגיאה Analytics totals: {e}", flush=True)
    return None

def get_analytics_page(url, period="7daysAgo"):
    """מושך נתוני כניסות לכתבה ספציפית"""
    token = get_analytics_token()
    if not token:
        return None
    try:
        # חלץ path מה-URL
        from urllib.parse import urlparse
        path = urlparse(url).path
        
        resp = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{GA_PROPERTY_ID}:runReport",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "dateRanges": [{"startDate": period, "endDate": "today"}],
                "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
                "dimensions": [{"name": "pageTitle"}, {"name": "pagePath"}],
                "dimensionFilter": {
                    "filter": {
                        "fieldName": "pagePath",
                        "stringFilter": {"matchType": "EXACT", "value": path}
                    }
                }
            },
            timeout=15
        )
        if resp.status_code == 200:
            rows = resp.json().get("rows", [])
            if rows:
                return {
                    "title": rows[0]["dimensionValues"][0]["value"],
                    "pageviews": rows[0]["metricValues"][0]["value"],
                    "users": rows[0]["metricValues"][1]["value"]
                }
    except Exception as e:
        print(f"שגיאה Analytics page: {e}", flush=True)
    return None


    """מחזיר סטטוס מערכת המייל"""
    status = "✅ פעילה" if email_system["active"] else "⏸️ מושהית"
    interval_min = email_system["interval"] // 60
    senders = "\n".join([f"• {s}" for s in email_system["allowed_senders"]])
    last = time.strftime("%H:%M", time.localtime(email_system["last_check"])) if email_system["last_check"] else "טרם נבדק"
    return f"""📧 <b>מערכת מייל</b>

<b>סטטוס:</b> {status}
<b>בדיקה כל:</b> {interval_min} דקות
<b>בדיקה אחרונה:</b> {last}
<b>כתובות מורשות:</b>
{senders}"""

def post_to_facebook(text, image_bytes=None, link=None):
    """פרסום לפייסבוק – דורש FB_PAGE_TOKEN"""
    fb_token = os.environ.get("FB_PAGE_TOKEN", "")
    fb_page_id = os.environ.get("FB_PAGE_ID", "")
    if not fb_token or not fb_page_id:
        return False, "❌ FB_PAGE_TOKEN או FB_PAGE_ID חסרים ב-Render"
    try:
        msg = text
        if image_bytes:
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{fb_page_id}/photos",
                data={"caption": msg, "access_token": fb_token},
                files={"source": ("image.jpg", image_bytes, "image/jpeg")},
                timeout=30
            )
        else:
            post_data = {"message": msg, "access_token": fb_token}
            if link:
                post_data["link"] = link
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{fb_page_id}/feed",
                data=post_data,
                timeout=15
            )
        if resp.status_code == 200:
            return True, resp.json().get("id", "")
        print(f"FB error: {resp.text[:300]}", flush=True)
        return False, resp.text[:200]
    except Exception as e:
        return False, str(e)

def resize_for_instagram(image_bytes):
    """מכין תמונה לאינסטגרם"""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        w, h = img.size
        ratio = w / h
        if ratio > 1.91:
            new_w = int(h * 1.91)
            img = img.crop(((w-new_w)//2, 0, (w+new_w)//2, h))
        elif ratio < 0.8:
            new_h = int(w / 0.8)
            img = img.crop((0, (h-new_h)//2, w, (h+new_h)//2))
        w, h = img.size
        if w < 320:
            img = img.resize((320, int(320*h/w)), Image.LANCZOS)
        if w > 1440:
            img = img.resize((1440, int(1440*h/w)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format='JPEG', quality=90)
        return out.getvalue()
    except Exception as e:
        print(f"שגיאה resize: {e}", flush=True)
        return image_bytes

def add_watermark(image_bytes):
    """מוסיף ווטרמארק לתמונה"""
    print(f"🖼 add_watermark: enabled={watermark_settings.get('enabled')}, mode={watermark_settings.get('mode')}", flush=True)
    if not watermark_settings.get("enabled"):
        return image_bytes
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        mode = watermark_settings.get("mode","text")
        if mode == "logo" and watermark_settings.get("logo_bytes"):
            logo = Image.open(io.BytesIO(watermark_settings["logo_bytes"])).convert("RGBA")
            logo_w = int(img.width * 0.15)
            logo_h = int(logo.height * logo_w / logo.width)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            px = int(img.width * watermark_settings.get("pos_x",95)/100) - logo_w
            py = int(img.height * watermark_settings.get("pos_y",95)/100) - logo_h
            overlay.paste(logo, (max(0,px), max(0,py)), logo)
        else:
            font_size = watermark_settings.get("font_size", 40)
            font_paths = {
                "default": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
            }
            try:
                font = ImageFont.truetype(font_paths.get(watermark_settings.get("font","bold"), font_paths["bold"]), font_size)
            except:
                font = ImageFont.load_default()
            text = watermark_settings.get("text","עדכוני חב״ד")
            bbox = draw.textbbox((0,0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            px = max(0, int(img.width * watermark_settings.get("pos_x",95)/100) - tw)
            py = max(0, int(img.height * watermark_settings.get("pos_y",95)/100) - th)
            def hex_to_rgba(h, a=255):
                h = h.lstrip('#')
                return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16), a)
            bg = watermark_settings.get("bg_color","#000000")
            if bg != "none":
                try:
                    bg_rgba = hex_to_rgba(bg, watermark_settings.get("bg_opacity",140))
                except:
                    bg_rgba = (0,0,0,140)
                draw.rectangle([px-8, py-8, px+tw+8, py+th+8], fill=bg_rgba)
            try:
                text_rgba = hex_to_rgba(watermark_settings.get("text_color","#FFFFFF"))
            except:
                text_rgba = (255,255,255,255)
            draw.text((px,py), text, font=font, fill=text_rgba)
        result = Image.alpha_composite(img, overlay)
        out = io.BytesIO()
        result.convert("RGB").save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception as e:
        print(f"שגיאה watermark: {e}", flush=True)
        return image_bytes

def create_story_template(post_image_bytes, title="", subtitle=""):
    """בונה תבנית סטורי 1080x1920 עם מסגרת כחול-לבן"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        W, H = 1080, 1920
        BLUE_DARK  = "#1A3A6B"
        BLUE_MID   = "#2255A4"
        BLUE_LIGHT = "#4A80D0"
        WHITE      = "#FFFFFF"
        GOLD       = "#D4AF37"

        # רקע כחול כהה
        story = Image.new("RGB", (W, H), BLUE_DARK)
        draw = ImageDraw.Draw(story)

        # פס עליון כחול בהיר
        draw.rectangle([0, 0, W, 180], fill=BLUE_MID)

        # לוגו / שם האתר בפס עליון
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            font_sub   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except:
            font_title = font_sub = font_small = ImageFont.load_default()

        site_name = "עדכוני חב״ד"
        bbox = draw.textbbox((0,0), site_name, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw)//2, 50), site_name, font=font_title, fill=WHITE)

        # קו זהב מתחת לפס
        draw.rectangle([0, 180, W, 190], fill=GOLD)

        # תמונת הפוסט במרכז – מרובעת
        if post_image_bytes:
            post_img = Image.open(io.BytesIO(post_image_bytes)).convert("RGB")
            # חתוך לריבוע
            pw, ph = post_img.size
            side = min(pw, ph)
            left = (pw - side) // 2
            top  = (ph - side) // 2
            post_img = post_img.crop((left, top, left+side, top+side))
            # שנה גודל
            img_size = 940
            post_img = post_img.resize((img_size, img_size), Image.LANCZOS)
            # מרכז אנכי
            img_y = 250
            story.paste(post_img, ((W - img_size)//2, img_y))
            # מסגרת לבנה סביב התמונה
            ix = (W - img_size)//2
            draw.rectangle([ix-6, img_y-6, ix+img_size+6, img_y+img_size+6],
                          outline=WHITE, width=6)

        # כותרת מתחת לתמונה
        text_y = 250 + 940 + 40
        if title:
            # שבור לשורות
            words = title.split()
            lines = []
            line = ""
            for word in words:
                test = (line + " " + word).strip()
                bbox = draw.textbbox((0,0), test, font=font_sub)
                if bbox[2] - bbox[0] > W - 80:
                    if line:
                        lines.append(line)
                    line = word
                else:
                    line = test
            if line:
                lines.append(line)

            for l in lines[:3]:
                bbox = draw.textbbox((0,0), l, font=font_sub)
                tw = bbox[2] - bbox[0]
                draw.text(((W-tw)//2, text_y), l, font=font_sub, fill=WHITE)
                text_y += 55

        # פס תחתון
        draw.rectangle([0, H-160, W, H], fill=BLUE_MID)
        draw.rectangle([0, H-160, W, H-150], fill=GOLD)

        # טקסט "לפוסט המלא ←" בפס תחתון
        cta = "לפוסט המלא ←"
        bbox = draw.textbbox((0,0), cta, font=font_sub)
        tw = bbox[2] - bbox[0]
        draw.text(((W-tw)//2, H-120), cta, font=font_sub, fill=WHITE)

        output = io.BytesIO()
        story.save(output, format="JPEG", quality=92)
        return output.getvalue()

    except Exception as e:
        print(f"שגיאה story template: {e}", flush=True)
        return post_image_bytes
    """מוסיף ווטרמארק לתמונה לפי הגדרות watermark_settings"""
    if not watermark_settings.get("enabled"):
        return image_bytes
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        mode = watermark_settings.get("mode", "text")

        if mode == "logo" and watermark_settings.get("logo_bytes"):
            # מצב לוגו
            logo = Image.open(io.BytesIO(watermark_settings["logo_bytes"])).convert("RGBA")
            logo_w = int(img.width * 0.15)
            logo_h = int(logo.height * logo_w / logo.width)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            px = int(img.width * watermark_settings.get("pos_x", 95) / 100) - logo_w
            py = int(img.height * watermark_settings.get("pos_y", 95) / 100) - logo_h
            overlay.paste(logo, (max(0,px), max(0,py)), logo)
        else:
            # מצב טקסט
            font_size = watermark_settings.get("font_size", 40)
            font_paths = {
                "default": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
            }
            font_path = font_paths.get(watermark_settings.get("font", "bold"), font_paths["bold"])
            try:
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()

            text = watermark_settings.get("text", "עדכוני חב״ד")
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # מיקום לפי אחוזים
            px = int(img.width * watermark_settings.get("pos_x", 95) / 100) - text_w
            py = int(img.height * watermark_settings.get("pos_y", 95) / 100) - text_h
            px = max(0, min(px, img.width - text_w))
            py = max(0, min(py, img.height - text_h))

            # המר hex לRGB
            def hex_to_rgb(hex_color, alpha=255):
                hex_color = hex_color.lstrip('#')
                r, g, b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
                return (r, g, b, alpha)

            # רקע
            bg_color = watermark_settings.get("bg_color", "#000000")
            bg_opacity = watermark_settings.get("bg_opacity", 140)
            if bg_color != "none":
                padding = 8
                try:
                    bg_rgba = hex_to_rgb(bg_color, bg_opacity)
                except:
                    bg_rgba = (0, 0, 0, bg_opacity)
                draw.rectangle(
                    [px-padding, py-padding, px+text_w+padding, py+text_h+padding],
                    fill=bg_rgba
                )

            # טקסט
            text_color = watermark_settings.get("text_color", "#FFFFFF")
            try:
                text_rgba = hex_to_rgb(text_color)
            except:
                text_rgba = (255, 255, 255, 255)
            draw.text((px, py), text, font=font, fill=text_rgba)

        result = Image.alpha_composite(img, overlay)
        output = io.BytesIO()
        result.convert("RGB").save(output, format="JPEG", quality=90)
        return output.getvalue()
    except Exception as e:
        print(f"שגיאה watermark: {e}", flush=True)
        return image_bytes
    """מכין תמונה לאינסטגרם – JPEG, יחס 4:5, מקסימום 1440px"""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        # המר ל-RGB אם צריך
        if img.mode != 'RGB':
            img = img.convert('RGB')
        w, h = img.size
        # חתוך ליחס 4:5 אם צריך
        target_ratio = 4 / 5
        current_ratio = w / h
        if current_ratio > 1.91:
            # רחב מדי – חתוך
            new_w = int(h * 1.91)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        elif current_ratio < 0.8:
            # גבוה מדי – חתוך
            new_h = int(w / 0.8)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))
        # הגדל אם קטן מדי
        w, h = img.size
        if w < 320:
            img = img.resize((320, int(320 * h / w)), Image.LANCZOS)
        # הקטן אם גדול מדי
        if w > 1440:
            img = img.resize((1440, int(1440 * h / w)), Image.LANCZOS)
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=90)
        return output.getvalue()
    except Exception as e:
        print(f"שגיאה resize: {e}", flush=True)
        return image_bytes
    """פרסום קרוסלה לאינסטגרם עם מספר תמונות"""
    ig_user_id = os.environ.get("IG_USER_ID", "")
    fb_token = os.environ.get("FB_PAGE_TOKEN", "")
    if not ig_user_id or not fb_token:
        return False, "IG_USER_ID או FB_PAGE_TOKEN חסרים"
    try:
        children = []
        for img in images_list[:10]:
            # התאם לאינסטגרם
            img = resize_for_instagram(img)
            # העלה לוורדפרס קודם כדי לקבל URL ציבורי
            _, img_url = upload_image_to_wp(img, "ig_post.jpg")
            if not img_url:
                continue
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
                data={
                    "image_url": img_url,
                    "is_carousel_item": "true",
                    "access_token": fb_token
                },
                timeout=30
            )
            print(f"IG carousel item: {resp.status_code} {resp.text[:100]}", flush=True)
            if resp.status_code == 200:
                children.append(resp.json().get("id"))
        if not children:
            return False, "לא הצלחתי להעלות תמונות לאינסטגרם"
        carousel_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
            data={
                "media_type": "CAROUSEL",
                "caption": caption,
                "children": ",".join(children),
                "access_token": fb_token
            },
            timeout=30
        )
        if carousel_resp.status_code != 200:
            return False, carousel_resp.text[:200]
        carousel_id = carousel_resp.json().get("id")
        publish_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
            data={"creation_id": carousel_id, "access_token": fb_token},
            timeout=15
        )
        if publish_resp.status_code == 200:
            return True, publish_resp.json().get("id")
        return False, publish_resp.text[:200]
    except Exception as e:
        return False, str(e)

def get_email_status():
    """מחזיר סטטוס מערכת המייל"""
    status = "✅ פעילה" if email_system["active"] else "⏸️ מושהית"
    interval_min = email_system["interval"] // 60
    senders = "\n".join([f"• {s}" for s in email_system["allowed_senders"]]) or "אין"
    last = time.strftime("%H:%M", time.localtime(email_system["last_check"])) if email_system["last_check"] else "טרם נבדק"
    return f"""📧 <b>מערכת מייל</b>

<b>סטטוס:</b> {status}
<b>בדיקה כל:</b> {interval_min} דקות
<b>בדיקה אחרונה:</b> {last}
<b>כתובות מורשות:</b>
{senders}"""

def post_to_instagram_carousel(caption, images_list):
    """פרסום קרוסלה לאינסטגרם עם מספר תמונות"""
    ig_user_id = os.environ.get("IG_USER_ID", "")
    fb_token = os.environ.get("FB_PAGE_TOKEN", "")
    if not ig_user_id or not fb_token:
        return False, "IG_USER_ID או FB_PAGE_TOKEN חסרים"
    try:
        children = []
        for img in images_list[:10]:
            img = resize_for_instagram(img)
            _, img_url = upload_image_to_wp(img, "ig_post.jpg")
            if not img_url:
                continue
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
                data={"image_url": img_url, "is_carousel_item": "true", "access_token": fb_token},
                timeout=30
            )
            if resp.status_code == 200:
                children.append(resp.json().get("id"))
        if not children:
            return False, "לא הצלחתי להעלות תמונות"
        carousel_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
            data={"media_type": "CAROUSEL", "caption": caption, "children": ",".join(children), "access_token": fb_token},
            timeout=30
        )
        if carousel_resp.status_code != 200:
            return False, carousel_resp.text[:200]
        carousel_id = carousel_resp.json().get("id")
        pub_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
            data={"creation_id": carousel_id, "access_token": fb_token},
            timeout=15
        )
        if pub_resp.status_code == 200:
            return True, pub_resp.json().get("id")
        return False, pub_resp.text[:200]
    except Exception as e:
        return False, str(e)

def post_to_instagram_story(media_id):
    """משתף פוסט קיים לסטורי אינסטגרם"""
    ig_user_id = os.environ.get("IG_USER_ID", "")
    fb_token = os.environ.get("FB_PAGE_TOKEN", "")
    if not ig_user_id or not fb_token:
        return False, "חסרים פרטי אינסטגרם"
    try:
        # צור container לסטורי
        resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
            data={
                "media_type": "STORIES",
                "source_type": "post",
                "source_media_id": media_id,
                "access_token": fb_token
            },
            timeout=30
        )
        if resp.status_code != 200:
            return False, resp.text[:200]
        container_id = resp.json().get("id")
        # פרסם
        pub_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": fb_token},
            timeout=15
        )
        if pub_resp.status_code == 200:
            return True, pub_resp.json().get("id","")
        return False, pub_resp.text[:200]
    except Exception as e:
        return False, str(e)

def post_to_instagram(text, image_bytes):
    """פרסום לאינסטגרם – דורש IG_USER_ID ו-FB_PAGE_TOKEN"""
    ig_user_id = os.environ.get("IG_USER_ID", "")
    fb_token = os.environ.get("FB_PAGE_TOKEN", "")
    if not ig_user_id or not fb_token:
        return False, "IG_USER_ID או FB_PAGE_TOKEN חסרים"
    try:
        image_bytes = resize_for_instagram(image_bytes)
        _, img_url = upload_image_to_wp(image_bytes, "ig_post.jpg")
        if not img_url:
            return False, "לא הצלחתי להעלות תמונה"
        create_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
            data={"image_url": img_url, "caption": text, "access_token": fb_token},
            timeout=30
        )
        print(f"IG media: {create_resp.status_code} {create_resp.text[:100]}", flush=True)
        if create_resp.status_code != 200:
            return False, create_resp.text[:200]
        media_id = create_resp.json().get("id")
        # המתן עד שהעיבוד מסתיים
        for attempt in range(10):
            time.sleep(3)
            status_resp = requests.get(
                f"https://graph.facebook.com/v18.0/{media_id}",
                params={"fields": "status_code", "access_token": fb_token},
                timeout=10
            )
            if status_resp.status_code == 200:
                status = status_resp.json().get("status_code", "")
                print(f"IG status: {status}", flush=True)
                if status == "FINISHED":
                    break
                elif status == "ERROR":
                    return False, "שגיאה בעיבוד התמונה"
        pub_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
            data={"creation_id": media_id, "access_token": fb_token},
            timeout=15
        )
        if pub_resp.status_code == 200:
            return True, pub_resp.json().get("id", "")
        return False, pub_resp.text[:200]
    except Exception as e:
        return False, str(e)

def post_to_telegram_channel(text, image_bytes=None):
    """שליחה לערוץ טלגרם"""
    try:
        if image_bytes:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": text, "parse_mode": "HTML"},
                files={"photo": ("img.jpg", image_bytes, "image/jpeg")},
                timeout=15
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
        return resp.status_code in (200, 201), ""
    except Exception as e:
        return False, str(e)

def upload_to_tiktok(video_bytes, title, hashtags=""):
    """העלאה לטיקטוק – דורש TIKTOK_TOKEN"""
    tiktok_token = os.environ.get("TIKTOK_TOKEN", "")
    if not tiktok_token:
        return False, "❌ TIKTOK_TOKEN חסר ב-Render"
    # TikTok API v2 - Content Posting
    try:
        # שלב 1: init upload
        init_resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {tiktok_token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": title,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": len(video_bytes),
                    "chunk_size": len(video_bytes),
                    "total_chunk_count": 1
                }
            },
            timeout=30
        )
        if init_resp.status_code != 200:
            return False, init_resp.text[:200]
        data = init_resp.json().get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        # שלב 2: העלה
        up_resp = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(video_bytes)),
                "Content-Range": f"bytes 0-{len(video_bytes)-1}/{len(video_bytes)}"
            },
            data=video_bytes,
            timeout=120
        )
        if up_resp.status_code in (200, 201, 204):
            return True, publish_id
        return False, up_resp.text[:200]
    except Exception as e:
        return False, str(e)

def show_distribution_menu(chat_id, draft, post_url="", post_title=""):
    """מציג תפריט הפצה לרשתות חברתיות אחרי פרסום"""
    msg = f"📢 <b>הפצה לרשתות חברתיות</b>"
    if post_title:
        msg += f"\n<b>{post_title}</b>"
    send_message(chat_id, msg, {
        "inline_keyboard": [
            [{"text": "📤 הכל ביחד", "callback_data": "dist_all"}],
            [{"text": "📘 פייסבוק", "callback_data": "dist_facebook"},
             {"text": "📸 אינסטגרם", "callback_data": "dist_instagram"}],
            [{"text": "📱 טלגרם", "callback_data": "dist_telegram"},
             {"text": "🐦 טוויטר", "callback_data": "dist_twitter"}],
            [{"text": "✅ סיום", "callback_data": "publish_done"}]
        ]
    })


    """מחזיר סטטוס מערכת המייל"""
    status = "✅ פעילה" if email_system["active"] else "⏸️ מושהית"
    interval_min = email_system["interval"] // 60
    senders = "\n".join([f"• {s}" for s in email_system["allowed_senders"]]) or "אין"
    last = time.strftime("%H:%M", time.localtime(email_system["last_check"])) if email_system["last_check"] else "טרם נבדק"
    return f"""📧 <b>מערכת מייל</b>

<b>סטטוס:</b> {status}
<b>בדיקה כל:</b> {interval_min} דקות
<b>בדיקה אחרונה:</b> {last}
<b>כתובות מורשות:</b>
{senders}"""

def check_emails():
    """בודק את תיבת הדואר ומטפל במיילים חדשים"""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return
    # אם יש מייל ממתין לאישור – לא מביא חדשים
    if email_system.get("pending_email"):
        return
    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header
        from datetime import datetime, timezone

        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASSWORD)
        mail.select("inbox")

        # רק מיילים שלא נקראו שהגיעו אחרי שהבוט עלה
        _, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        for eid in email_ids:
            if eid in email_system["seen_ids"]:
                continue

            _, msg_data = mail.fetch(eid, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])

            # סמן כנקרא
            mail.store(eid, '+FLAGS', '\\Seen')
            email_system["seen_ids"].add(eid)

            # חלץ כותרת
            subject_raw = msg.get("Subject", "")
            subject = decode_header(subject_raw)[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode("utf-8", errors="ignore")

            # חלץ שולח
            sender = msg.get("From", "")
            sender_email = sender.split("<")[-1].replace(">", "").strip().lower()

            # בדוק אם השולח מורשה
            if sender_email not in [s.lower() for s in email_system["allowed_senders"]]:
                continue

            # חלץ תוכן
            body = ""
            images = []
            videos = []

            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="ignore")
                elif ctype.startswith("image/"):
                    images.append(part.get_payload(decode=True))
                elif ctype.startswith("video/"):
                    videos.append(part.get_payload(decode=True))

            # זיהוי כותרות מיוחדות
            if "הוספת תמונות" in subject or "הוספת תמונה" in subject:
                email_system["pending_email"] = {
                    "type": "add_images",
                    "images": images,
                    "videos": videos
                }
                send_message(SUPER_ADMIN_ID,
                    f"📧 <b>מייל חדש: הוספת תמונות</b>\n"
                    f"משולח: {sender_email}\n"
                    f"תמונות: {len(images)}\n\n"
                    f"שלח לינק לכתבה שאליה להוסיף:", {
                    "inline_keyboard": [[
                        {"text": "❌ בטל", "callback_data": "email_cancel"}
                    ]]
                })

            elif "הוספת סרטון" in subject or "הוספת וידאו" in subject:
                email_system["pending_email"] = {
                    "type": "add_video",
                    "videos": videos
                }
                send_message(SUPER_ADMIN_ID,
                    f"📧 <b>מייל חדש: הוספת סרטון</b>\n"
                    f"משולח: {sender_email}\n\n"
                    f"שלח לינק לכתבה שאליה להוסיף:", {
                    "inline_keyboard": [[
                        {"text": "❌ בטל", "callback_data": "email_cancel"}
                    ]]
                })

            else:
                # מייל רגיל – שאל אם להכין כתבה
                email_system["pending_email"] = {
                    "type": "article",
                    "subject": subject,
                    "body": body,
                    "images": images,
                    "videos": videos
                }
                preview = body[:200] + "..." if len(body) > 200 else body
                send_message(SUPER_ADMIN_ID,
                    f"📧 <b>מייל חדש מ-{sender_email}</b>\n"
                    f"<b>כותרת:</b> {subject}\n"
                    f"<b>תמונות:</b> {len(images)} | <b>סרטונים:</b> {len(videos)}\n\n"
                    f"<b>תוכן:</b>\n{preview}\n\n"
                    f"האם להכין כתבה?", {
                    "inline_keyboard": [[
                        {"text": "✅ כן, הכן כתבה", "callback_data": "email_approve"},
                        {"text": "❌ לא", "callback_data": "email_reject"}
                    ]]
                })

            # עצור אחרי מייל אחד – המתן לאישור
            break

        mail.logout()
        email_system["last_check"] = time.time()

    except Exception as e:
        print(f"שגיאה בדיקת מייל: {e}", flush=True)

def email_monitor_loop():
    """לולאת בדיקת מייל ברקע"""
    while True:
        try:
            if email_system["active"]:
                check_emails()
            time.sleep(email_system["interval"])
        except Exception as e:
            print(f"שגיאה לולאת מייל: {e}", flush=True)
            time.sleep(60)

def auto_select_categories(title, body):
    """בוחר קטגוריות אוטומטית לפי תוכן הכתבה"""
    prompt = f"""בחר קטגוריות לכתבה הבאה לפי הכללים:

כלל 1: בחר קטגוריית על אחת בלבד (לא שתיים):
  - אם מוזכרת מדינה/עיר מחוץ לישראל → חב"ד בעולם (id:26)
  - אם מוזכר יישוב בישראל → חב"ד בארץ (id:11)  
  - אחרת → חדשות (id:25)
כלל 2: הוסף קטגוריית משנה אחת בלבד אם מתאימה
כלל 3: סה"כ לא יותר מ-2 קטגוריות

קטגוריות:
חב"ד בארץ(11): ירושלים(52), כפר חב"ד(45), לוד(50), צפת(51), קריית מלאכי(49)
חב"ד בעולם(26): אירופה(48)>אוקראינה(1087),אנגליה(1090),בלגיה(1091),צרפת(1089),רוסיה(1088) | ארה"ב(47), קראון הייטס(46)
חדשות(25): ברוך דיין האמת(62), דבר מלכות(1083), הפינה השבועית(63), זכרון להולכים(1084), חסידים מספרים(1085), מבצעים(1086), פוליטיקה(24)

כותרת: {title}
תוכן: {body[:400]}

החזר JSON בלבד:
{{"categories":[id1,id2],"category_names":["שם1","שם2"]}}"""

    try:
        # שלח ישירות ל-Gemini בלי build_prompt
        if GEMINI_API_KEY:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15
            )
            if resp.status_code == 200:
                result_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = clean_json_string(result_text)
                if parsed and "categories" in parsed:
                    return parsed["categories"], parsed["category_names"]
    except Exception as e:
        print(f"שגיאה קטגוריות: {e}", flush=True)
    return [25], ["חדשות"]


    """מחזיר סטטוס מערכת המייל"""
    status = "✅ פעילה" if email_system["active"] else "⏸️ מושהית"
    interval_min = email_system["interval"] // 60
    senders = "\n".join([f"• {s}" for s in email_system["allowed_senders"]])
    last = time.strftime("%H:%M", time.localtime(email_system["last_check"])) if email_system["last_check"] else "טרם נבדק"
    return f"""📧 <b>מערכת מייל</b>

<b>סטטוס:</b> {status}
<b>בדיקה כל:</b> {interval_min} דקות
<b>בדיקה אחרונה:</b> {last}
<b>כתובות מורשות:</b>
{senders}"""

def main():
    global offset
    print("🚀 בוט חבד מתחיל!", flush=True)
    load_drafts()

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands",
            json={"commands": [
                {"command": "new", "description": "✍️ כתבה חדשה"},
                {"command": "mazaltov", "description": "🎉 מזל טוב"},
                {"command": "cancel", "description": "❌ ביטול"}
            ]},
            timeout=10
        )
    except Exception as _e:
        print(f"שגיאה: {_e}", flush=True)
    
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    print("🌐 שרת HTTP פועל", flush=True)

    # הפעל מוניטור מייל
    if EMAIL_USER and EMAIL_PASSWORD:
        t_email = threading.Thread(target=email_monitor_loop, daemon=True)
        t_email.start()
        print("📧 מוניטור מייל פועל", flush=True)
    
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 0},
                timeout=10
            )
            data = resp.json()
            
            # טיפול ב-409 – instance כפול, ממתין
            if not data.get("ok") and data.get("error_code") == 409:
                time.sleep(5)
                continue
            
            updates = data.get("result", [])
            
            if not updates:
                time.sleep(1)
                continue
            
            for update in updates:
                offset = update["update_id"] + 1
                uid = update["update_id"]
                
                if uid in processed_updates:
                    continue
                processed_updates.add(uid)
                if len(processed_updates) > 200:
                    processed_updates.clear()
                
                print(f"עדכון: {uid}", flush=True)
                
                if "message" in update:
                    try:
                        handle_message(update["message"])
                    except Exception as e:
                        print(f"שגיאה handle_message: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                elif "callback_query" in update:
                    try:
                        handle_callback(update["callback_query"])
                    except Exception as e:
                        print(f"שגיאה handle_callback: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                save_drafts()
                    
        except Exception as e:
            error_msg = f"שגיאה בלולאה הראשית: {str(e)}"
            print(error_msg, flush=True)
            notify_admin_error(error_msg)
            time.sleep(5)

if __name__ == "__main__":
    main()
