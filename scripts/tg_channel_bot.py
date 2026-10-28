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
DISCLAIMER = "<blockquote><i>18+ · Ставки — только в легальных БК · Это прогноз, а не гарантия</i></blockquote>"

BRAND = {
    "accent": (178, 221, 16), "glow": (34, 48, 4), "line": (52, 66, 14), "track": (30, 36, 14),
    "mark": "VIPBET", "mark_font": ("InterDisplay-Black.otf", 34),
    "label": "Н А Ш   П Р О Г Н О З", "prob": "Вероятность по нашей оценке — {p}%",
    "pick_font": ("InterDisplay-Black.otf", 70), "vs_font": ("InterDisplay-Black.otf", 52),
    "signature": CFG.get("name", "Metod VIPBET"), "sign_font": ("InterDisplay-Black.otf", 38),
    "foot": ["18+ · Только легальные БК · Это прогноз, а не гарантия",
             BASE.replace("https://", "").rstrip("/")],
}
CARD_H = 1150  # карточки для канала обрезаны снизу: без подписи и адреса сайта
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
    ups = tg("getUpdates", {"limit": 100})
    seen = []
    for u in reversed(ups):
        upd = u.get("my_chat_member") or u.get("channel_post") or u.get("message") or {}
        c = upd.get("chat") or {}
        seen.append(f"{[k for k in u if k != 'update_id']}:{c.get('type')}")
        if c.get("type") in ("channel", "supergroup"):
            st["channel"] = str(c["id"])
            st["channel_title"] = c.get("title")
            return st["channel"]
    me = tg("getMe", {})
    print(f"::notice title=Канал (диагностика)::бот @{me.get('username')}, обновлений: {len(ups)}, типы: {', '.join(seen[:10]) or 'нет'}")
    return None


def buttons():
    """Под каждым постом — одна кнопка: «Ставим в Мелбет» (ваша реферальная ссылка)."""
    return json.dumps({"inline_keyboard": [[{"text": "🎯 Ставим в Мелбет", "url": CFG["reg_link"]}]]})


def promo_line():
    if not PROMO:
        return ""
    return f"\n🎁 Промокод <code>{e(CFG['promo'])}</code> — бонус {e(CFG['bonus'])}"


def plural(n, one, few, many):
    w = one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many
    return f"{n} {w}"


def date_ru(d):
    return tb.human(d)


def strip_tags(s):
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def short(text, limit):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: dot + 1] if dot > limit * 0.5 else cut + "…"


def match_line(p):
    return f"{SPORT.get(p.get('sport'), '🏆')} <b>{e(p['home'])} — {e(p['away'])}</b>"


def single(p, kind):
    lines = [HEAD[kind], "", match_line(p),
             f"🏆 {e(p.get('league', ''))} · {date_ru(p['date'])}, {e(p['time'])} МСК", "",
             f"✅ Прогноз: <i>{e(p['pick'])}</i> — <b>{tb.k(p['odds'])}</b>"]
    if p.get("prob"):
        lines.append(f"📊 Вероятность: {round(float(p['prob']))}%")
    head = "\n".join(lines)
    tail = "\n" + promo_line() + "\n\n" + DISCLAIMER
    room = 1024 - len(strip_tags(head)) - len(strip_tags(tail)) - 10
    quote = short(p.get("text") or p.get("more") or "", min(330, room))
    return f"{head}\n\n<blockquote>{e(quote)}</blockquote>{tail}"


