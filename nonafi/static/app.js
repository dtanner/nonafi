// nonafi jukebox UI: one screen. Left: what's playing. Right: pages of artists.
(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const PER_PAGE = 6;
  let artists = [];
  let current = null;   // artist being played
  let index = 0;        // song index in that artist's list
  let page = 0;
  // Song list for the playing artist, shown in place of the grid.
  const SONGS_PER_PAGE = 7, SONGS_TIMEOUT_MS = 15 * 1000;
  let songsOpen = false, songPage = 0, songsTimer;

  // ---- artist pages ---------------------------------------------------
  async function loadArtists() {
    let data;
    try { data = await (await fetch("/api/artists", { cache: "no-store" })).json(); } catch (e) { return; }
    const key = (list) => JSON.stringify(list.map(a => a.id + a.cover + a.tracks.length));
    if (key(data) === key(artists)) return;
    artists = data;
    render();
  }

  // The right side shows either artist pages or the playing artist's songs; the pager serves both.
  function render() {
    if (songsOpen && current) renderSongs(); else renderGrid();
  }
  function setPager(cur, pages) {
    $("pager").hidden = pages <= 1;
    $("page-num").textContent = `${cur + 1} / ${pages}`;
  }
  function turnPage(delta) {
    if (songsOpen && current) {
      songPage = Math.max(0, Math.min(Math.ceil(current.tracks.length / SONGS_PER_PAGE) - 1, songPage + delta));
    } else {
      page = Math.max(0, Math.min(Math.ceil(artists.length / PER_PAGE) - 1, page + delta));
    }
    render();
  }

  function renderGrid() {
    $("songs").hidden = true;
    const pages = Math.max(1, Math.ceil(artists.length / PER_PAGE));
    page = Math.min(page, pages - 1);
    const grid = $("grid");
    grid.hidden = false;
    grid.innerHTML = "";
    $("empty").hidden = artists.length > 0;
    setPager(page, pages);
    for (const a of artists.slice(page * PER_PAGE, (page + 1) * PER_PAGE)) {
      const b = document.createElement("button");
      b.className = "artist" + (current && current.id === a.id ? " current" : "");
      b.dataset.id = a.id;
      b.innerHTML = `<img src="${a.cover}" alt=""><div class="name"></div>`;
      b.querySelector(".name").textContent = a.name;
      b.addEventListener("click", () => tapArtist(a));
      grid.appendChild(b);
    }
  }
  $("page-up").addEventListener("click", () => turnPage(-1));
  $("page-down").addEventListener("click", () => turnPage(1));

  // ---- song list ------------------------------------------------------
  function renderSongs() {
    $("grid").hidden = true;
    $("empty").hidden = true;
    const songs = $("songs");
    songs.hidden = false;
    const pages = Math.max(1, Math.ceil(current.tracks.length / SONGS_PER_PAGE));
    songPage = Math.min(songPage, pages - 1);
    setPager(songPage, pages);
    const list = $("song-list");
    list.innerHTML = "";
    current.tracks.forEach((t, i) => {
      if (Math.floor(i / SONGS_PER_PAGE) !== songPage) return;
      const b = document.createElement("button");
      b.className = "btn song" + (i === index ? " current" : "");
      b.innerHTML = `<span class="num"></span><span class="name"></span>`;
      b.querySelector(".num").textContent = i + 1;
      b.querySelector(".name").textContent = t.title;
      b.addEventListener("click", () => { index = i; playTrack(); closeSongs(); });
      list.appendChild(b);
    });
  }
  function openSongs() {
    songsOpen = true;
    songPage = Math.floor(index / SONGS_PER_PAGE);
    touchSongs();
    render();
  }
  function closeSongs() {
    if (!songsOpen) return;
    songsOpen = false;
    clearTimeout(songsTimer);
    render();
  }
  // The list closes on its own after a while without a touch, so a stray open never sticks.
  function touchSongs() {
    if (!songsOpen) return;
    clearTimeout(songsTimer);
    songsTimer = setTimeout(closeSongs, SONGS_TIMEOUT_MS);
  }
  $("songs-back").addEventListener("click", closeSongs);
  // The now-playing cover and artist name open the list.
  for (const id of ["cover", "artist-name"]) $(id).addEventListener("click", () => { if (current) openSongs(); });

  // ---- playing --------------------------------------------------------
  function tapArtist(a) {
    // Tapping the artist that's already playing does nothing (no accidental restarts).
    if (current && current.id === a.id && !audio.paused) return;
    current = a;
    index = 0;
    playTrack();
    closeSongs();
    render();
  }

  function playTrack() {
    if (!current || !current.tracks.length) return;
    audio.src = current.tracks[index].url;
    audio.play().catch(() => {});
    renderPanel();
    if (songsOpen) render();   // keep the highlighted song current
  }

  function renderPanel() {
    $("idle").hidden = !!current;
    $("playing").hidden = !current;
    if (!current) return;
    const t = current.tracks[index] || {};
    $("cover").src = current.cover;
    $("artist-name").textContent = current.name;
    setTrackTitle(t.title || "");
    $("toggle").classList.toggle("playing", !audio.paused);
  }

  // Song names that don't fit scroll back and forth; the animation restarts only when the name changes.
  function setTrackTitle(title) {
    const box = $("track-title"), text = $("track-text");
    if (text.textContent === title && box.dataset.measured) return;
    text.textContent = title;
    box.classList.remove("scroll");
    box.dataset.measured = "";
    requestAnimationFrame(() => {
      const overflow = text.scrollWidth - box.clientWidth;
      box.dataset.measured = "1";
      if (overflow <= 0) return;
      box.style.setProperty("--marquee-shift", `-${overflow + 4}px`);
      box.style.setProperty("--marquee-time", `${Math.max(6, overflow / 25)}s`);
      box.classList.add("scroll");
    });
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
  $("prev").addEventListener("click", () => {
    if (!current) return;
    // A few seconds in (or on the first song), restart this song; otherwise go back one.
    if (audio.currentTime > 3 || index === 0) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
    index -= 1;
    playTrack();
  });

  audio.addEventListener("ended", () => {
    if (!current) return;
    if (index + 1 < current.tracks.length) {
      index += 1;
      playTrack();
    } else {
      // List finished: rewind to the first song and wait for Play.
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
  function goDim() { closeSongs(); dim.hidden = false; requestAnimationFrame(() => dim.classList.add("on")); }
  function wake() {
    dim.classList.remove("on");
    setTimeout(() => { if (!dim.classList.contains("on")) dim.hidden = true; }, 2000);
    clearTimeout(idleTimer);
    idleTimer = setTimeout(goDim, IDLE_MS);
  }
  dim.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); wake(); });
  document.addEventListener("pointerdown", () => { wake(); touchSongs(); }, true);
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
  function pickArtist(id) {
    const a = artists.find(x => x.id === id);
    if (!a) return;
    page = Math.floor(artists.indexOf(a) / PER_PAGE);
    tapArtist(a);
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
      case "play_artist":
        pickArtist(cmd.artist);
        break;
      case "play":
        if (!current && artists.length) pickArtist(artists[Math.floor(Math.random() * artists.length)].id);
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
  loadArtists();
  setInterval(loadArtists, 15000);   // pick up newly uploaded music
  listen();
})();
