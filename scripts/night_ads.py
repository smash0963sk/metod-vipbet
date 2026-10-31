"""Ночная реклама в Telegram-канале.

Вы присылаете боту канала (@Metod_vvvbot) в личку ссылку — бот пишет рекламные посты и ночью сам выкладывает:
3 основных поста (с картинкой и кнопкой) и к каждому — 2 коротких напоминания ответом на пост.
Утром (08:30 МСК) бот удаляет ночную рекламу, если не написано «без удаления».

Типы основных постов: VIP-канал · лесенка · экспресс · проходимость. За ночь — 3 из 4 по очереди,
или те, что вы указали в сообщении (например: «вип лесенка экспресс»).

Сообщение боту (всё, кроме ссылки, — по желанию, каждое с новой строки):
    https://t.me/+AbCdEf
    вип лесенка проходимость
    erid: 2SDnjc...
    рекламодатель: ИП Иванов И.И.
    название: Ставки от Макса
    без удаления
Команды: /status — очередь, /cancel — убрать последнюю ссылку, /stop — остановить рекламу этой ночью,
/delete — удалить уже вышедшие посты этой ночи, /help.

Режимы:  python scripts/night_ads.py inbox   — прочитать сообщения, удалить утреннюю рекламу (каждые 15 минут)
         python scripts/night_ads.py night   — ночная смена 22:50–04:30 МСК: публикует по плану и отвечает на сообщения
         python scripts/night_ads.py preview https://t.me/+abc [типы]  — показать посты без публикации
"""
import datetime as dt, html, json, os, random, re, subprocess, sys, time, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import persona_bot as pb

MSK = ZoneInfo("Europe/Moscow")
STATE_F = os.path.join(ROOT, "data", "night_ads.json")
CARD_DIR = os.path.join(ROOT, "data", "night_cards")
MAIN_TIMES = ["23:00", "01:00", "03:00"]   # основные посты (МСК); после полуночи — уже следующая дата
REMIND_AFTER = [40, 80]                    # напоминания: через 40 и 80 минут после основного поста
DEADLINE = "22:45"                         # ссылка, присланная позже, уходит на следующую ночь
DELETE_AT = "08:30"                        # утреннее удаление ночной рекламы
NIGHT_END = "04:30"
ORDER = ["vip", "ladder", "express", "rate"]
KEYWORDS = {"vip": ("вип", "vip"), "ladder": ("лесенк", "лестниц"), "express": ("экспресс", "экспрес"),
            "rate": ("проходим", "статист")}
DISCLAIMER = "<blockquote><i>18+ · Ставки — только в легальных БК · Прогноз — не гарантия выигрыша</i></blockquote>"

