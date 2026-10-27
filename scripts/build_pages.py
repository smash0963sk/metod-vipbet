"""Собирает статические страницы сайта Metod VIPBET из data/predictions.json:

  match/<id>.html   — отдельная страница каждого прогноза (для поиска в Яндексе и Google)
  archive.html      — архив прогнозов по дням с результатами
  privacy.html      — политика конфиденциальности
  sitemap.xml, robots.txt

Запускается сценарием .github/workflows/build-pages.yml после каждого обновления прогнозов.
Вручную: python3 scripts/build_pages.py
"""
import html, json, os, re, unicodedata
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "scripts", "site_config.json"), encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/") + "/"
MSK = timezone(timedelta(hours=3))
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
RESULT = {"pending": ("Ожидается", "st-pending"), "win": ("Зашёл", "st-win"), "loss": ("Не зашёл", "st-loss"), "return": ("Возврат", "st-return")}
COLORS = ["#b2dd10", "#f4f6ef", "#cdf248", "#8fb80c", "#e6ecd8", "#a3e635", "#d9f99d"]
e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def load(path, default):
    try:
        return json.load(open(os.path.join(ROOT, path), encoding="utf-8"))
    except FileNotFoundError:
        return default


# ---------- logos (same matching rules as on the main page) ----------
def norm_team(n):
    n = unicodedata.normalize("NFKD", str(n or "")).encode("utf-8").decode()
    n = "".join(c for c in n if not unicodedata.combining(c)).lower().replace("ё", "е")
    n = " " + re.sub(r"[^a-z0-9а-я]+", " ", n) + " "
    for _ in range(2):
        n = re.sub(r" (fc|cf|afc|ac|sc|fk|sk|ssc|ss|us|as|cd|club|calcio|hc|хк|фк|\d{4}) ", " ", n)
    return re.sub(r"\s+", " ", n).strip()


LOGOS = {"Футбол": {}, "Хоккей": {}}
for sport, files in (("Футбол", ["data/logos.json"]), ("Хоккей", ["data/logos_khl.json", "data/logos_nhl.json"])):
    for f in files:
        for name, t in load(f, {}).get("teams", {}).items():
            for key in [name] + t.get("aliases", []):
                LOGOS[sport].setdefault(key, t["file"])
                LOGOS[sport].setdefault(norm_team(key), t["file"])


def logo_for(p, side):
    if p.get(side + "Logo"):
        return p[side + "Logo"]
    idx = LOGOS.get(p.get("sport"), {})
    for n in (p.get(side + "En"), p.get(side)):
        if not n:
            continue
        if n in idx:
            return idx[n]
        k = norm_team(n)
        if k and k in idx:
            return idx[k]
    return None


def initials(n):
    words = [w for w in re.sub(r"[^A-Za-zА-Яа-яЁё0-9 ]", "", n).split() if w]
    return "".join(w[0] for w in words[:2]).upper()


def color(n):
    return COLORS[sum(ord(c) for c in n) % len(COLORS)]


def crest(p, side, cls="crest", prefix="../"):
    name = p[side]
    logo = logo_for(p, side)
    if logo:
        return f'<div class="{cls} has-logo"><img src="{prefix}{e(logo)}" alt="{e(name)}" width="48" height="48" loading="lazy"></div>'
    return f'<div class="{cls}" style="background:{color(name)}">{e(initials(name))}</div>'


# ---------- helpers ----------
def human_date(d):
    y, m, dd = map(int, d.split("-"))
    return f"{dd} {MONTHS[m - 1]} {y}"


def short_date(d):
    y, m, dd = d.split("-")
    return f"{dd}.{m}.{y}"


def fmt_k(k):
    try:
        return f"{float(k):.2f}"
    except (TypeError, ValueError):
        return "—"


def profit(p):
    return (float(p["odds"]) - 1) if p.get("result") == "win" else -1.0 if p.get("result") == "loss" else 0.0


def conf(n):
    n = int(n or 2)
    return '<span class="conf">' + "".join(f'<i class="{"on" if i <= n else ""}"></i>' for i in (1, 2, 3)) + "</span>"


