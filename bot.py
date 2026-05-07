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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

drafts = {}
offset = 0

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"שגיאה שליחה: {e}")

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

def publish_to_wp(draft):
    featured_id = None
    if draft.get("main_image"):
        featured_id, _ = upload_image_to_wp(draft["main_image"], "main.jpg")

    gallery_ids = []
    for i, img in enumerate(draft.get("gallery", [])):
        img_id, _ = upload_image_to_wp(img, f"gallery_{i}.jpg")
        if img_id:
            gallery_ids.append(img_id)

    content = draft.get("body", "")
    if gallery_ids:
        content += '\n\n[gallery ids="' + ",".join(str(i) for i in gallery_ids) + '"]'
    if draft.get("video_url"):
        content += f'\n\n[embed]{draft["video_url"]}[/embed]'

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
        "status": "draft",
        "categories": draft.get("categories", []),
        "tags": tag_ids,
    }
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

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    text = msg.get("text", "")

    if user_id not in drafts:
        drafts[user_id] = {"step": "idle", "gallery": []}

    draft = drafts[user_id]
    step = draft.get("step", "idle")

    if text in ("/start", "/new"):
        drafts[user_id] = {"step": "title", "gallery": []}
        send_message(chat_id, "📝 <b>כתבה חדשה</b>\n\nשלח את <b>כותרת</b> הכתבה:")
        return

    if text == "/cancel":
        drafts[user_id] = {"step": "idle", "gallery": []}
        send_message(chat_id, "❌ הכתבה בוטלה.")
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
            send_message(chat_id, f"✅ {len(draft['gallery'])} תמונות בגלריה!\n\nשלח <b>לינק וידאו מ-Vimeo</b> או /skip:")
        else:
            send_message(chat_id, "שלח תמונה או /done:")

    elif step == "video":
        draft["video_url"] = None if text == "/skip" else text
        draft["step"] = "confirm"
        summary = f"""📋 <b>סיכום:</b>

<b>כותרת:</b> {draft.get('title','')}
<b>כותרת משנה:</b> {draft.get('subtitle','')}
<b>כותרת אדומה:</b> {draft.get('red_title','')}
<b>תגיות:</b> {', '.join(draft.get('tags',[]))}
<b>קטגוריות:</b> {', '.join(draft.get('cat_names',[]))}
<b>תמונה ראשית:</b> {'✅' if draft.get('main_image') else '❌'}
<b>גלריה:</b> {len(draft.get('gallery',[]))} תמונות
<b>וידאו:</b> {draft.get('video_url') or 'אין'}

שלח /publish לפרסום או /cancel לביטול"""
        send_message(chat_id, summary)

    elif step == "confirm":
        if text == "/publish":
            send_message(chat_id, "⏳ מפרסם לוורדפרס...")
            resp = publish_to_wp(draft)
            if resp.status_code == 201:
                post_url = resp.json().get("link", "")
                send_message(chat_id, f"✅ <b>הכתבה פורסמה כטיוטה!</b>\n🔗 {post_url}")
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

    elif cb_data == "cat_done":
        draft["step"] = "main_image"
        send_message(chat_id, f"✅ קטגוריות: {', '.join(draft.get('cat_names',[]))}\n\nשלח את <b>התמונה הראשית</b>:")

def main():
    global offset
    print("🚀 בוט חבד מתחיל!", flush=True)
    
    # הפעל שרת HTTP ברקע
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    print("🌐 שרת HTTP פועל", flush=True)
    
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 0},
                timeout=10
            )
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
                    
        except Exception as e:
            print(f"שגיאה: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
