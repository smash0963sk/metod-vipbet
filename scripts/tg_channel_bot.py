"""Бот Telegram-канала Metod VIPBET: публикует прогнозы с сайта (data/predictions.json).

Слоты (время МСК, расписание — .github/workflows/tg-channel.yml):
  morning  09:05  итоги вчера (+ итоги недели по понедельникам) и список прогнозов на сегодня
  bet      11:05  «Ставка дня» — карточка + разбор + кнопки
  lock     14:05  «Верняк дня»
  express  17:05  «Экспресс дня»
  evening  19:05  «Прогноз на вечер» — лучший из оставшихся матчей

Секреты: TG_CHANNEL_BOT_TOKEN (или TG_BOT_TOKEN — можно тот же бот, что у персонажа),
TG_CHANNEL_ID — не обязателен: бот сам запоминает канал, в который его добавили администратором.
DRY_RUN=1 — только показать тексты. Опубликованное — в data/tg_channel_state.json.
"""
import html, json, os, sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import threads_bot as tb
import persona_bot as pb

CFG = tb.CFG
BASE = tb.BASE
STATE_FILE = os.path.join(ROOT, "data", "tg_channel_state.json")
CARD_DIR = os.path.join(ROOT, "data", "tg_cards")
PROMO = CFG.get("tg_channel_promo", True)
e = lambda s: html.escape(str(s if s is not None else ""), quote=False)
SPORT = tb.SPORT_EMOJI
DISCLAIMER = "<i>18+. Ставки — только в легальных букмекерских компаниях. Это прогноз, а не гарантия.</i>"

BRAND = {
    "accent": (178, 221, 16), "glow": (34, 48, 4), "line": (52, 66, 14), "track": (30, 36, 14),
    "mark": "VIPBET", "mark_font": ("InterDisplay-Black.otf", 34),
    "label": "Н А Ш   П Р О Г Н О З", "prob": "Вероятность по нашей оценке — {p}%",
    "pick_font": ("InterDisplay-Black.otf", 70), "vs_font": ("InterDisplay-Black.otf", 52),
    "signature": CFG.get("name", "Metod VIPBET"), "sign_font": ("InterDisplay-Black.otf", 38),
    "foot": ["18+ · Только легальные БК · Это прогноз, а не гарантия",
             BASE.replace("https://", "").rstrip("/")],
}
TITLES = {"bet": "С Т А В К А   Д Н Я", "lock": "В Е Р Н Я К   Д Н Я", "evening": "П Р О Г Н О З   Н А   В Е Ч Е Р"}
HEAD = {"bet": "🔥 <b>СТАВКА ДНЯ</b>", "lock": "🔒 <b>ВЕРНЯК ДНЯ</b>", "evening": "🌙 <b>ПРОГНОЗ НА ВЕЧЕР</b>"}


# ---------- состояние и Telegram ----------
def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except FileNotFoundError:
        return {"posted": {}}


def save_state(st):
    st["posted"] = dict(sorted(st["posted"].items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:400])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def token():
    return os.environ.get("TG_CHANNEL_BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")


def tg(method, fields, files=None):
    os.environ["TG_BOT_TOKEN"] = token()
    return pb.tg_call(method, fields, files)


def channel(st):
    """Канал: секрет TG_CHANNEL_ID, сохранённый id или канал, куда бота добавили администратором."""
    ch = os.environ.get("TG_CHANNEL_ID") or st.get("channel")
    if ch:
        return ch
    for u in reversed(tg("getUpdates", {"limit": 100, "allowed_updates": json.dumps(["my_chat_member", "channel_post"])})):
        upd = u.get("my_chat_member") or u.get("channel_post") or {}
        c = upd.get("chat") or {}
        if c.get("type") == "channel":
            st["channel"] = str(c["id"])
            st["channel_title"] = c.get("title")
            return st["channel"]
    return None


def buttons(p=None, site=True):
    rows = []
    if p is not None:
        rows.append([{"text": "📊 Полный разбор и статистика", "url": tb.page_url(p)}])
    elif site:
        rows.append([{"text": "📊 Все прогнозы на сайте", "url": BASE}])
    if PROMO:
        rows.append([{"text": f"🎁 Бонус {CFG['bonus']} · промокод {CFG['promo']}", "url": CFG["reg_link"]}])
    return json.dumps({"inline_keyboard": rows})


