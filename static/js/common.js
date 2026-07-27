// 우리사이 — 공통 스크립트
const USER = "me";
const DAYS = ["월", "화", "수", "목", "금"];
const HOURS = Array.from({ length: 13 }, (_, i) => i + 9); // 9시~21시

async function api(path, options) {
  // no-store 를 안 주면 브라우저가 GET 응답을 재사용한다.
  // 시간표를 고쳐도 배너·격자가 옛날 값 그대로 남던 원인이다.
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const post = (path, body) =>
  api(path, { method: "POST", body: JSON.stringify(body) });

function logoMark() {
  return `<div class="logo-mark">
    <i class="eye-l"></i><i class="eye-r"></i>
    <div class="smile"></div><i class="dot"></i>
  </div>`;
}

function badgeClass(label) {
  return label === "붐빔" ? "busy" : label === "보통" ? "normal" : "quiet";
}

function topbar(title, back = true) {
  return `<div class="topbar">
    ${back ? `<button class="back" onclick="history.back()">‹</button>` : logoMark()}
    <h1>${title}</h1>
  </div>`;
}

function tabbar(current) {
  const tabs = [
    { id: "home", href: "/home.html", icon: "◎", label: "홈" },
    { id: "chat", href: "/chat.html", icon: "◇", label: "챗봇" },
    { id: "friends", href: "/friends.html", icon: "◈", label: "시간표" },
    { id: "projects", href: "/projects.html", icon: "◐", label: "프로젝트" },
  ];
  return `<nav class="tabbar">${tabs
    .map(
      (t) =>
        `<a href="${t.href}" class="${t.id === current ? "on" : ""}">
           <span>${t.icon}</span>${t.label}</a>`
    )
    .join("")}</nav>`;
}

function chatFab() {
  // 탭바가 없는 화면(랜딩·사장님 대시보드 등)에서도 챗봇으로 바로 넘어가는 경로
  return `<a href="/chat.html" class="chat-fab">
    <span>◇</span>챗봇에게 물어보기
  </a>`;
}

function storeCard(s, opts = {}) {
  return `<div class="card tap" ${opts.onclick ? `onclick="${opts.onclick}"` : ""}>
    <div class="card-row">
      <div class="grow">
        <h3>${s.name}</h3>
        <div class="meta">${s.category} · 도보 ${s.walk_min}분${
    s.price_from ? ` · ${s.price_from.toLocaleString()}원~` : ""
  }</div>
      </div>
      <span class="badge ${badgeClass(s.congestion_label)}">${s.congestion_label}</span>
    </div>
    ${opts.extra || ""}
  </div>`;
}

// ===================== 앱 내 경로 안내 (홈·챗봇 공용) =====================
// 어느 화면에서든 openRoute(storeId)만 부르면 현재 위치 기준 소요시간·경로가
// 하단 시트로 뜬다. GPS·시트·스타일까지 이 파일 하나에 자체 완결.
let MY_POS = null;

// 데모 모드면 출발지를 경희대 정문으로 미리 채운다.
// 이렇게 해두면 GPS 를 안 켜도 '가는 길'이 "위치를 켜야 해요"에서 막히지 않고,
// 서버도 같은 좌표로 계산하므로 화면과 결과가 어긋나지 않는다.
const DEMO_READY = (async () => {
  try {
    const c = await (await fetch("/api/config")).json();
    if (c.demo && !MY_POS) MY_POS = { lat: c.lat, lng: c.lng, fixed: true };
    return c;
  } catch (e) { return { demo: false }; }
})();

function ensureRouteSheet() {
  if (document.getElementById("routeSheet")) return;
  const css = `
    #routeSheetBg{position:fixed;inset:0;background:rgba(31,36,48,.45);z-index:50;display:none}
    #routeSheetBg.show{display:block}
    #routeSheet{position:fixed;left:0;right:0;bottom:0;max-width:460px;margin:0 auto;
      background:#fff;border-radius:18px 18px 0 0;z-index:51;max-height:78vh;overflow:auto;
      transform:translateY(100%);transition:transform .22s ease-out}
    #routeSheet.show{transform:translateY(0)}
    #routeSheet .rs-head{padding:18px 18px 12px;border-bottom:1px solid var(--line-soft)}
    #routeSheet .rs-head h3{margin:0 0 4px;font-size:18px}
    #routeSheet .rs-sum{display:flex;gap:16px;padding:14px 18px;background:var(--bg-soft);font-size:13px}
    #routeSheet .rs-sum b{display:block;font-size:20px;color:var(--green);letter-spacing:-.4px}
    #routeSheet .rs-steps{padding:6px 18px 22px}
    #routeSheet .rs-step{display:flex;gap:11px;padding:11px 0;border-bottom:1px solid var(--line-soft)}
    #routeSheet .rs-n{width:22px;height:22px;border-radius:50%;background:var(--green-tint);
      color:var(--green);font-size:11px;font-weight:700;display:flex;align-items:center;
      justify-content:center;flex:0 0 auto}
    #routeSheet .rs-t{font-size:13.5px;color:var(--text-2)}
    #routeSheet .rs-m{font-size:11.5px;color:var(--gray-2);margin-top:2px}`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  document.body.insertAdjacentHTML("beforeend",
    `<div id="routeSheetBg" onclick="closeRoute()"></div><div id="routeSheet"></div>`);
}

function askMyLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      p => { MY_POS = { lat: p.coords.latitude, lng: p.coords.longitude }; resolve(MY_POS); },
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 });
  });
}

