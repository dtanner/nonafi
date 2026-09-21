"""Scan a music folder into albums, extracting tags and cover art."""

from __future__ import annotations

import hashlib
import io
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from mutagen import File as MutagenFile
from PIL import Image, ImageDraw, ImageFont

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".aac"}
COVER_NAMES = ("cover", "folder", "front", "album", "artwork")
COVER_SIZE = 500


@dataclass
class Track:
    id: str
    path: Path
    title: str
    number: int
    disc: int
    duration: float


@dataclass
class Album:
    id: str
    title: str
    artist: str
    tracks: list[Track] = field(default_factory=list)
    cover: bytes | None = None
    folder: Path | None = None

    def sort_tracks(self) -> None:
        self.tracks.sort(key=lambda t: (t.disc, t.number, natural_key(t.path.name)))


def natural_key(s: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def _first(tags, *keys) -> str | None:
    if tags is None:
        return None
    for k in keys:
        v = tags.get(k)
        if v:
            v = v[0] if isinstance(v, list) else v
            if hasattr(v, "text"):
                v = v.text[0] if v.text else None
            if v:
                return str(v).strip()
    return None


def _int(s: str | None) -> int:
    if not s:
        return 0
    m = re.match(r"\d+", str(s))
    return int(m.group()) if m else 0


def _embedded_cover(audio) -> bytes | None:
    """Return embedded picture bytes from any of the common tag formats."""
    tags = audio.tags
    if tags is None:
        return None
    # ID3 (mp3)
    if hasattr(tags, "getall"):
        pics = tags.getall("APIC")
        if pics:
            return bytes(pics[0].data)
    # MP4 (m4a)
    covr = tags.get("covr") if hasattr(tags, "get") else None
    if covr:
        return bytes(covr[0])
    # FLAC
    if getattr(audio, "pictures", None):
        return bytes(audio.pictures[0].data)
    # Ogg/Opus
    mbp = tags.get("metadata_block_picture") if hasattr(tags, "get") else None
    if mbp:
        import base64
        from mutagen.flac import Picture

        try:
            return bytes(Picture(base64.b64decode(mbp[0])).data)
        except Exception:
            return None
    return None


def _folder_cover(folder: Path) -> bytes | None:
    candidates = []
    for p in folder.iterdir():
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            rank = 0 if p.stem.lower() in COVER_NAMES else 1
            candidates.append((rank, p.name.lower(), p))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2].read_bytes()


def _normalize_cover(data: bytes) -> bytes | None:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _placeholder_cover(title: str, artist: str) -> bytes:
    """A plain generated cover so albums without art still look tappable."""
    from colorsys import hls_to_rgb

    hue = int(hashlib.md5(title.encode()).hexdigest(), 16) % 360
    r, g, b = hls_to_rgb(hue / 360, 0.32, 0.45)
    img = Image.new("RGB", (COVER_SIZE, COVER_SIZE), (int(r * 255), int(g * 255), int(b * 255)))
    draw = ImageDraw.Draw(img)
    max_w = COVER_SIZE - 50
    for size in (52, 46, 40, 34):
        font = _font(size)
        lines = _wrap(draw, title, font, max_w)
        if len(lines) <= 4 and all(draw.textlength(l, font=font) <= max_w for l in lines):
            break
    lines = lines[:4]
    small = _font(30)
    artist_lines = _wrap(draw, artist, small, max_w)[:2] if artist else []
    line_h, small_h = int(size * 1.2), 38
    total = len(lines) * line_h + (len(artist_lines) * small_h + 14 if artist_lines else 0)
    y = (COVER_SIZE - total) // 2
    for line in lines:
        draw.text(((COVER_SIZE - draw.textlength(line, font=font)) / 2, y), line, fill="white", font=font)
        y += line_h
    y += 14
    for line in artist_lines:
        draw.text(((COVER_SIZE - draw.textlength(line, font=small)) / 2, y), line, fill=(235, 235, 235), font=small)
        y += small_h
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _font(size: int):
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/piboto/Piboto-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        if os.path.exists(name):
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word wrap using measured widths; long single words are split."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        while draw.textlength(word, font=font) > max_w and len(word) > 1:
            cut = len(word)
            while cut > 1 and draw.textlength(word[:cut], font=font) > max_w:
                cut -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:cut])
            word = word[cut:]
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [text]


def _album_id(artist: str, title: str) -> str:
    return hashlib.sha1(f"{artist}\0{title}".lower().encode()).hexdigest()[:12]


def _track_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:16]


class Library:
    def __init__(self, root: Path):
        self.root = root
        self.albums: dict[str, Album] = {}
        self.tracks: dict[str, Track] = {}
        self._signature = None
        self._lock = threading.Lock()

    def _dir_signature(self):
        sig = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            try:
                sig.append((dirpath, os.stat(dirpath).st_mtime_ns, len(filenames)))
            except OSError:
                pass
        return tuple(sig)

    def refresh_if_changed(self) -> bool:
        with self._lock:
            sig = self._dir_signature()
            if sig == self._signature:
                return False
            self._scan()
            self._signature = sig
            return True

    def _scan(self) -> None:
        albums: dict[str, Album] = {}
        tracks: dict[str, Track] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            folder = Path(dirpath)
            for name in sorted(filenames, key=natural_key):
                path = folder / name
                if path.suffix.lower() not in AUDIO_EXTS or name.startswith("."):
                    continue
                try:
                    audio = MutagenFile(path, easy=False)
                except Exception:
                    audio = None
                easy = None
                try:
                    easy = MutagenFile(path, easy=True)
                except Exception:
                    pass
                tags = easy.tags if easy is not None else None
                title = _first(tags, "title") or path.stem
                album_title = _first(tags, "album") or (folder.name if folder != self.root else "Unknown Album")
                artist = (
                    _first(tags, "albumartist", "album_artist", "artist")
                    or (folder.parent.name if folder.parent != self.root and folder != self.root else "")
                )
                number = _int(_first(tags, "tracknumber"))
                disc = _int(_first(tags, "discnumber"))
                duration = float(getattr(getattr(audio, "info", None), "length", 0) or 0)

                aid = _album_id(artist, album_title)
                album = albums.get(aid)
                if album is None:
                    album = Album(id=aid, title=album_title, artist=artist, folder=folder)
                    albums[aid] = album
                if album.cover is None and audio is not None:
                    raw = _embedded_cover(audio)
                    if raw:
                        album.cover = _normalize_cover(raw)
                t = Track(id=_track_id(path), path=path, title=title, number=number, disc=disc, duration=duration)
                album.tracks.append(t)
                tracks[t.id] = t

        for album in albums.values():
            album.sort_tracks()
            if album.cover is None and album.folder is not None:
                raw = _folder_cover(album.folder)
                if raw:
                    album.cover = _normalize_cover(raw)
            if album.cover is None:
                album.cover = _placeholder_cover(album.title, album.artist)

        self.albums = dict(sorted(albums.items(), key=lambda kv: (kv[1].artist.lower(), kv[1].title.lower())))
        self.tracks = tracks

    def to_json(self) -> list[dict]:
        return [
            {
                "id": a.id,
                "title": a.title,
                "artist": a.artist,
                "cover": f"/covers/{a.id}-{hashlib.md5(a.cover).hexdigest()[:8]}.jpg",
                "tracks": [
                    {"id": t.id, "title": t.title, "url": f"/audio/{t.id}{t.path.suffix.lower()}", "duration": t.duration}
                    for t in a.tracks
                ],
            }
            for a in self.albums.values()
        ]
