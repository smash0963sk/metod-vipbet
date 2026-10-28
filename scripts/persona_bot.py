"""Бот персонажа «Виктор Платонов» для Instagram и Threads.

Контент 70/30: 70% — лайфстайл (мысли, фото из жизни мечты), 30% — разборы матчей
из data/predictions.json со ссылкой на Telegram. Правила — в persona/persona.json.

Слоты (время МСК, расписание — в .github/workflows/persona.yml):
  th_morning  09:10  Threads: мысль дня
  th_sport    12:40  Threads: разбор матча дня + ссылка на Telegram в комментарии
  th_photo    16:10  Threads: фото дня с подписью
  ig_post     18:30  Instagram: фото дня, а каждый 3-й из 10 дней — карточка разбора матча
  th_evening  20:10  Threads: каждый 3-й день — экспресс/верняк со ссылкой, иначе мысль

Запуск в два шага (между ними сценарий коммитит картинки, чтобы у них был публичный адрес):
  python3 scripts/persona_bot.py prepare <слот>   → persona/outbox.json + картинки в persona/media/
  python3 scripts/persona_bot.py publish          → публикация и отметка в persona/state.json

Фото: сначала свои из persona/inbox/ (рядом можно положить .txt с подписью),
иначе — бесплатный фотобанк Pixabay или Pexels по запросу из persona/content.json
(секрет PIXABAY_API_KEY или PEXELS_API_KEY).

Полуавтомат: если токенов Meta нет, но есть TG_BOT_TOKEN, готовые посты (фото + текст) приходят
вам в личный Telegram в нужное время, а вы публикуете их сами. Чат определяется по /start боту.

Секреты: THREADS_ACCESS_TOKEN, INSTAGRAM_ACCESS_TOKEN, PIXABAY_API_KEY (или PEXELS_API_KEY), TG_BOT_TOKEN, TG_CHAT_ID (не обязателен)
(THREADS_USER_ID и INSTAGRAM_USER_ID не обязательны — бот узнает их сам). DRY_RUN=1 — ничего не публиковать.
"""
import glob, json, os, re, shutil, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import threads_bot as tb  # выбор прогнозов дня — те же правила, что на сайте и в Threads

PDIR = os.path.join(ROOT, "persona")
PERSONA = json.load(open(os.path.join(PDIR, "persona.json"), encoding="utf-8"))
CONTENT = json.load(open(os.path.join(PDIR, "content.json"), encoding="utf-8"))
STATE_FILE = os.path.join(PDIR, "state.json")
OUTBOX = os.path.join(PDIR, "outbox.json")
TG = PERSONA.get("telegram") or tb.TG
START = date(2026, 10, 29)
TH_API = "https://graph.threads.net/v1.0"
IG_API = "https://graph.instagram.com/v23.0"
SPORT_TAG = {"Футбол": "#футбол", "Хоккей": "#хоккей", "Теннис": "#теннис", "Баскетбол": "#баскетбол"}
REPLIES = [
    "Все мои разборы, экспрессы и честные итоги — в Telegram 👉 {tg}",
    "Разбираю матчи каждый день в Telegram. Без гарантий, только логика 👉 {tg}",
    "Полный разбор этого матча и других игр дня — тут 👉 {tg}",
]
SPORT_FOOT = "Это моё мнение, а не гарантия."


def now():
    return tb.now()


def day_no(d=None):
    return ((d or now().date()) - START).days


def today():
    return now().strftime("%Y-%m-%d")


# ---------- состояние ----------
def load_state():
    try:
        st = json.load(open(STATE_FILE, encoding="utf-8"))
    except FileNotFoundError:
        st = {}
    for k, v in (("posted", {}), ("used_photos", []), ("used_thoughts", []), ("pexels_ids", []), ("day", {})):
        st.setdefault(k, v)
    return st