async function openRoute(id) {
  ensureRouteSheet();
  const sheet = document.getElementById("routeSheet");
  const bg = document.getElementById("routeSheetBg");
  sheet.innerHTML = `<div class="rs-head"><h3>현재 위치 확인 중…</h3></div>`;
  bg.classList.add("show"); sheet.classList.add("show");

  await DEMO_READY;                    // 데모 좌표가 채워질 때까지 기다린다
  if (!MY_POS) await askMyLocation();
  if (!MY_POS) {
    sheet.innerHTML = `
      <div class="rs-head"><h3>위치를 켜야 시간을 알 수 있어요</h3></div>
      <div class="empty">브라우저 위치 권한을 허용하면, 지금 있는 곳에서 몇 분 걸리는지 알려드려요.</div>
      <div style="padding:0 18px 24px"><button class="btn ghost" onclick="closeRoute()">닫기</button></div>`;
    return;
  }

  sheet.innerHTML = `<div class="rs-head"><h3>경로 계산 중…</h3></div>`;
  let r;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    const res = await fetch(`/api/route?lat=${MY_POS.lat}&lng=${MY_POS.lng}&store_id=${id}`,
                            { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(await res.text());
    r = await res.json();
  } catch (e) {
    sheet.innerHTML = `
      <div class="rs-head"><h3>경로를 불러오지 못했어요</h3></div>
      <div class="empty">${e.name === "AbortError" ? "응답이 너무 오래 걸려요. 다시 시도해주세요." : "가게 정보를 확인해주세요."}</div>
      <div style="padding:0 18px 24px"><button class="btn ghost" onclick="closeRoute()">닫기</button></div>`;
    return;
  }

  sheet.innerHTML = `
    <div class="rs-head">
      <h3>${r.store.name}</h3>
      <div class="meta">${r.store.address || r.store.category}</div>
    </div>
    <div class="rs-sum">
      <div><b>${r.walk_min}분</b>도보 소요</div>
      <div><b>${r.walk_meters}m</b>이동 거리</div>
      <div><b>${Math.round(r.walk_meters / 1.3)}</b>보 정도</div>
    </div>
    ${r.steps.length ? `<div class="rs-steps">${r.steps.map((s, i) => `
      <div class="rs-step">
        <div class="rs-n">${i + 1}</div>
        <div>
          <div class="rs-t">${s.text}</div>
          ${s.meters ? `<div class="rs-m">${s.meters}m · 약 ${Math.max(1, Math.round(s.seconds / 60))}분</div>` : ""}
        </div>
      </div>`).join("")}</div>`
      : `<div class="empty">상세 경로를 불러오지 못했습니다</div>`}
    <div style="padding:0 18px 24px"><button class="btn ghost" onclick="closeRoute()">닫기</button></div>`;
}

function closeRoute() {
  const sheet = document.getElementById("routeSheet");
  const bg = document.getElementById("routeSheetBg");
  if (sheet) sheet.classList.remove("show");
  if (bg) bg.classList.remove("show");
}
