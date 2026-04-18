"""history_cache.py — content-addressed cache for original analysis inputs.

Layout: historyCache/<cache_id>/meta.json
                               images/0.jpg, 1.jpg, ...

cache_id = first 16 hex chars of SHA-256 over canonical content.
Deduplication: if the directory already exists we skip writing.
The cache is optional — deleting it only removes the ability to
replay the original input; history entries remain intact.
"""

import base64
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path

if getattr(sys, "frozen", False):
    _CACHE_DIR = Path(sys.executable).parent / "historyCache"
else:
    _CACHE_DIR = Path(__file__).parent.parent / "historyCache"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _entry_dir(cache_id: str) -> Path:
    return _CACHE_DIR / cache_id


def _canonical_bytes(input_type: str, text: str | None, images) -> bytes:
    """Build a stable bytes representation for hashing."""
    if input_type == "text":
        return (text or "").encode("utf-8")
    if input_type == "image" and images:
        bio = BytesIO()
        images[0].save(bio, "PNG")
        return bio.getvalue()
    return b""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save(
    input_type: str,          # "text" | "image"
    text: str | None = None,  # plain text or URL string
    images=None,              # list[PIL.Image] — full resolution originals
) -> str:
    """Persist input to cache; return cache_id. No-ops if already cached."""
    canonical = _canonical_bytes(input_type, text, images)
    cache_id = _sha256_hex(canonical)
    entry_dir = _entry_dir(cache_id)

    if entry_dir.exists():
        return cache_id  # already stored

    entry_dir.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "input_type": input_type,
        "text": text,
        "image_count": 0,
    }

    if images:
        img_dir = entry_dir / "images"
        img_dir.mkdir(exist_ok=True)
        for i, img in enumerate(images):
            img_path = img_dir / f"{i}.jpg"
            img.convert("RGB").save(img_path, "JPEG", quality=85)
        meta["image_count"] = len(images)

    (entry_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cache_id


def load(cache_id: str | None) -> dict | None:
    """Load cache entry dict, or None if cache missing / invalid.

    Returned dict keys:
      input_type  str
      text        str | None
      image_count int
      images_b64  list[str]   (JPEG base64, may be empty)
    """
    if not cache_id:
        return None
    meta_path = _entry_dir(cache_id) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        img_count = meta.get("image_count", 0)
        images_b64: list[str] = []
        for i in range(img_count):
            img_path = _entry_dir(cache_id) / "images" / f"{i}.jpg"
            if img_path.exists():
                images_b64.append(base64.b64encode(img_path.read_bytes()).decode())
        meta["images_b64"] = images_b64
        return meta
    except Exception:
        return None


def clear_all() -> None:
    """Delete entire cache directory. History entries are unaffected."""
    import shutil
    if _CACHE_DIR.exists():
        shutil.rmtree(_CACHE_DIR)
