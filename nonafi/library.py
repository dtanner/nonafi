"""Scan a music folder into artists, extracting tags and cover art."""

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
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
COVER_NAMES = ("cover", "folder", "front", "artist", "artwork")
COVER_SIZE = 500


@dataclass
class Track:
    id: str
    path: Path
    title: str
    album: str
    number: int
    disc: int
    duration: float


@dataclass
class Artist:
    id: str
    name: str
    tracks: list[Track] = field(default_factory=list)
    cover: bytes | None = None
    folder: Path | None = None

    def sort_tracks(self, root: Path) -> None:
        # Keep each album's songs together and in order: by subfolder, then album tag, then disc and track number.
        def key(t: Track):
            rel = t.path.parent.relative_to(root) if t.path.is_relative_to(root) else t.path.parent
            return (natural_key(str(rel)), t.album.lower(), t.disc, t.number, natural_key(t.path.name))

        self.tracks.sort(key=key)


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
    """An image in the artist folder, preferring cover.jpg-style names, then images in its subfolders."""
    candidates = []
    for p in folder.rglob("*"):
        if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("."):
            depth = len(p.relative_to(folder).parts)
            rank = 0 if p.stem.lower() in COVER_NAMES else 1
            candidates.append((depth, rank, natural_key(str(p.relative_to(folder))), p))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3].read_bytes()


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


def _placeholder_cover(name: str) -> bytes:
    """A plain generated cover so artists without art still look tappable."""
    from colorsys import hls_to_rgb

    hue = int(hashlib.md5(name.encode()).hexdigest(), 16) % 360
    r, g, b = hls_to_rgb(hue / 360, 0.32, 0.45)
    img = Image.new("RGB", (COVER_SIZE, COVER_SIZE), (int(r * 255), int(g * 255), int(b * 255)))
    draw = ImageDraw.Draw(img)
    max_w = COVER_SIZE - 50
    for size in (60, 52, 46, 40, 34):
        font = _font(size)
        lines = _wrap(draw, name, font, max_w)
        if len(lines) <= 4 and all(draw.textlength(l, font=font) <= max_w for l in lines):
            break
    lines = lines[:4]
    line_h = int(size * 1.2)
    y = (COVER_SIZE - len(lines) * line_h) // 2
    for line in lines:
        draw.text(((COVER_SIZE - draw.textlength(line, font=font)) / 2, y), line, fill="white", font=font)
        y += line_h
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


def _artist_id(name: str) -> str:
    return hashlib.sha1(name.lower().encode()).hexdigest()[:12]


def _track_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:16]


class Library:
    """One entry per artist. The top-level folder under the music root names the artist; files dropped
    straight into the root are grouped by their album-artist/artist tag instead."""

    def __init__(self, root: Path):
        self.root = root
        self.artists: dict[str, Artist] = {}
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
        artists: dict[str, Artist] = {}
        tracks: dict[str, Track] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            folder = Path(dirpath)
            rel = folder.relative_to(self.root)
            artist_folder = self.root / rel.parts[0] if rel.parts else None
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
                if artist_folder is not None:
                    artist_name = artist_folder.name
                else:
                    artist_name = _first(tags, "albumartist", "album_artist", "artist") or "Unknown Artist"
                number = _int(_first(tags, "tracknumber"))
                disc = _int(_first(tags, "discnumber"))
                duration = float(getattr(getattr(audio, "info", None), "length", 0) or 0)

                aid = _artist_id(artist_name)
                artist = artists.get(aid)
                if artist is None:
                    artist = Artist(id=aid, name=artist_name, folder=artist_folder)
                    artists[aid] = artist
                t = Track(
                    id=_track_id(path), path=path, title=title, album=_first(tags, "album") or "",
                    number=number, disc=disc, duration=duration,
                )
                artist.tracks.append(t)
                tracks[t.id] = t

        for artist in artists.values():
            artist.sort_tracks(self.root)
            # An image in the artist folder wins; otherwise the first embedded picture; otherwise a placeholder.
            if artist.folder is not None:
                raw = _folder_cover(artist.folder)
                if raw:
                    artist.cover = _normalize_cover(raw)
            if artist.cover is None:
                for t in artist.tracks:
                    try:
                        audio = MutagenFile(t.path, easy=False)
                    except Exception:
                        continue
                    raw = _embedded_cover(audio) if audio is not None else None
                    if raw and (cover := _normalize_cover(raw)):
                        artist.cover = cover
                        break
            if artist.cover is None:
                artist.cover = _placeholder_cover(artist.name)

        self.artists = dict(sorted(artists.items(), key=lambda kv: natural_key(_sort_name(kv[1].name))))
        self.tracks = tracks

    def to_json(self) -> list[dict]:
        return [
            {
                "id": a.id,
                "name": a.name,
                "cover": f"/covers/{a.id}-{hashlib.md5(a.cover).hexdigest()[:8]}.jpg",
                "tracks": [
                    {"id": t.id, "title": t.title, "url": f"/audio/{t.id}{t.path.suffix.lower()}", "duration": t.duration}
                    for t in a.tracks
                ],
            }
            for a in self.artists.values()
        ]


def _sort_name(name: str) -> str:
    """Sort 'The Beatles' under B."""
    return re.sub(r"^(the|a|an)\s+", "", name.strip(), flags=re.IGNORECASE)
