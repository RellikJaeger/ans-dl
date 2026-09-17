#!/usr/bin/env python3
"""
Ani: New Stage — Manga Chapter Image Downloader (CLI)

Downloads manga chapter images from https://aninewstage.org.

Usage:
    python ans-dl.py <url> [output-dir]

    URL can be either:
      - A chapter page: https://aninewstage.org/view/<slug>/chapter/<N>
        → downloads that single chapter into <output-dir>/<slug>/chapter-<N>/
      - A post/details page: https://aninewstage.org/view/<slug>
        → discovers all chapter links, downloads each sequentially
          into <output-dir>/<slug>/chapter-<N>/

    -p N / --parallel N   Number of concurrent chapter downloads
                          (default: 4, only used for multi-chapter downloads)
    -u / up / upgrade      Self-upgrade: re-install from GitHub

Output layout:
    <slug>/chapter-01/page-01.png
    <slug>/chapter-01/page-02.png
    ...
    <slug>/chapter-02/page-01.png
    ...

Two image formats are supported:
    - Flat: each page = one full image (PNG/JPG/WebP, extension preserved)
    - Tiled: each page = 4 panel tiles composited into one PNG (2×2 grid)

Dependencies:
    Python 3.9+ stdlib only for flat chapters.
    Pillow (pip install pillow) required for tiled chapter remuxing.
    The script auto-detects the format — if Pillow is missing and a tiled
    chapter is encountered, it fails with a clear message.

Install (one-line, platform-specific — see README.md):
    macOS:   brew install python pillow
    Windows: scoop install python pillow
    Linux:   sudo apt install python3-full python3-pil
    Termux:  pkg install python python-pip && pip install pillow

Repo:
    https://github.com/RellikJaeger/ans-dl
"""

import gzip
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _default_output_dir() -> Path:
    """Platform-specific default downloads folder (no slug — caller appends
    the slug, same as an explicit path argument)."""
    plat = sys.platform
    # Android (Termux / ART)
    if plat == "android":
        return Path.home() / "storage" / "downloads"
    # Windows / macOS / Linux
    return Path.home() / "Downloads"


# ---------------------------------------------------------------------------
# Global state — parallel display + cancellation
# ---------------------------------------------------------------------------

_cancelled = False
_parallel_state: dict[int, dict] = {}   # chapter_num → {done,total,failed,current,kb,status}
_chapter_rows: dict[int, int] = {}      # chapter_num → terminal row number
_next_row: int = 0


def _sigint_handler(signum, frame):
    """Set cancellation flag — main thread handles clean exit."""
    global _cancelled
    _cancelled = True


# ---------------------------------------------------------------------------
# URL patterns + headers
# ---------------------------------------------------------------------------

CHAPTER_RE = re.compile(r"/view/([^/]+)/chapter/(\d+)")
SLUG_ONLY_RE = re.compile(r"/view/([^/]+)(?:/)?$")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:155.0) "
    "Gecko/20100101 Firefox/155.0"
)

# Browser-like headers for page fetches (HTML pages on aninewstage.org)
# Request gzip/deflate only — NOT brotli (not in stdlib, no pip installs)
PAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
}

# Browser-like headers for image CDN fetches (files.aninewstage.org)
IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
    "DNT": "1",
}


# ---------------------------------------------------------------------------
# Compression (stdlib only — no brotli)
# ---------------------------------------------------------------------------

def _decompress(body: bytes, encoding: str) -> bytes:
    """Decompress response body using stdlib only. No brotli (not in stdlib)."""
    enc = (encoding or "").lower()
    if enc in ("gzip", "x-gzip"):
        return gzip.decompress(body)
    if enc in ("deflate",):
        import zlib
        try:
            return zlib.decompress(body)
        except zlib.error:
            # Some servers use raw deflate (no zlib wrapper)
            return zlib.decompress(body, -zlib.MAX_WBITS)
    # Unknown encoding (shouldn't happen — we don't request br) — return raw
    return body


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch(url: str, timeout: int = 60, on_progress=None, headers: dict | None = None) -> bytes:
    """Fetch URL, handle gzip/deflate decompression via stdlib.
    Optional on_progress(bytes_so_far, total_bytes)."""
    req_headers = headers if headers is not None else dict(PAGE_HEADERS)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            encoding = resp.headers.get("Content-Encoding", "")
            body = resp.read()
            return _decompress(body, encoding)
    except urllib.error.HTTPError as e:
        print(f"[HTTP {e.code}] {url}", file=sys.stderr)
        return b""
    except urllib.error.URLError as e:
        print(f"[ERR] {url}: {e.reason}", file=sys.stderr)
        return b""


