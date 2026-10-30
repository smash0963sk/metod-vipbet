"""Озвучка эпизода через Fish Audio: каждая реплика — отдельный файл albert/build/<эпизод>/voice/NN.mp3.

python3 albert/tools/tts.py ep01
Секрет: FISH_API_KEY. Голоса — в albert/voices.json ({"A": "<id голоса Альберта>", "S": "<id голоса Стаса>"}).
Если голосов нет, бот выбирает популярные русские мужские голоса из библиотеки Fish Audio и записывает их в voices.json.
Уже озвученные реплики (тот же текст и голос) повторно не озвучиваются — Fish Audio платный.
"""
import hashlib, json, os, subprocess, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.fish.audio"
KEY = os.environ.get("FISH_API_KEY")
MODEL = os.environ.get("FISH_MODEL", "s2.1-pro")
VOICES_FILE = os.path.join(ROOT, "voices.json")
SPEED = {"A": 1.0, "S": 1.06, "X": 1.04}


def req(method, path, body=None, headers=None, raw=False):
    h = {"Authorization": f"Bearer {KEY}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(API + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.read() if raw else json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Fish Audio {e.code}: {e.read()[:300]!r}")


def list_voices():
    """Показывает русские мужские голоса из библиотеки Fish Audio (для выбора в albert/voices.json)."""
    seen = set()
    for sort in ("task_count", "score", "created_at"):
        for page in (1, 2):
            q = urllib.parse.urlencode({"language": "ru", "page_size": 50, "page_number": page, "sort_by": sort})
            for m in req("GET", f"/model?{q}").get("items", []):
                tags = [t.lower() for t in (m.get("tags") or [])]
                if m["_id"] in seen or "female" in tags or "male" not in tags:
                    continue
                seen.add(m["_id"])
                print(f"::notice title=Голос::{m.get('title')} | id {m['_id']} | {', '.join(tags[:8])}")


def pick_voices():
    # Голоса выбираются вручную: в библиотеке много клонов реальных людей — их использовать нельзя.
    try:
        v = json.load(open(VOICES_FILE, encoding="utf-8"))
    except FileNotFoundError:
        v = {}
    if not (v.get("A") and v.get("S")):  # X — Алекс (рассказчик про спорт)
        raise RuntimeError("Не выбраны голоса: укажите id в albert/voices.json (запустите с list_voices, чтобы увидеть варианты)")
    return v


ENGINE = os.environ.get("VOICE_ENGINE", "fish")
SUFFIX = "" if ENGINE == "fish" else "_" + ENGINE
# Бесплатные движки: Silero (офлайн, русская модель v4) и Edge TTS (голоса Microsoft)
SILERO = {"A": "eugene", "S": "aidar"}
EDGE = {"A": ("ru-RU-DmitryNeural", "-6Hz", "+0%"), "S": ("ru-RU-DmitryNeural", "+18Hz", "+8%")}
RU_WORDS = {"USDT": "ю эс ди т+и", "Tether": "т+эзер", "Telegram": "телегр+ам", "США": "сэ шэ +а"}


def clean(text):
    import re
    return re.sub(r"\[[^\]]*\]\s*", "", text).strip()  # теги эмоций понимает только Fish Audio


def for_silero(text):
    """Silero не читает латиницу и цифры — заменяем словами."""
    import re
    from num2words import num2words
    t = clean(text)
    for k, v in RU_WORDS.items():
        t = t.replace(k, v)
    t = re.sub(r"\b(\d{4})\s+год", lambda m: num2words(int(m.group(1)), lang="ru", to="ordinal") + " год", t)
    t = re.sub(r"\d+", lambda m: num2words(int(m.group(0)), lang="ru"), t)
    return t.replace("—", ",").replace("–", " ").replace("…", ".")


def for_plain(text):
    """Для открытых моделей: цифры словами, латиница — по-русски, без тегов и знаков ударения."""
    return for_silero(text).replace("+", "")


XTTS = {"A": "Damien Black", "S": "Andrew Chipper"}
_xtts = None


