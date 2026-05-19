"""Discover images under a local path or HTTP(S) directory listing (best-effort)."""

from __future__ import annotations

import mimetypes
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse

import httpx

from experiments.ui_state_extraction.config import ALLOWED_IMAGE_EXTENSIONS


class ImageDiscoveryError(RuntimeError):
    """Raised when the image root cannot be read or listing is unusable."""


_ALLOWED = tuple(e.lower() for e in ALLOWED_IMAGE_EXTENSIONS)
_IMAGE_CT_PREFIX = "image/"


def _norm_ext(path: str) -> str:
    lower = path.lower()
    for ext in _ALLOWED:
        if lower.endswith(ext):
            return ext
    return ""


def _skip_dir_name(name: str) -> bool:
    return name.startswith(".") or name == "__pycache__"


def _skip_file_name(name: str) -> bool:
    if name.startswith("."):
        return True
    lower = name.lower()
    return lower in {"thumbs.db", ".ds_store"}


def _local_discover(root: Path, allowed: Iterable[str]) -> list[dict]:
    allowed_set = {e.lower() for e in allowed}
    root = root.resolve()
    if not root.exists():
        raise ImageDiscoveryError(f"Local path does not exist: {root}")
    if not root.is_dir():
        raise ImageDiscoveryError(f"Local path is not a directory: {root}")

    records: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if not _skip_dir_name(d)]
        for fn in filenames:
            if _skip_file_name(fn):
                continue
            p = Path(dirpath) / fn
            ext = p.suffix.lower()
            if ext not in allowed_set:
                continue
            rel = p.relative_to(root).as_posix()
            records.append(
                {
                    "image_source_path": str(p.resolve()),
                    "relative_path": rel,
                    "filename": fn,
                    "stem": p.stem,
                    "extension": ext,
                }
            )
    records.sort(key=lambda r: r["relative_path"])
    return records


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.hrefs.append(v)
                return


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _http_fetch(client: httpx.Client, url: str) -> httpx.Response:
    try:
        r = client.get(url, follow_redirects=True, timeout=60.0)
    except httpx.RequestError as e:
        raise ImageDiscoveryError(f"HTTP request failed for {url!r}: {e}") from e
    return r


def _http_single_image(url: str, content_type: str | None) -> list[dict]:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    ext = _norm_ext(path)
    if ext:
        filename = path.rsplit("/", 1)[-1]
        stem = filename[: -len(ext)] if ext else filename
        rel = filename
        return [
            {
                "image_source_path": url,
                "relative_path": rel,
                "filename": filename,
                "stem": stem,
                "extension": ext,
            }
        ]
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct.startswith(_IMAGE_CT_PREFIX):
        filename = path.rsplit("/", 1)[-1] or "image"
        guessed_ext = mimetypes.guess_extension(ct) or ".png"
        if guessed_ext == ".jpe":
            guessed_ext = ".jpg"
        if guessed_ext not in _ALLOWED:
            guessed_ext = ".png"
        stem = Path(filename).stem
        rel = f"{stem}{guessed_ext}"
        return [
            {
                "image_source_path": url,
                "relative_path": rel,
                "filename": rel,
                "stem": stem,
                "extension": guessed_ext,
            }
        ]
    raise ImageDiscoveryError(
        f"URL does not look like an image (path extension and Content-Type inconclusive): {url!r}"
    )


def _http_crawl_directory(root_url: str, allowed: Iterable[str]) -> list[dict]:
    allowed_set = {e.lower() for e in allowed}
    base_parsed = urlparse(root_url)
    if base_parsed.scheme not in {"http", "https"}:
        raise ImageDiscoveryError(f"Unsupported URL scheme: {base_parsed.scheme!r}")

    if not root_url.endswith("/"):
        with httpx.Client() as client:
            r = _http_fetch(client, root_url)
            ct = (r.headers.get("content-type") or "").lower()
            final_url = str(r.url)
            path = unquote(urlparse(final_url).path)
            ext = _norm_ext(path)
            body_hint = ct.split(";")[0].strip().startswith(_IMAGE_CT_PREFIX)
            if ext or body_hint:
                return _http_single_image(final_url, r.headers.get("content-type"))
        root_url = root_url + "/"

    base_parsed = urlparse(root_url)
    root_path = unquote(base_parsed.path)
    if not root_path.endswith("/"):
        root_path += "/"

    records: list[dict] = []
    visited_dirs: set[str] = set()
    queue: list[str] = [root_url]

    with httpx.Client() as client:
        while queue:
            dir_url = queue.pop(0)
            if dir_url in visited_dirs:
                continue
            visited_dirs.add(dir_url)

            r = _http_fetch(client, dir_url)
            if r.status_code >= 400:
                raise ImageDiscoveryError(
                    f"Directory listing HTTP {r.status_code} for {dir_url!r}: {r.text[:200]!r}"
                )
            ctype = r.headers.get("content-type", "").lower()
            if "text/html" not in ctype and "html" not in ctype:
                if len(visited_dirs) == 1:
                    raise ImageDiscoveryError(
                        f"Expected HTML directory listing at {dir_url!r}, got Content-Type {ctype!r}. "
                        "Cannot crawl this URL as a folder."
                    )
                continue

            collector = _HrefCollector()
            try:
                collector.feed(r.text)
            except Exception as e:
                raise ImageDiscoveryError(
                    f"Failed to parse HTML listing from {dir_url!r}: {e}"
                ) from e

            found_any = False
            for href in collector.hrefs:
                if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                    continue
                abs_url = urljoin(dir_url, href)
                if not _same_origin(root_url, abs_url):
                    continue
                parsed_h = urlparse(abs_url)
                path_h = unquote(parsed_h.path)
                name = path_h.rstrip("/").rsplit("/", 1)[-1]
                if name in {".", ""} or path_h.endswith("/.."):
                    continue

                if path_h.endswith("/"):
                    if abs_url not in visited_dirs:
                        found_any = True
                        queue.append(abs_url)
                    continue

                ext = _norm_ext(path_h)
                if ext and ext in allowed_set:
                    found_any = True
                    rel = path_h
                    if rel.startswith(root_path):
                        rel = rel[len(root_path) :].lstrip("/")
                    else:
                        rel = path_h.rsplit("/", 1)[-1]
                    filename = path_h.rsplit("/", 1)[-1]
                    stem = filename[: -len(ext)] if ext else filename
                    records.append(
                        {
                            "image_source_path": abs_url,
                            "relative_path": rel.replace("\\", "/"),
                            "filename": filename,
                            "stem": stem,
                            "extension": ext,
                        }
                    )

            if len(visited_dirs) == 1 and not found_any and not records:
                raise ImageDiscoveryError(
                    f"No crawlable links found under {dir_url!r}. "
                    "Server may not expose directory listings, or HTML format is unsupported."
                )

    by_url = {r["image_source_path"]: r for r in records}
    records = list(by_url.values())
    records.sort(key=lambda r: r["relative_path"])
    return records


def discover_images(root_url_or_path: str, allowed_extensions: list[str] | None = None) -> list[dict]:
    allowed = tuple(allowed_extensions or ALLOWED_IMAGE_EXTENSIONS)
    root = root_url_or_path.strip()
    if not root:
        raise ImageDiscoveryError("IMAGE_ROOT_URL_OR_PATH is empty; set it in config.py.")

    lower = root.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return _http_crawl_directory(root, allowed)

    return _local_discover(Path(root), allowed)