def page(title, desc, canonical, body, prefix, extra_head=""):
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta name="theme-color" content="#050505">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{BASE}assets/vipbet-logo.jpg">
<link rel="icon" type="image/png" href="{prefix}assets/favicon.png">
<link rel="apple-touch-icon" href="{prefix}assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,700;0,800;0,900;1,800;1,900&family=Manrope:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="{prefix}assets/style.css?v=4">
{extra_head}
</head>
<body>
<header>
  <div class="wrap hd">
    <a class="logo" href="{prefix}index.html"><img src="{prefix}assets/vipbet-logo.jpg" alt="VIPBET" width="40" height="40"><span>Metod <b>VIP</b>BET</span></a>
    <button class="burger" id="burger" aria-label="Меню" aria-expanded="false">☰</button>
    <nav class="main" id="nav">
      <a href="{prefix}index.html#predictions">Прогнозы</a>
      <a href="{prefix}index.html#express">Экспресс дня</a>
      <a href="{prefix}index.html#news">Новости</a>
      <a href="{prefix}index.html#calc">Калькулятор</a>
      <a href="{prefix}archive.html">Архив</a>
      <a href="{prefix}school.html">Школа</a>
      <a href="{prefix}bonus.html">Бонус</a>
    </nav>
    <a class="btn btn-tg" href="{e(CFG['telegram'])}" target="_blank" rel="noopener">Telegram</a>
  </div>
</header>
<main>
{body}
</main>
<footer>
  <div class="wrap">
    <div class="ft">
      <div>
        <a class="logo" href="{prefix}index.html"><img src="{prefix}assets/vipbet-logo.jpg" alt="" width="40" height="40"><span>Metod <b>VIP</b>BET</span></a>
        <p>Информационный сайт с аналитикой спортивных событий. Мы не принимаем ставки и платежи. Прогнозы формируются с помощью ИИ.</p>
      </div>
      <div>
        <h4>Разделы</h4>
        <ul><li><a href="{prefix}index.html#predictions">Прогнозы</a></li><li><a href="{prefix}index.html#express">Экспресс дня</a></li><li><a href="{prefix}archive.html">Архив прогнозов</a></li><li><a href="{prefix}index.html#calc">Калькулятор</a></li><li><a href="{prefix}school.html">Школа беттинга</a></li><li><a href="{prefix}bonus.html">Промокод Мелбет</a></li></ul>
      </div>
      <div>
        <h4>Мы на связи</h4>
        <ul><li><a href="{e(CFG['telegram'])}" target="_blank" rel="noopener">Telegram-канал</a></li><li><a href="{e(CFG['reg_link'])}" target="_blank" rel="noopener nofollow sponsored">Регистрация в Мелбет</a></li><li><a href="{prefix}privacy.html">Политика конфиденциальности</a></li></ul>
      </div>
    </div>
    <div class="disc"><span class="age">18+</span><p>Прогнозы отражают оценку вероятностей и не гарантируют результат. Ставки на спорт связаны с риском потери денег — играйте ответственно и только у легальных букмекеров РФ. © {datetime.now(MSK).year} Metod VIPBET</p></div>
  </div>
