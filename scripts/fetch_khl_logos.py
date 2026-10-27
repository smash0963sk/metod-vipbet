"""Скачивает логотипы клубов КХЛ из открытого API лиги (то же API, что у мобильного приложения КХЛ).

Результат:
  assets/logos/khl-<id>.<ext>  — логотипы
  data/logos_khl.json          — справочник: название клуба -> файл и псевдонимы

Запускается сценарием GitHub Actions .github/workflows/khl-logos.yml.
"""
import json, os, re, sys, time, urllib.request

API = "https://khl.api.webcaster.pro/api/khl_mobile/teams_v2.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Русское название -> английское и другие варианты написания
ALIASES = {
    "Авангард": ["Avangard Omsk", "Avangard"],
    "Автомобилист": ["Avtomobilist Yekaterinburg", "Avtomobilist"],
    "Адмирал": ["Admiral Vladivostok", "Admiral"],
    "Ак Барс": ["Ak Bars Kazan", "Ak Bars"],
    "Амур": ["Amur Khabarovsk", "Amur"],
    "Барыс": ["Barys Astana", "Barys"],
    "Витязь": ["Vityaz Podolsk", "Vityaz"],
    "Динамо М": ["Dynamo Moscow", "Dinamo Moscow", "Динамо Москва", "Динамо"],
    "Динамо Мн": ["Dinamo Minsk", "Динамо Минск"],
    "Куньлунь Ред Стар": ["Kunlun Red Star", "Куньлунь"],
    "Драконы": ["Shanghai Dragons", "Шанхайские Драконы", "Драконы Шанхай", "Шанхай"],
    "Лада": ["Lada Togliatti", "Lada"],
    "Локомотив": ["Lokomotiv Yaroslavl", "Lokomotiv"],
    "Металлург Мг": ["Metallurg Magnitogorsk", "Металлург", "Металлург Магнитогорск"],
    "Нефтехимик": ["Neftekhimik Nizhnekamsk", "Neftekhimik"],
    "Салават Юлаев": ["Salavat Yulaev Ufa", "Salavat Yulaev"],
    "Северсталь": ["Severstal Cherepovets", "Severstal"],
    "Сибирь": ["Sibir Novosibirsk", "Sibir"],
    "СКА": ["SKA Saint Petersburg", "SKA St. Petersburg", "SKA"],
    "Сочи": ["HC Sochi", "ХК Сочи"],
    "Спартак": ["Spartak Moscow", "Спартак Москва"],
    "Торпедо": ["Torpedo Nizhny Novgorod", "Torpedo"],
    "Трактор": ["Traktor Chelyabinsk", "Traktor"],
    "ЦСКА": ["CSKA Moscow", "CSKA"],
}


def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\b(хк|hc)\b", " ", s)
    return re.sub(r"[^a-z0-9а-я]+", " ", s).strip()


def get(url, retries=5):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read(), r.headers.get("Content-Type", "")
        except Exception as e:  # API периодически не отвечает — повторяем
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"не удалось получить {url}: {last}")


def main():
    body, _ = get(API)
    raw = json.loads(body)
    teams = [w["team"] for w in raw if isinstance(w, dict) and isinstance(w.get("team"), dict)]
    if not teams:
        sys.exit("API не вернуло список клубов")
    alias_by_norm = {norm(k): v for k, v in ALIASES.items()}
    out = {}
    os.makedirs(os.path.join(ROOT, "assets", "logos"), exist_ok=True)
    for t in teams:
        name, image = t.get("name"), t.get("image")
        if not name or not image:
            continue
        try:
            data, ctype = get(image)
        except Exception as e:
            print("  ✗", name, e)
            continue
        if len(data) < 300:
            print("  ✗", name, "пустой файл")
            continue
        ext = ".svg" if "svg" in ctype or image.lower().endswith(".svg") else ".jpg" if "jpeg" in ctype else ".webp" if "webp" in ctype else ".png"
        fname = f"assets/logos/khl-{t.get('id')}{ext}"
        with open(os.path.join(ROOT, fname), "wb") as f:
            f.write(data)
        aliases = list(alias_by_norm.get(norm(name), []))
        if t.get("location"):
            aliases.append(f"{name} {t['location']}")
        out[name] = {"file": fname, "league": "KHL", "location": t.get("location"), "aliases": aliases}
        print("  ✓", name)
    with open(os.path.join(ROOT, "data", "logos_khl.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "khl.api.webcaster.pro", "teams": out}, f, ensure_ascii=False, indent=1)
    print(f"Логотипов КХЛ: {len(out)} из {len(teams)}")
    if not out:
        sys.exit(1)


if __name__ == "__main__":
    main()
