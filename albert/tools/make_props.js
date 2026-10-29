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
  // Звук: каждая реплика — чистка низов, компрессия, выравнивание громкости; звуки появления иконок;
  // фоновая музыка (если есть файл в albert/music), которая приглушается, пока персонажи говорят.
  audio = name + ".mp3";
  const SFX = path.join(ROOT, "engine", "sfx");
  const ins = [], filt = [];
  let n = 0;
  const vox = [];
  files.forEach((f, i) => {
    ins.push("-i", f);
    const ms = Math.round(tl[i].start * 1000);
    filt.push(`[${n}:a]aresample=44100,highpass=f=90,acompressor=threshold=0.125:ratio=3:attack=5:release=80:makeup=2,` +
      `loudnorm=I=-16:TP=-2:LRA=7,aresample=44100,aformat=channel_layouts=stereo,adelay=${ms}|${ms}[v${i}]`);
    vox.push(`[v${i}]`);
    n++;
  });
  filt.push(`${vox.join("")}amix=inputs=${vox.length}:normalize=0[vox]`);
  // звуковые эффекты
  const ev = [];
  let prevShot = null;
  tl.forEach((l, i) => {
    if (l.info) {
      if (l.info.flow) { ev.push(["whoosh", l.start]); l.info.flow.forEach((_, j) => ev.push(["pop", l.start + 0.05 + j * 0.18])); }
      else ev.push([l.info.icon === "tg" ? "ding" : "pop", l.start + 0.02]);
    }
    if (l.shot === "close" && prevShot !== "close") ev.push(["whoosh", Math.max(0, l.start - 0.12)]);
    prevShot = l.shot;
  });
  const sfx = [];
  ev.forEach(([nm, t], k) => {
    ins.push("-i", path.join(SFX, nm + ".wav"));
    const ms = Math.round(t * 1000);
    filt.push(`[${n}:a]aformat=channel_layouts=stereo,volume=${nm === "whoosh" ? 0.35 : 0.45},adelay=${ms}|${ms}[s${k}]`);
    sfx.push(`[s${k}]`);
    n++;
  });
  const mixIn = ["[voxm]"];
  if (sfx.length) { filt.push(`${sfx.join("")}amix=inputs=${sfx.length}:normalize=0[sfx]`); mixIn.push("[sfx]"); }
  // фоновая музыка
  const mdir = path.join(ROOT, "music");
  const tracks = fs.existsSync(mdir) ? fs.readdirSync(mdir).filter(f => /\.(mp3|wav|m4a|ogg)$/i.test(f)).sort() : [];
  const track = ep.music ? path.join(mdir, ep.music) : (tracks.length ? path.join(mdir, tracks[0]) : null);
  if (track && fs.existsSync(track)) {
    ins.push("-stream_loop", "-1", "-i", track);
    filt.push(`[vox]asplit=2[voxm][voxsc]`);
    filt.push(`[${n}:a]aresample=44100,aformat=channel_layouts=stereo,volume=${ep.musicVolume || 0.16},atrim=end=${total.toFixed(2)},afade=t=out:st=${Math.max(0, total - 1.5).toFixed(2)}:d=1.5[mus]`);
    filt.push(`[mus][voxsc]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[duck]`);
    mixIn.push("[duck]");
    n++;
  } else {
    filt.push(`[vox]anull[voxm]`);
  }
  filt.push(`${mixIn.join("")}amix=inputs=${mixIn.length}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9,aresample=44100,apad,atrim=end=${total.toFixed(2)}[out]`);
  execFileSync("ffmpeg", ["-y", "-v", "error", ...ins, "-filter_complex", filt.join(";"), "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
    path.join(ROOT, "remotion", "public", audio)]);
  console.log(`звук: ${files.length} реплик, эффектов ${ev.length}, музыка: ${track ? path.basename(track) : "нет"}`);
}
fs.writeFileSync(path.join(bdir, "props.json"), JSON.stringify({ ep, tl, total, audio }));
console.log(`props: ${tl.length} реплик, ${total.toFixed(1)} с, озвучка: ${audio ? "есть" : "нет"}, Whisper: ${align && typeof align[0] === "object" ? "да" : "нет"}`);