</footer>
<div class="toast" id="toast" role="status">Промокод скопирован</div>
<script src="{prefix}assets/common.js?v=1"></script>
<script>
(function(){{
  var b=document.getElementById('burger'),n=document.getElementById('nav');
  b.onclick=function(){{var o=n.classList.toggle('open');b.setAttribute('aria-expanded',o);}};
  var t=document.getElementById('toast');
  document.querySelectorAll('.copy-promo').forEach(function(btn){{btn.onclick=function(){{
    var done=function(){{t.classList.add('show');setTimeout(function(){{t.classList.remove('show');}},1600);}};
    if(navigator.clipboard){{navigator.clipboard.writeText('{e(CFG['promo'])}').then(done,done);}}else{{done();}}
  }};}});
}})();
</script>
</body>
</html>
"""


def promo_card():
    return f"""<div class="code-card">
        <small>Бонус по промокоду</small>
        <div class="bonus-sum">до <span>30 000 ₽</span></div>
        <div class="code"><b>{e(CFG['promo'])}</b><button type="button" class="copy-promo">Скопировать</button></div>
        <a class="btn btn-gold" href="{e(CFG['reg_link'])}" target="_blank" rel="noopener nofollow sponsored">Зарегистрироваться в Мелбет</a>
        <p class="fine"><b style="color:var(--text)">Ставьте только у легальных букмекеров РФ</b> с лицензией ФНС. 18+. Условия бонуса — на сайте букмекера.</p>
        <a class="btn btn-tg" href="{e(CFG['telegram'])}" target="_blank" rel="noopener">Прогнозы раньше всех — в Telegram</a>
      </div>"""


def arow(p, prefix):
    lbl, cls = RESULT.get(p.get("result"), RESULT["pending"])
    score = f" · {e(p['score'])}" if p.get("score") else ""
    return (f'<a class="arow" href="{prefix}match/{e(p["id"])}.html"><span class="t">{e(p["home"])} — {e(p["away"])}'
            f'<small>{e(p["sport"])} · {e(p["league"])} · {e(p["time"])} МСК · {e(p["pick"])}{score}</small></span>'
            f'<span class="k tabnum">{fmt_k(p.get("odds"))}</span><span class="status {cls}">{lbl}</span></a>')


def form_html(f):
    if not f:
        return '<p>Нет данных</p>'
    m = {"В": ("fW", "Победа"), "Н": ("fD", "Ничья"), "П": ("fL", "Поражение")}
    return '<div class="form">' + "".join(f'<i class="{m[c][0]}" title="{m[c][1]}">{c}</i>' for c in f if c in m) + "</div>"


def tag_badges(p):
    t = p.get("tags") or []
    return ('<span class="badge">Ставка дня</span>' if "bet_of_day" in t else "") + ('<span class="badge lock">Верняк дня</span>' if "lock_of_day" in t else "")


def stats_block(p):
    st = p.get("stats") or {}
    parts = []
    prob = p.get("prob")
    if prob:
        try:
            k = float(p.get("odds"))
            book = 100 / k
            parts.append(f'''<div class="valuebar">
          <div class="sbox"><small>Наша оценка</small><b class="tabnum">{round(float(prob))}%</b></div>
          <div class="sbox"><small>Оценка букмекера</small><b class="tabnum">{book:.0f}%</b></div>
          <div class="sbox"><small>Выгодно от кэфа</small><b class="tabnum">{100 / float(prob):.2f}</b></div>
        </div>''')
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    form = st.get("form") or {}
    if form.get("home") or form.get("away"):
        parts.append(f'''<div class="srow">
          <div class="sbox"><small>Форма: {e(p["home"])}</small>{form_html(form.get("home"))}</div>
          <div class="sbox"><small>Форма: {e(p["away"])}</small>{form_html(form.get("away"))}</div>
        </div>''')
    table = st.get("table") or {}
    if table.get("home") or table.get("away"):
        parts.append(f'''<div class="srow">
          <div class="sbox"><small>Положение: {e(p["home"])}</small><p>{e(table.get("home") or "—")}</p></div>
          <div class="sbox"><small>Положение: {e(p["away"])}</small><p>{e(table.get("away") or "—")}</p></div>
        </div>''')
    if st.get("h2h"):
        parts.append(f'<div class="sbox"><small>Очные встречи</small><p>{e(st["h2h"])}</p></div>')
    absent = st.get("absent") or {}
    if absent.get("home") or absent.get("away"):
        parts.append(f'''<div class="srow">
          <div class="sbox"><small>Не сыграют: {e(p["home"])}</small><p>{e(absent.get("home") or "Потерь нет")}</p></div>
          <div class="sbox"><small>Не сыграют: {e(p["away"])}</small><p>{e(absent.get("away") or "Потерь нет")}</p></div>
        </div>''')
    if st.get("note"):
        parts.append(f'<div class="sbox"><small>Важно</small><p>{e(st["note"])}</p></div>')
    if not parts:
        return ""
    legend = '<p class="fine">Форма — последние матчи, самый свежий справа. В — победа, Н — ничья, П — поражение.</p>' if form else ""
    return '<div class="mstats"><h2>Статистика матча</h2>' + "".join(parts) + legend + "</div>"


def match_page(p, all_p):
    title = f'{p["home"]} — {p["away"]}: прогноз и ставка на {short_date(p["date"])} | Metod VIPBET'
    desc = f'Прогноз на матч {p["home"]} — {p["away"]} ({p["league"]}) {human_date(p["date"])}: {p["pick"]} за {fmt_k(p.get("odds"))}. {p.get("text", "")}'[:300]
    url = f'{BASE}match/{p["id"]}.html'
    lbl, cls = RESULT.get(p.get("result"), RESULT["pending"])
    k = p.get("odds1x2") or []
    odds = ""
    if len(k) == 3:
        odds = '<div class="odds">' + "".join(f'<div class="odd"><small>{n}</small><b class="tabnum">{fmt_k(k[i])}</b></div>' for i, n in enumerate(["П1", "X", "П2"])) + "</div>"
    score = f'<div class="score-final" style="font-size:16px">Итоговый счёт: {e(p["score"])}</div>' if p.get("score") else ""
    same_day = [x for x in all_p if x["date"] == p["date"] and x["id"] != p["id"]]
    others = ""
    if same_day:
        others = '<section style="padding-top:8px"><div class="wrap"><h2 style="font-size:22px;margin-bottom:14px">Другие прогнозы на ' + e(human_date(p["date"])) + "</h2>" + "".join(arow(x, "../") for x in sorted(same_day, key=lambda x: x["time"])) + "</div></section>"
    ld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f'{p["home"]} — {p["away"]}',
          "startDate": f'{p["date"]}T{p["time"]}:00+03:00', "sport": p.get("sport"),
          "homeTeam": {"@type": "SportsTeam", "name": p["home"]}, "awayTeam": {"@type": "SportsTeam", "name": p["away"]},
          "description": p.get("text", ""), "url": url, "eventStatus": "https://schema.org/EventScheduled",
          "location": {"@type": "Place", "name": p.get("league", "")}}
    head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    body = f"""<section style="padding-block:36px 24px">
  <div class="wrap">
    <p class="crumbs"><a href="../index.html">Главная</a> › <a href="../index.html#predictions">Прогнозы</a> › {e(p['home'])} — {e(p['away'])}</p>
    <div class="eyebrow">{tag_badges(p)}{e(p['sport'])} · {e(p['league'])}</div>
    <h1 class="page-h1">{e(p['home'])} — {e(p['away'])}: прогноз на {e(human_date(p['date']))}</h1>
    <p class="meta" style="color:var(--dim);margin:0 0 24px">Начало: {e(human_date(p['date']))}, {e(p['time'])} по Москве</p>
    <div class="mp">
      <article class="mp-card">
        <div class="teams">
          <div class="team">{crest(p, 'home')}<span>{e(p['home'])}</span></div>
          <div class="vs"><b class="tabnum">{e(p['time'])}</b>МСК</div>
          <div class="team">{crest(p, 'away')}<span>{e(p['away'])}</span></div>
        </div>
        {odds}
        <div class="pickrow"><div class="pickbox"><small>Прогноз</small>{e(p['pick'])}</div><div class="pickbox k"><small>Кэф</small><b class="tabnum">{fmt_k(p.get('odds'))}</b></div><div class="pickbox"><small>Уверенность</small>{conf(p.get('confidence'))}</div><span class="status {cls}">{lbl}</span></div>
        {score}
        {stats_block(p)}
        <h2>Разбор матча</h2>
        <p>{e(p.get('text', ''))}</p>
        {f"<p>{e(p['more'])}</p>" if p.get('more') else ''}
        <p class="fine">Прогноз — оценка вероятности исхода, а не гарантия результата.</p>
      </article>
      <aside>{promo_card()}</aside>
    </div>
  </div>
