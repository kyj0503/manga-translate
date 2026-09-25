"use strict";

const TOKEN = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);

function withToken(path) {
  return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}`;
}

async function api(path, method = "GET") {
  const response = await fetch(withToken(path), { method });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function imageUrl(book, index) {
  return withToken(`/api/image?book=${book}&index=${index}`);
}

let appState = null;
let library = { root: "", books: [] };
const reader = { book: null, index: 0, request: 0, timer: null, result: null, lastWheel: 0 };

// ---------- screens ----------

function showScreen(name) {
  for (const id of ["setup", "library", "reader"]) $(id).hidden = id !== name;
}

function route() {
  const match = location.hash.match(/^#\/read\/(\d+)\/(\d+)$/);
  if (match) {
    openPage(Number(match[1]), Number(match[2]));
    return;
  }
  stopPolling();
  reader.book = null;
  if (location.hash === "#/library") {
    showScreen("library");
    loadLibrary();
    return;
  }
  showScreen("setup");
  renderSetup();
}

window.addEventListener("hashchange", route);

async function refreshState() {
  try {
    appState = await api("/api/state");
  } catch (e) {
    return;
  }
  if (!$("setup").hidden) renderSetup();
  renderReaderInfo();
  if (appState.runtime === "ready" && (location.hash === "" || location.hash === "#/")) {
    location.hash = "#/library";
  }
}

// ---------- setup ----------

async function act(path) {
  try {
    appState = await api(path, "POST");
  } catch (e) {
    alert(e.message);
  }
  renderSetup();
}

function makeButton(label, onClick, disabled) {
  const button = document.createElement("button");
  button.textContent = label;
  button.disabled = disabled;
  button.onclick = onClick;
  return button;
}

function renderSetup() {
  if (!appState) return;
  const busy = appState.task !== null;
  $("setup-languages").textContent = appState.languages;
  $("components").replaceChildren(
    ...appState.components.map((c) => {
      const row = document.createElement("tr");
      const label = document.createElement("td");
      label.textContent = c.label;
      const status = document.createElement("td");
      status.textContent = c.status;
      const actions = document.createElement("td");
      actions.append(makeButton("설치", () => act(`/api/install/${c.key}`), busy || c.ready));
      if (c.key === "model") {
        actions.append(
          makeButton("변경...", () => act("/api/model"), busy || appState.runtime === "ready" || appState.runtime === "starting")
        );
      }
      row.append(label, status, actions);
      return row;
    })
  );
  const ready = appState.runtime === "ready";
  $("start").textContent = ready ? "책장으로" : appState.runtime === "starting" ? "시작하는 중..." : "시작";
  $("start").disabled = !(ready || appState.can_start);
  $("cancel").disabled = !busy;
  const message = $("setup-message");
  message.textContent = appState.error || appState.message;
  message.className = appState.error ? "error" : "";
  const log = $("log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
  log.textContent = appState.log.join("\n");
  if (atBottom) log.scrollTop = log.scrollHeight;
}

$("start").onclick = () => {
  if (appState && appState.runtime === "ready") location.hash = "#/library";
  else act("/api/start");
};
$("cancel").onclick = () => act("/api/cancel");
$("to-setup").onclick = () => (location.hash = "#/setup");

// ---------- library ----------

async function loadLibrary() {
  try {
    library = await api("/api/library");
  } catch (e) {
    alert(e.message);
    return;
  }
  renderLibrary();
}

function renderLibrary() {
  $("library-root").textContent = library.root;
  $("library-empty").hidden = library.books.length > 0;
  $("books").replaceChildren(
    ...library.books.map((book) => {
      const card = document.createElement("a");
      card.className = "book";
      card.href = `#/read/${book.id}/${book.position}`;
      const cover = document.createElement("img");
      cover.loading = "lazy";
      cover.src = imageUrl(book.id, 0);
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = book.title;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${book.position + 1} / ${book.pages}쪽`;
      card.append(cover, title, meta);
      return card;
    })
  );
}

$("open-folder").onclick = async () => {
  try {
    library = await api("/api/library/open", "POST");
  } catch (e) {
    alert(e.message);
  }
  renderLibrary();
};

// ---------- reader ----------

function stopPolling() {
  if (reader.timer !== null) clearTimeout(reader.timer);
  reader.timer = null;
}

function setStatus(text, failed = false) {
  $("page-status").textContent = text;
  $("page-status").className = failed ? "failed" : "";
  $("retry").hidden = !failed;
}

function renderReaderInfo() {
  if (!appState) return;
  $("reader-model").textContent = appState.model;
  $("reader-languages").textContent = appState.languages;
  $("direction").value = appState.page_direction;
}

async function openPage(bookId, index) {
  showScreen("reader");
  if (!library.books[bookId]) await loadLibrary();
  const book = library.books[bookId];
  if (!book) {
    location.hash = "#/library";
    return;
  }
  index = Math.max(0, Math.min(index, book.pages - 1));
  stopPolling();
  reader.book = bookId;
  reader.index = index;
  reader.result = null;
  reader.request += 1;
  $("book-title").textContent = book.title;
  $("page-number").textContent = `${index + 1} / ${book.pages}`;
  $("overlay").replaceChildren();
  setStatus("번역 대기");
  $("page-image").src = imageUrl(bookId, index);
  if (index + 1 < book.pages) new Image().src = imageUrl(bookId, index + 1);
  book.position = index;
  api(`/api/progress?book=${bookId}&index=${index}`, "POST").catch(() => {});
  renderReaderInfo();
  pollTranslation(reader.request);
}

function pollTranslation(request) {
  api(`/api/translation?book=${reader.book}&index=${reader.index}`)
    .then((data) => {
      if (request !== reader.request) return;
      if (data.status === "done") {
        reader.result = data;
        setStatus(data.blocks.length ? "번역 완료" : "대사 없음");
        drawOverlay();
        return;
      }
      if (data.status === "failed") {
        setStatus(`번역 실패: ${data.error}`, true);
        return;
      }
      setStatus(data.status === "working" ? "번역 중..." : "번역 대기");
      reader.timer = setTimeout(() => pollTranslation(request), 500);
    })
    .catch((e) => {
      if (request !== reader.request) return;
      setStatus(e.message, true);
    });
}

$("retry").onclick = async () => {
  try {
    await api(`/api/retry?book=${reader.book}&index=${reader.index}`, "POST");
  } catch (e) {
    setStatus(e.message, true);
    return;
  }
  reader.request += 1;
  setStatus("번역 대기");
  pollTranslation(reader.request);
};

function drawOverlay() {
  const overlay = $("overlay");
  overlay.replaceChildren();
  const result = reader.result;
  if (!result || !$("overlay-toggle").checked) return;
  const [width, height] = result.size;
  for (const block of result.blocks) {
    const [x1, y1, x2, y2] = block.xyxy;
    const box = document.createElement("div");
    box.className = "bubble";
    box.style.left = `${(x1 / width) * 100}%`;
    box.style.top = `${(y1 / height) * 100}%`;
    box.style.width = `${((x2 - x1) / width) * 100}%`;
    box.style.height = `${((y2 - y1) / height) * 100}%`;
    box.title = block.text;
    const text = document.createElement("span");
    text.textContent = block.translation || block.text;
    box.append(text);
    overlay.append(box);
  }
  fitText();
}

// The largest font size at which each translation still fits its box.
function fitText() {
  for (const box of $("overlay").children) {
    let low = 6;
    let high = 72;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      box.style.fontSize = `${mid}px`;
      if (box.scrollHeight <= box.clientHeight && box.scrollWidth <= box.clientWidth) low = mid;
      else high = mid - 1;
    }
    box.style.fontSize = `${low}px`;
  }
}

$("page-image").addEventListener("load", drawOverlay);
window.addEventListener("resize", fitText);
$("overlay-toggle").onchange = drawOverlay;

$("direction").onchange = async () => {
  try {
    appState = await api(`/api/settings?page_direction=${$("direction").value}`, "POST");
  } catch (e) {
    alert(e.message);
  }
  renderReaderInfo();
};

$("to-library").onclick = () => (location.hash = "#/library");

function go(delta) {
  if (reader.book === null) return;
  const book = library.books[reader.book];
  const next = reader.index + delta;
  if (!book || next < 0 || next >= book.pages) return;
  location.hash = `#/read/${reader.book}/${next}`;
}

function rightToLeft() {
  return !appState || appState.page_direction !== "ltr";
}

document.addEventListener("keydown", (event) => {
  if ($("reader").hidden || event.target.tagName === "SELECT") return;
  if (event.key === "t" || event.key === "T") {
    $("overlay-toggle").checked = !$("overlay-toggle").checked;
    drawOverlay();
  } else if (event.key === "ArrowLeft") {
    go(rightToLeft() ? 1 : -1);
  } else if (event.key === "ArrowRight") {
    go(rightToLeft() ? -1 : 1);
  } else if (event.key === "PageDown" || event.key === " ") {
    go(1);
  } else if (event.key === "PageUp") {
    go(-1);
  }
});

$("stage").addEventListener("click", (event) => {
  const leftHalf = event.clientX < window.innerWidth / 2;
  go(leftHalf === rightToLeft() ? 1 : -1);
});

$("stage").addEventListener(
  "wheel",
  (event) => {
    const now = Date.now();
    if (now - reader.lastWheel < 250) return;
    reader.lastWheel = now;
    go(event.deltaY > 0 ? 1 : -1);
  },
  { passive: true }
);

// ---------- start ----------

refreshState().then(route);
setInterval(refreshState, 1000);
