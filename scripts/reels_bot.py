"""Бот рилсов: по расписанию публикует видео из albert/videos в Instagram (Reels).

  python scripts/reels_bot.py auto                     — по расписанию из reels/accounts.json (запускает GitHub Actions каждый час)
  python scripts/reels_bot.py now  [--account alex] [--video s03]   — опубликовать следующее видео сейчас
  python scripts/reels_bot.py status                   — показать очередь
  --dry                                                 — ничего не публиковать, только показать подписи

Токены: секрет IG_<КЛЮЧ>_TOKEN (IG_ALBERT_TOKEN, IG_ALEX_TOKEN), по желанию IG_<КЛЮЧ>_USER_ID.
Нет токена — бот присылает видео и готовую подпись в личный Telegram (TG_BOT_TOKEN), выложить можно вручную.
Загрузка: напрямую файлом (resumable upload Instagram API), запасной путь — по ссылке raw.githubusercontent.com.
"""
import argparse, datetime as dt, fnmatch, glob, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_F = os.path.join(ROOT, "reels", "accounts.json")
CAP_F = os.path.join(ROOT, "reels", "captions.json")
STATE_F = os.path.join(ROOT, "reels", "state.json")
VID_DIR = os.path.join(ROOT, "albert", "videos")
EP_DIR = os.path.join(ROOT, "albert", "episodes")
API_VER = "v23.0"
IG_API = f"https://graph.instagram.com/{API_VER}"
MSK = ZoneInfo("Europe/Moscow")
TG_LINE = "Разборы и продолжение — в Telegram, ссылка в профиле 👆"