</section>
{others}"""
    return page(title, desc, url, body, "../", head)


def archive_page(all_p):
    days = {}
    for p in all_p:
        days.setdefault(p["date"], []).append(p)
    settled = [p for p in all_p if p.get("result") in ("win", "loss", "return")]
    wins = sum(1 for p in settled if p["result"] == "win")
    losses = sum(1 for p in settled if p["result"] == "loss")
    total = sum(profit(p) for p in settled)
    summary = (f'<div class="tiles" style="margin-bottom:32px"><div class="tile"><small>Всего прогнозов</small><b class="tabnum">{len(all_p)}</b></div>'
               f'<div class="tile"><small>Зашло / не зашло</small><b class="tabnum">{wins} / {losses}</b></div>'
               f'<div class="tile {"good" if wins >= losses else "bad"}"><small>Проходимость</small><b class="tabnum">{round(wins / (wins + losses) * 100) if wins + losses else 0}%</b></div>'
               f'<div class="tile {"good" if total >= 0 else "bad"}"><small>Прибыль, ед.</small><b class="tabnum">{"+" if total >= 0 else "−"}{abs(total):.2f}</b></div></div>')
    blocks = []
    for d in sorted(days, reverse=True):
        ps = sorted(days[d], key=lambda x: x["time"])
        st = [p for p in ps if p.get("result") in ("win", "loss", "return")]
        w = sum(1 for p in st if p["result"] == "win"); l = sum(1 for p in st if p["result"] == "loss")
        pr = sum(profit(p) for p in st)
        info = f"{w} зашло · {l} не зашло · {'+' if pr >= 0 else '−'}{abs(pr):.2f} ед." if st else "матчи ещё не сыграны"
        blocks.append(f'<div class="day"><h2>{e(human_date(d))} <small>{info}</small></h2>' + "".join(arow(p, "") for p in ps) + "</div>")
    body = f"""<section style="padding-block:36px">
  <div class="wrap">
    <p class="crumbs"><a href="index.html">Главная</a> › Архив прогнозов</p>
    <div class="eyebrow">Честная статистика</div>
    <h1 class="page-h1">Архив прогнозов</h1>
    <p style="color:var(--dim);margin:0 0 24px;max-width:62ch">Все прогнозы Metod VIPBET по дням, включая проигранные. Прибыль считается при ставке 1 единица на каждый прогноз.</p>
    {summary}
    {''.join(blocks) or '<div class="empty">Архив пополнится после первых прогнозов.</div>'}
  </div>