def synth_xtts(text, who, path):
    global _xtts
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    if _xtts is None:
        from TTS.api import TTS
        _xtts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    wav = path + ".wav"
    _xtts.tts_to_file(text=for_plain(text), file_path=wav, speaker=XTTS[who], language="ru", split_sentences=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "192k", path], check=True)
    os.remove(wav)


_silero = None


def synth_silero(text, who, path):
    global _silero
    import torch
    if _silero is None:
        _silero, _ = torch.hub.load("snakers4/silero-models", model="silero_tts", language="ru", speaker="v4_ru", trust_repo=True)
    wav = path + ".wav"
    _silero.save_wav(text=for_silero(text), speaker=SILERO[who], sample_rate=48000, put_accent=True, put_yo=True, audio_path=wav)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "192k", path], check=True)
    os.remove(wav)


def synth_edge(text, who, path):
    voice, pitch, rate = EDGE[who]
    tries = [["--pitch=" + pitch, "--rate=" + rate]] * 4 + [[]] * 2
    time.sleep(2)  # Microsoft ограничивает частоту запросов
    for k, extra in enumerate(tries):
        r = subprocess.run(["edge-tts", "--voice", voice, *extra, "--text", clean(text), "--write-media", path], capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 1000:
            if not extra and pitch:  # без параметров — меняем тон уже в ffmpeg
                tmp = path + ".tmp.mp3"
                semis = int(pitch.replace("Hz", "")) / 12.0
                f = 2 ** (semis / 12)
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-af", f"asetrate=24000*{f:.4f},aresample=24000,atempo={1 / f:.4f}", tmp], check=True)
                os.replace(tmp, path)
            return
        print(f"Edge TTS: попытка {k + 1} не удалась: {(r.stderr or '').strip()[-120:]}")
        time.sleep(min(60, 5 * 2 ** k))
    if os.path.exists(path):
        os.remove(path)
    raise RuntimeError("Edge TTS не отдал звук (сервис Microsoft не отвечает этому серверу)")


ELEVEN_FILE = os.path.join(ROOT, "voices_eleven.json")
ELEVEN_DEFAULT = {"A": "JBFqnCBsd6RMkjVDRZzb", "S": "TX3LPaxmHKxFdv7VOQHJ"}  # George и Liam — стандартные голоса ElevenLabs


def eleven_voices():
    try:
        v = json.load(open(ELEVEN_FILE, encoding="utf-8"))
        return {"A": v.get("A") or ELEVEN_DEFAULT["A"], "S": v.get("S") or ELEVEN_DEFAULT["S"], "model": v.get("model")}
    except FileNotFoundError:
        return dict(ELEVEN_DEFAULT, model=None)


def synth_eleven(text, who, path, voices, prev_text=None, next_text=None):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("Нет секрета ELEVENLABS_API_KEY")
    model = voices.get("model") or os.environ.get("ELEVEN_MODEL") or "eleven_v4"
    settings = {"stability": 0.4, "similarity_boost": 0.8}
    if model != "eleven_v4":
        settings.update(style=0.35, use_speaker_boost=True)
    body = {"text": text, "model_id": model, "voice_settings": settings}
    if prev_text:
        body["previous_text"] = clean(prev_text)
    if next_text:
        body["next_text"] = clean(next_text)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voices[who]}?output_format=mp3_44100_192"
    for attempt in range(3):
        r = urllib.request.Request(url, data=json.dumps(body).encode(),
                                   headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
        try:
            with urllib.request.urlopen(r, timeout=180) as resp:
                open(path, "wb").write(resp.read())
            return
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode("utf-8", "ignore")
            if e.code in (401, 402, 403) or "quota" in msg:
                raise RuntimeError(f"ElevenLabs {e.code}: {msg}")
            if e.code == 422 and model == "eleven_v4":
                model = body["model_id"] = "eleven_multilingual_v2"  # запасная модель
                continue
            if attempt == 2:
                raise RuntimeError(f"ElevenLabs {e.code}: {msg}")
            time.sleep(5)


def synth_fish(text, who, path, voices):
    global MODEL
    body = {"text": text, "reference_id": voices[who], "format": "mp3", "mp3_bitrate": 192, "normalize": True,
            "latency": "normal", "prosody": {"speed": SPEED.get(who, 1.0)}}
    for attempt in range(4):
        try:
            audio = req("POST", "/v1/tts", body, {"model": MODEL}, raw=True)
            break
        except RuntimeError as e:
            if "402" in str(e):
                if MODEL != "s2.1-pro-free":
                    print(f"::warning title=Fish Audio::Нет баланса API для {MODEL} — перехожу на бесплатную модель s2.1-pro-free")
                    MODEL = "s2.1-pro-free"
                    continue
                raise RuntimeError("Fish Audio: нет баланса API и бесплатная модель недоступна (402)")
            if attempt == 3:
                raise
            time.sleep(5)
    open(path, "wb").write(audio)


def main(ep_name):
    if ENGINE == "own":  # свои файлы: albert/build/<эпизод>/voice_own/01.mp3, 02.mp3 …
        ep = json.load(open(os.path.join(ROOT, "episodes", ep_name + ".json"), encoding="utf-8"))
        out = os.path.join(ROOT, "build", ep_name, "voice_own")
        miss = [f"{i:02d}.mp3" for i in range(1, len(ep["lines"]) + 1) if not os.path.exists(os.path.join(out, f"{i:02d}.mp3"))]
        if miss:
            raise RuntimeError(f"Не хватает файлов озвучки в albert/build/{ep_name}/voice_own: {', '.join(miss)}")
        print(f"::notice title=Озвучка::Использую ваши файлы ({len(ep['lines'])} реплик)")
        return
    if ENGINE == "fish" and not KEY:
        print("::warning title=Озвучка::Нет секрета FISH_API_KEY — видео будет без голоса")
        return
    ep = json.load(open(os.path.join(ROOT, "episodes", ep_name + ".json"), encoding="utf-8"))
    voices = (pick_voices() if ENGINE == "fish" else eleven_voices() if ENGINE == "eleven"
              else SILERO if ENGINE == "silero" else XTTS if ENGINE == "xtts" else {k: v[0] + v[1] for k, v in EDGE.items()})
    out = os.path.join(ROOT, "build", ep_name, "voice" + SUFFIX)
    os.makedirs(out, exist_ok=True)
    meta_f = os.path.join(out, "meta.json")
    meta = json.load(open(meta_f)) if os.path.exists(meta_f) else {}
    made = 0
    for i, ln in enumerate(ep["lines"], 1):
        text = ln.get("say") or ln["text"]
        voice = voices[ln["who"]]
        h = hashlib.sha1(f"{ENGINE}|{voice}|{text}".encode()).hexdigest() if ENGINE != "fish" else hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()
        f = os.path.join(out, f"{i:02d}.mp3")
        if os.path.exists(f) and meta.get(f"{i:02d}") == h:
            continue
        if ENGINE == "eleven":
            lines = ep["lines"]
            prev = (lines[i - 2].get("say") or lines[i - 2]["text"]) if i > 1 else None
            nxt = (lines[i].get("say") or lines[i]["text"]) if i < len(lines) else None
            synth_eleven(text, ln["who"], f, voices, prev, nxt)
        elif ENGINE == "silero":
            synth_silero(text, ln["who"], f)
        elif ENGINE == "xtts":
            synth_xtts(text, ln["who"], f)
        elif ENGINE == "edge":
            synth_edge(text, ln["who"], f)
        else:
            synth_fish(text, ln["who"], f, voices)
        meta[f"{i:02d}"] = h
        json.dump(meta, open(meta_f, "w"), indent=1)  # сохраняем сразу: при сбое готовые реплики не переозвучиваются
        made += 1
        print(f"{i:02d} [{ln['who']}] {text}")
    json.dump(meta, open(meta_f, "w"), indent=1)
    print(f"::notice title=Озвучка ({ENGINE})::Озвучено реплик: {made} (остальные взяты из кэша)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_voices()
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "ep01")