def save_state(st):
    st["posted"] = dict(sorted(st["posted"].items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:400])
    st["pexels_ids"] = st["pexels_ids"][-500:]
    keep = sorted(st["day"])[-14:]
    st["day"] = {d: st["day"][d] for d in keep}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def next_item(items, used):
    """Первый неиспользованный элемент; когда закончились — по кругу, не повторяя последние 10."""
    fresh = [x for x in items if x["id"] not in used]
    if not fresh:
        recent = set(used[-10:])
        fresh = [x for x in items if x["id"] not in recent] or items
        used[:] = used[-10:]
    return fresh[0]


# ---------- фото ----------
def http_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def phone_look(im, seed=0):
    """Убирает «стоковый» лоск: чуть спокойнее цвета, тёплый тон телефона, лёгкая виньетка. Чёрный остаётся чёрным."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    im = ImageEnhance.Color(im).enhance(0.92)
    r, g, b = im.split()
    r = r.point(lambda v: min(255, int(v * 1.025)))
    b = b.point(lambda v: int(v * 0.97))
    im = Image.merge("RGB", (r, g, b))
    w, h = im.size
    vign = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vign).ellipse((-w * 0.3, -h * 0.25, w * 1.3, h * 1.25), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(w // 5))
    return Image.composite(im, ImageEnhance.Brightness(im).enhance(0.86), vign)


def crop_4x5(src, dst, look=False, seed=0):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = im.size
    tw, th = (w, int(w * 5 / 4)) if w * 5 / 4 <= h else (int(h * 4 / 5), h)
    left, top = (w - tw) // 2, (h - th) // 2
    im = im.crop((left, top, left + tw, top + th)).resize((1080, 1350), Image.LANCZOS)
    if look:
        im = phone_look(im, seed)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst, "JPEG", quality=88, optimize=True, progressive=True)


def download(url, tmp):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 persona-bot"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)


PEOPLE = {"woman", "women", "man", "men", "girl", "girls", "boy", "boys", "people", "person", "persons", "portrait",
          "model", "face", "lady", "child", "children", "kid", "kids", "couple", "female", "male", "human", "selfie",
          "businessman", "businesswoman", "bride", "groom", "baby", "teen", "guy", "family", "friends"}


def has_people(text, query):
    """Отсеивает фото с людьми: чужие узнаваемые лица нельзя выдавать за окружение персонажа."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    allowed = set(re.findall(r"[a-z]+", query.lower()))  # силуэт пары разрешён, если он прямо в запросе
    return bool((words & PEOPLE) - allowed)


def stock_photo(query, used, dst):
    """Фото из бесплатного фотобанка: Pexels (PEXELS_API_KEY) или Pixabay (PIXABAY_API_KEY)."""
    fake = os.environ.get("PERSONA_FAKE_PHOTO")  # для локальной проверки без интернета
    if fake:
        crop_4x5(fake, dst, look=True, seed=len(used))
        used.add(f"test:{dst}")
        return {"source": "test", "query": query, "pexels_id": f"test:{dst}"}
    tmp = dst + ".src"
    key = os.environ.get("PEXELS_API_KEY")
    if key:
        url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 30})
        for ph in http_json(url, {"Authorization": key, "User-Agent": "persona-bot"}).get("photos", []):
            if str(ph["id"]) in used or has_people(ph.get("alt", ""), query):
                continue
            download(ph["src"].get("large2x") or ph["src"]["original"], tmp)
            crop_4x5(tmp, dst, look=True, seed=ph["id"])
            os.remove(tmp)
            used.add(str(ph["id"]))
            return {"source": "pexels", "pexels_id": ph["id"], "author": ph.get("photographer"), "page": ph.get("url")}
    key = os.environ.get("PIXABAY_API_KEY")
    if key:
        # Pixabay: картинки нужно скачивать к себе (постоянные ссылки на их сервер запрещены правилами API)
        words = query.split()
        for q in (query, " ".join(words[:3]), " ".join(words[:2])):
            for orient in ("vertical", "all"):
                url = "https://pixabay.com/api/?" + urllib.parse.urlencode({
                    "key": key, "q": q[:100], "image_type": "photo", "orientation": orient,
                    "safesearch": "true", "per_page": 50, "order": "popular", "min_height": 1000})
                for ph in http_json(url, {"User-Agent": "persona-bot"}).get("hits", []):
                    pid = f"pixabay:{ph['id']}"
                    if pid in used or has_people(ph.get("tags", ""), query):
                        continue
                    download(ph.get("largeImageURL") or ph["webformatURL"], tmp)
                    crop_4x5(tmp, dst, look=True, seed=ph["id"])
                    os.remove(tmp)
                    used.add(pid)
                    return {"source": "pixabay", "pexels_id": pid, "author": ph.get("user"), "page": ph.get("pageURL")}
    return None


IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def inbox_dump(d):
    """Свои фото: папка persona/inbox/<любое имя>/ с кадрами (+ caption.txt) — это один дамп;
    отдельный файл в persona/inbox/ (+ файл .txt с тем же именем) — пост из одного фото."""
    base = os.path.join(PDIR, "inbox")
    folders = sorted(f for f in glob.glob(os.path.join(base, "*")) if os.path.isdir(f))
    for f in folders:
        files = sorted(x for x in glob.glob(os.path.join(f, "*")) if x.lower().endswith(IMG_EXT))[:10]
        if not files:
            continue
        imgs = []
        for i, src in enumerate(files, 1):
            rel = f"persona/media/{d}-own-{i}.jpg"
            crop_4x5(src, os.path.join(ROOT, rel))
            imgs.append(rel)
        cap = os.path.join(f, "caption.txt")
        return imgs, (open(cap, encoding="utf-8").read().strip() if os.path.exists(cap) else None), os.path.relpath(f, ROOT)
    files = sorted(x for x in glob.glob(os.path.join(base, "*")) if x.lower().endswith(IMG_EXT))
    if files:
        rel = f"persona/media/{d}-own-1.jpg"
        crop_4x5(files[0], os.path.join(ROOT, rel))
        txt = os.path.splitext(files[0])[0] + ".txt"
        return [rel], (open(txt, encoding="utf-8").read().strip() if os.path.exists(txt) else None), os.path.relpath(files[0], ROOT)
    return None


def photo_of_day(st, plan):
    """Фотодамп дня — один на Threads (первые 4 кадра) и Instagram (вся карусель). Выбирается раз в день."""
    d = today()
    old = st["day"].get(d)
    if old:
        imgs = old.get("images") or ([old["image"]] if old.get("image") else [])
        if imgs and all(os.path.exists(os.path.join(ROOT, x)) for x in imgs):
            return dict(old, images=imgs)
    if plan.get("day"):
        return plan["day"][d]
    dumps = CONTENT.get("dumps") or []
    item = next_item(dumps, list(st["used_photos"])) if dumps else next_item(CONTENT["photos"], list(st["used_photos"]))
    shots = item.get("shots") or [item["query"]]
    own = inbox_dump(d)
    used = set(map(str, st["pexels_ids"]))
    new_ids = []
    if own:
        imgs, caption, src = own
        plan["mark"]["inbox"] = src
        meta = {"source": "inbox", "file": src}
    else:
        imgs, caption = [], None
        for i, q in enumerate(shots, 1):
            rel = f"persona/media/{d}-{item['id']}-{i}.jpg"
            try:
                m = stock_photo(q, used, os.path.join(ROOT, rel))
            except Exception as e:
                print(f"::warning title=Фото::{q}: {e}")
                m = None
            if m:
                imgs.append(rel)
                new_ids.append(m.get("pexels_id"))
        meta = {"source": "stock", "shots": len(imgs)}
        if len(imgs) < (2 if len(shots) > 1 else 1):
            return None
    ig = caption or item["ig"]
    th = caption or item["th"]
    day = {"item": item["id"], "images": imgs, "ig": ig, "th": th, "music": item.get("music"), "place": item.get("place"), "meta": meta}
    plan["day"] = {d: day}
    plan["mark"]["photo"] = item["id"]
    plan["mark"]["pexels_ids"] = [x for x in new_ids if x]
    return day