def promo_line():
    if not PROMO:
        return ""
    return f"\n\n🎁 Мелбет: промокод <code>{e(CFG['promo'])}</code> — бонус {e(CFG['bonus'])} новым игрокам."


# ---------- тексты ----------
def date_ru(d):
    return tb.human(d)


def single(p, kind):
    em = SPORT.get(p.get("sport"), "🏆")
    lines = [HEAD[kind], "",
             f"{em} <b>{e(p['home'])} — {e(p['away'])}</b>",
             f"🏆 {e(p.get('league', ''))} · {date_ru(p['date'])}, {e(p['time'])} МСК", "",
             f"✅ <b>{e(p['pick'])} за {tb.k(p['odds'])}</b>"]
    if p.get("prob"):
        lines.append(f"📊 Вероятность по нашей оценке: {round(float(p['prob']))}%")
    st = p.get("stats") or {}
    form = st.get("form") or {}
    if form.get("home") and form.get("away"):
        lines.append(f"📈 Форма: {e(form['home'])} / {e(form['away'])}")
    head = "\n".join(lines)
    tail = promo_line() + "\n\n" + DISCLAIMER
    body = (p.get("text") or "").strip()
    more = (p.get("more") or "").strip()
    room = 1024 - len(strip_tags(head)) - len(strip_tags(tail)) - 8  # лимит подписи к фото
    txt = body + ("\n\n" + more if more else "")
    if len(txt) > room:
        txt = body if len(body) <= room else body[: room - 1].rsplit(" ", 1)[0] + "…"
    return f"{head}\n\n{e(txt)}{tail}"


def strip_tags(s):
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def express_text(legs, day):
    total = 1.0
    rows = []
    for i, p in enumerate(legs, 1):
        total *= float(p["odds"])
        rows.append(f"{i}. {SPORT.get(p.get('sport'), '🏆')} {e(p['home'])} — {e(p['away'])}, {e(p['time'])}\n"
                    f"     ✅ {e(p['pick'])} — <b>{tb.k(p['odds'])}</b>")
    return (f"🧩 <b>ЭКСПРЕСС ДНЯ · {date_ru(day)}</b>\n\n" + "\n\n".join(rows) +
            f"\n\n💰 Общий коэффициент: <b>{total:.2f}</b>\n\n"
            "Экспресс проигрывает, если не зашло хотя бы одно событие, — ставьте на него меньше, чем на одиночные."
            + promo_line() + "\n\n" + DISCLAIMER)


def results_block(preds, day):
    ps = [p for p in preds if p["date"] == day and p.get("result") in ("win", "loss", "return")]
    if not ps:
        return None
    mark = {"win": "✅", "loss": "❌", "return": "↩️"}
    w = sum(p["result"] == "win" for p in ps)
    profit = sum(tb_profit(p) for p in ps)
    rows = [f"{mark[p['result']]} {e(p['home'])} — {e(p['away'])} {e(p.get('score') or '')} · {e(p['pick'])} ({tb.k(p['odds'])})" for p in ps]
    return (f"📈 <b>Итоги {date_ru(day)}</b>\n" + "\n".join(rows) +
            f"\n\nЗашло {w} из {len(ps)} · {'+' if profit >= 0 else '−'}{abs(profit):.2f} ед.")


def tb_profit(p):
    return (float(p["odds"]) - 1) if p["result"] == "win" else -1 if p["result"] == "loss" else 0


def week_block(preds, today):
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    ps = [p for p in preds if start.isoformat() <= p["date"] <= end.isoformat() and p.get("result") in ("win", "loss", "return")]
    if not ps:
        return None
    w = sum(p["result"] == "win" for p in ps)
    l = sum(p["result"] == "loss" for p in ps)
    profit = sum(tb_profit(p) for p in ps)
    roi = profit / len(ps) * 100
    return (f"🗓 <b>Итоги недели {start.day}.{start.month:02d}–{end.day}.{end.month:02d}</b>\n"
            f"Прогнозов: {len(ps)} · зашло {w}, не зашло {l}\n"
            f"Прибыль: {'+' if profit >= 0 else '−'}{abs(profit):.2f} ед. · ROI {roi:+.1f}%")


