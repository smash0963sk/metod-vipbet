"""Разметка слов в озвучке через Whisper (faster-whisper): когда звучит каждое слово реплики.

python3 albert/tools/align.py ep01  →  albert/build/ep01/align.json
[{ "dur": длительность файла, "speechStart": .., "speechEnd": .., "words": [{"s":..,"e":..}, …] или null }, …]
Слова сценария сопоставляются со словами Whisper (difflib); несовпавшие — интерполируются по соседям.
"""
import difflib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm(w):
    return re.sub(r"[^a-zа-я0-9]", "", w.lower().replace("ё", "е"))


def duration(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).decode().strip())


def map_words(script, heard):
    a = [norm(w) for w in script]
    b = [norm(h["w"]) for h in heard]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times = [None] * len(script)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = (heard[blk.b + k]["s"], heard[blk.b + k]["e"])
    # частичные совпадения (например, «тачку» ~ «тачку,»): по похожести
    for i, w in enumerate(a):
        if times[i] is None and heard:
            best = max(range(len(b)), key=lambda j: difflib.SequenceMatcher(None, w, b[j]).ratio())
            if difflib.SequenceMatcher(None, w, b[best]).ratio() > 0.6:
                times[i] = (heard[best]["s"], heard[best]["e"])
    matched = sum(t is not None for t in times)
    if matched < max(1, len(script) * 0.5):
        return None
    # интерполяция пропусков
    first = heard[0]["s"] if heard else 0
    last = heard[-1]["e"] if heard else 0
    for i in range(len(times)):
        if times[i] is None:
            prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), first)
            nxt_i = next((j for j in range(i + 1, len(times)) if times[j]), None)
            nxt = times[nxt_i][0] if nxt_i is not None else last
            gap_n = (nxt_i if nxt_i is not None else len(times)) - i
            step = max(0.08, (nxt - prev) / (gap_n + 1))
            times[i] = (prev, prev + step)
    # монотонность
    out, t0 = [], 0
    for s, e in times:
        s = max(s, t0)
        e = max(e, s + 0.08)
        out.append({"s": round(s, 3), "e": round(e, 3)})
        t0 = s
    return out


def main(ep_name):
    vdir = os.path.join(ROOT, "build", ep_name, "voice")
    ep = json.load(open(os.path.join(ROOT, "episodes", ep_name + ".json"), encoding="utf-8"))
    files = [os.path.join(vdir, f"{i:02d}.mp3") for i in range(1, len(ep["lines"]) + 1)]
    if not all(os.path.exists(f) for f in files):
        print("::warning title=Whisper::Озвучка есть не для всех реплик — разметку слов пропускаю")
        return
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    res = []
    for ln, f in zip(ep["lines"], files):
        segs, _ = model.transcribe(f, language="ru", word_timestamps=True, beam_size=5, vad_filter=False)
        heard = [{"w": w.word.strip(), "s": w.start, "e": w.end} for s in segs for w in (s.words or [])]
        script = ln["text"].split()
        words = map_words(script, heard)
        res.append({"dur": round(duration(f), 3),
                    "speechStart": round(heard[0]["s"], 3) if heard else 0,
                    "speechEnd": round(heard[-1]["e"], 3) if heard else None,
                    "words": words})
        print(f"{ln['text']}\n   Whisper: {' '.join(h['w'] for h in heard)}\n   слов размечено: {'все' if words else 'нет (равномерно)'}")
    json.dump(res, open(os.path.join(ROOT, "build", ep_name, "align.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for r in res if r["words"])
    print(f"::notice title=Whisper::Слова размечены в {ok} из {len(res)} реплик")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ep01")
