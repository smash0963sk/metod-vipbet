"""Бот Telegram-канала Metod VIPBET: публикует прогнозы с сайта (data/predictions.json).

Запускается каждый час (.github/workflows/tg-channel.yml) и публикует то, что пора по расписанию SCHEDULE (МСК):
  ежедневно: 09 утро (итоги + прогнозы дня), 11 ставка дня, 12 опрос «Кто победит?», 13 новости,
             14 верняк, 17 экспресс, 19 прогноз на вечер;
  ср 15 школа ставок · пт 18 матчи выходных · вс 20 ответственная игра;
  1-го числа 10 — итоги месяца с графиком и обновление закреплённого поста.
  При каждом запуске бот отвечает на свои посты «✅ Зашло / ❌ Не зашло», когда результат появился на сайте.
Ручной запуск: python3 scripts/tg_channel_bot.py <слот> (или auto / results).

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

DISCLAIMER_SHORT = "<blockquote><i>18+ · Ставки — только в легальных БК</i></blockquote>"

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
    return f"\n🎁 Промокод <b>{e(CFG['promo'])}</b> — бонус {e(CFG['bonus'])}"


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
                     "\n\n<i>Ставка дня — в 11:00, опрос — в 12:00, новости — в 13:00, верняк — в 14:00, экспресс — в 17:00, прогноз на вечер — в 19:00 (МСК).</i>")
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


# ---------- ещё картинки ----------
def base_canvas(title):
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1080, CARD_H
    im = Image.new("RGB", (W, H), (9, 9, 9))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-200, -380, W + 200, 520), fill=70)
    im = Image.composite(Image.new("RGB", (W, H), BRAND["glow"]), im, glow.filter(ImageFilter.GaussianBlur(160))).convert("RGBA")
    d = ImageDraw.Draw(im)
    d.text((84, 96), title, font=pb.font("Inter-SemiBold.otf", 26), fill=BRAND["accent"])
    d.text((W - 84, 92), BRAND["mark"], font=pb.font(*BRAND["mark_font"]), fill=BRAND["accent"], anchor="ra")
    return im, d


def save(im, rel):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.convert("RGB").save(path, "JPEG", quality=92, optimize=True)
    return rel


def vs_card(p, title, big, small, rel):
    """Матч без нашего прогноза — для «Угадай счёт»."""
    im, d = base_canvas(title)
    W, LIME, WHITE, GREY = 1080, BRAND["accent"], (245, 242, 235), (150, 146, 138)
    d.text((84, 146), f"{p.get('league', '')} · {date_ru(p['date'])}, {p['time']} МСК"[:60], font=pb.font("Inter-Regular.otf", 28), fill=GREY)
    S, top = 230, 250
    for side, cx in (("home", W * 0.27), ("away", W * 0.73)):
        im.alpha_composite(pb.crest(p, side, S, LIME), (int(cx - S / 2), top))
        fn = pb.font("Inter-SemiBold.otf", 36)
        y = top + S + 30
        for line in pb.wrap(d, p[side], fn, 380)[:2]:
            d.text((cx, y), line, font=fn, fill=WHITE, anchor="ma")
            y += 46
    d.text((W / 2, top + S / 2), "vs", font=pb.font(*BRAND["vs_font"]), fill=LIME, anchor="mm")
    d.line((84, 690, W - 84, 690), fill=BRAND["line"], width=2)
    d.text((W / 2, 830), big, font=pb.font("InterDisplay-Black.otf", 150), fill=WHITE, anchor="mm")
    d.text((W / 2, 980), small, font=pb.font("Inter-SemiBold.otf", 36), fill=LIME, anchor="mm")
    return save(im, rel)


def text_card(title, big, small, rel):
    """Карточка с крупной фразой — школа ставок, ответственная игра, новости."""
    im, d = base_canvas(title)
    WHITE, GREY = (245, 242, 235), (150, 146, 138)
    fb = pb.font("InterDisplay-Black.otf", 74)
    lines = pb.wrap(d, big, fb, 1080 - 168)
    while len(lines) > 6:
        fb = pb.font("InterDisplay-Black.otf", fb.size - 8)
        lines = pb.wrap(d, big, fb, 1080 - 168)
    fs = pb.font("Inter-Regular.otf", 32)
    sl = pb.wrap(d, small or "", fs, 1080 - 168)[:8]
    total = len(lines) * int(fb.size * 1.15) + 40 + len(sl) * 46
    y = max(230, 200 + (CARD_H - 200 - total) // 2)
    d.rectangle((84, y - 40, 164, y - 30), fill=BRAND["accent"])
    for line in lines:
        d.text((84, y), line, font=fb, fill=WHITE)
        y += int(fb.size * 1.15)
    y += 40
    for line in sl:
        d.text((84, y), line, font=fs, fill=GREY)
        y += 46
    return save(im, rel)


def chart_card(title, sub, points, stats, rel):
    """Итоги месяца: кривая прибыли по дням (в единицах ставки) и цифры."""
    im, d = base_canvas(title)
    LIME, WHITE, GREY = BRAND["accent"], (245, 242, 235), (150, 146, 138)
    d.text((84, 146), sub, font=pb.font("Inter-Regular.otf", 28), fill=GREY)
    x0, x1, y0, y1 = 110, 1000, 250, 700
    vals = [0.0] + [v for _, v in points]
    lo, hi = min(vals + [0]), max(vals + [0])
    if hi - lo < 1:
        hi, lo = hi + 0.5, lo - 0.5
    Y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)
    X = lambda i: x0 + i / max(1, len(vals) - 1) * (x1 - x0)
    d.line((x0, Y(0), x1, Y(0)), fill=(70, 70, 60), width=2)
    pts = [(X(i), Y(v)) for i, v in enumerate(vals)]
    if len(pts) > 1:
        d.line(pts, fill=LIME, width=7, joint="curve")
    d.ellipse((pts[-1][0] - 9, pts[-1][1] - 9, pts[-1][0] + 9, pts[-1][1] + 9), fill=LIME)
    fs = pb.font("Inter-Regular.otf", 24)
    d.text((x0 - 12, Y(0)), "0", font=fs, fill=GREY, anchor="rm")
    d.text((x1, pts[-1][1] - 22), f"{vals[-1]:+.2f}", font=pb.font("Inter-SemiBold.otf", 30), fill=WHITE, anchor="rb")
    y = 770
    d.line((84, y, 996, y), fill=BRAND["line"], width=2)
    cols = list(stats.items())
    for i, (k, v) in enumerate(cols[:4]):
        cx = 84 + i * 230
        d.text((cx, y + 40), k, font=pb.font("Inter-SemiBold.otf", 22), fill=LIME)
        d.text((cx, y + 76), v, font=pb.font("InterDisplay-Black.otf", 56), fill=WHITE)
    return save(im, rel)


# ---------- публикация ----------
def send(ch, img_rel, caption, dry, markup=True):
    print(f"[фото {img_rel}]\n{strip_tags(caption)}\n({len(strip_tags(caption))} симв.)\n")
    if dry:
        return None
    f = {"chat_id": ch, "caption": caption, "parse_mode": "HTML"}
    if markup:
        f["reply_markup"] = buttons()
    return tg("sendPhoto", f, {"photo": os.path.join(ROOT, img_rel)}).get("message_id")


def send_photo_post(ch, p, kind, dry):
    rel = f"data/tg_cards/{p['id']}-{kind}.jpg"
    path = os.path.join(ROOT, rel)
    pb.render_card(p, path, dict(BRAND, title=TITLES[kind]))
    from PIL import Image
    Image.open(path).crop((0, 0, 1080, CARD_H)).save(path, "JPEG", quality=92, optimize=True)  # без нижних подписей
    return send(ch, rel, single(p, kind), dry)


def reply(ch, msg, text, dry):
    print(f"[ответ на {msg}] {strip_tags(text)}\n")
    if dry:
        return None
    return tg("sendMessage", {"chat_id": ch, "text": text, "parse_mode": "HTML",
                              "reply_parameters": json.dumps({"message_id": msg, "allow_sending_without_reply": True})}).get("message_id")


def score_pair(score):
    import re
    m = re.findall(r"\d+", str(score or ""))
    return (int(m[0]), int(m[1])) if len(m) >= 2 else None


def outcome_text(p):
    sc = score_pair(p.get("score"))
    if not sc:
        return None
    h, a = sc
    if h > a:
        return f"победа «{p['home']}»"
    if a > h:
        return f"победа «{p['away']}»"
    return "ничья"


def by_id(preds):
    return {p["id"]: p for p in preds}


# ---------- рубрики ----------
def do_morning(ch, st, preds, dry):
    txt, shown = morning_text(preds)
    if not txt:
        return None
    d = tb.now().strftime("%Y-%m-%d")
    rel = f"data/tg_cards/{d}-morning.jpg"
    day_preds_all, day = tb.open_today(preds)
    if shown:
        list_card("П Р О Г Н О З Ы   Д Н Я", f"{date_ru(day)} · {plural(len(day_preds_all), 'матч', 'матча', 'матчей')}", shown[:6], os.path.join(ROOT, rel))
    else:
        y = (tb.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yest = [p for p in preds if p["date"] == y and p.get("result") in ("win", "loss", "return")]
        list_card("И Т О Г И   Д Н Я", date_ru(y), yest[:6], os.path.join(ROOT, rel))
    return {"msg": send(ch, rel, txt, dry)}


def posted_ids(st):
    out = set()
    for v in st["posted"].values():
        if v.get("pid"):
            out.add(v["pid"])
    return out


def do_single(ch, st, preds, dry, slot):
    used = posted_ids(st)
    p = tb.pick_tag(preds, "bet_of_day" if slot == "bet" else "lock_of_day") if slot != "evening" else None
    day_preds, _ = tb.open_today(preds)
    if slot == "evening":
        rest = [x for x in day_preds if x["id"] not in used and tb.start(x) > tb.now() + timedelta(minutes=30)]
        p = max(rest, key=lambda x: (x.get("prob") or 50, -abs(float(x["odds"]) - 1.8))) if rest else None
    elif p and p["id"] in used:
        rest = [x for x in day_preds if x["id"] not in used]
        p = max(rest, key=lambda x: (x.get("prob") or 50) * float(x["odds"])) if rest else None
    if not p:
        return None
    return {"msg": send_photo_post(ch, p, slot, dry), "pid": p["id"], "kind": "single"}


def do_express(ch, st, preds, dry):
    legs, day = tb.express(preds)
    if not legs:
        return None
    rel = f"data/tg_cards/{day}-express.jpg"
    total = 1.0
    for p in legs:
        total *= float(p["odds"])
    list_card("Э К С П Р Е С С   Д Н Я", f"{date_ru(day)} · {plural(len(legs), 'событие', 'события', 'событий')}", legs, os.path.join(ROOT, rel), total)
    return {"msg": send(ch, rel, express_text(legs, day), dry), "legs": [p["id"] for p in legs], "kind": "express", "total": round(total, 2)}


def big_match(preds, days=(0,), sports=("Футбол",)):
    now = tb.now()
    dates = {(now + timedelta(days=x)).strftime("%Y-%m-%d") for x in days}
    cand = [p for p in preds if p["date"] in dates and p.get("result") == "pending" and tb.start(p) > now + timedelta(hours=1)]
    if not cand:
        return None
    score = lambda p: (p.get("sport") in sports, bool(p.get("featured")), "bet_of_day" in (p.get("tags") or []), -abs((p.get("prob") or 50) - 50))
    return max(cand, key=score)


def do_poll(ch, st, preds, dry):
    p = big_match(preds, (0,), ("Футбол", "Хоккей"))
    if not p:
        return None
    em = SPORT.get(p.get("sport"), "🏆")
    if p.get("sport") == "Футбол":
        opts = [f"Победа «{p['home']}»", "Ничья", f"Победа «{p['away']}»"]
    else:
        opts = [f"Победа «{p['home']}»", f"Победа «{p['away']}»"]
    q = f"{em} Кто победит? {p['home']} — {p['away']}, сегодня в {p['time']} МСК"[:300]
    print(f"[опрос] {q} / {opts}\n")
    if dry:
        return {"msg": None, "pid": p["id"], "kind": "poll"}
    r = tg("sendPoll", {"chat_id": ch, "question": q, "options": json.dumps([{"text": o[:100]} for o in opts]), "is_anonymous": "true"})
    return {"msg": r.get("message_id"), "pid": p["id"], "kind": "poll"}


def do_guess(ch, st, preds, dry):
    p = big_match(preds, (0, 1), ("Футбол",))
    if not p:
        return None
    rel = vs_card(p, "У Г А Д А Й   С Ч Ё Т", "? : ?", "Пишите свой счёт в комментариях", f"data/tg_cards/{p['id']}-guess.jpg")
    cap = (f"🎯 <b>УГАДАЙ СЧЁТ</b>\n\n{match_line(p)}\n🏆 {e(p.get('league', ''))} · {date_ru(p['date'])}, {e(p['time'])} МСК\n\n"
           "Напишите в комментариях точный счёт матча. После игры отметим всех, кто угадал 👏\n\n"
           "<i>Просто ради интереса — без призов и ставок.</i>")
    return {"msg": send(ch, rel, cap, dry, markup=False), "pid": p["id"], "kind": "guess"}


def do_weekend(ch, st, preds, dry):
    now = tb.now()
    days = [(now + timedelta(days=x)) for x in (1, 2)]
    dates = {x.strftime("%Y-%m-%d") for x in days}
    cand = [p for p in preds if p["date"] in dates and p.get("result") == "pending"]
    if len(cand) < 2:
        return None
    top = sorted(cand, key=lambda p: (not p.get("featured"), "bet_of_day" not in (p.get("tags") or []), -(p.get("prob") or 0)))[:5]
    top = sorted(top, key=tb.start)
    rel = list_card("М А Т Ч И   В Ы Х О Д Н Ы Х", " · ".join(date_ru(x) for x in sorted(dates)), top, os.path.join(ROOT, f"data/tg_cards/{now:%Y-%m-%d}-weekend.jpg"))
    rows = [f"{match_line(p)} · {date_ru(p['date'])}, {e(p['time'])}\n✅ <i>{e(p['pick'])}</i> — <b>{tb.k(p['odds'])}</b>\n<blockquote>{e(short(p.get('text', ''), 120))}</blockquote>" for p in top]
    cap = "🗓 <b>ГЛАВНЫЕ МАТЧИ ВЫХОДНЫХ</b>\n\n" + "\n".join(rows) + "\n" + promo_line() + "\n\n" + DISCLAIMER
    while len(strip_tags(cap)) > 1024 and len(rows) > 2:
        rows = rows[:-1]
        cap = "🗓 <b>ГЛАВНЫЕ МАТЧИ ВЫХОДНЫХ</b>\n\n" + "\n".join(rows) + "\n" + promo_line() + "\n\n" + DISCLAIMER
    return {"msg": send(ch, f"data/tg_cards/{now:%Y-%m-%d}-weekend.jpg", cap, dry)}


def do_news(ch, st, preds, dry):
    try:
        news = json.load(open(os.path.join(ROOT, "data", "news.json"), encoding="utf-8")).get("news", [])
    except FileNotFoundError:
        return None
    now = tb.now()
    fresh = {now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")}
    seen = set(st.get("news_ids", []))
    items = [n for n in news if n.get("date") in fresh and n.get("id") not in seen]
    items = sorted(items, key=lambda n: n.get("date"), reverse=True)[:5]
    if len(items) < 2:
        return None
    def build(its):
        return "📰 <b>НОВОСТИ ДНЯ</b>\n\n" + "\n".join(
            f"{SPORT.get(n.get('sport'), '🏆')} <b>{e(n['title'])}</b>\n<blockquote>{e(short(n.get('text', ''), 170))}</blockquote>" for n in its)
    cap = build(items)
    while len(strip_tags(cap)) > 1024 and len(items) > 2:
        items = items[:-1]
        cap = build(items)
    rel = text_card("Н О В О С Т И   Д Н Я", items[0]["title"], " · ".join(n["title"] for n in items[1:4]), f"data/tg_cards/{now:%Y-%m-%d}-news.jpg")
    st["news_ids"] = (list(seen) + [n["id"] for n in items])[-200:]
    return {"msg": send(ch, rel, cap, dry, markup=False)}


def article_points(a, n=4):
    import ast
    body = a.get("body")
    if isinstance(body, str):
        try:
            body = ast.literal_eval(body)
        except Exception:
            body = []
    pts, cur = [], None
    for blk in body or []:
        if not isinstance(blk, (list, tuple)) or len(blk) < 2:
            continue
        if blk[0] == "h2":
            cur = blk[1]
        elif blk[0] == "p" and cur:
            pts.append((cur, short(str(blk[1]), 150)))
            cur = None
    return pts[:n]


def do_school(ch, st, preds, dry):
    try:
        arts = json.load(open(os.path.join(ROOT, "data", "articles.json"), encoding="utf-8")).get("articles", [])
    except FileNotFoundError:
        return None
    if not arts:
        return None
    used = st.get("school", [])
    fresh = [a for a in arts if a["slug"] not in used] or arts
    a = sorted(fresh, key=lambda x: x.get("date", ""))[0]
    pts = article_points(a)
    def build(ps):
        body = "\n\n".join(f"▪️ <b>{e(h)}</b>\n{e(t)}" for h, t in ps)
        return f"🎓 <b>ШКОЛА СТАВОК</b>\n\n<b>{e(a['title'])}</b>\n<blockquote>{e(short(a.get('lead', ''), 260))}</blockquote>\n\n{body}\n\n" + DISCLAIMER_SHORT
    cap = build(pts)
    while len(strip_tags(cap)) > 1024 and len(pts) > 1:
        pts = pts[:-1]
        cap = build(pts)
    rel = text_card("Ш К О Л А   С Т А В О К", a["title"], short(a.get("lead", ""), 200), f"data/tg_cards/school-{a['slug']}.jpg")
    st["school"] = (used + [a["slug"]])[-50:] if a["slug"] not in used else [a["slug"]]
    return {"msg": send(ch, rel, cap, dry, markup=False)}


RESPONSIBLE = [
    ("Ставьте только то, что не жалко потерять", "Ставки — это развлечение, а не способ заработка. Деньги на жизнь, кредиты и бюджет семьи — никогда не в банк."),
    ("Не отыгрывайтесь", "Серия минусов бывает у всех. Увеличивать ставку после проигрыша — самый быстрый способ остаться без банка."),
    ("1–3% банка на одну ставку", "Тогда даже неудачная неделя не выбьет вас из игры. Дистанция важнее одного матча."),
    ("Злитесь, устали или выпили — сегодня без ставок", "Эмоции — главный враг. Решения принимаются на холодную голову."),
    ("Записывайте каждую ставку", "Учёт отрезвляет лучше любых советов: через месяц вы точно знаете, что работает, а что нет."),
    ("Никто не угадывает всё", "Тот, кто обещает 100% проходимость или «договорные матчи», — мошенник. Мы показываем все результаты, включая минусы."),
    ("Перестало быть в удовольствие — сделайте паузу", "В приложении легальной БК можно поставить лимиты на депозит или самоисключение. Это нормально и правильно."),
    ("Не берите в долг на ставки", "Ни у друзей, ни у банка. Ставка в долг — это уже не игра, а проблема."),
]


def do_responsible(ch, st, preds, dry):
    i = st.get("responsible", 0) % len(RESPONSIBLE)
    big, small = RESPONSIBLE[i]
    rel = text_card("О Т В Е Т С Т В Е Н Н А Я   И Г Р А", big, small, f"data/tg_cards/responsible-{i}.jpg")
    cap = f"🧠 <b>ОТВЕТСТВЕННАЯ ИГРА</b>\n\n<b>{e(big)}</b>\n<blockquote>{e(small)}</blockquote>\n\n" + DISCLAIMER_SHORT
    st["responsible"] = i + 1
    return {"msg": send(ch, rel, cap, dry, markup=False)}


def stats_for(ps):
    done = [p for p in ps if p.get("result") in ("win", "loss", "return")]
    if not done:
        return None
    w = sum(p["result"] == "win" for p in done)
    l = sum(p["result"] == "loss" for p in done)
    r = len(done) - w - l
    prof = sum(tb_profit(p) for p in done)
    return {"n": len(done), "w": w, "l": l, "r": r, "profit": prof, "roi": prof / len(done) * 100,
            "hit": w / max(1, w + l) * 100, "best": max((p for p in done if p["result"] == "win"), key=lambda p: float(p["odds"]), default=None)}


MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def do_monthly(ch, st, preds, dry):
    now = tb.now()
    first = now.replace(day=1)
    last_month = first - timedelta(days=1)
    ym = last_month.strftime("%Y-%m")
    ps = sorted([p for p in preds if p["date"].startswith(ym)], key=tb.start)
    s = stats_for(ps)
    if not s:
        return None
    daily, run = {}, 0.0
    for p in ps:
        if p.get("result") in ("win", "loss", "return"):
            run += tb_profit(p)
            daily[p["date"]] = run
    pts = sorted(daily.items())
    name = f"{MONTHS_NOM[last_month.month - 1]} {last_month.year}"
    rel = chart_card("И Т О Г И   М Е С Я Ц А", f"{name} · прибыль в единицах ставки", pts,
                     {"ПРОГНОЗОВ": str(s["n"]), "ЗАШЛО": f"{s['hit']:.0f}%", "ПРИБЫЛЬ": f"{s['profit']:+.1f}", "ROI": f"{s['roi']:+.0f}%"},
                     f"data/tg_cards/{ym}-month.jpg")
    best = s["best"]
    cap = (f"📊 <b>ИТОГИ МЕСЯЦА · {name.upper()}</b>\n\n"
           f"Прогнозов: <b>{s['n']}</b> · зашло <b>{s['w']}</b>, не зашло <b>{s['l']}</b>, возвратов {s['r']}\n"
           f"Проходимость: <b>{s['hit']:.1f}%</b>\n"
           f"Прибыль: <b>{'+' if s['profit'] >= 0 else '−'}{abs(s['profit']):.2f} ед.</b> · ROI <b>{s['roi']:+.1f}%</b>\n"
           + (f"\n🏆 Лучший прогноз: <b>{e(best['home'])} — {e(best['away'])}</b>, <i>{e(best['pick'])}</i> за <b>{tb.k(best['odds'])}</b>\n" if best else "")
           + "<blockquote>Считаем честно: каждый прогноз — ставка в 1 единицу, все результаты на сайте в архиве.</blockquote>"
           + "\n" + promo_line() + "\n\n" + DISCLAIMER)
    return {"msg": send(ch, rel, cap, dry)}


def pinned_text(preds):
    s = stats_for(preds)
    stat = (f"📊 <b>Наша статистика:</b> {s['n']} прогнозов · зашло {s['hit']:.0f}% · ROI {s['roi']:+.1f}%\n"
            "<i>Показываем все результаты, включая проигрыши.</i>\n\n") if s else ""
    return ("👑 <b>Добро пожаловать в канал Metod VIPBET!</b>\n\n"
            "Каждый день — прогнозы на футбол, хоккей и теннис с разбором, вероятностью и честной статистикой.\n\n"
            "🕘 <b>Расписание (МСК)</b>\n"
            "09:00 — итоги вчера и прогнозы дня\n11:00 — 🔥 ставка дня\n12:00 — опрос «Кто победит?»\n"
            "13:00 — новости спорта\n14:00 — 🔒 верняк дня\n17:00 — 🧩 экспресс дня\n19:00 — 🌙 прогноз на вечер\n"
            "Ср — школа ставок · Пт — матчи выходных · Вс — ответственная игра · 1-го числа — итоги месяца\n\n"
            + stat +
            f"🎁 Бонус новым игрокам Мелбет — <b>{e(CFG['bonus'])}</b> по промокоду <b>{e(CFG['promo'])}</b>\n\n" + DISCLAIMER_SHORT)


def do_pinned(ch, st, preds, dry):
    txt = pinned_text(preds)
    print(f"[закреп]\n{strip_tags(txt)}\n")
    if dry:
        return {"msg": None}
    old = st.get("pinned")
    if old:
        try:
            tg("editMessageText", {"chat_id": ch, "message_id": old, "text": txt, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true", "reply_markup": buttons()})
            return {"msg": old}
        except Exception as ex:
            if "not modified" in str(ex):
                return {"msg": old}
            print(f"::warning title=Канал::Не удалось обновить закреп: {ex}")
    m = tg("sendMessage", {"chat_id": ch, "text": txt, "parse_mode": "HTML", "disable_web_page_preview": "true",
                           "reply_markup": buttons()}).get("message_id")
    st["pinned"] = m
    try:
        tg("pinChatMessage", {"chat_id": ch, "message_id": m, "disable_notification": "true"})
    except Exception as ex:
        print(f"::warning title=Канал::Пост опубликован, но не закреплён — дайте боту право «Редактирование сообщений»: {ex}")
    return {"msg": m}


# ---------- «зашло / не зашло» ответами на посты ----------
def do_results(ch, st, preds, dry):
    idx = by_id(preds)
    cutoff = (tb.now() - timedelta(days=7)).isoformat()
    n = 0
    for key, v in st["posted"].items():
        if v.get("replied") or not v.get("msg") or v.get("at", "") < cutoff:
            continue
        kind = v.get("kind")
        text = None
        if kind == "single" and v.get("pid") in idx:
            p = idx[v["pid"]]
            sc = f" {e(p['score'])}" if p.get("score") else ""
            if p.get("result") == "win":
                text = f"✅ <b>ЗАШЛО!</b>\n<b>{e(p['home'])} — {e(p['away'])}</b>{sc}\n<i>{e(p['pick'])}</i> — <b>{tb.k(p['odds'])}</b> 🔥"
            elif p.get("result") == "loss":
                text = (f"❌ <b>Не зашло.</b>\n<b>{e(p['home'])} — {e(p['away'])}</b>{sc}\n<i>{e(p['pick'])}</i> — {tb.k(p['odds'])}\n"
                        "<blockquote>Бывает. Играем дистанцию, а не один матч.</blockquote>")
            elif p.get("result") == "return":
                text = f"↩️ <b>Возврат.</b>\n<b>{e(p['home'])} — {e(p['away'])}</b>{sc}\n<i>{e(p['pick'])}</i> — ставка вернулась"
        elif kind == "express" and v.get("legs"):
            legs = [idx.get(x) for x in v["legs"]]
            if all(l and l.get("result") in ("win", "loss", "return") for l in legs):
                mark = {"win": "✅", "loss": "❌", "return": "↩️"}
                rows = "\n".join(f"{mark[l['result']]} <b>{e(l['home'])} — {e(l['away'])}</b> {e(l.get('score') or '')} · <i>{e(l['pick'])}</i>" for l in legs)
                if any(l["result"] == "loss" for l in legs):
                    text = f"❌ <b>Экспресс не зашёл.</b>\n{rows}"
                else:
                    tot = 1.0
                    for l in legs:
                        tot *= float(l["odds"]) if l["result"] == "win" else 1.0
                    text = f"✅ <b>ЭКСПРЕСС ЗАШЁЛ!</b> Коэффициент <b>{tot:.2f}</b> 🔥\n{rows}"
        elif kind in ("poll", "guess") and v.get("pid") in idx:
            p = idx[v["pid"]]
            if p.get("result") in ("win", "loss", "return") and p.get("score"):
                if kind == "poll":
                    text = f"🏁 <b>Матч завершён: {e(p['score'])}</b> — {e(outcome_text(p) or '')}.\nКто проголосовал верно? 👏"
                    if not dry:
                        try:
                            tg("stopPoll", {"chat_id": ch, "message_id": v["msg"]})
                        except Exception:
                            pass
                else:
                    text = f"🏁 <b>Итоговый счёт: {e(p['home'])} — {e(p['away'])} {e(p['score'])}</b>\nКто угадал — отметьтесь в комментариях 👏"
        if text:
            reply(ch, v["msg"], text, dry)
            if not dry:
                v["replied"] = True
            n += 1
    return n


# ---------- расписание ----------
# (слот, время МСК, условие дня недели/месяца) — бот запускается каждый час и публикует то, что пора
SCHEDULE = [
    ("monthly", "10:00", lambda t: t.day == 1),
    ("pinned", "10:00", lambda t: t.day == 1),
    ("morning", "09:00", None),
    ("bet", "11:00", None),
    ("poll", "12:00", None),
    ("news", "13:00", None),
    ("lock", "14:00", None),
    ("school", "15:00", lambda t: t.weekday() == 2),
    ("express", "17:00", None),
    ("weekend", "18:00", lambda t: t.weekday() == 4),
    ("evening", "19:00", None),
    ("responsible", "20:00", lambda t: t.weekday() == 6),
]
LATE = timedelta(hours=3)  # если запуск GitHub задержался — публикуем, но не позже чем через 3 часа

HANDLERS = {
    "morning": do_morning, "express": do_express, "poll": do_poll, "guess": do_guess, "weekend": do_weekend,
    "news": do_news, "school": do_school, "responsible": do_responsible, "monthly": do_monthly, "pinned": do_pinned,
}


def run_slot(slot, ch, st, preds, dry):
    if slot in ("bet", "lock", "evening"):
        return do_single(ch, st, preds, dry, slot)
    return HANDLERS[slot](ch, st, preds, dry)


def due_slots(now):
    out = []
    for slot, hm, cond in SCHEDULE:
        if cond and not cond(now):
            continue
        h, m = map(int, hm.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if at <= now < at + LATE:
            out.append(slot)
    return out


def main():
    arg = (sys.argv[1] if len(sys.argv) > 1 else "auto").strip()
    valid = {s for s, _, _ in SCHEDULE} | {"auto", "results", "guess"}
    if arg not in valid:
        sys.exit(__doc__)
    dry = os.environ.get("DRY_RUN") == "1" or not token()
    if not token():
        print("::warning title=Канал::Нет секрета TG_BOT_TOKEN — работаю в режиме проверки")
    st = load_state()
    st.setdefault("posted", {})
    preds = tb.load()
    ch = None if dry else channel(st)
    if not dry and not ch:
        print("::warning title=Канал::Бот не знает канал: добавьте его администратором канала (право «Публикация сообщений») и запустите снова")
        save_state(st)
        return
    now = tb.now()
    d = now.strftime("%Y-%m-%d")
    replied = do_results(ch, st, preds, dry)
    if replied:
        print(f"::notice title=Канал::Ответов «зашло/не зашло»: {replied}")
    slots = due_slots(now) if arg == "auto" else ([] if arg == "results" else [arg])
    for slot in slots:
        key = f"{slot}:{d}"
        if key in st["posted"] and arg == "auto":
            continue
        try:
            res = run_slot(slot, ch, st, preds, dry)
        except Exception as ex:
            print(f"::warning title=Канал::{slot}: ошибка {ex}")
            continue
        if not res:
            print(f"::notice title=Канал::{key}: подходящих материалов нет — пропуск")
            if not dry:
                st["posted"][key] = {"at": now.isoformat(timespec="seconds"), "skipped": True}
            continue
        if dry:
            print(f"::notice title=Канал (проверка)::{key}: не опубликовано")
            continue
        st["posted"][key] = dict(res, at=now.isoformat(timespec="seconds"), slot=slot)
        print(f"::notice title=Канал::Опубликовано {key} в «{st.get('channel_title') or ch}»")
    if not dry:
        save_state(st)


if __name__ == "__main__":
    main()
