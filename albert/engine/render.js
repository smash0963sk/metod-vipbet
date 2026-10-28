// Рендер эпизода: node render.js ep01.json out.mp4 [папка_с_озвучкой]
// Озвучка: файлы 01.mp3, 02.mp3 … — по одному на реплику; длительность реплики берётся из файла.
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), path = require("path");
const { buildFrame, timeline } = require("./scene.js");

const [epFile, out, voiceDir, onlyFrames] = process.argv.slice(2);
const ep = JSON.parse(fs.readFileSync(epFile, "utf8"));
const FPS = ep.fps || 30;

let durs = null, voiceFiles = null;
if (voiceDir && fs.existsSync(voiceDir)) {
  voiceFiles = ep.lines.map((_, i) => path.join(voiceDir, String(i + 1).padStart(2, "0") + ".mp3"));
  durs = voiceFiles.map(f => fs.existsSync(f)
    ? parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString()) : null);
}
const tl = timeline(ep, durs);
const total = tl[tl.length - 1].end + (ep.tail || 1.6);
fs.writeFileSync(out.replace(/\.mp4$/, ".timeline.json"), JSON.stringify(tl.map(l => ({ who: l.who, text: l.text, start: +l.start.toFixed(2), end: +l.end.toFixed(2) })), null, 1));

(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const f64 = n => fs.readFileSync(path.join(__dirname, n)).toString("base64");
  await pg.setContent(`<html><head><style>
    @font-face{font-family:IDB;src:url(data:font/otf;base64,${f64("InterDisplay-Black.otf")})}
    @font-face{font-family:IDE;src:url(data:font/otf;base64,${f64("InterDisplay-ExtraBold.otf")})}
    body{margin:0;overflow:hidden}</style></head><body><div id="s"></div>
    <span style="font-family:IDB">а</span><span style="font-family:IDE">а</span></body></html>`);
  await pg.evaluate(() => document.fonts.ready);
  if (onlyFrames) {  // предпросмотр отдельных кадров: "t1,t2,…"
    for (const t of onlyFrames.split(",").map(Number)) {
      await pg.evaluate(svg => { document.getElementById("s").innerHTML = svg; }, buildFrame(ep, tl, t));
      await pg.screenshot({ path: out.replace(/\.mp4$/, `_${t}.jpg`), type: "jpeg", quality: 85 });
    }
    await b.close();
    return;
  }
  const silent = out.replace(/\.mp4$/, ".silent.mp4");
  const ff = spawn("ffmpeg", ["-y", "-v", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", silent], { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.ceil(total * FPS);
  for (let i = 0; i < n; i++) {
    await pg.evaluate(svg => { document.getElementById("s").innerHTML = svg; }, buildFrame(ep, tl, i / FPS));
    const buf = await pg.screenshot({ type: "jpeg", quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (i % 150 === 0) process.stderr.write(`кадр ${i}/${n}\n`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on("close", r));
  await b.close();
  if (voiceFiles && voiceFiles.some(f => fs.existsSync(f))) {
    // собираем озвучку: каждая реплика ставится на своё время
    const ins = [], filt = [];
    let k = 0;
    voiceFiles.forEach((f, i) => {
      if (!fs.existsSync(f)) return;
      ins.push("-i", f);
      filt.push(`[${k + 1}:a]adelay=${Math.round(tl[i].start * 1000)}|${Math.round(tl[i].start * 1000)}[a${k}]`);
      k++;
    });
    const mix = filt.join(";") + ";" + Array.from({ length: k }, (_, i) => `[a${i}]`).join("") + `amix=inputs=${k}:normalize=0[aout]`;
    execFileSync("ffmpeg", ["-y", "-v", "error", "-i", silent, ...ins, "-filter_complex", mix, "-map", "0:v", "-map", "[aout]",
      "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out]);
    fs.unlinkSync(silent);
  } else {
    fs.renameSync(silent, out);
  }
  console.log(`Готово: ${out} (${total.toFixed(1)} с)`);
})();