# ---------- тексты ----------
# Без обещаний дохода, «100% заходов» и выдуманной статистики: такие формулировки — недостоверная реклама (ФЗ «О рекламе»).
TYPES = {
    "vip": {
        "emoji": "💎", "label": "V I P   К А Н А Л", "big": "VIP-канал по ставкам на спорт", "color": (233, 185, 73), "btn": "💎 Вступить в VIP",
        "main": [
            "💎 <b>VIP-КАНАЛ ПО СТАВКАМ НА СПОРТ</b>\n\n{name}Пока все спят — самое время подготовиться к завтрашним матчам. "
            "В канале каждый день разбирают игры по футболу и хоккею и объясняют, почему выбран именно этот исход.\n\n"
            "<blockquote>• Прогнозы с разбором, а не просто «П1»\n• Футбол, хоккей, теннис\n• Без «договорняков» и обещаний золотых гор</blockquote>",
            "👑 <b>VIP ДЛЯ ТЕХ, КТО СТАВИТ С ГОЛОВОЙ</b>\n\n{name}Здесь не кричат «100% заход». Здесь считают коэффициенты, "
            "смотрят составы и мотивацию команд — и только потом дают прогноз.\n\n"
            "<blockquote>Подпишись сейчас — разборы на завтра выйдут уже утром.</blockquote>",
            "🔐 <b>ВХОД В VIP ОТКРЫТ</b>\n\n{name}Канал, где прогноз — это не угадайка, а расчёт: статистика, форма, составы. "
            "Каждый день — матчи с подробным разбором.\n\n<blockquote>Заходи, пока есть место, и смотри сам.</blockquote>",
        ],
        "remind": ["💎 VIP-канал ещё открыт — успей зайти до утра 👇", "💎 Разборы на завтра уже готовят. Ты в VIP? 👇",
                   "💎 Напоминаем: VIP-канал по ставкам на спорт 👇", "👑 Ночью вход в VIP открыт — заходи 👇"],
    },
    "ladder": {
        "emoji": "🪜", "label": "Л Е С Е Н К А", "big": "Ночная лесенка стартует", "color": (178, 221, 16), "btn": "🪜 Смотреть лесенку",
        "main": [
            "🪜 <b>НОЧНАЯ ЛЕСЕНКА СТАРТУЕТ</b>\n\n{name}Лесенка — серия ставок, где каждая следующая делается из выигрыша предыдущей. "
            "В канале каждую ступень разбирают отдельно: матч, коэффициент, логика выбора.\n\n"
            "<blockquote>Следи за ступенями и решай сам. Ставь только ту сумму, которую не жалко потерять.</blockquote>",
            "🪜 <b>ЛЕСЕНКА: ШАГ ЗА ШАГОМ</b>\n\n{name}Небольшие коэффициенты, подробный разбор каждого матча и честный итог по каждой ступени.\n\n"
            "<blockquote>Интересно, дойдёт ли лесенка до конца? Подпишись и смотри в реальном времени.</blockquote>",
            "📈 <b>НОВАЯ ЛЕСЕНКА — В КАНАЛЕ</b>\n\n{name}Одна ступень — один матч с разбором. Видно каждую ставку и каждый результат.\n\n"
            "<blockquote>Начни следить с первой ступени.</blockquote>",
        ],
        "remind": ["🪜 Лесенка уже идёт — следи за ступенями 👇", "🪜 Новая ступень лесенки — в канале 👇",
                   "🪜 Не пропусти лесенку этой ночью 👇", "📈 Лесенка с разбором каждого матча 👇"],
    },
    "express": {
        "emoji": "🔥", "label": "Э К С П Р Е С С", "big": "Экспресс с разбором каждого события", "color": (255, 122, 48), "btn": "🔥 Забрать экспресс",
        "main": [
            "🔥 <b>НОЧНОЙ ЭКСПРЕСС</b>\n\n{name}Экспресс из 3–4 событий, и каждое разобрано: форма команд, составы, мотивация. "
            "Ничего лишнего — только матчи и логика.\n\n"
            "<blockquote>Экспресс — это риск: не зашло одно событие — не зашло всё. Поэтому здесь каждое событие с разбором.</blockquote>",
            "⚡ <b>ЭКСПРЕСС ДНЯ — В КАНАЛЕ</b>\n\n{name}Футбол, хоккей, теннис — самые интересные события дня в одном купоне. "
            "Разбор каждого события и итог после матчей.\n\n<blockquote>Посмотри до старта матчей.</blockquote>",
            "🔥 <b>ЭКСПРЕСС НА ЗАВТРА УЖЕ СОБИРАЮТ</b>\n\n{name}Отбирают события, где коэффициент выглядит недооценённым, "
            "и объясняют каждый выбор.\n\n<blockquote>Подпишись, чтобы не пропустить публикацию.</blockquote>",
        ],
        "remind": ["🔥 Ночной экспресс — в канале 👇", "⚡ Экспресс с разбором каждого события 👇",
                   "🔥 Успей посмотреть экспресс до старта матчей 👇", "⚡ Напоминаем про экспресс дня 👇"],
    },
    "rate": {
        "emoji": "📊", "label": "П Р О Х О Д И М О С Т Ь", "big": "Проходимость, которую можно проверить", "color": (64, 196, 255), "btn": "📊 Проверить канал",
        "main": [
            "📊 <b>ПРОХОДИМОСТЬ, КОТОРУЮ МОЖНО ПРОВЕРИТЬ</b>\n\n{name}Не верь скринам — смотри ленту. "
            "Прогнозы публикуются до матча, а результат виден каждому: листай и считай сам.\n\n"
            "<blockquote>Высокая проходимость — это когда её не нужно доказывать словами.</blockquote>",
            "✅ <b>КАНАЛ С ВЫСОКОЙ ПРОХОДИМОСТЬЮ ПРОГНОЗОВ?</b>\n\n{name}Не принимай на веру — проверь. "
            "Открой канал, пролистай последние прогнозы и посмотри, сколько из них зашло.\n\n"
            "<blockquote>Решение — за тобой.</blockquote>",
            "📊 <b>СЧИТАЙ САМ</b>\n\n{name}Каждый прогноз — с матчем, коэффициентом и временем публикации. "
            "Всё на виду, всё можно пересчитать.\n\n<blockquote>Хороший канал не боится, что его проверят.</blockquote>",
        ],
        "remind": ["📊 Проверь проходимость прогнозов сам 👇", "✅ Прогнозы публикуются до матча — смотри ленту 👇",
                   "📊 Канал, где проходимость можно пересчитать 👇", "✅ Не верь скринам — проверь ленту 👇"],
    },
}