</section>"""
    return page("Архив прогнозов на спорт с результатами | Metod VIPBET",
                "Архив всех прогнозов Metod VIPBET по дням: результаты, проходимость и прибыль. Честная статистика без удалённых ставок.",
                BASE + "archive.html", body, "")


def privacy_page():
    upd = human_date(datetime.now(MSK).strftime("%Y-%m-%d"))
    body = f"""<section style="padding-block:36px">
  <div class="wrap prose">
    <p class="crumbs"><a href="index.html">Главная</a> › Политика конфиденциальности</p>
    <h1 class="page-h1">Политика конфиденциальности</h1>
    <p>Редакция от {e(upd)}. Настоящая политика описывает, какие данные обрабатывает сайт Metod VIPBET (далее — Сайт) и как они используются. Документ составлен в соответствии с Федеральным законом № 152-ФЗ «О персональных данных».</p>
    <h2>1. Какие данные мы собираем</h2>
    <p>Сайт не предлагает регистрацию, не принимает платежи и не просит вводить имя, телефон или электронную почту. Мы не собираем персональные данные, позволяющие установить вашу личность.</p>
    <p>Для работы Сайта браузер сохраняет на вашем устройстве технические отметки в cookies и локальном хранилище: подтверждение возраста 18+, согласие с этим уведомлением, а также кэш логотипов команд, чтобы страницы открывались быстрее. Эти данные остаются на вашем устройстве и не передаются нам.</p>
    <h2>2. Сторонние сервисы</h2>
    <p>Сайт размещён на GitHub Pages и загружает шрифты с сервиса Google Fonts. При открытии страниц эти сервисы могут получать технические данные: IP-адрес, тип браузера, время запроса. Их обработка регулируется политиками GitHub и Google.</p>
    <p>Ссылки на сайты букмекеров и Telegram ведут на сторонние ресурсы. Обработка данных на этих ресурсах регулируется их собственными правилами.</p>
    <h2>3. Возрастное ограничение</h2>
    <p>Сайт содержит информацию о ставках на спорт и предназначен только для лиц старше 18 лет. Прогнозы носят информационный характер и не являются призывом делать ставки. Ставки на спорт разрешены в России только у букмекеров с лицензией ФНС России.</p>
    <h2>4. Как удалить данные</h2>
    <p>Вы можете в любой момент очистить cookies и данные сайта в настройках браузера. После этого Сайт снова спросит подтверждение возраста.</p>
    <h2>5. Контакты</h2>
    <p>Вопросы о работе Сайта можно задать в нашем <a href="{e(CFG['telegram'])}" target="_blank" rel="noopener" style="color:var(--gold2)">Telegram-канале</a>.</p>
  </div>
