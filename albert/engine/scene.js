// Сцена: персонажи + слово-субтитр над говорящим + инфографика сверху. buildFrame(ep, timeline, t) → SVG 1080×1920
const { albert, stas } = require("./chars.js");
const INK = "#1E1E24", ORANGE = "#F7931A", GOLD = "#C98A10", GREEN = "#2DB36B", RED = "#E2463B", BLUE = "#2AABEE";

const ease = x => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
const back = x => { x = Math.min(1, Math.max(0, x)); const c = 1.7; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

// ---------- иконки (центр cx,cy; размер s) ----------
const ICONS = {
  btc: s => `<circle r="${s / 2}" fill="${ORANGE}" stroke="${INK}" stroke-width="7"/><circle r="${s / 2 - 16}" fill="none" stroke="#FFC46B" stroke-width="5"/>
             <text y="${s * 0.2}" text-anchor="middle" font-family="IDB" font-size="${s * 0.62}" fill="#FFFFFF" stroke="${INK}" stroke-width="4" paint-order="stroke">₿</text>`,
  cash: s => [2, 1, 0].map(i => `<g transform="translate(${i * 14 - 14},${-i * 16 + 16}) rotate(${-6 + i * 4})"><rect x="${-s * 0.55}" y="${-s * 0.3}" width="${s * 1.1}" height="${s * 0.6}" rx="12" fill="#5CC98A" stroke="${INK}" stroke-width="6"/>
             <circle r="${s * 0.17}" fill="#3FA66E" stroke="${INK}" stroke-width="4"/><text y="${s * 0.09}" text-anchor="middle" font-family="IDB" font-size="${s * 0.26}" fill="#FFFFFF">$</text></g>`).join(""),
  lock: s => `<path d="M${-s * 0.25} ${-s * 0.05} V${-s * 0.25} A${s * 0.25} ${s * 0.25} 0 0 1 ${s * 0.25} ${-s * 0.25} V${-s * 0.05}" fill="none" stroke="${INK}" stroke-width="${s * 0.11}"/>
             <path d="M${-s * 0.25} ${-s * 0.05} V${-s * 0.25} A${s * 0.25} ${s * 0.25} 0 0 1 ${s * 0.25} ${-s * 0.25} V${-s * 0.05}" fill="none" stroke="#B9BEC8" stroke-width="${s * 0.06}"/>
             <rect x="${-s * 0.38}" y="${-s * 0.08}" width="${s * 0.76}" height="${s * 0.56}" rx="18" fill="#E9B949" stroke="${INK}" stroke-width="7"/>
             <circle cy="${s * 0.15}" r="${s * 0.07}" fill="${INK}"/><rect x="-6" y="${s * 0.16}" width="12" height="${s * 0.16}" rx="6" fill="${INK}"/>`,
  doc: s => `<path d="M${-s * 0.36} ${-s * 0.5} H${s * 0.18} L${s * 0.36} ${-s * 0.32} V${s * 0.5} H${-s * 0.36} Z" fill="#FFFFFF" stroke="${INK}" stroke-width="7" stroke-linejoin="round"/>
             ${[-0.26, -0.12, 0.02].map(y => `<line x1="${-s * 0.24}" y1="${s * y}" x2="${s * 0.24}" y2="${s * y}" stroke="#C9CCD3" stroke-width="10" stroke-linecap="round"/>`).join("")}
             <g transform="translate(0,${s * 0.28}) rotate(-12)"><rect x="${-s * 0.3}" y="${-s * 0.1}" width="${s * 0.6}" height="${s * 0.2}" rx="8" fill="none" stroke="${RED}" stroke-width="6"/>
             <text y="${s * 0.06}" text-anchor="middle" font-family="IDB" font-size="${s * 0.14}" fill="${RED}">НАЛОГ</text></g>`,
  car: s => `<g transform="scale(${s / 300})"><path d="M-170 30 Q-168 -6 -120 -14 L-60 -24 Q-20 -62 40 -62 Q96 -60 130 -22 L160 -16 Q186 -10 186 24 L186 40 L-170 40 Z" fill="${INK}" stroke="${INK}" stroke-width="8" stroke-linejoin="round"/>
             <path d="M-40 -24 Q-8 -52 38 -52 Q80 -50 104 -24 Z" fill="#9FD4F5" stroke="${INK}" stroke-width="6"/><line x1="34" y1="-52" x2="30" y2="-24" stroke="${INK}" stroke-width="6"/>
             <path d="M-150 6 L176 6" stroke="${ORANGE}" stroke-width="8"/>
             <circle cx="-100" cy="40" r="34" fill="#2B2B30" stroke="${INK}" stroke-width="8"/><circle cx="-100" cy="40" r="14" fill="#B9BEC8"/>
             <circle cx="120" cy="40" r="34" fill="#2B2B30" stroke="${INK}" stroke-width="8"/><circle cx="120" cy="40" r="14" fill="#B9BEC8"/>
             <ellipse cx="8" cy="80" rx="190" ry="10" fill="rgba(0,0,0,.10)"/></g>`,
  arrow: s => `<path d="M${-s * 0.4} 0 H${s * 0.25}" stroke="${INK}" stroke-width="14" stroke-linecap="round" stroke-dasharray="2 26"/>
             <path d="M${s * 0.12} ${-s * 0.18} L${s * 0.38} 0 L${s * 0.12} ${s * 0.18}" fill="none" stroke="${INK}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>`,
  chartUp: s => `<rect x="${-s * 0.5}" y="${-s * 0.38}" width="${s}" height="${s * 0.76}" rx="22" fill="#FFFFFF" stroke="${INK}" stroke-width="7"/>
             <path d="M${-s * 0.36} ${s * 0.2} L${-s * 0.14} ${s * 0.02} L${s * 0.02} ${s * 0.1} L${s * 0.32} ${-s * 0.22}" fill="none" stroke="${GREEN}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
             <path d="M${s * 0.16} ${-s * 0.24} L${s * 0.34} ${-s * 0.24} L${s * 0.34} ${-s * 0.06}" fill="none" stroke="${GREEN}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>`,
  chartDown: s => `<rect x="${-s * 0.5}" y="${-s * 0.38}" width="${s}" height="${s * 0.76}" rx="22" fill="#FFFFFF" stroke="${INK}" stroke-width="7"/>
             <path d="M${-s * 0.36} ${-s * 0.22} L${-s * 0.12} ${-s * 0.04} L${s * 0.04} ${-s * 0.12} L${s * 0.32} ${s * 0.2}" fill="none" stroke="${RED}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
             <path d="M${s * 0.16} ${s * 0.22} L${s * 0.34} ${s * 0.22} L${s * 0.34} ${s * 0.04}" fill="none" stroke="${RED}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>`,
  warn: s => `<path d="M0 ${-s * 0.46} L${s * 0.5} ${s * 0.4} H${-s * 0.5} Z" fill="#FFD43B" stroke="${INK}" stroke-width="8" stroke-linejoin="round"/>
             <rect x="-9" y="${-s * 0.18}" width="18" height="${s * 0.32}" rx="9" fill="${INK}"/><circle cy="${s * 0.26}" r="11" fill="${INK}"/>`,
  tg: s => `<circle r="${s / 2}" fill="${BLUE}" stroke="${INK}" stroke-width="7"/>
             <path d="M${-s * 0.26} ${-s * 0.01} L${s * 0.24} ${-s * 0.2} L${s * 0.14} ${s * 0.24} L${s * 0.02} ${s * 0.1} L${-s * 0.06} ${s * 0.2} L${-s * 0.08} ${s * 0.06} Z" fill="#FFFFFF" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>`,
  usdt: s => `<circle r="${s / 2}" fill="#26A17B" stroke="${INK}" stroke-width="7"/><circle r="${s / 2 - 16}" fill="none" stroke="#7FD8BB" stroke-width="5"/>
             <text y="${s * 0.2}" text-anchor="middle" font-family="IDB" font-size="${s * 0.6}" fill="#FFFFFF" stroke="${INK}" stroke-width="4" paint-order="stroke">₮</text>`,
  bank: s => `<path d="M${-s * 0.5} ${-s * 0.18} L0 ${-s * 0.46} L${s * 0.5} ${-s * 0.18} Z" fill="#E9B949" stroke="${INK}" stroke-width="7" stroke-linejoin="round"/>
             ${[-0.34, -0.12, 0.1, 0.32].map(x => `<rect x="${s * x - 12}" y="${-s * 0.14}" width="24" height="${s * 0.46}" fill="#FFFFFF" stroke="${INK}" stroke-width="6"/>`).join("")}
             <rect x="${-s * 0.52}" y="${s * 0.32}" width="${s * 1.04}" height="${s * 0.12}" fill="#E9B949" stroke="${INK}" stroke-width="7"/>`,
};

function icon(name, cx, cy, s, k) {
  const f = ICONS[name];
  if (!f) return "";
  return `<g transform="translate(${cx},${cy}) scale(${k})">${f(s)}</g>`;
}

// ---------- тайминг ----------
function timeline(ep, align) {
  // align[i]: число (длительность файла озвучки) или {dur, words:[{s,e}]} — разметка слов от Whisper (секунды от начала файла)
  const rate = ep.charsPerSec || 14;
  let t = ep.lead || 0.3;
  return ep.lines.map((ln, i) => {
    const text = ln.text;
    const al = align && align[i] != null ? (typeof align[i] === "number" ? { dur: align[i] } : align[i]) : null;
    const d = al && al.dur ? al.dur : Math.max(0.9, text.length / rate + 0.15);
    const words = text.split(/\s+/).filter(Boolean);
    let ws;
    if (al && al.words && al.words.length === words.length) {
      ws = words.map((w, j) => ({ w, s: t + al.words[j].s, e: t + Math.max(al.words[j].e, al.words[j].s + 0.08) }));
    } else {
      const weights = words.map(w => w.replace(/[^\wа-яё0-9%₿$]/gi, "").length + 2);
      const sum = weights.reduce((a, b) => a + b, 0);
      const s0 = al && al.speechStart != null ? al.speechStart : 0, s1 = al && al.speechEnd != null ? al.speechEnd : d;
      let acc = t + s0;
      ws = words.map((w, j) => { const s = acc; acc += (s1 - s0) * weights[j] / sum; return { w, s, e: acc }; });
    }
    const out = { ...ln, start: t, end: t + d, words: ws };
    t += d + (ln.pause != null ? ln.pause : ep.gap || 0.25);
    return out;
  });
}

function charSvg(who, o) {
  return who === "A" ? albert(o) : stas(o);
}

function buildFrame(ep, tl, t) {
  const W = 1080, H = 1920;
  // текущая реплика: последняя начавшаяся
  let idx = 0;
  for (let i = 0; i < tl.length; i++) if (t >= tl[i].start - 0.001) idx = i;
  const ln = tl[idx];
  const speaking = t >= ln.start && t <= ln.end;
  const word = ln.words.find(w => t >= w.s && t < w.e) || (t > ln.end ? null : ln.words[0]);
  const talkFor = who => {
    if (!speaking || ln.who !== who || !word) return 0;
    const ph = (t - word.s) / Math.max(0.05, word.e - word.s);
    return ph > 0.82 ? 0 : 0.45 + 0.55 * Math.abs(Math.sin(t * 22));
  };
  const blink = (t % 3.3) < 0.12;
  const shot = ln.shot || "duo";
  const parts = [];
  // фон
  parts.push(`<defs><radialGradient id="bg" cx="50%" cy="42%" r="75%"><stop offset="0" stop-color="${ep.bg2 || "#FFF7E8"}"/><stop offset="1" stop-color="${ep.bg || "#FBE2BC"}"/></radialGradient></defs>
    <rect width="${W}" height="${H}" fill="url(#bg)"/>`);

  // инфографика (держится, пока в следующих репликах нет новой)
  let infoIdx = -1;
  for (let i = idx; i >= 0; i--) { if (tl[i].info) { infoIdx = i; break; } if (tl[i].clear) break; }
  if (infoIdx >= 0 && shot !== "close") {
    const inf = tl[infoIdx].info;
    const k = back((t - tl[infoIdx].start) / 0.35);
    const top = 330;
    if (inf.flow) {
      const n = inf.flow.length, gapX = Math.min(300, 880 / Math.max(1, n - 1) * 0.92), sz = n >= 4 ? 175 : 210;
      inf.flow.forEach((nm, j) => {
        const kk = back((t - tl[infoIdx].start - j * 0.18) / 0.35);
        parts.push(icon(nm, W / 2 + (j - (n - 1) / 2) * gapX, top, nm === "arrow" ? sz * 0.8 : sz, kk));
      });
    } else if (inf.icon) {
      parts.push(icon(inf.icon, W / 2, top - (inf.big ? 20 : 0), inf.size || 230, k));
    }
    const ty = inf.icon || inf.flow ? top + 200 : top + 90;
    if (inf.big) parts.push(`<text x="${W / 2}" y="${ty}" text-anchor="middle" font-family="IDB" font-size="${inf.bigSize || 120}" fill="${inf.color || GOLD}" opacity="${ease((t - tl[infoIdx].start - 0.1) / 0.25)}">${esc(inf.big)}</text>`);
    if (inf.label) parts.push(`<text x="${W / 2}" y="${ty + (inf.big ? 64 : 0)}" text-anchor="middle" font-family="IDE" font-size="46" fill="${INK}" opacity="${ease((t - tl[infoIdx].start - 0.2) / 0.25)}">${esc(inf.label)}</text>`);
  }

  // персонажи
  const place = (who, x, feetY, sc, extra = "") => {
    const bob = who === ln.who && speaking ? Math.sin(t * 7) * 4 : Math.sin(t * 2 + (who === "A" ? 1 : 0)) * 2;
    const pose = who === ln.who ? (ln.pose || "idle") : (ln.listen || "idle");
    const o = { pose, talk: talkFor(who), blink: who === "S" && blink };
    return `<g transform="translate(${x - 210 * sc},${feetY - 985 * sc + bob}) scale(${sc})" ${extra}>${charSvg(who, o)}</g>`;
  };
  let capX = W / 2, capY = 860;
  if (shot === "solo") {
    parts.push(place(ln.who, W / 2, 1790, 1.12));
    capY = 1790 - 985 * 1.12 + 100 * 1.12 - 45;
  } else if (shot === "close") {
    const sc = 2.4;
    parts.push(place(ln.who, 760, 1100 + 735 * sc, sc));
    capX = 300; capY = 760;
  } else {
    const xs = { S: 285, A: 795 };
    parts.push(place("S", xs.S, 1780, 0.98));
    parts.push(place("A", xs.A, 1780, 0.98));
    capX = xs[ln.who]; capY = 1780 - 985 * 0.98 + 100 * 0.98 - 45;
  }

  // слово над говорящим
  if (word && speaking) {
    const kk = 0.86 + 0.14 * ease((t - word.s) / 0.08);
    let size = shot === "close" ? 110 : 92;
    let wpx = word.w.length * size * 0.6;
    if (wpx > W - 80) { size = Math.floor(size * (W - 80) / wpx); wpx = W - 80; }
    capX = Math.min(Math.max(capX, wpx / 2 + 40), W - wpx / 2 - 40);  // слово не выходит за край кадра
    parts.push(`<g transform="translate(${capX},${capY}) scale(${kk})"><text x="0" y="0" text-anchor="middle" font-family="IDB" font-size="${size}" fill="${INK}" stroke="${ep.bg2 || "#FFF7E8"}" stroke-width="14" paint-order="stroke" stroke-linejoin="round">${esc(word.w)}</text></g>`);
  }
  // подпись автора и дисклеймер
  if (ep.handle && shot !== "close") parts.push(`<text x="${W / 2}" y="1835" text-anchor="middle" font-family="IDE" font-size="30" fill="#7A6A55">${esc(ep.handle)}</text>`);
  const last = tl[tl.length - 1];
  if (ep.disclaimer && t > last.start) parts.push(`<text x="${W / 2}" y="1880" text-anchor="middle" font-family="IDE" font-size="28" fill="#9A8A74">${esc(ep.disclaimer)}</text>`);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${parts.join("")}</svg>`;
}

module.exports = { buildFrame, timeline };