def e(s):
    return html.escape(s or "", quote=False)


def ad_line(ad):
    """Маркировка рекламы: «Реклама» + рекламодатель + erid (если прислали)."""
    parts = ["Реклама"]
    if ad.get("advertiser"):
        parts.append(e(ad["advertiser"]).rstrip("."))
    if ad.get("erid"):
        parts.append("erid: " + e(ad["erid"]))
    return "<i>" + ". ".join(parts) + "</i>"


def main_text(ad, kind, variant):
    t = TYPES[kind]
    name = f"📢 Канал <b>«{e(ad['name'])}»</b>\n\n" if ad.get("name") else ""
    body = t["main"][variant % len(t["main"])].replace("{name}", name)
    return f"{body}\n\n👉 <a href=\"{e(ad['link'])}\">Перейти в канал</a>\n\n{DISCLAIMER}\n{ad_line(ad)}"


def remind_text(ad, kind, k):
    t = TYPES[kind]
    return f"{t['remind'][k % len(t['remind'])]}\n<a href=\"{e(ad['link'])}\">{e(ad.get('name') or 'Перейти в канал')}</a>\n\n<i>18+ · {ad_line(ad)[3:]}"


def button(ad, kind):
    return json.dumps({"inline_keyboard": [[{"text": TYPES[kind]["btn"], "url": ad["link"]}]]})


# ---------- картинка ----------
def card(ad, kind, rel):
    from PIL import Image, ImageDraw, ImageFilter
    t = TYPES[kind]
    W, H = 1080, 1080
    col = t["color"]
    im = Image.new("RGB", (W, H), (9, 9, 9))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-220, -420, W + 220, 560), fill=90)
    tint = tuple(int(c * 0.22) for c in col)
    im = Image.composite(Image.new("RGB", (W, H), tint), im, glow.filter(ImageFilter.GaussianBlur(170)))
    d = ImageDraw.Draw(im)
    d.text((84, 96), t["label"], font=pb.font("Inter-SemiBold.otf", 28), fill=col)
    d.text((W - 84, 92), "НОЧЬ", font=pb.font("InterDisplay-Black.otf", 34), fill=col, anchor="ra")
    fb = pb.font("InterDisplay-Black.otf", 96)
    lines = pb.wrap(d, t["big"].upper(), fb, W - 168)
    while len(lines) > 4:
        fb = pb.font("InterDisplay-Black.otf", fb.size - 8)
        lines = pb.wrap(d, t["big"].upper(), fb, W - 168)
    y = 330
    d.rectangle((84, y - 50, 184, y - 38), fill=col)
    for ln in lines:
        d.text((84, y), ln, font=fb, fill=(245, 242, 235))
        y += int(fb.size * 1.1)
    if ad.get("name"):
        y += 30
        fn = pb.font("Inter-SemiBold.otf", 44)
        for ln in pb.wrap(d, ad["name"], fn, W - 168)[:2]:
            d.text((84, y), ln, font=fn, fill=col)
            y += 56
    d.line((84, H - 170, W - 84, H - 170), fill=tuple(int(c * 0.4) for c in col), width=2)
    d.text((84, H - 130), "Подписаться — по кнопке под постом", font=pb.font("Inter-Regular.otf", 32), fill=(170, 166, 158))
    d.text((W - 84, H - 130), "18+", font=pb.font("Inter-SemiBold.otf", 32), fill=(170, 166, 158), anchor="ra")
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, "JPEG", quality=92, optimize=True)
    return rel