</section>"""
    return page("Политика конфиденциальности | Metod VIPBET", "Политика конфиденциальности сайта Metod VIPBET: какие данные обрабатываются и как.", BASE + "privacy.html", body, "")


FAQ = [
    ("Как получить бонус по промокоду VIPBET2026?", "Зарегистрируйтесь в Мелбет по нашей ссылке и укажите промокод VIPBET2026 в поле промокода при регистрации. После первого пополнения счёта бонус начисляется по правилам акции букмекера."),
    ("Можно ли ввести промокод после регистрации?", "Как правило, приветственный промокод вводится только при регистрации нового игрового счёта. Если вы забыли его указать, уточните возможность в поддержке букмекера."),
    ("Кто может получить бонус?", "Новые игроки старше 18 лет, которые впервые регистрируются у букмекера. Повторные регистрации и мультиаккаунты бонус не получают."),
    ("Сколько составляет бонус?", "До 30 000 ₽. Точный размер зависит от суммы первого пополнения. Требования к отыгрышу, сроки и минимальный коэффициент указаны в правилах акции на сайте букмекера."),
    ("Почему важно ставить у легального букмекера?", "Легальные букмекеры работают по лицензии ФНС России и подключены к ЕЦУПИС: выплаты защищены законом, а выигрыши можно спокойно вывести на карту. Нелегальные сайты могут заблокировать счёт или не выплатить выигрыш."),
    ("Где брать прогнозы для ставок?", "На главной странице Metod VIPBET каждое утро появляются свежие прогнозы с разбором, Экспресс дня, Ставка дня и Верняк дня. Все результаты, включая проигрыши, мы показываем в архиве."),
]


def bonus_page():
    steps = [
        ("Перейдите по ссылке", "Нажмите кнопку «Зарегистрироваться в Мелбет» на этой странице."),
        ("Заполните регистрацию", "Укажите телефон или почту и придумайте пароль. Регистрация доступна только с 18 лет."),
        ("Введите промокод VIPBET2026", "В поле «Промокод» вставьте VIPBET2026 — скопировать его можно кнопкой на этой странице."),
        ("Пополните счёт", "После первого депозита бонус до 30 000 ₽ начислится по правилам акции."),
        ("Ставьте по прогнозам", "Используйте наши ежедневные прогнозы, Экспресс дня и калькулятор ставок."),
    ]
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]}
    head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    body = f"""<section style="padding-block:36px">
  <div class="wrap">
    <p class="crumbs"><a href="index.html">Главная</a> › Промокод Мелбет</p>
    <div class="eyebrow">Бонус для новых игроков</div>
    <h1 class="page-h1">Промокод Мелбет {e(CFG['promo'])} — бонус до 30 000 ₽</h1>
    <p style="color:var(--dim);max-width:64ch;margin:0 0 28px">Зарегистрируйтесь в Мелбет с промокодом {e(CFG['promo'])} и получите приветственный бонус. Ниже — пошаговая инструкция и ответы на частые вопросы.</p>
    <div class="mp">
      <div>
        <h2 style="font-size:22px;margin-bottom:14px">Как получить бонус</h2>
        <ol class="steps-big">{''.join(f'<li><b>{e(t)}</b>{e(d)}</li>' for t, d in steps)}</ol>
        <h2 style="font-size:22px;margin:32px 0 14px">Частые вопросы</h2>
        <div class="faq prose">{''.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in FAQ)}</div>
      </div>
      <aside>{promo_card()}</aside>
    </div>
  </div>
</section>"""
    return page(f"Промокод Мелбет {CFG['promo']} — бонус до 30 000 ₽ | Metod VIPBET",
                f"Промокод Мелбет {CFG['promo']}: бонус до 30 000 ₽ новым игрокам. Пошаговая инструкция, как ввести промокод, и ответы на частые вопросы.",
                BASE + "bonus.html", body, "", head)


def article_html(a):
    out = []
    for kind, val in a.get("body", []):
        if kind == "h2":
            out.append(f"<h2>{e(val)}</h2>")
        elif kind == "p":
            out.append(f"<p>{e(val)}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in val) + "</ul>")
    return "".join(out)


def school_pages(arts):
    arts = sorted(arts, key=lambda a: a.get("date", ""), reverse=True)
    cards = "".join(f'<a class="acard" href="school/{e(a["slug"])}.html"><small>Школа беттинга</small><h3>{e(a["title"])}</h3><p>{e(a.get("lead", ""))}</p></a>' for a in arts)
    index = f"""<section style="padding-block:36px">
  <div class="wrap">
    <p class="crumbs"><a href="index.html">Главная</a> › Школа беттинга</p>
    <div class="eyebrow">Обучение</div>
    <h1 class="page-h1">Школа беттинга</h1>
    <p style="color:var(--dim);max-width:62ch;margin:0 0 28px">Простые объяснения ставок на спорт: тоталы, форы, экспрессы и управление банком. Новые статьи появляются каждую неделю.</p>
    <div class="acards">{cards or '<div class="empty">Статьи скоро появятся.</div>'}</div>
  </div>
