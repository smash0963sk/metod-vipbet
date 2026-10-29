// Персонажи в плоском 2D-стиле с обводкой. Система координат персонажа: 420×1000, ступни внизу (y≈980).
const INK = "#1E1E24";
const SW = 6;

function limb(x, y, a1, a2, upperLen, foreLen, sleeve, skin, sleeveW = 46, armW = 34, handR = 22, handFill) {
  // рука: плечо (x,y), a1 — угол плеча от вертикали вниз (градусы, + к центру тела зеркалится снаружи),
  // a2 — сгиб локтя относительно плеча
  return `<g transform="translate(${x},${y}) rotate(${a1})">
    <line x1="0" y1="0" x2="0" y2="${upperLen}" stroke="${INK}" stroke-width="${sleeveW + SW * 2}" stroke-linecap="round"/>
    <g transform="translate(0,${upperLen}) rotate(${a2})">
      <line x1="0" y1="0" x2="0" y2="${foreLen}" stroke="${INK}" stroke-width="${armW + SW * 2}" stroke-linecap="round"/>
      <line x1="0" y1="0" x2="0" y2="${foreLen}" stroke="${skin}" stroke-width="${armW}" stroke-linecap="round"/>
      <circle cx="0" cy="${foreLen + 6}" r="${handR}" fill="${handFill || skin}" stroke="${INK}" stroke-width="${SW}"/>
    </g>
    <line x1="0" y1="0" x2="0" y2="${upperLen}" stroke="${sleeve}" stroke-width="${sleeveW}" stroke-linecap="round"/>
  </g>`;
}

// позы: [левая рука a1,a2], [правая рука a1,a2] — «левая/правая» с точки зрения зрителя
const POSES = {
  idle: [[14, -6], [-14, 6]],
  explain: [[14, -6], [-62, -78]],   // правая ладонь вперёд-вверх, объясняет
  explain2: [[62, 78], [-14, 6]],    // то же левой рукой
  chin: [[14, -6], [-22, 158]],      // рука у подбородка — думает
  shrug: [[58, 70], [-58, -70]],     // разводит руками
  point: [[14, -6], [-150, -10]],    // показывает вверх
  stop: [[48, 100], [-48, -100]],    // «нет-нет», ладони вперёд
  head: [[14, -6], [-150, -60]],     // чешет затылок
};

const FRONT = new Set(["chin"]);  // в этих позах правая рука рисуется поверх торса

function albert(o = {}) {
  const skin = "#F2C29B", hair = "#33261F", vest = "#F7931A", vestD = "#D67608", tee = "#24262D", jeans = "#2F3E5C";
  const [L, R] = POSES[o.pose || "idle"];
  const mouth = o.talk > 0.05
    ? `<ellipse cx="212" cy="322" rx="${12 + o.talk * 4}" ry="${4 + o.talk * 9}" fill="#6B2626" stroke="${INK}" stroke-width="5"/>`
    : `<path d="M188 318 Q214 334 238 314" fill="none" stroke="${INK}" stroke-width="6" stroke-linecap="round"/>`;
  return `
  <ellipse cx="210" cy="985" rx="160" ry="22" fill="rgba(0,0,0,.10)"/>
  <!-- ноги -->
  <rect x="148" y="600" width="58" height="340" rx="22" fill="${jeans}" stroke="${INK}" stroke-width="${SW}"/>
  <rect x="214" y="600" width="58" height="340" rx="22" fill="${jeans}" stroke="${INK}" stroke-width="${SW}"/>
  <!-- кроссовки -->
  <path d="M118 968 Q118 930 150 928 L204 928 Q214 952 210 968 Z" fill="#FFFFFF" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M302 968 Q302 930 270 928 L216 928 Q206 952 210 968 Z" fill="#FFFFFF" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M124 958 L206 958" stroke="${vest}" stroke-width="8"/><path d="M296 958 L214 958" stroke="${vest}" stroke-width="8"/>
  <!-- руки сзади -->
  ${limb(138, 430, L[0], L[1], 82, 150, tee, skin)}
  ${FRONT.has(o.pose) ? "" : limb(282, 430, R[0], R[1], 82, 150, tee, skin)}
  <!-- торс: чёрная футболка и оранжевый жилет -->
  <path d="M128 430 Q130 398 170 392 L250 392 Q290 398 292 430 L296 612 Q210 630 124 612 Z" fill="${tee}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M128 430 Q130 398 168 392 L196 396 L198 616 Q160 618 124 612 Z" fill="${vest}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M292 430 Q290 398 252 392 L224 396 L222 616 Q260 618 296 612 Z" fill="${vest}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  ${[460, 510, 560].map(y => `<path d="M130 ${y} L196 ${y + 2} M224 ${y + 2} L290 ${y}" stroke="${vestD}" stroke-width="5" stroke-linecap="round"/>`).join("")}
  <!-- цепь с монетой -->
  <path d="M186 398 Q192 452 210 470 Q228 452 234 398" fill="none" stroke="#E9B949" stroke-width="6"/>
  <circle cx="210" cy="482" r="17" fill="#E9B949" stroke="${INK}" stroke-width="4"/>
  <text x="210" y="492" text-anchor="middle" font-family="IDB" font-size="24" fill="${INK}">₿</text>
  ${FRONT.has(o.pose) ? limb(282, 430, R[0], R[1], 82, 150, tee, skin) : ""}
  <!-- шея и голова -->
  <rect x="188" y="320" width="44" height="80" rx="14" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <circle cx="117" cy="262" r="18" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <circle cx="303" cy="262" r="18" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <ellipse cx="210" cy="252" rx="94" ry="100" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <!-- борода -->
  <path d="M120 270 Q128 352 210 360 Q292 352 300 270 Q292 318 254 330 Q232 300 210 302 Q188 300 166 330 Q128 318 120 270 Z" fill="${hair}" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>
  <!-- волосы с коком -->
  <path d="M114 248 Q104 176 152 148 Q176 104 236 112 Q300 116 312 176 Q318 214 306 250 Q300 206 268 196 Q246 178 214 186 Q176 182 152 202 Q122 214 114 248 Z" fill="${hair}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M170 140 Q206 108 250 124" fill="none" stroke="#5A463B" stroke-width="6" stroke-linecap="round"/>
  <!-- очки -->
  <line x1="196" y1="252" x2="224" y2="252" stroke="#E9B949" stroke-width="7"/>
  <circle cx="168" cy="254" r="32" fill="${INK}" stroke="#E9B949" stroke-width="6"/>
  <circle cx="252" cy="254" r="32" fill="${INK}" stroke="#E9B949" stroke-width="6"/>
  <path d="M152 240 Q160 232 170 232" stroke="#FFFFFF" stroke-width="5" fill="none" stroke-linecap="round" opacity=".8"/>
  <path d="M236 240 Q244 232 254 232" stroke="#FFFFFF" stroke-width="5" fill="none" stroke-linecap="round" opacity=".8"/>
  ${mouth}`;
}