# ---------- карточка разбора для Instagram ----------
def font(name, size, var=None):
    from PIL import ImageFont
    f = ImageFont.truetype(os.path.join(PDIR, "fonts", name), size)
    if var:
        try:
            f.set_variation_by_name(var)
        except Exception:
            pass
    return f


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def crest(p, side, size):
    from PIL import Image, ImageDraw
    from build_pages import logo_for, initials
    c = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    logo = logo_for(p, side)
    path = os.path.join(ROOT, logo) if logo else None
    if path and os.path.exists(path):
        d.ellipse((0, 0, size - 1, size - 1), fill=(242, 239, 232, 255))
        lg = Image.open(path).convert("RGBA")
        box = int(size * 0.62)
        r = min(box / lg.width, box / lg.height)
        lg = lg.resize((max(1, int(lg.width * r)), max(1, int(lg.height * r))), Image.LANCZOS)
        c.alpha_composite(lg, ((size - lg.width) // 2, (size - lg.height) // 2))
    else:
        d.ellipse((0, 0, size - 1, size - 1), fill=(201, 169, 110, 255))
        f = font("InterDisplay-Black.otf", size // 3)
        t = initials(p[side])
        d.text((size / 2, size / 2), t, font=f, fill=(10, 10, 10), anchor="mm")
    return c


def render_card(p, dst):
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1080, 1350
    GOLD, WHITE, GREY = (201, 169, 110), (245, 242, 235), (150, 146, 138)
    im = Image.new("RGB", (W, H), (9, 9, 9))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-200, -380, W + 200, 520), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    im = Image.composite(Image.new("RGB", (W, H), (60, 48, 28)), im, glow).convert("RGBA")
    d = ImageDraw.Draw(im)
    M = 84
    d.text((M, 96), "Р А З Б О Р   М А Т Ч А", font=font("Inter-SemiBold.otf", 26), fill=GOLD)
    d.text((W - M, 92), "В.И.П.", font=font("Lora-Variable.ttf", 34, "Bold"), fill=GOLD, anchor="ra")
    when = f"{p.get('league', '')} · {tb.human(p['date'])}, {p['time']} МСК"
    d.text((M, 146), when, font=font("Inter-Regular.otf", 28), fill=GREY)

    S, top = 230, 250
    for side, cx in (("home", W * 0.27), ("away", W * 0.73)):
        im.alpha_composite(crest(p, side, S), (int(cx - S / 2), top))
        fn = font("Inter-SemiBold.otf", 36)
        y = top + S + 30
        for line in wrap(d, p[side], fn, 380)[:2]:
            d.text((cx, y), line, font=fn, fill=WHITE, anchor="ma")
            y += 46
    d.text((W / 2, top + S / 2), "vs", font=font("Lora-Italic-Variable.ttf", 64, "Italic"), fill=GOLD, anchor="mm")

    y = 690
    d.line((M, y, W - M, y), fill=(70, 60, 42), width=2)
    y += 48
    d.text((M, y), "М О Й   В Ы Б О Р", font=font("Inter-SemiBold.otf", 26), fill=GOLD)
    y += 54
    fp = font("Lora-Variable.ttf", 76, "Bold")
    for line in wrap(d, p["pick"], fp, W - 2 * M)[:2]:
        d.text((M, y), line, font=fp, fill=WHITE)
        y += 92
    y += 14
    d.text((M, y), f"коэффициент {tb.k(p['odds'])}", font=font("InterDisplay-Black.otf", 48), fill=GOLD)
    y += 96
    if p.get("prob"):
        pr = max(0, min(100, round(float(p["prob"]))))
        d.text((M, y), f"Моя оценка вероятности — {pr}%", font=font("Inter-Regular.otf", 30), fill=GREY)
        y += 52
        d.rounded_rectangle((M, y, W - M, y + 14), 7, fill=(40, 36, 30))
        d.rounded_rectangle((M, y, M + (W - 2 * M) * pr / 100, y + 14), 7, fill=GOLD)

    d.line((M, H - 196, W - M, H - 196), fill=(70, 60, 42), width=2)
    d.text((M, H - 160), PERSONA["name"], font=font("Lora-Italic-Variable.ttf", 40, "Italic"), fill=WHITE)
    d.text((M, H - 102), "18+ · Это мнение, а не гарантия · Только легальные БК", font=font("Inter-Regular.otf", 26), fill=GREY)
    d.text((M, H - 66), "Полный разбор — в Telegram, ссылка в профиле", font=font("Inter-Regular.otf", 26), fill=GREY)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.convert("RGB").save(dst, "JPEG", quality=92, optimize=True)


# ---------- тексты ----------
def intro(p):
    lst = CONTENT.get("sport_intros") or ["Мой разбор на сегодня."]
    return lst[sum(map(ord, p["id"])) % len(lst)]


def th_single(p):
    em = tb.SPORT_EMOJI.get(p.get("sport"), "🏆")
    head = (f"{intro(p)}\n\n{em} {p['home']} — {p['away']}\n"
            f"{p.get('league', '')}, {tb.human(p['date'])}, {p['time']} МСК\n\n"
            f"Мой выбор: {p['pick']} (кф {tb.k(p['odds'])})")
    tail = f"{SPORT_FOOT} Полный разбор — в Telegram, ссылка в комментарии 👇\n18+ {tb.TOPIC}"
    return tb.fit(head, p.get("text", ""), tail)


def th_express(legs, day):
    total = 1.0
    lines = []
    for p in legs:
        total *= float(p["odds"])
        lines.append(f"▪️ {p['home']} — {p['away']}: {p['pick']} ({tb.k(p['odds'])})")
    head = f"Вечерние матчи, которые я смотрю ({tb.human(day)}):\n\n" + "\n".join(lines) + f"\n\nВместе — кф {total:.2f}"
    body = "Экспресс — это риск: одна ошибка, и всё мимо. Играю только на ту сумму, которую готов потерять."
    tail = f"Разбор каждого матча — в Telegram, ссылка в комментарии 👇\n18+ {tb.TOPIC}"
    return tb.fit(head, body, tail)


def ig_sport(p):
    text = p.get("text", "")
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0].rstrip(",.;:—- ") + "…"
    tag = SPORT_TAG.get(p.get("sport"), "#спорт")
    return (f"{intro(p)}\n\n{p['home']} — {p['away']}\n{p.get('league', '')}, {tb.human(p['date'])}, {p['time']} МСК\n"
            f"Мой выбор: {p['pick']}, кф {tb.k(p['odds'])}\n\n{text}\n\n"
            "Это моё мнение, а не гарантия результата. Ставки — только в легальных букмекерских компаниях "
            "и только на сумму, которую не жалко потерять.\n\n"
            "Полный разбор и другие матчи — в Telegram, ссылка в шапке профиля.\n18+\n\n"
            f"#прогнознаспорт {tag} #аналитика")


# ---------- планирование слота ----------
def thought_post(st, plan):
    t = next_item(CONTENT["thoughts"], list(st["used_thoughts"]))
    plan["mark"]["thought"] = t["id"]
    plan["posts"].append({"platform": "threads", "text": t["th"]})


def prepare(slot):
    st = load_state()
    d = today()
    n = day_no()
    key = f"{slot}:{d}"
    plan = {"slot": slot, "key": key, "posts": [], "mark": {}, "day": None, "created": now().isoformat(timespec="seconds")}
    if key in st["posted"]:
        print(f"Слот {key} уже опубликован")
        return write_outbox(None)
    preds = tb.load()

    if slot == "th_morning":
        thought_post(st, plan)

    elif slot == "th_sport":
        used = set(v.get("sport") for v in st["posted"].values() if v.get("slot") in ("th_sport", "th_evening"))
        p = tb.pick_tag(preds, "bet_of_day")
        if p and p["id"] in used:
            day_preds, _ = tb.open_today(preds)
            rest = [x for x in day_preds if x["id"] not in used]
            p = max(rest, key=lambda x: (x.get("prob") or 50) * float(x["odds"])) if rest else None
        if p:
            plan["posts"].append({"platform": "threads", "text": th_single(p), "tg_reply": True})
            plan["mark"]["sport"] = p["id"]
        else:
            print("Нет прогнозов на сегодня — вместо разбора публикую мысль")
            thought_post(st, plan)

    elif slot == "th_photo":
        day = photo_of_day(st, plan)
        if day:
            plan["posts"].append({"platform": "threads", "text": day["th"], "images": day["images"][:4]})
        else:
            print("::warning title=Персонаж::Нет фото (нет ключа фотобанка PIXABAY_API_KEY / PEXELS_API_KEY и пустая папка persona/inbox) — публикую мысль")
            thought_post(st, plan)

    elif slot == "ig_post":
        sport_day = n % 10 in (2, 5, 8)
        p = None
        if sport_day:
            used = set(v.get("sport") for v in st["posted"].values() if v.get("slot") == "ig_post")
            day_preds, _ = tb.open_today(preds)
            p = tb.pick_tag(preds, "bet_of_day")
            if p and p["id"] in used:
                p = next((x for x in sorted(day_preds, key=tb.start) if x["id"] not in used), None)
        if p:
            rel = f"persona/media/{d}-card-{p['id']}.jpg"
            render_card(p, os.path.join(ROOT, rel))
            plan["posts"].append({"platform": "instagram", "text": ig_sport(p), "images": [rel]})
            plan["mark"]["sport"] = p["id"]
        else:
            day = photo_of_day(st, plan)
            if not day:
                print("::warning title=Персонаж::Нет фото для Instagram — пост пропущен")
                return write_outbox(None)
            plan["posts"].append({"platform": "instagram", "text": day["ig"], "images": day["images"], "music": day.get("music")})

    elif slot == "th_evening":
        if n % 3 == 0:
            legs, dd = tb.express(preds)
            if legs:
                plan["posts"].append({"platform": "threads", "text": th_express(legs, dd), "tg_reply": True})
                plan["mark"]["sport"] = "express:" + dd
            else:
                morning = st["posted"].get(f"th_sport:{d}", {}).get("sport")
                p = tb.pick_tag(preds, "lock_of_day")
                if p and p["id"] != morning:
                    plan["posts"].append({"platform": "threads", "text": th_single(p), "tg_reply": True})
                    plan["mark"]["sport"] = p["id"]
        if not plan["posts"]:
            thought_post(st, plan)
    else:
        sys.exit(f"Неизвестный слот: {slot}")
    write_outbox(plan)


def write_outbox(plan):
    if plan is None:
        if os.path.exists(OUTBOX):
            os.remove(OUTBOX)
        return
    with open(OUTBOX, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    for post in plan["posts"]:
        print(f"----- {plan['key']} → {post['platform']} ({len(post['text'])} симв.){' + фото: ' + str(len(post['images'])) if post.get('images') else ''} -----")
        print(post["text"])
        if post.get("tg_reply"):
            print(f"[комментарий] {REPLIES[0].format(tg=TG)}")
        print()


# ---------- публикация ----------
def call(base, method, path, params, token):
    params = dict(params, access_token=token)
    url = f"{base}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{base.split('/')[2]} {e.code}: {e.read()[:400]!r}")


def wait_ready(base, cid, field, token, ok="FINISHED"):
    for _ in range(30):
        s = call(base, "GET", cid, {"fields": field}, token).get(field)
        if s == ok:
            return
        if s in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Контейнер {cid}: {s}")
        time.sleep(5)
    raise RuntimeError(f"Контейнер {cid} не обработан за 150 секунд")


def media_url(rel):
    base = os.environ.get("PERSONA_MEDIA_BASE")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "smash0963sk/metod-vipbet")
        base = f"https://raw.githubusercontent.com/{repo}/main/"
    return base.rstrip("/") + "/" + rel


