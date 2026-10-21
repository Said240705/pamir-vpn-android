// Могну — один SVG на все состояния (как в кабинете): спит (off), старается (busy), в очках и золотой короне (on).
// Настроение меняет data-mood у контейнера, всё остальное — CSS (style.css, раздел «Могну»).
// С 20 декабря по 10 января на корону надевается новогодняя шапка — та же, что в кабинете (mognu-season.js).

const CROWN = "84,44 80,2 104,22 120,-10 136,22 160,2 156,44";
const CONE = "M66 32 C70 -6 104 -40 150 -42 C182 -43 204 -26 214 -2 C206 -12 192 -18 178 -16 C164 -14 158 -2 160 14 L172 32 Z";
const FOLD = "M150 -42 C182 -43 204 -26 214 -2 C206 -12 192 -18 178 -16 C170 -15 164 -10 161 -2 C166 -22 160 -36 150 -42 Z";
const HAT =
  '<g class="m-hat" transform="translate(74 26) rotate(-28) scale(.82) translate(-120 -34) translate(240 0) scale(-1 1)">' +
  `<path d="${CONE}" fill="#fff" stroke="#fff" stroke-width="20" stroke-linejoin="round"/>` +
  `<path d="${CONE}" fill="#E5323F"/><path d="${FOLD}" fill="#B8202D"/>` +
  '<path d="M86 10 C100 -14 122 -28 146 -32" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="7" stroke-linecap="round"/>' +
  '<rect x="54" y="18" width="132" height="32" rx="16" fill="#fff" stroke="#fff" stroke-width="10"/>' +
  '<rect x="54" y="18" width="132" height="32" rx="16" fill="#F4F2FA"/>' +
  '<path d="M70 30 h8 M92 38 h8 M114 28 h8 M136 38 h8 M158 30 h8" stroke="#D9D4EA" stroke-width="5" stroke-linecap="round"/>' +
  '<g class="h-pom"><circle cx="214" cy="0" r="17" fill="#fff" stroke="#fff" stroke-width="10"/>' +
  '<circle cx="214" cy="0" r="17" fill="#F4F2FA"/><circle cx="219" cy="-5" r="5" fill="#fff"/></g></g>';

export function newYear(now = new Date()) {
  try {
    const f = localStorage.getItem("mognu_ny");
    if (f === "1") return true;
    if (f === "0") return false;
  } catch (e) { /* без хранилища — по дате */ }
  const m = now.getMonth(), d = now.getDate();
  return (m === 11 && d >= 20) || (m === 0 && d <= 10);
}

export function mascotSvg(ny = newYear()) {
  return '<svg class="mognu" viewBox="0 -40 240 290" aria-hidden="true">' +
    // золотые искры (подключено) и «скорость» по бокам (подключаем)
    '<path class="m-spark" d="M40 -20 l6 14 l14 6 l-14 6 l-6 14 l-6 -14 l-14 -6 l14 -6z M206 -6 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4z" fill="#FFC93C"/>' +
    '<path class="m-lines" d="M6 110 h-26 M2 140 h-34 M6 170 h-22 M234 110 h26 M238 140 h34 M234 170 h22" stroke="#fff" stroke-width="6" stroke-linecap="round"/>' +
    '<g class="m-figure">' +
    '<rect x="18" y="40" width="204" height="204" rx="58" fill="#080418" fill-opacity=".45"/>' +
    '<rect x="18" y="30" width="204" height="204" rx="58" fill="#fff"/>' +
    '<rect class="m-body" x="28" y="40" width="184" height="184" rx="50"/>' +
    `<g class="m-crown"><polygon points="${CROWN}" fill="#fff" stroke="#fff" stroke-width="14" stroke-linejoin="round"/>` +
    `<polygon class="m-crown-fill" points="${CROWN}"/>${ny ? HAT : ""}</g>` +
    // спит
    '<g class="f-off"><path d="M72 128 q15 13 30 0 M138 128 q15 13 30 0" fill="none" stroke="#14102A" stroke-width="8" stroke-linecap="round"/>' +
    '<path d="M108 172 q12 6 24 0" fill="none" stroke="#14102A" stroke-width="7" stroke-linecap="round"/></g>' +
    // старается
    '<g class="f-busy"><path d="M70 104 L104 116 M170 104 L136 116" stroke="#14102A" stroke-width="8" stroke-linecap="round"/>' +
    '<circle cx="88" cy="134" r="10" fill="#14102A"/><circle cx="152" cy="134" r="10" fill="#14102A"/>' +
    '<path d="M100 176 h40" stroke="#14102A" stroke-width="8" stroke-linecap="round"/>' +
    '<path d="M190 74 q10 16 0 24 q-10 -8 0 -24z" fill="#7FD4FF" stroke="#fff" stroke-width="3"/></g>' +
    // в очках
    '<g class="f-on"><path d="M50 108 L112 108 L120 124 L128 108 L190 108 L186 120 L176 146 Q170 152 160 152 L142 152 Q132 152 130 142 L124 126 L116 126 L110 142 Q108 152 98 152 L80 152 Q70 152 64 146 L54 120 Z" fill="#14102A"/>' +
    '<path class="m-glint" d="M78 116 L96 116 M150 116 L166 116" stroke="#fff" stroke-width="5" stroke-linecap="round"/>' +
    '<path d="M98 180 q26 16 52 -8" fill="none" stroke="#14102A" stroke-width="8" stroke-linecap="round"/></g>' +
    "</g>" +
    '<g class="m-zzz" fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round">' +
    '<path class="z1" d="M186 -10 h18 l-18 20 h18" stroke-width="5"/><path class="z2" d="M214 -36 h11 l-11 13 h11" stroke-width="4"/></g>' +
    "</svg>";
}

// Вставляет Могну во все .mascot-slot страницы
export function mountMascots(ny = newYear()) {
  document.documentElement.classList.toggle("ny", ny);
  for (const el of document.querySelectorAll(".mascot-slot")) if (!el.firstChild) el.innerHTML = mascotSvg(ny);
}