function stas(o = {}) {
  const skin = "#F6D5BC", hair = "#D9732B", tee = "#7CCFB8", pants = "#C9B497";
  const [L, R] = POSES[o.pose || "idle"];
  const blink = o.blink ? `<path d="M168 252 L190 252 M230 252 L252 252" stroke="${INK}" stroke-width="6" stroke-linecap="round"/>`
    : `<circle cx="179" cy="252" r="10" fill="${INK}"/><circle cx="241" cy="252" r="10" fill="${INK}"/>`;
  const mouth = o.talk > 0.05
    ? `<ellipse cx="210" cy="312" rx="${10 + o.talk * 3}" ry="${3 + o.talk * 9}" fill="#6B2626" stroke="${INK}" stroke-width="5"/>`
    : `<path d="M196 312 Q210 318 224 312" fill="none" stroke="${INK}" stroke-width="6" stroke-linecap="round"/>`;
  const brows = o.pose === "chin" || o.pose === "head"
    ? `<path d="M160 222 L194 230 M226 230 L260 222" stroke="${INK}" stroke-width="7" stroke-linecap="round"/>`
    : `<path d="M162 226 Q178 216 194 224 M226 224 Q242 216 258 226" stroke="${INK}" stroke-width="7" fill="none" stroke-linecap="round"/>`;
  return `
  <ellipse cx="210" cy="985" rx="150" ry="22" fill="rgba(0,0,0,.10)"/>
  <rect x="152" y="600" width="54" height="340" rx="22" fill="${pants}" stroke="${INK}" stroke-width="${SW}"/>
  <rect x="214" y="600" width="54" height="340" rx="22" fill="${pants}" stroke="${INK}" stroke-width="${SW}"/>
  <path d="M122 968 Q122 932 152 930 L204 930 Q212 952 208 968 Z" fill="#545A66" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M298 968 Q298 932 268 930 L216 930 Q208 952 212 968 Z" fill="#545A66" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  ${limb(140, 430, L[0], L[1], 80, 150, tee, skin, 44, 32, 21)}
  ${FRONT.has(o.pose) ? "" : limb(280, 430, R[0], R[1], 80, 150, tee, skin, 44, 32, 21)}
  <path d="M132 432 Q134 400 172 394 L248 394 Q286 400 288 432 L292 614 Q210 630 128 614 Z" fill="${tee}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <path d="M184 396 Q210 420 236 396" fill="none" stroke="${INK}" stroke-width="5"/>
  ${FRONT.has(o.pose) ? limb(280, 430, R[0], R[1], 80, 150, tee, skin, 44, 32, 21) : ""}
  <rect x="190" y="322" width="40" height="78" rx="14" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <circle cx="122" cy="262" r="17" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <circle cx="298" cy="262" r="17" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <ellipse cx="210" cy="252" rx="90" ry="96" fill="${skin}" stroke="${INK}" stroke-width="${SW}"/>
  <path d="M122 232 Q118 170 160 150 Q172 120 206 132 Q226 110 252 132 Q292 138 300 186 Q306 212 298 236 Q286 196 256 190 Q238 176 214 186 Q190 174 170 190 Q138 198 122 232 Z" fill="${hair}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
  <circle cx="150" cy="290" r="14" fill="#F2A98F" opacity=".55"/><circle cx="270" cy="290" r="14" fill="#F2A98F" opacity=".55"/>
  ${brows}${blink}${mouth}`;
}

if (typeof module !== "undefined") module.exports = { albert, stas };