# ---------- время и план ночи ----------
def now():
    fake = os.environ.get("NIGHT_NOW")  # для проверки: NIGHT_NOW=2026-11-01T23:10
    return dt.datetime.fromisoformat(fake).replace(tzinfo=MSK) if fake else dt.datetime.now(MSK)


def at(night_date, hm):
    """Время ночи: всё, что раньше полудня, — уже следующие сутки."""
    h, m = map(int, hm.split(":"))
    d = dt.date.fromisoformat(night_date) + dt.timedelta(days=1 if h < 12 else 0)
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=MSK)


def plan(ad):
    items = []
    for i, (hm, kind) in enumerate(zip(MAIN_TIMES, ad["types"])):
        t0 = at(ad["night"], hm)
        items.append({"key": f"m{i}", "t": t0, "kind": kind, "main": True, "variant": ad["seed"] + i})
        for k, mins in enumerate(REMIND_AFTER):
            items.append({"key": f"m{i}r{k}", "t": t0 + dt.timedelta(minutes=mins), "kind": kind, "main": False, "of": f"m{i}",
                          "variant": ad["seed"] + i * 2 + k})
    return items


def night_label(night):
    d = dt.date.fromisoformat(night)
    n = d + dt.timedelta(days=1)
    mon = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"в ночь на {n.day} {mon[n.month - 1]} (с {MAIN_TIMES[0]} МСК {d.day} {mon[d.month - 1]})"


# ---------- состояние ----------
def load():
    try:
        st = json.load(open(STATE_F, encoding="utf-8"))
    except FileNotFoundError:
        st = {}
    st.setdefault("offset", 0)
    st.setdefault("queue", [])
    st.setdefault("count", 0)
    return st