def express_text(legs, day):
    total = 1.0
    rows = []
    per = max(90, (1024 - 420) // max(1, len(legs)) - 70)
    for i, p in enumerate(legs, 1):
        total *= float(p["odds"])
        rows.append(f"{i}️⃣ {match_line(p)} · {e(p['time'])}\n"
                    f"✅ <i>{e(p['pick'])}</i> — <b>{tb.k(p['odds'])}</b>\n"
                    f"<blockquote>{e(short(p.get('text', ''), per))}</blockquote>")
    return (f"🧩 <b>ЭКСПРЕСС ДНЯ · {date_ru(day)}</b>\n\n" + "\n".join(rows) +
            f"\n💰 Общий коэффициент: <b>{total:.2f}</b>\n"
            "<i>Экспресс не зайдёт, если ошибся хотя бы один исход, — ставьте на него меньше обычного.</i>\n"
            + promo_line() + "\n\n" + DISCLAIMER)


def tb_profit(p):
    return (float(p["odds"]) - 1) if p["result"] == "win" else -1 if p["result"] == "loss" else 0


def results_block(preds, day):
    ps = [p for p in preds if p["date"] == day and p.get("result") in ("win", "loss", "return")]
    if not ps:
        return None
    mark = {"win": "✅", "loss": "❌", "return": "↩️"}
    w = sum(p["result"] == "win" for p in ps)
    profit = sum(tb_profit(p) for p in ps)
    rows = [f"{mark[p['result']]} <b>{e(p['home'])} — {e(p['away'])}</b> {e(p.get('score') or '')} · <i>{e(p['pick'])}</i> ({tb.k(p['odds'])})" for p in ps]
    return (f"📈 <b>Итоги {date_ru(day)}</b>\n" + "\n".join(rows) +
            f"\nЗашло {w} из {len(ps)} · {'+' if profit >= 0 else '−'}{abs(profit):.2f} ед.")


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
    shown = sorted(day_preds, key=tb.start)[:8]
    if shown:
        rows = [f"🕒 {e(p['time'])} {match_line(p)}\n<i>{e(p['pick'])}</i> — <b>{tb.k(p['odds'])}</b>" for p in shown]
        parts.append(f"📅 <b>Прогнозы на {date_ru(day)}</b>\n\n" + "\n\n".join(rows) +
                     "\n\n<i>Ставка дня — в 11:00, верняк — в 14:00, экспресс — в 17:00, прогноз на вечер — в 19:00 (МСК).</i>")
    if len(parts) == 1:
        return None, []
    text = "\n\n".join(parts) + "\n" + promo_line() + "\n\n" + DISCLAIMER
    while len(strip_tags(text)) > 1024 and len(shown) > 2:  # подпись к фото — до 1024 символов
        shown = shown[:-1]
        rows = rows[:-1]
        parts[-1] = f"📅 <b>Прогнозы на {date_ru(day)}</b>\n\n" + "\n\n".join(rows)
        text = "\n\n".join(parts) + "\n" + promo_line() + "\n\n" + DISCLAIMER
    return text, shown


# ---------- картинки ----------
def list_card(title, sub, items, dst, total=None):
    """Карточка со списком матчей (экспресс, прогнозы дня) в стиле VIPBET."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1080, 1350
    LIME, WHITE, GREY = BRAND["accent"], (245, 242, 235), (150, 146, 138)
    im = Image.new("RGB", (W, H), (9, 9, 9))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-200, -380, W + 200, 520), fill=70)
    im = Image.composite(Image.new("RGB", (W, H), BRAND["glow"]), im, glow.filter(ImageFilter.GaussianBlur(160))).convert("RGBA")
    d = ImageDraw.Draw(im)
    M = 84
    d.text((M, 96), title, font=pb.font("Inter-SemiBold.otf", 26), fill=LIME)
    d.text((W - M, 92), BRAND["mark"], font=pb.font(*BRAND["mark_font"]), fill=LIME, anchor="ra")
    d.text((M, 146), sub, font=pb.font("Inter-Regular.otf", 28), fill=GREY)
    n = len(items)
    bottom = CARD_H - 40 - (180 if total else 0)
    row_h = min(250, (bottom - 230) // max(1, n))
    S = min(96, row_h - 60)
    y = 230
    for p in items:
        im.alpha_composite(pb.crest(p, "home", S, LIME), (M, int(y)))
        im.alpha_composite(pb.crest(p, "away", S, LIME), (M + S - 18, int(y)))
        x = M + 2 * S + 20
        ft = pb.font("Inter-SemiBold.otf", 34 if row_h > 150 else 30)
        name = f"{p['home']} — {p['away']}"
        while d.textlength(name, font=ft) > W - M - x and len(name) > 10:
            name = name[:-2].rstrip() + "…" if not name.endswith("…") else name[:-3].rstrip() + "…"
        d.text((x, y + 2), name, font=ft, fill=WHITE)
        pk = f"{p['pick']}  ·  {tb.k(p['odds'])}"
        fpk = pb.font("InterDisplay-Black.otf", 34 if row_h > 150 else 30)
        d.text((x, y + 48), pk, font=fpk, fill=LIME)
        d.text((x, y + 92), f"{p['time']} МСК · {p.get('league', '')}"[:48], font=pb.font("Inter-Regular.otf", 24), fill=GREY)
        y += row_h
    if total:
        d.line((M, bottom + 20, W - M, bottom + 20), fill=BRAND["line"], width=2)
        d.text((M, bottom + 50), "О Б Щ И Й   К О Э Ф Ф И Ц И Е Н Т", font=pb.font("Inter-SemiBold.otf", 24), fill=LIME)
        d.text((M, bottom + 86), f"{total:.2f}", font=pb.font("InterDisplay-Black.otf", 72), fill=WHITE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.convert("RGB").crop((0, 0, W, CARD_H)).save(dst, "JPEG", quality=92, optimize=True)


# ---------- публикация ----------
def send(ch, img_rel, caption, dry):
    print(f"[фото {img_rel}]\n{strip_tags(caption)}\n({len(strip_tags(caption))} симв.)\n")
    if dry:
        return None
    r = tg("sendPhoto", {"chat_id": ch, "caption": caption, "parse_mode": "HTML", "reply_markup": buttons()},
           {"photo": os.path.join(ROOT, img_rel)})
    return r.get("message_id")


def send_photo_post(ch, p, kind, dry):
    rel = f"data/tg_cards/{p['id']}-{kind}.jpg"
    path = os.path.join(ROOT, rel)
    pb.render_card(p, path, dict(BRAND, title=TITLES[kind]))
    from PIL import Image
    Image.open(path).crop((0, 0, 1080, CARD_H)).save(path, "JPEG", quality=92, optimize=True)  # без нижних подписей
    return send(ch, rel, single(p, kind), dry)


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
        txt, shown = morning_text(preds)
        if txt:
            rel = f"data/tg_cards/{d}-morning.jpg"
            day_preds_all, day = tb.open_today(preds)
            if shown:
                list_card("П Р О Г Н О З Ы   Д Н Я", f"{date_ru(day)} · {plural(len(day_preds_all), 'матч', 'матча', 'матчей')}", shown[:6], os.path.join(ROOT, rel))
            else:
                yest = [p for p in preds if p["date"] == (tb.now() - timedelta(days=1)).strftime("%Y-%m-%d") and p.get("result") in ("win", "loss", "return")]
                list_card("И Т О Г И   Д Н Я", date_ru(yest[0]["date"]) if yest else "", yest[:6], os.path.join(ROOT, rel))
            msg = send(ch, rel, txt, dry)
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
            rel = f"data/tg_cards/{day}-express.jpg"
            total = 1.0
            for p in legs:
                total *= float(p["odds"])
            list_card("Э К С П Р Е С С   Д Н Я", f"{date_ru(day)} · {plural(len(legs), 'событие', 'события', 'событий')}", legs, os.path.join(ROOT, rel), total)
            msg = send(ch, rel, express_text(legs, day), dry)
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