def load(f, default):
    try:
        return json.load(open(f, encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_state(st):
    json.dump(st, open(STATE_F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def now():
    fake = os.environ.get("REELS_NOW")  # для проверки расписания: REELS_NOW=2026-10-31T19:20
    return dt.datetime.fromisoformat(fake).replace(tzinfo=MSK) if fake else dt.datetime.now(MSK)


# ---------- очередь ----------
def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def all_videos():
    return sorted((os.path.basename(f)[:-4] for f in glob.glob(os.path.join(VID_DIR, "*.mp4"))), key=natural)


def queue(acc, st):
    """Видео аккаунта по порядку шаблонов; варианты озвучки (ep02_silero и т.п.) не берём."""
    vids = [v for v in all_videos() if "_" not in v]
    out = []
    for pat in acc["videos"]:
        for v in vids:
            if fnmatch.fnmatch(v, pat) and v not in out:
                out.append(v)
    return [v for v in out if v not in st["posted"]]


# ---------- подпись ----------
def auto_caption(name):
    """Подпись из сценария: первая фраза (крючок) + призыв из предпоследней реплики."""
    ep = load(os.path.join(EP_DIR, name + ".json"), {})
    lines = [l["text"] for l in ep.get("lines", [])]
    if not lines:
        return ep.get("title", "")
    hook = lines[0]
    cta = next((l for l in reversed(lines) if "плюс" in l.lower()), None)
    parts = [f"🔥 {hook}"]
    if ep.get("title"):
        parts.append(ep["title"] + " — досмотри до конца.")
    if cta:
        parts.append(re.sub(r"[Пп]иши плюс в комментариях\.?", "Пиши «+» в комментариях 👇", cta))
    return "\n\n".join(parts)


def caption(name, acc, cfg):
    c = load(CAP_F, {}).get(name)
    text = c["text"] if c else auto_caption(name)
    tags = " ".join(t for t in [acc.get("hashtags", ""), (c or {}).get("tags", "")] if t)
    tail = [TG_LINE]
    if acc.get("footer"):
        tail.append(acc["footer"])
    if cfg.get("ai_note"):
        tail.append(cfg["ai_note"])
    out = text.strip() + "\n\n" + "\n".join(tail) + ("\n\n" + tags if tags else "")
    return out[:2200]  # лимит Instagram


# ---------- Instagram API ----------
def call(method, path, params, token, base=IG_API):
    params = dict(params, access_token=token)
    url = f"{base}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Instagram {e.code}: {e.read()[:500].decode('utf-8', 'replace')}")


def wait_ready(cid, token, minutes=8):
    """Instagram обрабатывает видео 30 с – несколько минут."""
    last = None
    for _ in range(minutes * 6):
        r = call("GET", cid, {"fields": "status_code,status"}, token)
        last = r
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram не принял видео: {r.get('status')}")
        time.sleep(10)
    raise RuntimeError(f"Видео не обработано за {minutes} мин: {last}")


def upload_file(cid, path, token):
    size = os.path.getsize(path)
    req = urllib.request.Request(f"https://rupload.facebook.com/ig-api-upload/{API_VER}/{cid}", data=open(path, "rb").read(),
                                 method="POST", headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Загрузка файла {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")
    if not res.get("success", True):
        raise RuntimeError(f"Загрузка файла: {res}")


def publish_reel(name, cap, token, user_id, cfg):
    uid = user_id or call("GET", "me", {"fields": "user_id"}, token)["user_id"]
    path = os.path.join(VID_DIR, name + ".mp4")
    base = {"media_type": "REELS", "caption": cap, "share_to_feed": "true", "thumb_offset": str(cfg.get("thumb_offset_ms", 0))}
    try:  # 1) загружаем файл напрямую — не зависит от хостинга
        r = call("POST", f"{uid}/media", dict(base, upload_type="resumable"), token)
        cid = r["id"]
        upload_file(cid, path, token)
        wait_ready(cid, token)
    except RuntimeError as ex:  # 2) запасной путь — Instagram сам скачивает видео по публичной ссылке
        print(f"::warning title=Reels::прямая загрузка не удалась ({ex}); пробую по ссылке")
        repo = os.environ.get("GITHUB_REPOSITORY", "smash0963sk/metod-vipbet")
        url = f"https://raw.githubusercontent.com/{repo}/main/albert/videos/{name}.mp4"
        cid = call("POST", f"{uid}/media", dict(base, video_url=url), token)["id"]
        wait_ready(cid, token)
    mid = call("POST", f"{uid}/media_publish", {"creation_id": cid}, token)["id"]
    try:
        link = call("GET", mid, {"fields": "permalink"}, token).get("permalink")
    except RuntimeError:
        link = None
    return mid, link


# ---------- Telegram (уведомления и ручной режим) ----------
def tg(method, fields, video=None):
    tok = os.environ.get("TG_BOT_TOKEN")
    if not tok:
        return None
    url = f"https://api.telegram.org/bot{tok}/{method}"
    if video:
        b = "----reels" + str(int(time.time() * 1000))
        body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
        body += (f'--{b}\r\nContent-Disposition: form-data; name="video"; filename="{os.path.basename(video)}"\r\n'
                 "Content-Type: video/mp4\r\n\r\n").encode() + open(video, "rb").read() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r).get("result")
    except urllib.error.HTTPError as e:
        print(f"::warning title=Telegram::{e.code}: {e.read()[:200]!r}")
        return None


def tg_chat():
    return os.environ.get("TG_CHAT_ID") or load(os.path.join(ROOT, "persona", "state.json"), {}).get("tg_chat")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_manual(name, acc, cap):
    chat = tg_chat()
    if not chat or not os.environ.get("TG_BOT_TOKEN"):
        return False
    path = os.path.join(VID_DIR, name + ".mp4")
    tg("sendVideo", {"chat_id": chat, "supports_streaming": "true",
                     "caption": f"🎬 Рилс для Instagram «{acc['name']}» — {name}\nВыложите сейчас: подпись следующим сообщением (нажмите — скопируется)."}, video=path)
    tg("sendMessage", {"chat_id": chat, "parse_mode": "HTML", "text": f"<code>{esc(cap)}</code>"})
    return True


# ---------- публикация ----------
def post_one(key, acc, cfg, st, video=None, dry=False):
    q = queue(acc, st)
    name = video or (q[0] if q else None)
    if not name:
        msg = f"Очередь рилсов «{acc['name']}» закончилась — нужны новые видео."
        print(f"::warning title=Reels::{msg}")
        if not dry and not st.setdefault("empty_warned", {}).get(key):
            st["empty_warned"][key] = now().isoformat(timespec="minutes")
            chat = tg_chat()
            chat and tg("sendMessage", {"chat_id": chat, "text": "⚠️ " + msg})
        return None
    cap = caption(name, acc, cfg)
    print(f"\n=== {acc['name']} · {name} (в очереди ещё {max(0, len(q) - 1)}) ===\n{cap}\n")
    if dry:
        return name
    token = os.environ.get(f"IG_{key.upper()}_TOKEN")
    if token:
        mid, link = publish_reel(name, cap, token, os.environ.get(f"IG_{key.upper()}_USER_ID"), cfg)
        st["posted"][name] = {"account": key, "at": now().isoformat(timespec="minutes"), "id": mid, "link": link}
        print(f"::notice title=Reels::{acc['name']}: опубликован {name} {link or mid}")
        chat = tg_chat()
        chat and tg("sendMessage", {"chat_id": chat, "text": f"✅ Instagram «{acc['name']}»: опубликован рилс {name}\n{link or ''}"})
    elif cfg.get("telegram_fallback", True) and send_manual(name, acc, cap):
        st["posted"][name] = {"account": key, "at": now().isoformat(timespec="minutes"), "id": "telegram"}
        print(f"::notice title=Reels::Нет секрета IG_{key.upper()}_TOKEN — {name} отправлен вам в Telegram для ручной публикации")
    else:
        print(f"::warning title=Reels::Нет секрета IG_{key.upper()}_TOKEN и не настроен Telegram — {name} не опубликован")
        return None
    st.setdefault("empty_warned", {}).pop(key, None)
    return name


def due_slots(acc, st, key, cfg):
    """Слоты на сегодня, время которых наступило (не позже late_hours) и которые ещё не отработаны."""
    t = now()
    done = st.setdefault("slots", {})
    out = []
    for hm in acc.get("times_msk", []):
        h, m = map(int, hm.split(":"))
        at = t.replace(hour=h, minute=m, second=0, microsecond=0)
        sid = f"{key}:{t.date()}:{hm}"
        if at <= t < at + dt.timedelta(hours=cfg.get("late_hours", 3)) and sid not in done:
            out.append(sid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["auto", "now", "status"])
    ap.add_argument("--account", default="all")
    ap.add_argument("--video", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    cfg = load(CFG_F, {})
    st = load(STATE_F, {"posted": {}})
    st.setdefault("posted", {})
    accs = {k: v for k, v in cfg["accounts"].items() if a.account in ("all", "", k)}
    if not accs:
        sys.exit(f"Нет аккаунта {a.account}. Есть: {', '.join(cfg['accounts'])}")

    if a.mode == "status":
        for k, acc in accs.items():
            q = queue(acc, st)
            mode = "API" if os.environ.get(f"IG_{k.upper()}_TOKEN") else "Telegram (нет токена)"
            print(f"{acc['name']} [{k}] · {', '.join(acc['times_msk'])} МСК · {mode}\n  в очереди {len(q)}: {' '.join(q) or '—'}")
        return

    failed = False
    for k, acc in accs.items():
        try:
            if a.mode == "now":
                video = a.video or None
                if video and not os.path.exists(os.path.join(VID_DIR, video + ".mp4")):
                    sys.exit(f"Нет файла albert/videos/{video}.mp4")
                post_one(k, acc, cfg, st, video, a.dry)
            else:
                for sid in due_slots(acc, st, k, cfg):
                    post_one(k, acc, cfg, st, None, a.dry)
                    if not a.dry:
                        st["slots"][sid] = now().isoformat(timespec="minutes")
        except Exception as ex:
            failed = True
            print(f"::error title=Reels {acc['name']}::{ex}")
            chat = tg_chat()
            chat and not a.dry and tg("sendMessage", {"chat_id": chat, "text": f"❌ Instagram «{acc['name']}»: не удалось опубликовать.\n{str(ex)[:600]}"})
        finally:
            if not a.dry:
                # храним отметки слотов только за последние 3 дня
                cut = str((now() - dt.timedelta(days=3)).date())
                st["slots"] = {s: v for s, v in st.get("slots", {}).items() if s.split(":")[1] >= cut}
                save_state(st)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
