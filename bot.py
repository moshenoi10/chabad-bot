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
youtube_tokens = {}

# ─── מערכת הרשאות ────────────────────────────────────────
SUPER_ADMIN_ID = "1798097090"  # אתה – הרשאה מלאה תמיד

# רמות הרשאה: "admin" = כל הגישה, "editor" = העלאה בלבד, "blocked" = חסום
users_permissions = {
    SUPER_ADMIN_ID: "admin"
}

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
    if len(activity_log) > 100:  # שמור רק 100 פעולות אחרונות
        activity_log.pop(0)
    print(f"📋 לוג: {entry['time']} | {username} | {action}", flush=True)

def get_permission(user_id):
    uid = str(user_id)
    if uid == SUPER_ADMIN_ID:
        return "admin"
    return users_permissions.get(uid, None)  # None = לא מורשה

def is_admin(user_id):
    return get_permission(user_id) == "admin"

def is_editor(user_id):
    perm = get_permission(user_id)
    return perm in ("admin", "editor")

def notify_admin_error(error_msg):
    """שולח שגיאה קריטית לאדמין"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": SUPER_ADMIN_ID, "text": f"⚠️ <b>שגיאה בבוט:</b>\n\n{error_msg}", "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass  # שמירת tokens זמנית

class Handler(BaseHTTPRequestHandler):
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
            # שמור רק נתונים שאפשר לסריאליז (לא bytes של תמונות)
            safe_drafts = {}
            for uid, d in drafts.items():
                safe = {k: v for k, v in d.items() 
                       if k not in ("main_image", "gallery", "mazaltov_images", "pending_group_files")}
                safe_drafts[uid] = safe
            pickle.dump(safe_drafts, f)
    except:
        pass

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
        [{"text": "👥 ניהול משתמשים"}, {"text": "📊 לוג פעולות"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

MAIN_MENU = {
    "keyboard": [
        [{"text": "✍️ כתבה חדשה"}, {"text": "🤖 העלאה חכמה"}],
        [{"text": "🎉 מזל טוב"}, {"text": "🎬 העלאה ליוטיוב"}],
        [{"text": "✏️ עריכת כתבה"}, {"text": "🗑️ מחיקת כתבה"}],
        [{"text": "📋 כתבות אחרונות"}, {"text": "📝 טיוטות"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=10)
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
        # בדיקה אם הtoken פג תוקף
        if youtube_tokens.get("refresh_token"):
            new_token = refresh_youtube_token(youtube_tokens["refresh_token"])
            if new_token:
                youtube_tokens["access_token"] = new_token
                access_token = new_token

        # העלאת הסרטון
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
        
        # שימוש ב-resumable upload
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
            return f"https://www.youtube.com/watch?v={video_id}", None
        return None, f"שגיאה: {upload_resp.status_code}"
    except Exception as e:
        return None, str(e)

def wait_for_vimeo(video_id, max_wait=300):
    """ממתין עד שהסרטון מוכן ב-Vimeo"""
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
        except:
            pass
        time.sleep(10)
    return False

def upload_to_vimeo(video_bytes, title="סרטון חדש"):
    if not VIMEO_TOKEN:
        return None
    try:
        headers = {
            "Authorization": f"bearer {VIMEO_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.vimeo.*+json;version=3.4"
        }
        create_resp = requests.post(
            "https://api.vimeo.com/me/videos",
            headers=headers,
            json={
                "upload": {"approach": "tus", "size": len(video_bytes)},
                "name": title,
                "privacy": {"view": "anybody"}
            },
            timeout=30
        )
        if create_resp.status_code != 200:
            print(f"שגיאה יצירת Vimeo: {create_resp.text[:200]}", flush=True)
            return None

        upload_link = create_resp.json()["upload"]["upload_link"]
        video_uri = create_resp.json()["uri"]
        video_id = video_uri.split("/")[-1]

        # העלאת הקובץ
        upload_resp = requests.patch(
            upload_link,
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
                "Content-Length": str(len(video_bytes))
            },
            data=video_bytes,
            timeout=120
        )
        if upload_resp.status_code in (204, 200):
            # המתנה לעיבוד
            print(f"ממתין לעיבוד Vimeo {video_id}...", flush=True)
            wait_for_vimeo(video_id)
            return f"https://vimeo.com/{video_id}"
        else:
            print(f"שגיאה העלאת Vimeo: {upload_resp.status_code}", flush=True)
            return None
    except Exception as e:
        print(f"שגיאה Vimeo: {e}", flush=True)
        return None

def notify_channel(title, subtitle, url):
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
    return ADMIN_MENU if is_admin(str(user_id)) else MAIN_MENU
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
    featured_id = None
    if draft.get("main_image"):
        featured_id, _ = upload_image_to_wp(draft["main_image"], "main.jpg")

    # גלריה – תמונות אחת מתחת לשנייה
    gallery_content = ""
    for i, img in enumerate(draft.get("gallery", [])):
        img_id, img_url = upload_image_to_wp(img, f"gallery_{i}.jpg")
        if img_url:
            gallery_content += f'\n<figure class="wp-block-image size-full"><img src="{img_url}" /></figure>\n'

    # עיבוד גוף הכתבה – המרת פורמט וואטסאפ ושמירת פיסקאות
    body_text = convert_whatsapp_format(draft.get("body", ""))
    # פיצול לפסקאות – גם שורה אחת וגם שתי שורות
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
        content += f'\n\n[embed]{url}[/embed]'

    tag_ids = []
    for tag in draft.get("tags", []):
        try:
            r = requests.post(f"{WP_URL}/tags", json={"name": tag},
                            auth=(WP_USER, WP_PASSWORD), timeout=10)
            if r.status_code in (200, 201):
                tag_ids.append(r.json()["id"])
        except:
            pass

    post_data = {
        "title": draft.get("title", ""),
        "content": content,
        "excerpt": draft.get("subtitle", ""),
        "status": status,
        "categories": draft.get("categories", []),
        "tags": tag_ids,
        "acf": {
            "tag_label": draft.get("red_title", "")
        }
    }
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

def convert_whatsapp_format(text):
    """המרת פורמט וואטסאפ ל-HTML"""
    import re
    text = re.sub(r'\*([^*]+)\*', r'<strong>\1</strong>', text)
    text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)
    text = re.sub(r'~([^~]+)~', r'<s>\1</s>', text)
    return text

def process_with_gemini(text):
    if not GEMINI_API_KEY:
        return None
    prompt = f"""אתה עורך כתבות מנוסה לאתר חדשות חרדי. קיבלת טקסט גולמי. עליך לייצר:

