// Готовит данные для Remotion: таймлайн (с разметкой Whisper, если есть) и общую дорожку озвучки.
// node albert/tools/make_props.js ep01  →  albert/build/ep01/props.json + albert/remotion/public/ep01.mp3
const fs = require("fs"), path = require("path");
const { execFileSync } = require("child_process");
const { timeline } = require("../engine/scene.js");

const name = process.argv[2] || "ep01";
const ROOT = path.join(__dirname, "..");
const ep = JSON.parse(fs.readFileSync(path.join(ROOT, "episodes", name + ".json"), "utf8"));
const bdir = path.join(ROOT, "build", name);
fs.mkdirSync(bdir, { recursive: true });
const vdir = path.join(bdir, "voice");
const files = ep.lines.map((_, i) => path.join(vdir, String(i + 1).padStart(2, "0") + ".mp3"));
const haveVoice = files.every(f => fs.existsSync(f));

let align = null;
const af = path.join(bdir, "align.json");
if (haveVoice && fs.existsSync(af)) align = JSON.parse(fs.readFileSync(af, "utf8"));
else if (haveVoice) align = files.map(f => parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString()));

const tl = timeline(ep, align);
const total = tl[tl.length - 1].end + (ep.tail || 1.6);
let audio = null;
if (haveVoice) {
  audio = name + ".mp3";
  const ins = [], filt = [];
  files.forEach((f, i) => { ins.push("-i", f); const ms = Math.round(tl[i].start * 1000); filt.push(`[${i}:a]adelay=${ms}|${ms}[a${i}]`); });
  const mix = filt.join(";") + ";" + files.map((_, i) => `[a${i}]`).join("") + `amix=inputs=${files.length}:normalize=0,apad,atrim=end=${total.toFixed(2)}[out]`;
  execFileSync("ffmpeg", ["-y", "-v", "error", ...ins, "-filter_complex", mix, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
    path.join(ROOT, "remotion", "public", audio)]);
}
fs.writeFileSync(path.join(bdir, "props.json"), JSON.stringify({ ep, tl, total, audio }));
console.log(`props: ${tl.length} реплик, ${total.toFixed(1)} с, озвучка: ${audio ? "есть" : "нет"}, Whisper: ${align && typeof align[0] === "object" ? "да" : "нет"}`);