def save(st):
    st["queue"] = st["queue"][-60:]
    os.makedirs(os.path.dirname(STATE_F), exist_ok=True)
    json.dump(st, open(STATE_F, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)


def commit(st, msg="Ночная реклама: состояние"):
    save(st)
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    sh = lambda *a: subprocess.run(a, cwd=ROOT, capture_output=True, text=True)
    sh("git", "config", "user.name", "github-actions[bot]")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", "data/night_ads.json")
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        return
    sh("git", "commit", "-m", msg)
    for _ in range(5):
        if sh("git", "pull", "--rebase", "origin", "main").returncode == 0 and sh("git", "push", "origin", "HEAD:main").returncode == 0:
            return
        time.sleep(random.randint(4, 12))
    print("::warning title=Ночная реклама::не удалось сохранить состояние в репозиторий")


# ---------- Telegram ----------
def token():
    return os.environ.get("TG_CHANNEL_BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")


def tg(method, fields, files=None):
    os.environ["TG_BOT_TOKEN"] = token()
    return pb.tg_call(method, fields, files)


def owner():
    o = os.environ.get("TG_OWNER_ID")
    if o:
        return o
    try:
        return str(json.load(open(os.path.join(ROOT, "persona", "state.json"), encoding="utf-8")).get("tg_chat") or "")
    except FileNotFoundError:
        return ""


def channel():
    ch = os.environ.get("TG_CHANNEL_ID")
    if ch:
        return ch
    return json.load(open(os.path.join(ROOT, "data", "tg_channel_state.json"), encoding="utf-8")).get("channel")


def say(text, **kw):
    try:
        return tg("sendMessage", dict({"chat_id": owner(), "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}, **kw))
    except Exception as ex:
        print(f"::warning title=Ночная реклама::не смог ответить: {ex}")


# ---------- разбор сообщения ----------
LINK_RE = re.compile(r"(https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{5,})")


def norm_link(s):
    s = s.strip().rstrip(".,)")
    if s.startswith("@"):
        return "https://t.me/" + s[1:]
    if s.startswith("t.me/"):
        return "https://" + s
    return s


def channel_name(link):
    """Название канала со страницы t.me (работает и для приглашений t.me/+...)."""
    if "t.me/" not in link:
        return None
    try:
        req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
        page = urllib.request.urlopen(req, timeout=20).read(200000).decode("utf-8", "replace")
        m = re.search(r'<meta property="og:title" content="([^"]+)"', page)
        name = html.unescape(m.group(1)).strip() if m else None
        if name and not name.lower().startswith("telegram"):
            return name[:60]
    except Exception as ex:
        print(f"название канала не получено: {ex}")
    return None


def parse(text):
    m = LINK_RE.search(text)
    if not m:
        return None
    ad = {"link": norm_link(m.group(1)), "delete": True}
    m_erid = re.search(r"(?i)erid\s*:\s*([A-Za-z0-9]+)", text)
    if m_erid:
        ad["erid"] = m_erid.group(1)
    low = text.lower()
    for line in text.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k.startswith("рекламодатель") and v:
            ad["advertiser"] = v
        elif k.startswith("назван") and v:
            ad["name"] = v[:60]
    if "без удален" in low or "не удаля" in low:
        ad["delete"] = False
    types = []
    for word in re.findall(r"[a-zа-яё]+", low):
        for kind, keys in KEYWORDS.items():
            if word.startswith(keys) and kind not in types:
                types.append(kind)
    ad["types_asked"] = types
    return ad


def next_night(st):
    t = now()
    first = t.date() if t < t.replace(hour=int(DEADLINE[:2]), minute=int(DEADLINE[3:]), second=0) else t.date() + dt.timedelta(days=1)
    if t.hour < 5:  # сейчас ночь — сегодняшняя ночь уже идёт
        first = t.date()
    busy = {a["night"] for a in st["queue"] if a.get("status") in ("queued", "running")}
    d = first
    while str(d) in busy:
        d += dt.timedelta(days=1)
    return str(d)


def pick_types(st, asked):
    types = list(asked)
    i = st["count"]
    while len(types) < len(MAIN_TIMES):
        k = ORDER[i % len(ORDER)]
        i += 1
        if k not in types:
            types.append(k)
    return types[:len(MAIN_TIMES)]


def enqueue(st, ad):
    ad["name"] = ad.get("name") or channel_name(ad["link"])
    ad["types"] = pick_types(st, ad.pop("types_asked", []))
    ad["night"] = next_night(st)
    ad["seed"] = st["count"]
    ad["id"] = f"ad{st['count'] + 1}"
    ad["status"] = "queued"
    ad["added"] = now().isoformat(timespec="minutes")
    ad["posts"] = {}
    st["count"] += 1
    st["queue"].append(ad)
    return ad


def send_preview(ad):
    names = {"vip": "💎 VIP-канал", "ladder": "🪜 Лесенка", "express": "🔥 Экспресс", "rate": "📊 Проходимость"}
    lines = [f"✅ Принял: {e(ad['link'])}", f"Название: <b>{e(ad.get('name') or 'не нашёл — можно прислать «название: …»')}</b>",
             f"Выйдет {night_label(ad['night'])}:"]
    for hm, kind in zip(MAIN_TIMES, ad["types"]):
        lines.append(f"• {hm} — {names[kind]} + 2 напоминания")
    lines.append("Утром в " + DELETE_AT + " — удалю." if ad["delete"] else "Удалять утром не буду.")
    if not ad.get("erid"):
        lines.append("\n⚠️ Нет erid. Рекламу в Telegram нужно маркировать: пришлите «erid: …» отдельным сообщением, "
                     "и я добавлю его к последней ссылке.")
    lines.append("\nНиже — как будут выглядеть посты. Отменить: /cancel")
    say("\n".join(lines))
    for i, kind in enumerate(ad["types"]):
        rel = card(ad, kind, f"data/night_cards/{ad['id']}-{kind}.jpg")
        try:
            tg("sendPhoto", {"chat_id": owner(), "caption": main_text(ad, kind, ad["seed"] + i), "parse_mode": "HTML",
                             "reply_markup": button(ad, kind)}, {"photo": os.path.join(ROOT, rel)})
        except Exception as ex:
            say(f"Не смог показать пост: {e(str(ex))[:300]}")
    say("Пример напоминания:\n\n" + remind_text(ad, ad["types"][0], ad["seed"]), reply_markup=button(ad, ad["types"][0]))


def tonight(st):
    t = now()
    night = str(t.date() - dt.timedelta(days=1)) if t.hour < 12 else str(t.date())
    return next((a for a in st["queue"] if a["night"] == night and a.get("status") in ("queued", "running", "done", "stopped")), None), night


def delete_posts(ad):
    ch, n = channel(), 0
    for key, mid in list(ad.get("posts", {}).items()):
        try:
            tg("deleteMessage", {"chat_id": ch, "message_id": mid})
            n += 1
        except Exception as ex:
            print(f"::warning title=Ночная реклама::не удалил {mid}: {ex}")
    ad["deleted"] = now().isoformat(timespec="minutes")
    return n


def handle(st, msg):
    text = (msg.get("text") or msg.get("caption") or "").strip()
    cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""
    if cmd in ("/start", "/help"):
        say(__doc__.split("Режимы:")[0].replace("<", "&lt;"))
        return
    if cmd == "/status":
        act = [a for a in st["queue"] if a.get("status") in ("queued", "running")]
        if not act:
            say("Очередь пуста. Пришлите ссылку — поставлю рекламу на ближайшую ночь.")
        else:
            say("\n".join(f"• {night_label(a['night'])}: {e(a.get('name') or a['link'])} — {', '.join(a['types'])}"
                          f"{'' if a.get('erid') else ' · ⚠️ нет erid'}{' · идёт сейчас' if a['status'] == 'running' else ''}" for a in act))
        return
    if cmd == "/cancel":
        q = [a for a in st["queue"] if a.get("status") == "queued"]
        if not q:
            say("Отменять нечего.")
        else:
            q[-1]["status"] = "cancelled"
            say(f"❌ Отменил рекламу {e(q[-1].get('name') or q[-1]['link'])} ({night_label(q[-1]['night'])}).")
        return
    if cmd == "/stop":
        ad, _ = tonight(st)
        if ad and ad["status"] in ("queued", "running"):
            ad["status"] = "stopped"
            say("⏹ Остановил: этой ночью больше постов не будет. Удалить вышедшие — /delete")
        else:
            say("Этой ночью реклама не идёт.")
        return
    if cmd == "/delete":
        ad, _ = tonight(st)
        if ad and ad.get("posts"):
            say(f"🗑 Удалил постов: {delete_posts(ad)}")
        else:
            say("Удалять нечего.")
        return
    m_erid = re.match(r"(?i)^erid\s*:\s*(\S+)", text)
    if m_erid and not LINK_RE.search(text):
        q = [a for a in st["queue"] if a.get("status") == "queued"]
        if q:
            q[-1]["erid"] = m_erid.group(1)
            say(f"✅ erid добавлен к рекламе {e(q[-1].get('name') or q[-1]['link'])}")
        else:
            say("Нет рекламы в очереди, к которой можно добавить erid.")
        return
    ad = parse(text)
    if not ad:
        say("Пришлите ссылку на канал (например https://t.me/+AbCd), и я поставлю ночную рекламу. Помощь — /help")
        return
    ad = enqueue(st, ad)
    send_preview(ad)


def inbox(st, wait=0):
    """Читает личные сообщения боту. Отвечает только владельцу."""
    ups = tg("getUpdates", {"offset": st["offset"], "timeout": wait, "allowed_updates": json.dumps(["message"])})
    me = owner()
    for u in ups:
        st["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue
        if str(chat.get("id")) != me:
            try:
                tg("sendMessage", {"chat_id": chat["id"], "text": "Это частный бот канала. Связаться с администратором — через канал."})
            except Exception:
                pass
            continue
        try:
            handle(st, msg)
        except Exception as ex:
            say(f"Ошибка: {e(str(ex))[:400]}")
            print(f"::warning title=Ночная реклама::{ex}")
    return len(ups)


# ---------- публикация ----------
def post(st, ad, item):
    ch = channel()
    if item["main"]:
        rel = card(ad, item["kind"], f"data/night_cards/{ad['id']}-{item['kind']}.jpg")
        res = tg("sendPhoto", {"chat_id": ch, "caption": main_text(ad, item["kind"], item["variant"]), "parse_mode": "HTML",
                               "reply_markup": button(ad, item["kind"])}, {"photo": os.path.join(ROOT, rel)})
    else:
        f = {"chat_id": ch, "text": remind_text(ad, item["kind"], item["variant"]), "parse_mode": "HTML",
             "disable_web_page_preview": "true", "reply_markup": button(ad, item["kind"])}
        if ad["posts"].get(item["of"]):
            f["reply_parameters"] = json.dumps({"message_id": ad["posts"][item["of"]], "allow_sending_without_reply": True})
        res = tg("sendMessage", f)
    ad["posts"][item["key"]] = res["message_id"]
    print(f"::notice title=Ночная реклама::{item['t']:%H:%M} {item['key']} {item['kind']} → сообщение {res['message_id']}")


def night_shift(st):
    _, night0 = tonight(st)
    end = at(night0, NIGHT_END)
    while True:
        ad, night = tonight(st)
        if ad and ad["status"] in ("queued", "running"):
            ad["status"] = "running"
            todo = [i for i in plan(ad) if i["key"] not in ad["posts"] and i["key"] not in ad.get("skipped", [])]
            if not todo:
                ad["status"] = "done"
                say(f"🌙 Ночная реклама {e(ad.get('name') or ad['link'])} вышла полностью: {len(ad['posts'])} постов."
                    + (f" Удалю в {DELETE_AT}." if ad["delete"] else ""))
                commit(st)
                continue
            item = todo[0]
            if now() >= item["t"]:
                late = now() - item["t"]
                if not item["main"] and late > dt.timedelta(minutes=30):
                    ad.setdefault("skipped", []).append(item["key"])  # сильно опоздали — напоминание пропускаем
                    continue
                try:
                    post(st, ad, item)
                except Exception as ex:
                    ad.setdefault("skipped", []).append(item["key"])
                    say(f"❌ Не вышел пост {item['key']}: {e(str(ex))[:300]}")
                commit(st)
                continue
            wait = (item["t"] - now()).total_seconds()
        else:
            wait = (end - now()).total_seconds()
        if now() >= end:
            break
        if inbox(st, wait=int(max(1, min(50, wait)))):
            commit(st)
    commit(st)


def morning_cleanup(st):
    t = now()
    for ad in st["queue"]:
        if ad.get("delete") and ad.get("posts") and not ad.get("deleted") and t >= at(ad["night"], DELETE_AT):
            if t - at(ad["night"], DELETE_AT) > dt.timedelta(hours=40):  # Telegram даёт удалять только 48 часов
                ad["deleted"] = "слишком поздно"
                continue
            n = delete_posts(ad)
            say(f"🧹 Удалил ночную рекламу {e(ad.get('name') or ad['link'])}: {n} постов.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "inbox"
    if mode == "preview":
        link = sys.argv[2] if len(sys.argv) > 2 else "https://t.me/+example"
        st = {"queue": [], "count": int(os.environ.get("SEED", 0)), "offset": 0}
        ad = parse(" ".join(sys.argv[2:]) or link)
        ad.setdefault("name", os.environ.get("NAME"))
        ad = enqueue(st, ad)
        for i in plan(ad):
            txt = main_text(ad, i["kind"], i["variant"]) if i["main"] else remind_text(ad, i["kind"], i["variant"])
            if i["main"]:
                print("[картинка]", card(ad, i["kind"], f"data/night_cards/preview-{i['kind']}.jpg"))
            print(f"--- {i['t']:%d.%m %H:%M} {i['key']} ---\n{re.sub(r'<[^>]+>', '', txt)}\n")
        return
    if not token():
        sys.exit("Нет секрета TG_CHANNEL_BOT_TOKEN")
    st = load()
    if mode == "night":
        night_shift(st)
    else:
        if inbox(st):
            commit(st)
        morning_cleanup(st)
        commit(st)


if __name__ == "__main__":
    main()