1. **כותרת ראשית** - משפט מושך ומלא שמסכם את הכתבה, בין 8-15 מילים. חייב להכיל את שם האירוע/אדם המרכזי.

2. **כותרת משנה** - תיאור מפורט יותר, בין 15-25 מילים. צריך לכלול פרטים מרכזיים נוספים מהכתבה כמו שמות, מקומות, אירועים.

3. **כותרת אדומה** - 2-4 מילים בלבד, הדגשה קצרה וחזקה.

4. **גוף הכתבה** - העתק את הטקסט המקורי בדיוק, ללא שינוי כלשהו.

5. **תגיות** - בין 5-8 מילות מפתח רלוונטיות מהטקסט.

חוקים מחייבים:
- אסור להוסיף מידע שלא קיים בטקסט המקורי
- אסור לשנות אפילו מילה אחת בגוף הכתבה
- הכותרת הראשית חייבת להיות לפחות 8 מילים
- התגיות חייבות להיות לפחות 5

החזר תשובה בפורמט JSON בלבד ללא backticks:
{{"title": "...", "subtitle": "...", "red_title": "...", "body": "...", "tags": ["...", "...", "...", "...", "..."]}}

הטקסט:
{text}"""

    try:
        for attempt in range(3):
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if resp.status_code in (429, 503):
                print(f"Gemini {resp.status_code}, מחכה 15 שניות... (ניסיון {attempt+1}/3)", flush=True)
                time.sleep(15)
                continue
            if resp.status_code == 200:
                result = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                result = result.strip().replace("```json", "").replace("```", "").strip()
                return json.loads(result)
            print(f"שגיאה Gemini: {resp.status_code}", flush=True)
            break
    except Exception as e:
        print(f"שגיאה Gemini: {e}", flush=True)
    return None

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

    # בדיקת הרשאות
    perm = get_permission(user_id)

    if perm == "blocked":
        send_message(chat_id, "❌ הגישה שלך חסומה.")
        return

    if perm is None:
        # משתמש לא מורשה
        send_message(chat_id, "⛔ אין לך הרשאה להשתמש בבוט.\n\nפנה למנהל לקבלת גישה.")
        # הודעה לאדמין
        notify_admin_error(f"משתמש חדש ביקש גישה:\nשם: {username}\nID: {user_id}\n\nלאשר: /approve_{user_id}\nלחסום: /block_{user_id}")
        return

    if user_id not in drafts:
        drafts[user_id] = {"step": "idle", "gallery": []}

    draft = drafts[user_id]
    step = draft.get("step", "idle")

    # פקודות ניהול – רק אדמין
    if text.startswith("/approve_") and is_admin(user_id):
        target_id = text.replace("/approve_", "")
        users_permissions[target_id] = "editor"
        send_message(chat_id, f"✅ משתמש {target_id} אושר כעורך!")
        send_message(int(target_id), "✅ הגישה שלך אושרה! שלח /start להתחיל.", MAIN_MENU)
        log_action(user_id, username, f"אישור משתמש {target_id}")
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
        send_message(chat_id, f"✅ משתמש {target_id} הוגדר כאדמין!")
        return

    if text == "👥 ניהול משתמשים" and is_admin(user_id):
        users_list = "\n".join([f"• {uid}: {perm}" for uid, perm in users_permissions.items()])
        send_message(chat_id, f"👥 <b>משתמשים מורשים:</b>\n\n{users_list}\n\nלהוסיף עורך: /approve_[ID]\nלחסום: /block_[ID]\nלהפוך לאדמין: /makeadmin_[ID]")
        return

    if text == "📊 לוג פעולות" and is_admin(user_id):
        if activity_log:
            log_text = "\n".join([f"• {e['time']} | {e['username']} | {e['action']}" for e in activity_log[-20:]])
            send_message(chat_id, f"📊 <b>20 פעולות אחרונות:</b>\n\n{log_text}")
        else:
            send_message(chat_id, "אין פעולות בלוג עדיין.")
        return

    # לוג פעולה
    if text and not text.startswith("/"):
        log_action(user_id, username, f"הודעה: {text[:50]}")

    if text in ("/start", "/new", "✍️ כתבה חדשה"):
        if text == "/start":
            menu = ADMIN_MENU if is_admin(user_id) else MAIN_MENU
            send_message(chat_id, "שלום! 👋 בחר פעולה:", menu)
            return
        drafts[user_id] = {"step": "title", "gallery": []}
        send_message(chat_id, "📝 <b>כתבה חדשה</b>\n\nשלח את <b>כותרת</b> הכתבה:")
        return

    if text in ("/smart", "🤖 העלאה חכמה"):
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
        if not is_admin(user_id):
            send_message(chat_id, "❌ אין לך הרשאה למחוק כתבות.")
            return
        drafts[user_id] = {"step": "delete_url", "gallery": []}
        send_message(chat_id, "🗑️ <b>מחיקת כתבה</b>\n\nשלח את ה-URL של הכתבה למחיקה:")
        return

    if text in ("/cancel", "❌ ביטול"):
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ הפעולה בוטלה.", get_menu(user_id))
        return

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
        cats = get_wp_categories()
        keyboard = {"inline_keyboard": []}
        row = []
        for cat_name, cat_id in cats.items():
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
            # המרת פורמט וואטסאפ בגוף הכתבה
            body_clean = convert_whatsapp_format(result.get("body", text))
            draft.update({
                "title": result.get("title", ""),
                "subtitle": result.get("subtitle", ""),
                "red_title": result.get("red_title", ""),
                "body": body_clean,
                "tags": result.get("tags", []),
                "step": "smart_preview"
            })
            # הצגת גוף בתצוגה מקדימה ללא תגי HTML
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
                    [{"text": "✏️ ערוך כותרת", "callback_data": "smart_edit_title"},
                     {"text": "✏️ ערוך גוף", "callback_data": "smart_edit_body"}],
                    [{"text": "✏️ ערוך תגיות", "callback_data": "smart_edit_tags"},
                     {"text": "❌ ביטול", "callback_data": "publish_cancel"}]
                ]
            })
        else:
            send_message(chat_id, "❌ שגיאה בעיבוד. נסה שוב או השתמש בהעלאה ידנית.", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}

    elif step == "smart_edit_title_input":
        draft["title"] = text
        draft["step"] = "smart_preview"
        send_message(chat_id, f"✅ כותרת עודכנה!\n\n<b>כותרת:</b> {text}\n\nהמשך?", {
            "inline_keyboard": [[
                {"text": "✅ מאשר, המשך", "callback_data": "smart_approve"},
                {"text": "❌ ביטול", "callback_data": "publish_cancel"}
            ]]
        })

    elif step == "smart_edit_body_input":
        draft["body"] = text
        draft["step"] = "smart_preview"
        send_message(chat_id, "✅ גוף עודכן!\n\nהמשך?", {
            "inline_keyboard": [[
                {"text": "✅ מאשר, המשך", "callback_data": "smart_approve"},
                {"text": "❌ ביטול", "callback_data": "publish_cancel"}
            ]]
        })

    elif step == "smart_edit_tags_input":
        draft["tags"] = [t.strip() for t in text.split(",")]
        draft["step"] = "smart_preview"
        send_message(chat_id, f"✅ תגיות עודכנו!\n\n{', '.join(draft['tags'])}\n\nהמשך?", {
            "inline_keyboard": [[
                {"text": "✅ מאשר, המשך", "callback_data": "smart_approve"},
                {"text": "❌ ביטול", "callback_data": "publish_cancel"}
            ]]
        })

    elif step == "schedule_time":
        try:
            from datetime import datetime
            dt = datetime.strptime(text.strip(), "%d/%m/%Y %H:%M")
            iso_date = dt.strftime("%Y-%m-%dT%H:%M:00")
            draft["schedule_date"] = iso_date
            send_message(chat_id, "⏳ מתזמן פרסום...")
            resp = publish_to_wp(draft, "future", iso_date)
            if resp.status_code == 201:
                send_message(chat_id, f"✅ <b>הכתבה מתוזמנת לפרסום ב-{text}!</b>", get_menu(user_id))
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
            drafts[user_id] = {"step": "idle", "gallery": []}
        except ValueError:
            send_message(chat_id, "⚠️ פורמט שגוי. נסה שוב:\n<code>DD/MM/YYYY HH:MM</code>")

    elif step == "edit_url":
        try:
            # נסה לחלץ ID מהURL
            part = text.rstrip("/").split("/")[-1]
            if part.isdigit():
                r = requests.get(f"{WP_URL}/posts/{part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                if r.status_code == 200:
                    post = r.json()
                else:
                    send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                    return
            else:
                r = requests.get(f"{WP_URL}/posts?slug={part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                posts = r.json()
                if posts:
                    post = posts[0]
                else:
                    send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                    return

            draft["edit_id"] = post["id"]
            draft["step"] = "edit_field"
            send_message(chat_id, f"""✏️ <b>עורך כתבה:</b>