def threads_post(text, images=None, reply_to=None, link=None):
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ.get("THREADS_USER_ID") or call(TH_API, "GET", "me", {"fields": "id"}, tok)["id"]
    images = images or []
    params = {"text": text}
    if len(images) > 1:  # карусель: сначала контейнер на каждый кадр
        kids = []
        for img in images[:20]:
            k = call(TH_API, "POST", f"{uid}/threads", {"media_type": "IMAGE", "image_url": media_url(img), "is_carousel_item": "true"}, tok)["id"]
            wait_ready(TH_API, k, "status", tok)
            kids.append(k)
        params.update(media_type="CAROUSEL", children=",".join(kids))
    elif images:
        params.update(media_type="IMAGE", image_url=media_url(images[0]))
    else:
        params["media_type"] = "TEXT"
    if reply_to:
        params["reply_to_id"] = reply_to
    if link:
        params["link_attachment"] = link
    cid = call(TH_API, "POST", f"{uid}/threads", params, tok)["id"]
    if images:
        wait_ready(TH_API, cid, "status", tok)
    else:
        time.sleep(5)
    return call(TH_API, "POST", f"{uid}/threads_publish", {"creation_id": cid}, tok)["id"]


def instagram_post(caption, images):
    tok = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    uid = os.environ.get("INSTAGRAM_USER_ID") or call(IG_API, "GET", "me", {"fields": "user_id"}, tok)["user_id"]
    if len(images) > 1:
        kids = []
        for img in images[:10]:
            k = call(IG_API, "POST", f"{uid}/media", {"image_url": media_url(img), "is_carousel_item": "true"}, tok)["id"]
            wait_ready(IG_API, k, "status_code", tok)
            kids.append(k)
        cid = call(IG_API, "POST", f"{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption}, tok)["id"]
    else:
        cid = call(IG_API, "POST", f"{uid}/media", {"image_url": media_url(images[0]), "caption": caption}, tok)["id"]
    wait_ready(IG_API, cid, "status_code", tok)
    return call(IG_API, "POST", f"{uid}/media_publish", {"creation_id": cid}, tok)["id"]


# ---------- доставка в личный Telegram (полуавтомат, пока нет доступа к API Meta) ----------
SLOT_INFO = {
    "th_morning": ("Threads", "09:10", "мысль дня"),
    "th_sport": ("Threads", "12:40", "разбор матча"),
    "th_photo": ("Threads", "16:10", "фото дня"),
    "ig_post": ("Instagram", "18:30", "пост"),
    "th_evening": ("Threads", "20:10", "вечерний пост"),
}


def tg_call(method, fields, files=None):
    """files: {"имя_поля": путь}; для sendMediaGroup картинки передаются как attach://имя_поля."""
    url = f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/{method}"
    if files:
        boundary = "----persona" + str(int(time.time() * 1000))
        body = b""
        for k, v in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, path in files.items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{os.path.basename(path)}"\r\n'
                     "Content-Type: image/jpeg\r\n\r\n").encode() + open(path, "rb").read() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)["result"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram {e.code}: {e.read()[:300]!r}")


def tg_chat(st):
    """Куда слать: секрет TG_CHAT_ID, сохранённый чат или тот, кто написал боту /start."""
    chat = os.environ.get("TG_CHAT_ID") or st.get("tg_chat")
    if chat:
        return chat
    for u in reversed(tg_call("getUpdates", {"limit": 100})):
        c = (u.get("message") or {}).get("chat") or {}
        if c.get("type") == "private":
            st["tg_chat"] = str(c["id"])
            return st["tg_chat"]
    return None


def tg_deliver(plan, post, st, chat):
    import html as h
    where, at, kind = SLOT_INFO.get(plan["slot"], ("Threads", "", "пост"))
    if post["platform"] == "instagram":
        where = "Instagram"
        kind = "карточка разбора матча" if plan["mark"].get("sport") else "фотодамп дня"
    icon = "📸" if where == "Instagram" else "🧵"
    head = f"{icon} <b>{where}</b> · {kind}\nОпубликовать в {at} МСК (или запланировать в приложении)"
    imgs = post.get("images") or []
    if len(imgs) > 1:
        head += f"\nКарусель из {len(imgs)} фото — сохраните все и выложите одним постом в том же порядке."
    elif imgs:
        head += "\n\nСохраните фото: нажмите на него → «Сохранить»."
    if post.get("music"):
        head += f"\n🎵 Музыка (добавьте в приложении): {h.escape(post['music'])}"
    if len(imgs) > 1:
        tg_call("sendMessage", {"chat_id": chat, "text": head, "parse_mode": "HTML"})
        for start_i in range(0, len(imgs), 10):
            part = imgs[start_i:start_i + 10]
            media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(part))]
            tg_call("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)},
                    {f"p{i}": os.path.join(ROOT, x) for i, x in enumerate(part)})
    elif imgs:
        tg_call("sendPhoto", {"chat_id": chat, "caption": head, "parse_mode": "HTML"}, {"photo": os.path.join(ROOT, imgs[0])})
    else:
        tg_call("sendMessage", {"chat_id": chat, "text": head, "parse_mode": "HTML"})
    tg_call("sendMessage", {"chat_id": chat, "parse_mode": "HTML",
                            "text": f"Текст поста — нажмите на блок, чтобы скопировать:\n<pre>{h.escape(post['text'])}</pre>"})
    if post.get("tg_reply"):
        reply = REPLIES[len(st["posted"]) % len(REPLIES)].format(tg=TG)
        tg_call("sendMessage", {"chat_id": chat, "parse_mode": "HTML", "disable_web_page_preview": "true",
                                "text": f"Сразу после публикации — <b>первым комментарием</b> под постом:\n<pre>{h.escape(reply)}</pre>"})
    return "telegram"


