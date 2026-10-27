"""Сообщает Яндексу (протокол IndexNow) о новых и изменённых страницах сайта.

Использование: python3 scripts/indexnow.py <файл1.html> <файл2.html> ...
Пути — относительно корня репозитория. Запускается сценарием build-pages.yml.
"""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "scripts", "site_config.json"), encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/") + "/"
KEY = CFG.get("indexnow_key")
HOST = BASE.split("/")[2]


def to_url(rel):
    rel = rel.strip().lstrip("./")
    if rel in ("index.html", ""):
        return BASE
    return BASE + rel


def main(paths):
    if not KEY:
        print("Нет indexnow_key в site_config.json")
        return
    pages = sorted({to_url(p) for p in paths if p.endswith(".html") and os.path.exists(os.path.join(ROOT, p))})
    if not pages:
        print("Новых страниц нет")
        return
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"{BASE}{KEY}.txt", "urlList": pages[:10000]}).encode()
    for endpoint in ("https://yandex.com/indexnow", "https://api.indexnow.org/indexnow"):
        try:
            req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"::notice title=IndexNow::{endpoint} ответил {r.status}, отправлено страниц: {len(pages)}")
        except urllib.error.HTTPError as e:
            print(f"::warning title=IndexNow::{endpoint} ошибка {e.code}: {e.read()[:200]!r}")
        except Exception as e:
            print(f"::warning title=IndexNow::{endpoint} ошибка: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