def morning_text(preds):
    now = tb.now()
    parts = ["☀️ <b>Доброе утро!</b>"]
    if now.weekday() == 0:
        wk = week_block(preds, now.date())
        if wk:
            parts.append(wk)
    res = results_block(preds, (now - timedelta(days=1)).strftime("%Y-%m-%d"))
    if res:
        parts.append(res)
    day_preds, day = tb.open_today(preds)
    if day_preds:
        rows = [f"{SPORT.get(p.get('sport'), '🏆')} {e(p['time'])} {e(p['home'])} — {e(p['away'])} · {e(p['pick'])} ({tb.k(p['odds'])})"
                for p in sorted(day_preds, key=tb.start)[:10]]
        parts.append(f"📅 <b>Прогнозы на {date_ru(day)}</b>\n" + "\n".join(rows) +
                     "\n\nСтавка дня — в 11:00, верняк — в 14:00, экспресс — в 17:00, прогноз на вечер — в 19:00 (МСК).")
    if len(parts) == 1:
        return None
    return "\n\n".join(parts) + "\n\n" + DISCLAIMER


# ---------- публикация ----------
def send_photo_post(ch, p, kind, dry):
    rel = f"data/tg_cards/{p['id']}-{kind}.jpg"
    pb.render_card(p, os.path.join(ROOT, rel), dict(BRAND, title=TITLES[kind]))
    cap = single(p, kind)
    print(f"[фото {rel}]\n{strip_tags(cap)}\n")
    if dry:
        return None
    r = tg("sendPhoto", {"chat_id": ch, "caption": cap, "parse_mode": "HTML", "reply_markup": buttons(p)},
           {"photo": os.path.join(ROOT, rel)})
    return r.get("message_id")


def send_text(ch, text, dry, p=None, site=True):
    print(strip_tags(text) + "\n")
    if dry:
        return None
    r = tg("sendMessage", {"chat_id": ch, "text": text, "parse_mode": "HTML",
                           "disable_web_page_preview": "true", "reply_markup": buttons(p, site)})
    return r.get("message_id")


def main():
    slot = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if slot not in ("morning", "bet", "lock", "express", "evening"):
        sys.exit(__doc__)
    dry = os.environ.get("DRY_RUN") == "1" or not token()
    if not token():
        print("::warning title=Канал::Нет секрета TG_BOT_TOKEN — работаю в режиме проверки")
    st = load_state()
    preds = tb.load()
    d = tb.now().strftime("%Y-%m-%d")
    key = f"{slot}:{d}"
    if key in st["posted"]:
        print(f"Уже опубликовано: {key}")
        return
    ch = None if dry else channel(st)
    if not dry and not ch:
        print("::warning title=Канал::Бот не знает канал: добавьте его администратором канала (право «Публикация сообщений») и запустите снова")
        save_state(st)
        return
    posted = {v.get("pid") for v in st["posted"].values() if v.get("pid")}
    msg, pid = None, None
    if slot == "morning":
        txt = morning_text(preds)
        if txt:
            msg = send_text(ch, txt, dry)
    elif slot in ("bet", "lock"):
        p = tb.pick_tag(preds, "bet_of_day" if slot == "bet" else "lock_of_day")
        if p and p["id"] in posted:
            day_preds, _ = tb.open_today(preds)
            rest = [x for x in day_preds if x["id"] not in posted]
            p = max(rest, key=lambda x: (x.get("prob") or 50) * float(x["odds"])) if rest else None
        if p:
            msg, pid = send_photo_post(ch, p, slot, dry), p["id"]
    elif slot == "express":
        legs, day = tb.express(preds)
        if legs:
            msg = send_text(ch, express_text(legs, day), dry)
    elif slot == "evening":
        now = tb.now()
        day_preds, _ = tb.open_today(preds)
        rest = [x for x in day_preds if x["id"] not in posted and tb.start(x) > now + timedelta(minutes=30)]
        if rest:
            p = max(rest, key=lambda x: (x.get("prob") or 50, -abs(float(x["odds"]) - 1.8)))
            msg, pid = send_photo_post(ch, p, "evening", dry), p["id"]
    if msg is None and not dry:
        print(f"::notice title=Канал::{key}: подходящих прогнозов нет — пост пропущен")
        save_state(st)
        return
    if dry:
        print(f"::notice title=Канал (проверка)::{key}: пост не опубликован")
        return
    st["posted"][key] = {"at": tb.now().isoformat(timespec="seconds"), "msg": msg, "pid": pid}
    save_state(st)
    print(f"::notice title=Канал::Опубликовано {key} в «{st.get('channel_title') or ch}»")


if __name__ == "__main__":
    main()
