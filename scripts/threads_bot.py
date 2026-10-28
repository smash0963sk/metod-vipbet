"""Бот Metod VIPBET для Threads: публикует прогнозы через официальный Threads API (Meta)
и ведёт читателей в Telegram-канал (ссылка — в первом комментарии под постом).

Слоты (запускаются сценарием .github/workflows/threads.yml):
  morning — итоги вчерашнего дня (если есть закрытые прогнозы) + «Ставка дня»
  midday  — «Верняк дня»
  evening — «Экспресс дня»

Переменные окружения (секреты GitHub):
  THREADS_USER_ID       — числовой id аккаунта Threads
  THREADS_ACCESS_TOKEN  — долгоживущий токен (threads_basic, threads_content_publish)
  DRY_RUN=1             — ничего не публиковать, только показать тексты

Опубликованное запоминается в data/threads_state.json, чтобы не было повторов.
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "scripts", "site_config.json"), encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/") + "/"
MSK = timezone(timedelta(hours=3))
API = "https://graph.threads.net/v1.0"
STATE_FILE = os.path.join(ROOT, "data", "threads_state.json")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
SPORT_EMOJI = {"Футбол": "⚽", "Хоккей": "🏒", "Теннис": "🎾", "Баскетбол": "🏀", "Киберспорт": "🎮"}
LIMIT = 500  # максимум символов в посте Threads
TOPIC = "#ставкинаспорт"  # Threads учитывает один хештег-тему на пост
WITH_PROMO = bool(CFG.get("threads_with_promo", False))
TG = CFG.get("threads_telegram") or CFG["telegram"]  # отдельная ссылка для Threads — видно, сколько пришло именно оттуда
# "reply" — ссылка на Telegram в первом комментарии (посты без ссылок Threads показывает шире)
# "attach" — ссылка прямо в посте
LINK_MODE = CFG.get("threads_link_mode", "reply")
REPLIES = [
    "Все прогнозы дня, разборы и итоги — в нашем Telegram-канале 👉 {tg}",
    "Ставки дня, экспрессы и честная статистика каждый день — в Telegram 👉 {tg}",
    "Подписывайся на Telegram, чтобы получать прогнозы раньше всех 👉 {tg}",
]


def now():
    return datetime.now(MSK)


def human(d):
    y, m, dd = map(int, d.split("-"))
    return f"{dd} {MONTHS[m - 1]}"


def start(p):
    return datetime.fromisoformat(f'{p["date"]}T{p["time"]}:00+03:00')


def k(x):
    return f"{float(x):.2f}"


def page_url(p):
    return f'{BASE}match/{p["id"]}.html'


def fit(head, body, tail):
    """Собирает пост и обрезает основной текст, чтобы уложиться в лимит Threads."""
    room = LIMIT - len(head) - len(tail) - 4
    if len(body) > room:
        body = body[: max(0, room - 1)].rsplit(" ", 1)[0].rstrip(",.;:—- ") + "…"
    return f"{head}\n\n{body}\n\n{tail}".strip()


def tail_text():
    t = "Полный разбор и все прогнозы — в Telegram, ссылка в комментарии 👇" if LINK_MODE == "reply" else "Полный разбор и все прогнозы — в нашем Telegram 👇"
    if WITH_PROMO:
        t += f"\nПромокод {CFG['promo']} — бонус {CFG['bonus']} в Мелбет."
    return t + f"\n18+ {TOPIC}"


def load():
    d = json.load(open(os.path.join(ROOT, "data", "predictions.json"), encoding="utf-8"))
    return [p for p in d.get("predictions", []) if p.get("id") and p.get("home") and p.get("away")]


def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except FileNotFoundError:
        return {"posted": {}}


def save_state(st):
    keep = sorted(st["posted"].items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:300]
    st["posted"] = dict(keep)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


# ---------- выбор прогнозов (те же правила, что на сайте) ----------
def open_today(preds):
    t = now()
    opened = [p for p in preds if p.get("result") == "pending" and start(p) > t]
    today = t.strftime("%Y-%m-%d")
    day = today if any(p["date"] == today for p in opened) else (min((p["date"] for p in opened), default=None))
    return [p for p in opened if p["date"] == day], day


def pick_tag(preds, tag):
    day_preds, _ = open_today(preds)
    tagged = [p for p in day_preds if tag in (p.get("tags") or [])]
    if tagged:
        return sorted(tagged, key=start)[0]
    if not day_preds:
        return None
    if tag == "bet_of_day":
        return max(day_preds, key=lambda p: (p.get("prob") or 50) * float(p["odds"]))
    cand = [p for p in day_preds if float(p["odds"]) >= 1.4] or day_preds
    return max(cand, key=lambda p: (p.get("prob") or 0, p.get("confidence") or 2, -float(p["odds"])))


def express(preds):
    day_preds, day = open_today(preds)
    cand = sorted([p for p in day_preds if 1.4 <= float(p["odds"]) <= 2.3],
                  key=lambda p: (-(p.get("confidence") or 2), float(p["odds"])))
    legs, seen = [], set()
    for p in cand:
        key = (p["home"], p["away"])
        if key in seen:
            continue
        seen.add(key)
        legs.append(p)
        if len(legs) == 3:
            break
    return (legs, day) if len(legs) >= 2 else ([], day)


# ---------- тексты постов ----------
def post_single(p, title):
    em = SPORT_EMOJI.get(p.get("sport"), "🏆")
    head = (f"{title} · {em} {p.get('sport', '')}\n"
            f"{p['home']} — {p['away']}\n"
            f"{p.get('league', '')}, {human(p['date'])}, {p['time']} МСК\n\n"
            f"✅ {p['pick']} за {k(p['odds'])}")
    if p.get("prob"):
        head += f"\n📊 Наша оценка: {round(float(p['prob']))}%"
    return fit(head, p.get("text", ""), tail_text())


def post_express(legs, day):
    total = 1.0
    lines = []
    for p in legs:
        total *= float(p["odds"])
        lines.append(f"▪️ {p['home']} — {p['away']}: {p['pick']} ({k(p['odds'])})")
    head = f"🧩 Экспресс дня на {human(day)}\n\n" + "\n".join(lines) + f"\n\nОбщий коэффициент: {total:.2f}"
    body = "Экспресс рискованнее одиночных ставок: он проигрывает, если не зашло хотя бы одно событие."
    return fit(head, body, tail_text())


def post_results(preds, day):
    ps = [p for p in preds if p["date"] == day and p.get("result") in ("win", "loss", "return")]
    if not ps:
        return None
    w = sum(p["result"] == "win" for p in ps)
    l = sum(p["result"] == "loss" for p in ps)
    profit = sum((float(p["odds"]) - 1) if p["result"] == "win" else -1 if p["result"] == "loss" else 0 for p in ps)
    mark = {"win": "✅", "loss": "❌", "return": "↩️"}
    lines = [f"{mark[p['result']]} {p['home']} — {p['away']} {p.get('score') or ''}: {p['pick']} ({k(p['odds'])})".replace("  ", " ") for p in ps]
    head = f"📈 Итоги {human(day)}: {w} зашло, {l} не зашло, {'+' if profit >= 0 else '−'}{abs(profit):.2f} ед."
    body = "\n".join(lines)
    t = ("Показываем все результаты, включая проигрыши. Прогнозы на сегодня — в Telegram, ссылка в комментарии 👇" if LINK_MODE == "reply"
         else "Показываем все результаты, включая проигрыши. Прогнозы на сегодня — в нашем Telegram 👇") + f"\n18+ {TOPIC}"
    return fit(head, body, t)


# ---------- Threads API ----------
def api(method, path, params):
    params = dict(params)
    params["access_token"] = os.environ["THREADS_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url, data=data if method == "POST" else None, method=method)
    if method == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Threads API {e.code}: {e.read()[:300]!r}")


def publish(text, link=None, reply_to=None):
    uid = os.environ["THREADS_USER_ID"]
    params = {"media_type": "TEXT", "text": text}
    if link:
        params["link_attachment"] = link
    if reply_to:
        params["reply_to_id"] = reply_to
    container = api("POST", f"{uid}/threads", params)["id"]
    time.sleep(5)  # Meta рекомендует подождать перед публикацией контейнера
    return api("POST", f"{uid}/threads_publish", {"creation_id": container})["id"]


def send(st, key, text, dry):
    """Публикует пост и ссылку на Telegram (в комментарии или прямо в посте)."""
    if key in st["posted"]:
        print(f"Уже опубликовано: {key}")
        return
    reply = REPLIES[len(st["posted"]) % len(REPLIES)].format(tg=TG)
    print(f"----- {key} ({len(text)} симв.) -----\n{text}")
    print(f"[{'комментарий' if LINK_MODE == 'reply' else 'ссылка в посте'}] {reply if LINK_MODE == 'reply' else TG}\n")
    if dry:
        print(f"::notice title=Threads (проверка)::{key}: пост не опубликован, включён DRY_RUN")
        return
    if LINK_MODE == "reply":
        post_id = publish(text)
        time.sleep(10)
        try:
            publish(reply, link=TG, reply_to=post_id)
        except Exception as e:  # пост уже вышел — не дублируем его из-за ошибки комментария
            print(f"::warning title=Threads::Пост {key} опубликован, но комментарий со ссылкой не добавлен: {e}")
    else:
        post_id = publish(text, link=TG)
    st["posted"][key] = {"at": now().isoformat(timespec="seconds"), "id": post_id}
    print(f"::notice title=Threads::Опубликовано {key}, id {post_id}")
    time.sleep(30)


def main():
    slot = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if slot not in ("morning", "midday", "evening"):
        h = now().hour
        slot = "morning" if h < 12 else "midday" if h < 16 else "evening"
    dry = os.environ.get("DRY_RUN") == "1" or not os.environ.get("THREADS_ACCESS_TOKEN")
    if dry and not os.environ.get("THREADS_ACCESS_TOKEN"):
        print("::warning title=Threads::Нет секрета THREADS_ACCESS_TOKEN — работаю в режиме проверки, без публикации")
    preds = load()
    st = load_state()
    print(f"Слот: {slot}")
    if slot == "morning":
        y = (now() - timedelta(days=1)).strftime("%Y-%m-%d")
        txt = post_results(preds, y)
        if txt:
            send(st, f"results:{y}", txt, dry)
        p = pick_tag(preds, "bet_of_day")
        if p:
            send(st, f"bet:{p['id']}", post_single(p, "🔥 Ставка дня"), dry)
    elif slot == "midday":
        p = pick_tag(preds, "lock_of_day")
        if p:
            send(st, f"lock:{p['id']}", post_single(p, "🔒 Верняк дня"), dry)
    elif slot == "evening":
        legs, day = express(preds)
        if legs:
            send(st, f"express:{day}", post_express(legs, day), dry)
        else:
            print("На сегодня нет подходящих событий для экспресса")
    if not dry:
        save_state(st)


if __name__ == "__main__":
    main()