<b>{post['title']['rendered']}</b>

מה תרצה לערוך?""", {
                "inline_keyboard": [
                    [{"text": "כותרת", "callback_data": "edit_title"},
                     {"text": "כותרת אדומה", "callback_data": "edit_red_title"}],
                    [{"text": "תמונה ראשית", "callback_data": "edit_image"},
                     {"text": "הוספת תמונות", "callback_data": "edit_gallery"}],
                    [{"text": "הוספת סרטון", "callback_data": "edit_video"}]
                ]
            })
        except Exception as e:
            send_message(chat_id, f"❌ שגיאה: {e}")

    elif step == "edit_field_value":
        field = draft.get("edit_field")
        post_id = draft.get("edit_id")
        update_data = {}
        if field == "title":
            update_data["title"] = text
        elif field == "red_title":
            update_data["acf"] = {"tag_label": text}
        r = requests.post(f"{WP_URL}/posts/{post_id}", json=update_data,
                         auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code == 200:
            send_message(chat_id, "✅ הכתבה עודכנה!", get_menu(user_id))
        else:
            send_message(chat_id, f"❌ שגיאה: {r.text[:200]}")
        drafts[user_id] = {"step": "idle", "gallery": []}

    elif step == "edit_gallery_upload":
        if "photo" in msg:
            content_bytes = get_file(msg["photo"][-1]["file_id"])
            if content_bytes:
                # הוסף תמונה לגלריה הקיימת
                post_id = draft.get("edit_id")
                img_id, img_url = upload_image_to_wp(content_bytes, f"gallery_add.jpg")
                if img_url:
                    r = requests.get(f"{WP_URL}/posts/{post_id}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                    if r.status_code == 200:
                        existing_content = r.json().get("content", {}).get("raw", "")
                        new_content = existing_content + f'\n<figure class="wp-block-image size-full"><img src="{img_url}" /></figure>\n'
                        requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content},
                                    auth=(WP_USER, WP_PASSWORD), timeout=10)
                send_message(chat_id, f"✅ תמונה נוספה! שלח עוד או /done")
        elif text == "/done":
            send_message(chat_id, "✅ הגלריה עודכנה!", get_menu(user_id))
            drafts[user_id] = {"step": "idle", "gallery": []}
        else:
            send_message(chat_id, "שלח תמונה או /done:")

    elif step == "edit_video_url":
        post_id = draft.get("edit_id")
        r = requests.get(f"{WP_URL}/posts/{post_id}", auth=(WP_USER, WP_PASSWORD), timeout=10)
        if r.status_code == 200:
            existing_content = r.json().get("content", {}).get("raw", "")
            new_content = existing_content + f'\n\n[embed]{text}[/embed]'
            requests.post(f"{WP_URL}/posts/{post_id}", json={"content": new_content},
                        auth=(WP_USER, WP_PASSWORD), timeout=10)
            send_message(chat_id, "✅ סרטון נוסף לכתבה!", get_menu(user_id))
        else:
            send_message(chat_id, "❌ שגיאה בעדכון")
        drafts[user_id] = {"step": "idle", "gallery": []}

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

    elif step == "delete_url":
        try:
            part = text.rstrip("/").split("/")[-1]
            if part.isdigit():
                r = requests.get(f"{WP_URL}/posts/{part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                if r.status_code == 200:
                    post = r.json()
                else:
                    send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                    return
            else:
                r = requests.get(f"{WP_URL}/posts?slug={part}", auth=(WP_USER, WP_PASSWORD), timeout=10)
                posts = r.json()
                if posts:
                    post = posts[0]
                else:
                    send_message(chat_id, "❌ כתבה לא נמצאה. נסה שוב:")
                    return

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

    elif step == "mazaltov_multi":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft.setdefault("mazaltov_images", []).append(content)
                # שלח הודעה רק בתמונה הראשונה
                if len(draft["mazaltov_images"]) == 1:
                    send_message(chat_id, "📸 מקבל תמונות... שלח /done כשסיימת")
        elif text == "/done":
            images = draft.get("mazaltov_images", [])
            if not images:
                send_message(chat_id, "⚠️ לא התקבלו תמונות.")
                return
            send_message(chat_id, f"⏳ מעלה {len(images)} כתבות מזל טוב...")
            success = 0
            for i, img in enumerate(images):
                featured_id, _ = upload_image_to_wp(img, f"mazaltov_{i}.jpg")
                post_data = {
                    "title": "מזל טוב",
                    "content": "",
                    "status": "publish",
                    "categories": [18, 103],
                    "acf": {"tag_label": "מזל טוב"}
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
                    "categories": [18, 103],
                    "acf": {"tag_label": "מזל טוב"}
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

    elif step == "main_image":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft["main_image"] = content
                draft["step"] = "gallery"
                send_message(chat_id, "✅ תמונה ראשית נשמרה!\n\nשלח תמונות לגלריה.\nכשסיימת שלח /done")
        else:
            send_message(chat_id, "⚠️ שלח תמונה:")

    elif step == "gallery":
        if "photo" in msg:
            content = get_file(msg["photo"][-1]["file_id"])
            if content:
                draft["gallery"].append(content)
                send_message(chat_id, f"✅ תמונה {len(draft['gallery'])} נוספה. שלח עוד או /done")
        elif text == "/done":
            draft["step"] = "video"
            send_message(chat_id, f"✅ {len(draft['gallery'])} תמונות בגלריה!\n\nשלח <b>קובץ סרטון</b> להעלאה ל-Vimeo, <b>לינק</b> ידני, או /skip:")
        else:
            send_message(chat_id, "שלח תמונה או /done:")

    elif step == "video":
        if text == "/skip":
            draft["step"] = "confirm"
            _show_summary(chat_id, draft)
        elif text == "/done":
            draft["step"] = "confirm"
            _show_summary(chat_id, draft)
        elif "video" in msg or "document" in msg:
            file_id = msg.get("video", msg.get("document", {})).get("file_id")
            media_group_id = msg.get("media_group_id")
            if media_group_id:
                if draft.get("current_media_group") != media_group_id:
                    draft["current_media_group"] = media_group_id
                    draft["pending_group_files"] = []
                if file_id not in draft["pending_group_files"]:
                    draft["pending_group_files"].append(file_id)
                # שלח הודעה רק בסרטון הראשון
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
        elif text.startswith("http"):
            draft.setdefault("videos", []).append(text)
            send_message(chat_id, f"✅ לינק {len(draft['videos'])} נוסף!\n\nשלח סרטון נוסף או /done לסיום:")
        else:
            send_message(chat_id, "שלח קובץ סרטון, לינק, /upload_all לכמה סרטונים, או /skip:")

    elif step == "confirm":
        if text == "/publish":
            send_message(chat_id, "⏳ מפרסם לוורדפרס...")
            resp = publish_to_wp(draft)
            if resp.status_code == 201:
                post_data_resp = resp.json()
                post_url = post_data_resp.get("link", "")
                send_message(chat_id, f"✅ <b>הכתבה פורסמה!</b>\n🔗 {post_url}", get_menu(user_id))
                # שליחה לערוץ
                notify_channel(
                    draft.get("title", ""),
                    draft.get("subtitle", ""),
                    post_url
                )
                drafts[user_id] = {"step": "idle", "gallery": []}
            else:
                send_message(chat_id, f"❌ שגיאה: {resp.text[:200]}")
        else:
            send_message(chat_id, "שלח /publish לפרסום או /cancel לביטול")

def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    user_id = str(cb["from"]["id"])
    cb_data = cb["data"]

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                 json={"callback_query_id": cb["id"]}, timeout=10)

    draft = drafts.get(user_id, {})

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
                url = upload_to_vimeo(video_bytes, f"{draft.get('title', 'סרטון')} {i+1}")
                if url:
                    draft.setdefault("videos", []).append(url)
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
                vimeo_url = upload_to_vimeo(video_bytes, draft.get("title", "סרטון"))
                if vimeo_url:
                    draft.setdefault("videos", []).append(vimeo_url)
                    send_message(chat_id, f"✅ עלה ל-Vimeo!\n🔗 {vimeo_url}\n\nשלח סרטון נוסף או /done:")
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
        # עובר לבחירת קטגוריות כמו כתבה רגילה
        draft["step"] = "categories"
        cats = get_wp_categories()
        keyboard = {"inline_keyboard": []}
        row = []
        for cat_name, cat_id in cats.items():
            row.append({"text": cat_name, "callback_data": f"cat_{cat_id}_{cat_name}"})
            if len(row) == 2:
                keyboard["inline_keyboard"].append(row)
                row = []
        if row:
            keyboard["inline_keyboard"].append(row)
        keyboard["inline_keyboard"].append([{"text": "✅ סיימתי", "callback_data": "cat_done"}])
        draft["categories"] = []
        draft["cat_names"] = []
        send_message(chat_id, "✅ מעולה! בחר <b>קטגוריות</b>:", keyboard)

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
        resp = publish_to_wp(draft, "publish")
        if resp.status_code == 201:
            post_url = resp.json().get("link", "")
            send_message(chat_id, f"✅ <b>הכתבה פורסמה!</b>\n🔗 {post_url}", get_menu(user_id))
            notify_channel(draft.get("title", ""), draft.get("subtitle", ""), post_url)
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
        draft["step"] = "schedule_time"
        send_message(chat_id, "⏰ שלח את מועד הפרסום בפורמט:\n<code>DD/MM/YYYY HH:MM</code>\n\nלדוגמה: <code>15/05/2026 09:00</code>")

    elif cb_data == "publish_cancel":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ הפעולה בוטלה.", get_menu(user_id))

    elif cb_data == "cat_done":
        draft["step"] = "main_image"
        send_message(chat_id, f"✅ קטגוריות: {', '.join(draft.get('cat_names',[]))}\n\nשלח את <b>התמונה הראשית</b>:")

    elif cb_data == "edit_title":
        draft["step"] = "edit_field_value"
        draft["edit_field"] = "title"
        send_message(chat_id, "שלח את הכותרת החדשה:")

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
        send_message(chat_id, "שלח תמונות להוספה לגלריה.\nכשסיימת שלח /done:")

    elif cb_data == "edit_video":
        draft["step"] = "edit_video_url"
        send_message(chat_id, "שלח לינק וידאו מ-Vimeo:")

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

def main():
    global offset
    print("🚀 בוט חבד מתחיל!", flush=True)
    load_drafts()

    # הגדרת תפריט פקודות
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
    except:
        pass
    
    # הפעל שרת HTTP ברקע
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    print("🌐 שרת HTTP פועל", flush=True)
    
    while True:
        try:
            print(f"בודק עדכונים... offset={offset}", flush=True)
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 0},
                timeout=10
            )
            print(f"תגובה: {resp.text[:200]}", flush=True)
            updates = resp.json().get("result", [])
            
            if not updates:
                time.sleep(1)
                continue
            
            for update in updates:
                offset = update["update_id"] + 1
                print(f"עדכון: {update['update_id']}", flush=True)
                
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
                save_drafts()
                    
        except Exception as e:
            error_msg = f"שגיאה בלולאה הראשית: {str(e)}"
            print(error_msg, flush=True)
            notify_admin_error(error_msg)
            time.sleep(5)

if __name__ == "__main__":
    main()
