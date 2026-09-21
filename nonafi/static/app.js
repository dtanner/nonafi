// nonafi jukebox UI: one screen. Left: what's playing. Right: pages of albums.
(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const PER_PAGE = 6;
  let albums = [];
  let current = null;   // album being played
  let index = 0;        // song index in that album
  let page = 0;
  let volume = 50;

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

  // ---- volume (real system volume, via the server) ---------------------
  function renderVolume() {
    const m = $("vol-meter");
    m.innerHTML = "";
    for (let i = 1; i <= 10; i++) {
      const s = document.createElement("i");
      if (volume >= i * 10 - 5) s.classList.add("on");
      m.appendChild(s);
    }
  }
  async function setVolume(v) {
    volume = Math.max(0, Math.min(100, v));
    renderVolume();
    try {
      const res = await fetch("/api/volume", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ volume }) });
      const data = await res.json();
      if (typeof data.volume === "number") { volume = data.volume; renderVolume(); }
    } catch (e) {}
  }
  $("vol-up").addEventListener("click", () => setVolume(volume + 10));
  $("vol-down").addEventListener("click", () => setVolume(volume - 10));
  fetch("/api/volume").then(r => r.json()).then(d => { if (typeof d.volume === "number") volume = d.volume; renderVolume(); })
    .catch(renderVolume);

  // No long-press menus, no pinch zoom.
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("gesturestart", (e) => e.preventDefault());

  renderPanel();
  loadAlbums();
  setInterval(loadAlbums, 15000);   // pick up newly uploaded music
})();