def fetch_text(url: str) -> str:
    body = fetch(url)
    if not body:
        return ""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1")


# ---------------------------------------------------------------------------
# Page parsing
# ---------------------------------------------------------------------------

def extract_slides_info(html_text: str) -> list[dict]:
    """Extract slide data from reader page HTML.

    Returns a list of slide dicts. Each dict has one of two shapes:

      Flat (full-page images):
          {"url": "https://...", "type": "flat"}

      Tiled (1 manga page = 2x2 panel grid):
          {"tiles": [url0, url1, url2, url3],
           "cols": 2, "rows": 2, "r": 0.75,
           "type": "tiles"}

    The caller uses this to decide whether to download-and-save directly
    (flat) or download tiles → composite → save (tiled).
    """

    m = re.search(
        r"slides\s*:\s*JSON\.parse\s*\(\s*'(.+?)'\s*\)\s*,?",
        html_text,
        re.DOTALL,
    )
    if not m:
        raise ValueError(
            "Could not find 'slides: JSON.parse(...)' in page HTML. "
            "Site structure may have changed."
        )

    raw = m.group(1)

    # Decode escape sequences present in HTML source
    decoded = (
        raw
        .replace("\\u0022", '"')   # \\u0022 → "
        .replace("\\u0027", "'")    # \\u0027 → '
        .replace("\\n", "\n")       # \\n → newline
        .replace("\\t", "\t")       # \\t → tab
    )
    # Collapse N backslashes before a slash into a single slash
    decoded = re.sub(r"\\+/", "/", decoded)

    try:
        slides = json.loads(decoded)
    except json.JSONDecodeError:
        print("[warn] JSON parse failed, using regex fallback", file=sys.stderr)
        url_pattern = re.compile(
            r"https?://files\.aninewstage\.org/"
            r"file/ans-assets/[^'\\\"]+\.(?:png|jpg|jpeg|webp)"
        )
        urls = url_pattern.findall(decoded)
        if not urls:
            raise ValueError("No image URLs found in slides data")
        return [{"url": u, "type": "flat"} for u in urls]

    if not isinstance(slides, list):
        raise ValueError(f"Expected a list, got {type(slides).__name__}")

    result: list[dict] = []
    for item in slides:
        if isinstance(item, str):
            result.append({"url": item, "type": "flat"})
        elif isinstance(item, dict) and "tiles" in item:
            tiles = [t for t in item["tiles"] if isinstance(t, str)]
            if not tiles:
                continue
            result.append({
                "tiles": tiles,
                "cols": item.get("cols", 2),
                "rows": item.get("rows", 2),
                "r": item.get("r"),
                "type": "tiles",
            })
        elif isinstance(item, dict) and "url" in item:
            result.append({"url": item["url"], "type": "flat"})
        else:
            # Unexpected shape — skip silently
            continue

    if not result:
        raise ValueError("No image URLs found in slides data")

    return result


# Backward-compat alias — old callers still use list[str]
def extract_slides_urls(html_text: str) -> list[str]:
    """Flatten slides into a plain URL list (legacy API)."""
    info = extract_slides_info(html_text)
    urls: list[str] = []
    for slide in info:
        if slide["type"] == "flat":
            urls.append(slide["url"])
        else:
            urls.extend(slide["tiles"])
    return urls


def _remux_slide_tiles(tiles: list[str], output_path: Path) -> bool:
    """Download 4 tile images and composite into one page image.

    Tile order: top-left(0), top-right(1), bottom-left(2), bottom-right(3).
    Uses Pillow for compositing. Returns True on success, False on failure.
    """
    try:
        from PIL import Image
        from io import BytesIO
    except ImportError:
        print("[error] Pillow not available - cannot remux tiles", file=sys.stderr)
        return False

    tile_images = []
    for url in tiles:
        body = fetch(url, headers=IMAGE_HEADERS)
        if not body:
            return False
        try:
            tile_images.append(Image.open(BytesIO(body)))
        except Exception:
            return False

    if len(tile_images) != 4:
        return False

    w, h = tile_images[0].size
    mode = tile_images[0].mode

    # 2x2 grid composite
    composite = Image.new(mode, (w * 2, h * 2))
    composite.paste(tile_images[0], (0, 0))       # TL
    composite.paste(tile_images[1], (w, 0))        # TR
    composite.paste(tile_images[2], (0, h))        # BL
    composite.paste(tile_images[3], (w, h))        # BR

    composite.save(output_path, format="PNG")
    return True