</section>"""
    pages = {"school.html": page("Школа беттинга — как делать ставки на спорт | Metod VIPBET",
                                 "Обучение ставкам на спорт простыми словами: тотал, фора, экспресс, банкролл-менеджмент.",
                                 BASE + "school.html", index, "")}
    for a in arts:
        others = "".join(f'<a class="acard" href="{e(o["slug"])}.html"><small>Читать</small><h3>{e(o["title"])}</h3></a>' for o in arts if o["slug"] != a["slug"])[:4000]
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "description": a.get("lead", ""),
              "datePublished": a.get("date"), "author": {"@type": "Organization", "name": "Metod VIPBET"}, "inLanguage": "ru"}
        head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
        body = f"""<section style="padding-block:36px">
  <div class="wrap">
    <p class="crumbs"><a href="../index.html">Главная</a> › <a href="../school.html">Школа беттинга</a> › {e(a['title'])}</p>
    <div class="mp">
      <article class="prose">
        <div class="eyebrow">Школа беттинга</div>
        <h1 class="page-h1">{e(a['title'])}</h1>
        <p style="font-size:18px;color:var(--text)">{e(a.get('lead', ''))}</p>
        {article_html(a)}
        <p class="fine" style="margin-top:24px">18+. Ставки на спорт связаны с риском потери денег. Делайте ставки только у легальных букмекеров РФ.</p>
      </article>
      <aside>{promo_card()}</aside>
    </div>
    {f'<h2 style="font-size:22px;margin:36px 0 14px">Ещё статьи</h2><div class="acards">{others}</div>' if others else ''}
  </div>
</section>"""
        pages[f"school/{a['slug']}.html"] = page(f"{a['title']} | Школа беттинга Metod VIPBET", a.get("lead", "")[:300],
                                                 f"{BASE}school/{a['slug']}.html", body, "../", head)
    return pages


def write(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if old != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def main():
    data = load("data/predictions.json", {"predictions": []})
    preds = [p for p in data.get("predictions", []) if p.get("id") and p.get("home") and p.get("away") and p.get("date")]
    for p in preds:
        p.setdefault("time", "00:00")
    ids = set()
    for p in preds:
        write(f"match/{p['id']}.html", match_page(p, preds))
        ids.add(p["id"] + ".html")
    mdir = os.path.join(ROOT, "match")
    if os.path.isdir(mdir):
        for f in os.listdir(mdir):
            if f.endswith(".html") and f not in ids:
                os.remove(os.path.join(mdir, f))
    write("archive.html", archive_page(preds))
    write("privacy.html", privacy_page())
    write("bonus.html", bonus_page())
    arts = [a for a in load("data/articles.json", {"articles": []}).get("articles", []) if a.get("slug") and a.get("title")]
    sp = school_pages(arts)
    for rel, text in sp.items():
        write(rel, text)
    sdir = os.path.join(ROOT, "school")
    if os.path.isdir(sdir):
        keep = {rel.split("/", 1)[1] for rel in sp if rel.startswith("school/")}
        for f in os.listdir(sdir):
            if f.endswith(".html") and f not in keep:
                os.remove(os.path.join(sdir, f))
    today = datetime.now(MSK).strftime("%Y-%m-%d")
    urls = [(BASE, today, "daily", "1.0"), (BASE + "archive.html", today, "daily", "0.8"), (BASE + "privacy.html", today, "yearly", "0.2"),
            (BASE + "bonus.html", today, "weekly", "0.9"), (BASE + "school.html", today, "weekly", "0.6")]
    urls += [(f"{BASE}school/{a['slug']}.html", min(a.get("date", today), today), "monthly", "0.6") for a in arts]
    urls += [(f"{BASE}match/{p['id']}.html", min(p["date"], today), "daily" if p.get("result") == "pending" else "monthly", "0.7") for p in sorted(preds, key=lambda x: x["date"], reverse=True)]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += "".join(f"  <url><loc>{e(u)}</loc><lastmod>{d}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>\n" for u, d, c, pr in urls)
    sm += "</urlset>\n"
    write("sitemap.xml", sm)
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n")
    print(f"Страниц матчей: {len(preds)}")


if __name__ == "__main__":
    main()
