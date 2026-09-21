// nonafi jukebox UI: one screen. Left: what's playing. Right: pages of albums.
(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const PER_PAGE = 6;
  let albums = [];
  let current = null;   // album being played
  let index = 0;        // song index in that album
  let page = 0;

  // ---- album pages ----------------------------------------------------
  async function loadAlbums() {
    let data;
    try { data = await (await fetch("/api/albums", { cache: "no-store" })).json(); } catch (e) { return; }
    const key = (list) => JSON.stringify(list.map(a => a.id + a.cover + a.tracks.length));
    if (key(data) === key(albums)) return;
    albums = data;
    renderGrid();
  }

  function renderGrid() {
    const pages = Math.max(1, Math.ceil(albums.length / PER_PAGE));
    page = Math.min(page, pages - 1);
    const grid = $("grid");
    grid.innerHTML = "";
    $("empty").hidden = albums.length > 0;
    $("pager").hidden = pages <= 1;
    $("page-num").textContent = `${page + 1} / ${pages}`;
    for (const a of albums.slice(page * PER_PAGE, (page + 1) * PER_PAGE)) {
      const b = document.createElement("button");
      b.className = "album" + (current && current.id === a.id ? " current" : "");
      b.dataset.id = a.id;
      b.innerHTML = `<img src="${a.cover}" alt=""><div class="name"></div><div class="who"></div>`;
      b.querySelector(".name").textContent = a.title;
      b.querySelector(".who").textContent = a.artist;
      b.addEventListener("click", () => tapAlbum(a));
      grid.appendChild(b);
    }
  }
  $("page-up").addEventListener("click", () => { page = Math.max(0, page - 1); renderGrid(); });
  $("page-down").addEventListener("click", () => {
    page = Math.min(Math.ceil(albums.length / PER_PAGE) - 1, page + 1); renderGrid();
  });

  // ---- playing --------------------------------------------------------
  function tapAlbum(a) {
    // Tapping the album that's already playing does nothing (no accidental restarts).
    if (current && current.id === a.id && !audio.paused) return;
    current = a;
    index = 0;
    playTrack();
    renderGrid();
  }

  function playTrack() {
    if (!current || !current.tracks.length) return;
    audio.src = current.tracks[index].url;
    audio.play().catch(() => {});
    renderPanel();
  }

  function renderPanel() {
    $("idle").hidden = !!current;
    $("playing").hidden = !current;
    if (!current) return;
    const t = current.tracks[index] || {};
    $("cover").src = current.cover;
    $("album-title").textContent = current.title;
    $("track-title").textContent = t.title || "";
    $("toggle").classList.toggle("playing", !audio.paused);
  }

  $("toggle").addEventListener("click", () => {
    if (!current) return;
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  });
  $("next").addEventListener("click", () => {
    if (!current) return;
    index = (index + 1) % current.tracks.length;
    playTrack();
  });

  audio.addEventListener("ended", () => {
    if (!current) return;
    if (index + 1 < current.tracks.length) {
      index += 1;
      playTrack();
    } else {
      // Album finished: rewind to the first song and wait for Play.
      index = 0;
      audio.src = current.tracks[0].url;
      renderPanel();
    }
  });
  audio.addEventListener("play", renderPanel);
  audio.addEventListener("pause", renderPanel);
  audio.addEventListener("error", () => {
    if (current && index + 1 < current.tracks.length) { index += 1; playTrack(); }
  });
  audio.addEventListener("timeupdate", () => {
    $("bar").style.width = (audio.duration ? (audio.currentTime / audio.duration) * 100 : 0) + "%";
  });

  // No long-press menus, no pinch zoom.
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("gesturestart", (e) => e.preventDefault());

  // ---- idle dimming ---------------------------------------------------
  // After IDLE_MS without a touch, dim the screen. The next touch only wakes it.
  const IDLE_MS = 10 * 60 * 1000;
  const dim = $("dim");
  let idleTimer;
  function goDim() { dim.hidden = false; requestAnimationFrame(() => dim.classList.add("on")); }
  function wake() {
    dim.classList.remove("on");
    setTimeout(() => { if (!dim.classList.contains("on")) dim.hidden = true; }, 2000);
    clearTimeout(idleTimer);
    idleTimer = setTimeout(goDim, IDLE_MS);
  }
  dim.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); wake(); });
  document.addEventListener("pointerdown", wake, true);
  wake();

  // ---- voice commands -------------------------------------------------
  // The voice service posts to /api/command; the server relays it here over SSE.
  const banner = $("banner");
  let bannerTimer;
  function showBanner(text, ms) {
    banner.textContent = text;
    banner.hidden = false;
    clearTimeout(bannerTimer);
    if (ms) bannerTimer = setTimeout(() => { banner.hidden = true; }, ms);
  }
  function chime(freq) {
    try {
      const ctx = chime.ctx || (chime.ctx = new (window.AudioContext || window.webkitAudioContext)());
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = freq;
      g.gain.setValueAtTime(0.25, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      o.connect(g).connect(ctx.destination);
      o.start(); o.stop(ctx.currentTime + 0.25);
    } catch (e) {}
  }
  function pickAlbum(id) {
    const a = albums.find(x => x.id === id);
    if (!a) return;
    page = Math.floor(albums.indexOf(a) / PER_PAGE);
    tapAlbum(a);
  }
  function onCommand(cmd) {
    wake();
    switch (cmd.action) {
      case "listening":
        chime(880);
        showBanner("Listening…", 8000);
        break;
      case "heard":
        showBanner(cmd.text ? `“${cmd.text}”` : "Didn't catch that", 4000);
        break;
      case "play_album":
        pickAlbum(cmd.album);
        break;
      case "play":
        if (!current && albums.length) pickAlbum(albums[Math.floor(Math.random() * albums.length)].id);
        else if (current && audio.paused) audio.play().catch(() => {});
        break;
      case "pause":
        if (current && !audio.paused) audio.pause();
        break;
      case "next":
        if (current) { index = (index + 1) % current.tracks.length; playTrack(); }
        break;
    }
  }
  function listen() {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => { try { onCommand(JSON.parse(e.data)); } catch (err) {} };
    es.onerror = () => { es.close(); setTimeout(listen, 3000); };
  }

  renderPanel();
  loadAlbums();
  setInterval(loadAlbums, 15000);   // pick up newly uploaded music
  listen();
})();