# ---------------------------------------------------------------------------
# Chapter discovery
# ---------------------------------------------------------------------------

def discover_chapters(details_url: str) -> list[tuple[int, str, str]]:
    """Fetch details page and extract chapter (number, url, title) tuples."""
    html = fetch_text(details_url)
    if not html:
        raise ValueError(f"Failed to fetch details page: {details_url}")

    slug_match = SLUG_ONLY_RE.search(details_url)
    base_slug = slug_match.group(1) if slug_match else "unknown"

    # Find all chapter links
    chapter_links = re.findall(
        r'href="(/[^\"]*?/chapter/(\d+)[^\"]*)"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )

    chapters = {}
    for href, num_str, title in chapter_links:
        num = int(num_str)
        full_url = href if href.startswith("http") else "https://aninewstage.org" + href
        if num not in chapters:
            chapters[num] = (num, full_url, title.strip())

    # Also try to find chapters via any link containing /chapter/
    if not chapters:
        chapter_links2 = re.findall(
            r'href="([^"]*?/chapter/(\d+)[^\"]*)"',
            html,
        )
        for href, num_str in chapter_links2:
            num = int(num_str)
            full_url = href if href.startswith("http") else "https://aninewstage.org" + href
            if num not in chapters:
                chapters[num] = (num, full_url, f"Chapter {num}")

    result = sorted(chapters.values(), key=lambda x: x[0])
    if not result:
        raise ValueError(
            f"No chapter links found on details page: {details_url}"
        )
    return result


def is_chapter_url(url: str) -> bool:
    return bool(CHAPTER_RE.search(url))


def parse_url(url: str) -> dict:
    """Return parsed info from a URL."""
    info = {"url": url, "is_chapter": False}

    m = CHAPTER_RE.search(url)
    if m:
        info["is_chapter"] = True
        info["slug"] = m.group(1)
        info["chapter_num"] = int(m.group(2))
    else:
        sm = SLUG_ONLY_RE.search(url)
        if sm:
            info["slug"] = sm.group(1)
            info["chapter_num"] = None
        else:
            raise ValueError(f"URL is not an aninewstage.org page: {url}")

    return info


# ===========================================================================
# Download
# ===========================================================================

def download_images(urls: list[str], output_dir: Path, chapter_num: int,
                     on_image_progress=None) -> tuple[int, int]:
    """Download images sequentially. Returns (done, failed).

    If on_image_progress is None (sequential mode): prints inline
        progress with \r byte-level updates (XX% (N KB) → OK — N KB).
    If on_image_progress is provided (parallel mode): calls it after each
        image with (done, total, failed, current_filename, kb). No direct
        printing — the caller owns the display.
    """
    total = len(urls)
    done = 0
    failed = 0

    for i, url in enumerate(urls, 1):
        if _cancelled:
            break

        ext = url.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            ext = "png"
        filename = f"page-{i:02d}.{ext}"
        dest = output_dir / filename

        if dest.exists():
            done += 1
            if on_image_progress is not None:
                on_image_progress(done, total, failed, filename, 0)
            continue

        # Create the chapter folder only when we're about to write the
        # first image — never leave empty folders behind on cancel.
        output_dir.mkdir(parents=True, exist_ok=True)

        if on_image_progress is None:
            # ---- Sequential mode: own the display ----
            print(f"    [{i:>3}/{total}] {filename} ... ", end="", flush=True)

        def on_progress(downloaded: int, total_bytes: int | None) -> None:
            if on_image_progress is None and total_bytes:
                pct = downloaded * 100 // total_bytes
                print(f"\r      {pct:3d}% ({downloaded // 1024} KB)  ", end="", flush=True)
            elif on_image_progress is None:
                print(f"\r      {downloaded // 1024} KB        ", end="", flush=True)

        body = fetch(url, on_progress=on_progress if on_image_progress is None else None,
                     headers=IMAGE_HEADERS)
        if body:
            dest.write_bytes(body)
            done += 1
            kb = len(body) // 1024
            if on_image_progress is not None:
                on_image_progress(done, total, failed, filename, kb)
            else:
                print(f"\r      OK — {kb} KB     ")
        else:
            failed += 1
            if on_image_progress is not None:
                on_image_progress(done, total, failed, filename, 0)
            else:
                print("FAILED")

    return done, failed


def download_chapter(
    chapter_url: str,
    output_base: Path,
    silent: bool = False,
    on_chapter_start=None,
    on_image_progress=None,
) -> dict:
    """Download a single chapter. Returns stats dict.

    silent=True        → no printing; caller owns display (parallel mode).
    on_chapter_start   → called as on_chapter_start(chapter_num, total_images).
    on_image_progress  → called as on_image_progress(done, total, failed,
                                          current_filename, kb).
    """
    info = parse_url(chapter_url)
    slug = info["slug"]
    chapter_num = info["chapter_num"]
    chapter_dir = output_base / slug / f"chapter-{chapter_num:02d}"

    if not silent:
        print()
        print(f"Chapter {chapter_num:02d} — {chapter_url}")
        print(f"Output: {chapter_dir}/")
        print()

    html = fetch_text(chapter_url)
    if not html:
        if not silent:
            print("[FAIL] Could not fetch chapter page", file=sys.stderr)
        return {"done": 0, "failed": 0, "chapter": chapter_num}

    slides_info = extract_slides_info(html)
    if not slides_info:
        if not silent:
            print("[FAIL] No images found in chapter page", file=sys.stderr)
        return {"done": 0, "failed": 0, "chapter": chapter_num}

    # Determine total pages: each slide (flat or tiled) = 1 page
    total_pages = len(slides_info)

    if on_chapter_start is not None:
        on_chapter_start(chapter_num, total_pages)

    if not silent:
        tiled = sum(1 for s in slides_info if s["type"] == "tiles")
        flat = total_pages - tiled
        print(f"Found {total_pages} pages ({flat} flat, {tiled} tiled)")

    done = 0
    failed = 0

    for idx, slide in enumerate(slides_info, 1):
        if _cancelled:
            break

        if slide["type"] == "flat":
            # --- Flat slide: download single image ---
            url = slide["url"]
            ext = url.rsplit(".", 1)[-1].lower()
            if ext not in ("png", "jpg", "jpeg", "webp"):
                ext = "png"
            filename = f"page-{idx:02d}.{ext}"
            dest = chapter_dir / filename

            if dest.exists():
                done += 1
                if on_image_progress is not None:
                    on_image_progress(done, total_pages, failed, filename, 0)
                continue

            chapter_dir.mkdir(parents=True, exist_ok=True)

            if on_image_progress is None:
                print(f"    [{idx:>3}/{total_pages}] {filename} ... ", end="", flush=True)

            def on_progress(downloaded: int, total_bytes: int | None) -> None:
                if on_image_progress is None and total_bytes:
                    pct = downloaded * 100 // total_bytes
                    print(f"\r      {pct:3d}% ({downloaded // 1024} KB)  ", end="", flush=True)
                elif on_image_progress is None:
                    print(f"\r      {downloaded // 1024} KB        ", end="", flush=True)

            body = fetch(url, on_progress=on_progress if on_image_progress is None else None,
                         headers=IMAGE_HEADERS)
            if body:
                dest.write_bytes(body)
                done += 1
                kb = len(body) // 1024
                if on_image_progress is not None:
                    on_image_progress(done, total_pages, failed, filename, kb)
                else:
                    print(f"\r      OK — {kb} KB     ")
            else:
                failed += 1
                if on_image_progress is not None:
                    on_image_progress(done, total_pages, failed, filename, 0)
                else:
                    print("FAILED")

        elif slide["type"] == "tiles":
            # --- Tiled slide: download tiles, composite, save ---
            tiles = slide["tiles"]
            filename = f"page-{idx:02d}.png"  # Always PNG for composites
            dest = chapter_dir / filename

            if dest.exists():
                done += 1
                if on_image_progress is not None:
                    on_image_progress(done, total_pages, failed, filename, 0)
                continue

            chapter_dir.mkdir(parents=True, exist_ok=True)

            if on_image_progress is None:
                print(f"    [{idx:>3}/{total_pages}] {filename} (composite) ... ", end="", flush=True)

            # Download all 4 tiles first
            tile_bodies = []
            tile_ok = True
            for tile_url in tiles:
                body = fetch(tile_url, headers=IMAGE_HEADERS)
                if not body:
                    tile_ok = False
                    break
                tile_bodies.append(body)

            if tile_ok:
                try:
                    from PIL import Image
                    from io import BytesIO
                    tile_imgs = [Image.open(BytesIO(b)) for b in tile_bodies]
                    w, h = tile_imgs[0].size
                    mode = tile_imgs[0].mode
                    composite = Image.new(mode, (w * 2, h * 2))
                    composite.paste(tile_imgs[0], (0, 0))
                    composite.paste(tile_imgs[1], (w, 0))
                    composite.paste(tile_imgs[2], (0, h))
                    composite.paste(tile_imgs[3], (w, h))
                    composite.save(dest, format="PNG")
                    done += 1
                    kb = dest.stat().st_size // 1024
                    if on_image_progress is not None:
                        on_image_progress(done, total_pages, failed, filename, kb)
                    else:
                        print(f"\r      OK — {kb} KB     ")
                except Exception as e:
                    print(f"\r      Composite failed: {e}", file=sys.stderr)
                    failed += 1
                    if on_image_progress is not None:
                        on_image_progress(done, total_pages, failed, filename, 0)
                    else:
                        print("FAILED")
            else:
                failed += 1
                if on_image_progress is not None:
                    on_image_progress(done, total_pages, failed, filename, 0)
                else:
                    print("FAILED")

    if not silent:
        print(f"Chapter {chapter_num:02d}: {done} downloaded, {failed} failed")

    return {"done": done, "failed": failed, "chapter": chapter_num}


# ---------------------------------------------------------------------------
# Parallel-mode display — main thread owns stdout, workers stay silent
# ---------------------------------------------------------------------------

def _format_chapter_line(num: int, st: dict) -> str:
    """Render one chapter's current state as a single display line."""
    if st["status"] == "fail":
        return (f"  Chapter {num:02d}: "
                f"FAILED — {st['failed']} images failed")
    if st["total"] == 0:
        return f"  Chapter {num:02d}: (no images)"
    pct = st["done"] * 100 // st["total"]
    if st["current"]:
        return (f"  Chapter {num:02d}: "
                f"[{st['done']:>3}/{st['total']:<3}] "
                f"{st['current']} ... {pct}% ({st['kb']} KB)")
    return (f"  Chapter {num:02d}: "
            f"[{st['done']:>3}/{st['total']:<3}] ... {pct}%")


def _refresh_parallel_display() -> None:
    """Clear and redraw every active chapter line in place.

    Uses ANSI escape sequences to jump to each chapter's assigned row,
    clear it, and overwrite with the latest state. One stdout owner (the
    main thread) — no garbled output from concurrent thread writes.
    """
    if not _chapter_rows:
        return

    if not sys.stdout.isatty():
        # Non-TTY (pipe/log): just dump each line
        for num in sorted(_chapter_rows.keys()):
            st = _parallel_state.get(num)
            if st and st["status"] != "waiting":
                print(_format_chapter_line(num, st))
        return

    out: list[str] = []
    for num in sorted(_chapter_rows.keys()):
        st = _parallel_state.get(num)
        if not st or st["status"] == "waiting":
            continue
        row = _chapter_rows[num]
        out.append(f"\033[{row};1H")   # cursor to row, column 1
        out.append("\033[2K")          # clear the whole line
        out.append(_format_chapter_line(num, st))

    sys.stdout.write("".join(out))
    sys.stdout.flush()


# ===========================================================================
# Batch download (multi-chapter)
# ===========================================================================

def download_all_chapters(
    details_url: str,
    output_base: Path,
    delay: float = 2.0,
    jobs: int = 1,
) -> dict:
    """Discover and download all chapters from a details page.

    When jobs > 1, downloads up to `jobs` chapters in parallel via
    ThreadPoolExecutor (stdlib, no pip). Each chapter downloads its own
    images sequentially within its thread. The main thread owns the display:
    one clean line per active chapter, updating in place.
    """
    chapters = discover_chapters(details_url)
    slug = (
        chapters[0][1].split("/view/")[-1].split("/chapter")[0].strip("/")
        if chapters else "unknown"
    )
    slug = slug or parse_url(details_url)["slug"]

    print()
    print(f"Post: {details_url}")
    print(f"Chapters found: {len(chapters)}")
    print(f"Output base: {output_base}/")
    print(f"Parallel chapters: {jobs}")
    print()

    total_done = 0
    total_failed = 0
    total_chapters = len(chapters)

    # ---- Sequential ----
    if jobs <= 1:
        for idx, (num, url, title) in enumerate(chapters, 1):
            if _cancelled:
                break
            stats = download_chapter(url, output_base)
            total_done += stats["done"]
            total_failed += stats["failed"]
            if idx < total_chapters:
                print(f"\n  → Waiting {delay}s before next chapter...")
                time.sleep(delay)

        if _cancelled:
            print("\nCancelled by user.", file=sys.stderr)
            sys.exit(130)

        print()
        print(f"Batch complete: {total_done} images downloaded, {total_failed} failed")
        print(f" across {total_chapters} chapters")
        print()
        return {"done": total_done, "failed": total_failed, "chapters": total_chapters}

    # ---- Parallel ----
    from concurrent.futures import ThreadPoolExecutor

    # Pre-assign a terminal row to every chapter (dense, no gaps).
    global _next_row, _chapter_rows, _parallel_state
    _chapter_rows = {}
    _parallel_state = {}
    _next_row = 3  # row 1 = "Downloading..." header, row 2 = blank

    for idx, (num, url, title) in enumerate(chapters):
        _chapter_rows[num] = _next_row + idx
        _parallel_state[num] = {
            "done": 0, "total": 0, "failed": 0,
            "current": "", "kb": 0, "status": "waiting",
        }

    def _worker(chapter_info):
        num, url, title = chapter_info
        st = _parallel_state[num]
        st["status"] = "download"

        def on_chapter_start(cnum, total):
            _parallel_state[cnum]["total"] = total

        def on_image_progress(done, total, failed, current, kb):
            _parallel_state[num]["done"] = done
            _parallel_state[num]["total"] = total
            _parallel_state[num]["failed"] = failed
            _parallel_state[num]["current"] = current
            _parallel_state[num]["kb"] = kb

        return download_chapter(
            url, output_base,
            silent=True,
            on_chapter_start=on_chapter_start,
            on_image_progress=on_image_progress,
        )

    pool = ThreadPoolExecutor(max_workers=jobs)
    try:
        futures = {pool.submit(_worker, ch): ch for ch in chapters}

        # Main-thread display loop — one owner of stdout.
        while not _cancelled:
            if all(f.done() for f in futures):
                break
            _refresh_parallel_display()
            time.sleep(0.1)

        # Collect results. Don't keep done chapters in the display —
        # only actively-downloading chapters occupy lines. Final stats
        # below cover the totals.
        for future in futures:
            if future.done():
                stats = future.result()
                total_done += stats["done"]
                total_failed += stats["failed"]
                _parallel_state.pop(stats["chapter"], None)
    finally:
        # On Ctrl+C: cancel queued futures so later chapters never start.
        # Don't wait for running threads — os._exit kills them.
        pool.shutdown(wait=False, cancel_futures=True)

    # Final in-place refresh so every line shows its end state.
    _refresh_parallel_display()
    print()  # move cursor below the chapter block

    if _cancelled:
        print("Cancelled by user.", file=sys.stderr)
        sys.stderr.flush()
        os._exit(130)

    print()
    print(f"Batch complete: {total_done} images downloaded, {total_failed} failed")
    print(f" across {total_chapters} chapters")
    print()

    return {"done": total_done, "failed": total_failed, "chapters": total_chapters}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _do_upgrade() -> None:
    """Self-upgrade: re-install from GitHub (yt-style `up` command).

    Detects platform and runs the appropriate upgrade one-liner via
    subprocess. On Windows, prints instructions since the multi-command
    chain is a PowerShell/cmd operation.
    """
    plat = sys.platform
    repo = "https://github.com/RellikJaeger/ans-dl"

    if plat == "darwin":
        # macOS — brew handles all deps including Pillow.
        # Print the copy-paste one-liner (same as the install command in README).
        # User pastes it into their own terminal — separate process, fully auto.
        print("Upgrading ans-dl (macOS)...")
        print()
        print(
            "/bin/bash -c \"$(curl -fsSL "
            "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\" "
            "&& brew update && brew upgrade -y "
            "&& brew install git python pillow "
            "&& brew cleanup --prune=all "
            "&& cd \"$HOME\" "
            "&& rm -rf \"./ans-dl/\" "
            "&& git clone -b main --depth 1 " + repo + " "
            "&& mkdir -p \"$HOME/.local/bin\" "
            "&& source \"$HOME/.zshrc\" "
            "&& mv \"./ans-dl/ans-dl\" \"./ans-dl/ans-dl.py\" \"$HOME/.local/bin/\" "
            "&& chmod a+x \"$HOME/.local/bin/ans-dl\" "
            "&& rm -rf \"./ans-dl/\" "
            "&& clear "
            "&& ans-dl --help"
        )
        print()
        print()
        print("Run the commands above in your terminal to upgrade ans-dl.")
        print()

    elif plat == "win32":
        # Windows — the upgrade is a PowerShell/cmd multi-command chain.
        # Print it for the user to copy-paste (subprocess can't easily
        # replicate the start /i cmd /k ... && exit pattern).
        print("Upgrading ans-dl (Windows)...")
        print()
        cmd = (
            "powershell -c \"Set-ExecutionPolicy RemoteSigned -Scope CurrentUser; "
            "irm https://get.scoop.sh | iex; exit\" "
            "&& scoop install git python sudo pillow "
            "&& cd %UserProfile% "
            "&& rm -rf \".\\ans-dl\\\" "
            "&& git clone -b main " + repo + " "
            "&& sudo cmd /c move /y \".\\ans-dl\\ans-dl.bat\" \".\\ans-dl\\ans-dl.py\" \"%SystemRoot%\\\" "
            "&& rm -rf \".\\ans-dl\\\" "
            "&& start /i cmd /k \"ans-dl --help\" "
            "&& exit"
        )
        print(cmd)
        print()

    elif plat == "linux":
        if os.path.exists("/data/data/com.termux/files/usr/bin/pkg"):
            # Termux — pkg is the package manager, pip for Pillow
            cmd = (
                "yes | (pkg up && pkg in git python python-pip ffmpeg "
                "&& pip install --upgrade pillow "
                "&& git clone -b main --depth 1 " + repo + " "
                "&& chmod a+x ans-dl/ans-dl "
                "&& mv ans-dl/ans-dl ans-dl/ans-dl.py $PREFIX/bin "
                "&& rm -rf ans-dl "
                "&& mkdir -p $HOME/bin "
                "&& if [ -x \"$HOME/bin/termux-url-opener\" ]; then "
                "    if grep -q \"aninewstage\" \"$HOME/bin/termux-url-opener\"; then "
                "        echo \"Existing termux-url-opener already handles aninewstage.org — leaving it alone\"; "
                "    else "
                "        cp \"$HOME/bin/termux-url-opener\" \"$HOME/bin/termux-url-opener-orig\"; "
                "        cat > \"$HOME/bin/termux-url-opener\" << 'EOF'"
            )
            # Write the heredoc content for termux-url-opener
            url_opener_content = (
                "#!/bin/bash\n"
                "remaining=()\n"
                "for url in \"$@\"; do\n"
                "    case \"$url\" in\n"
                "        http://aninewstage.org/*|https://aninewstage.org/*)\n"
                "            ans-dl \"$url\"\n"
                "            ;;\n"
                "        *)\n"
                "            remaining+=(\"$url\")\n"
                "            ;;\n"
                "    esac\n"
                "done\n"
                "if [ ${#remaining[@]} -gt 0 ]; then\n"
                "    \"$HOME/bin/termux-url-opener-orig\" \"${remaining[@]}\"\n"
                "fi\n"
            )
            cmd += "\n" + url_opener_content + "\nEOF\n"
            cmd += (
                "    fi; else if command -v yt >/dev/null 2>&1; then "
                "cat > \"$HOME/bin/termux-url-opener\" << 'EOF'"
            )
            yt_opener_content = (
                "#!/bin/bash\n"
                "remaining=()\n"
                "for url in \"$@\"; do\n"
                "    case \"$url\" in\n"
                "        http://aninewstage.org/*|https://aninewstage.org/*)\n"
                "            ans-dl \"$url\"\n"
                "            ;;\n"
                "        *)\n"
                "            remaining+=(\"$url\")\n"
                "            ;;\n"
                "    esac\n"
                "done\n"
                "if [ ${#remaining[@]} -gt 0 ]; then\n"
                "    yt \"${remaining[@]}\"\n"
                "fi\n"
                "EOF\n"
            )
            cmd += "\n" + yt_opener_content + "\nEOF\n"
            cmd += (
                "else cat > \"$HOME/bin/termux-url-opener\" << 'EOF'"
            )
            ansdl_only_content = (
                "#!/bin/bash\n"
                "for url in \"$@\"; do\n"
                "    case \"$url\" in\n"
                "        http://aninewstage.org/*|https://aninewstage.org/*)\n"
                "            ans-dl \"$url\"\n"
                "            ;;\n"
                "    esac\n"
                "done\n"
                "EOF\n"
            )
            cmd += "\n" + ansdl_only_content
            cmd += (
                "fi; fi "
                "&& chmod a+x \"$HOME/bin/termux-url-opener\") "
                "&& rm -rf $HOME/bin/ans-dl $HOME/.local/bin/ans-dl "
                "&& if ! grep -qxF \"export PATH=\\$HOME/bin:\\$PATH\" \"$HOME/.bashrc\"; then "
                "    echo \"export PATH=\\$HOME/bin:\\$PATH\" >> \"$HOME/.bashrc\"; "
                "fi "
                "&& source \"$HOME/.bashrc\" "
                "&& clear "
                "&& ans-dl --help"
            )
            print("Upgrading ans-dl (Termux)...")
            subprocess.run(cmd, shell=True, check=False)

        else:
            # Regular Linux — apt handles all deps including python3-pil
            cmd = (
                "sudo apt update && sudo apt install -y git python3-full python3-pil "
                "&& cd \"$HOME\" "
                "&& rm -rf \"./ans-dl/\" "
                "&& git clone -b main --depth 1 " + repo + " "
                "&& mkdir -p \"$HOME/.local/bin\" "
                "&& mv \"./ans-dl/ans-dl\" \"./ans-dl/ans-dl.py\" \"$HOME/.local/bin/\" "
                "&& chmod a+x \"$HOME/.local/bin/ans-dl\" "
                "&& rm -rf \"./ans-dl/\" "
                "&& clear "
                "&& ans-dl --help"
            )
            print("Upgrading ans-dl (Linux)...")
            subprocess.run(cmd, shell=True, check=False)

    else:
        print("Upgrading ans-dl...")
        print()
        print("Manual upgrade: clone the repo and install platform deps.")
        print("Repo: " + repo)
        print()


def main() -> None:
    signal.signal(signal.SIGINT, _sigint_handler)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Help flag before anything else
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        sys.exit(0)

    # Upgrade flag
    if "-u" in sys.argv[1:] or "up" in sys.argv[1:] or "upgrade" in sys.argv[1:]:
        _do_upgrade()
        sys.exit(0)

    # Parse optional flags
    parallel = 4   # default: 4 chapters in parallel for multi-chapter downloads
    args = list(sys.argv[1:])
    if "-p" in args or "--parallel" in args:
        flag = "-p" if "-p" in args else "--parallel"
        idx = args.index(flag)
        try:
            parallel = int(args[idx + 1])
        except (IndexError, ValueError):
            print(f"Error: {flag} requires a number (e.g. {flag} 4)", file=sys.stderr)
            sys.exit(1)
        args.pop(idx)       # remove flag
        args.pop(idx)       # remove the number

    if not args:
        print(__doc__)
        sys.exit(1)

    url = args[0]

    # Parse URL early so we can derive a slug for the default output dir
    try:
        info = parse_url(url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_base = (
        Path(args[1]) if len(args) > 1
        else _default_output_dir()
    )

    if info["is_chapter"]:
        # Single chapter download (always sequential, parallel flag ignored)
        result = download_chapter(url, output_base)
        if result["failed"]:
            sys.exit(1)
    else:
        # Details page — discover and download all chapters
        result = download_all_chapters(url, output_base, delay=2.0, jobs=parallel)
        if result["failed"] and not _cancelled:
            sys.exit(1)

    if not _cancelled:
        print(f"\nAll done. Files saved under: {output_base}/")


if __name__ == "__main__":
    main()