def publish():
    if not os.path.exists(OUTBOX):
        print("Публиковать нечего")
        return
    plan = json.load(open(OUTBOX, encoding="utf-8"))
    st = load_state()
    dry = os.environ.get("DRY_RUN") == "1"
    ids = []
    for post in plan["posts"]:
        plat = post["platform"]
        need = "THREADS_ACCESS_TOKEN" if plat == "threads" else "INSTAGRAM_ACCESS_TOKEN"
        if dry or (not os.environ.get(need) and not os.environ.get("TG_BOT_TOKEN")):
            why = "включён режим проверки" if dry else f"нет секрета {need} или TG_BOT_TOKEN"
            print(f"::notice title=Персонаж ({plat})::{plan['key']}: не опубликовано — {why}")
            continue
        if not os.environ.get(need):
            chat = tg_chat(st)
            if not chat:
                print("::warning title=Персонаж::Не знаю, куда присылать посты: напишите своему боту /start в Telegram")
                continue
            ids.append(tg_deliver(plan, post, st, chat))
            print(f"::notice title=Персонаж ({plat})::{plan['key']}: готовый пост отправлен вам в Telegram")
            continue
        if plat == "threads":
            pid = threads_post(post["text"], post.get("images"))
            if post.get("tg_reply"):
                time.sleep(10)
                reply = REPLIES[len(st["posted"]) % len(REPLIES)].format(tg=TG)
                try:
                    threads_post(reply, reply_to=pid, link=TG)
                except Exception as e:
                    print(f"::warning title=Threads::Пост вышел, но комментарий со ссылкой не добавлен: {e}")
        else:
            pid = instagram_post(post["text"], post["images"])
        ids.append(pid)
        print(f"::notice title=Персонаж ({plat})::Опубликовано {plan['key']}, id {pid}")
    if not ids:
        return
    m = plan["mark"]
    if m.get("photo") and m["photo"] not in st["used_photos"]:
        st["used_photos"].append(m["photo"])
    if m.get("thought"):
        st["used_thoughts"].append(m["thought"])
    st["pexels_ids"].extend(m.get("pexels_ids") or [])
    if plan.get("day"):
        st["day"].update(plan["day"])
    if m.get("inbox"):
        src = os.path.join(ROOT, m["inbox"])
        if os.path.isdir(src):
            shutil.rmtree(src)
        for f in (src, os.path.splitext(src)[0] + ".txt"):
            if os.path.isfile(f):
                os.remove(f)
    st["posted"][plan["key"]] = {"at": now().isoformat(timespec="seconds"), "slot": plan["slot"], "ids": ids, "sport": m.get("sport")}
    save_state(st)
    os.remove(OUTBOX)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prepare" and len(sys.argv) > 2:
        prepare(sys.argv[2])
    elif cmd == "publish":
        publish()
    else:
        sys.exit(__doc__)
