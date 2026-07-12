from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import unquote, urljoin, urlparse

from cli_downloader.core.errors import AdapterResolutionError
from ehentai.urls import EHentaiSite, build_gallery_url


class EHentaiParseError(AdapterResolutionError):
    """Raised when E-Hentai data cannot be parsed into site models."""


@dataclass(frozen=True)
class EHentaiTag:
    namespace: str
    value: str


@dataclass(frozen=True)
class EHentaiGalleryMetadata:
    gid: int
    token: str
    site: EHentaiSite
    url: str
    title: str = ""
    title_jpn: str = ""
    category: str = ""
    uploader: str = ""
    tags: tuple[EHentaiTag, ...] = ()
    file_count: int = 0
    filesize: str = ""
    posted: str = ""
    rating: float = 0.0
    torrent_count: int = 0
    thumbnail_url: str = ""


@dataclass(frozen=True)
class EHentaiGalleryImage:
    index: int
    page_url: str
    filename: str | None = None


@dataclass(frozen=True)
class EHentaiResolvedImage:
    image_url: str
    filename: str


@dataclass(frozen=True)
class EHentaiTorrentCandidate:
    url: str
    title: str
    size: str = ""
    seeds: int = 0
    peers: int = 0
    downloads: int = 0


@dataclass(frozen=True)
class EHentaiListingCandidate:
    gid: int
    token: str
    url: str
    title: str
    thumbnail_url: str = ""
    summary: str = ""


@dataclass(frozen=True)
class EHentaiListingPage:
    candidates: tuple[EHentaiListingCandidate, ...]
    next_url: str | None = None
    prev_url: str | None = None


def parse_gallery_metadata_response(
    payload: Mapping[str, Any],
    *,
    site: EHentaiSite,
) -> EHentaiGalleryMetadata:
    gmetadata = payload.get("gmetadata")
    if not isinstance(gmetadata, list) or not gmetadata:
        raise EHentaiParseError("No metadata returned for gallery")

    meta = gmetadata[0]
    if not isinstance(meta, Mapping):
        raise EHentaiParseError("Gallery metadata entry is not an object")
    if "error" in meta:
        raise EHentaiParseError(f"API error: {meta['error']}")

    gid = _required_int(meta, "gid")
    token = _required_text(meta, "token")

    return EHentaiGalleryMetadata(
        gid=gid,
        token=token,
        site=site,
        url=build_gallery_url(gid, token, site),
        title=_optional_text(meta, "title"),
        title_jpn=_optional_text(meta, "title_jpn"),
        category=_optional_text(meta, "category"),
        uploader=_optional_text(meta, "uploader"),
        tags=_parse_tags(meta.get("tags", ())),
        file_count=_optional_int(meta, "filecount"),
        filesize=_optional_text(meta, "filesize"),
        posted=_optional_text(meta, "posted"),
        rating=_optional_float(meta, "rating"),
        torrent_count=_optional_int(meta, "torrentcount"),
        thumbnail_url=_optional_text(meta, "thumb"),
    )


def parse_gallery_image_list_html(
    html: str,
    *,
    base_url: str = "",
    limit: int | None = None,
) -> tuple[EHentaiGalleryImage, ...]:
    parser = _GalleryImageListParser(base_url=base_url)
    parser.feed(html)
    parser.close()

    if not parser.saw_gallery_container:
        raise EHentaiParseError("Gallery image list is missing #gdt thumbnail container")

    images = parser.images
    if limit is not None:
        images = images[:limit]
    return tuple(
        EHentaiGalleryImage(index=index + 1, page_url=image.page_url, filename=image.filename)
        for index, image in enumerate(images)
    )


def parse_image_page_html(
    html: str,
    *,
    fallback_filename: str | None = None,
    index: int | None = None,
) -> EHentaiResolvedImage:
    parser = _ImagePageParser()
    parser.feed(html)
    parser.close()

    if not parser.image_url:
        raise EHentaiParseError("Image page is missing #img source")

    filename = (
        parser.filename_from_info or fallback_filename or _filename_from_url(parser.image_url)
    )
    if not filename and index is not None:
        filename = f"{index:04d}.jpg"
    if not filename:
        raise EHentaiParseError("Image page filename could not be resolved")

    return EHentaiResolvedImage(
        image_url=parser.image_url,
        filename=filename,
    )


def parse_torrent_candidates_html(
    html: str,
    *,
    base_url: str = "",
) -> tuple[EHentaiTorrentCandidate, ...]:
    parser = _TorrentCandidateParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return tuple(parser.candidates)


def parse_listing_page_html(
    html: str,
    *,
    base_url: str = "",
) -> EHentaiListingPage:
    parser = _ListingPageParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return EHentaiListingPage(
        candidates=tuple(parser.candidates),
        next_url=parser.next_url,
        prev_url=parser.prev_url,
    )


def _parse_tags(value: Any) -> tuple[EHentaiTag, ...]:
    if not isinstance(value, list):
        return ()

    tags: list[EHentaiTag] = []
    for raw_tag in value:
        if not isinstance(raw_tag, str) or not raw_tag:
            continue
        if ":" in raw_tag:
            namespace, tag_value = raw_tag.split(":", 1)
        else:
            namespace, tag_value = "misc", raw_tag
        tags.append(EHentaiTag(namespace=namespace, value=tag_value))
    return tuple(tags)


def _required_int(meta: Mapping[str, Any], key: str) -> int:
    if key not in meta:
        raise EHentaiParseError(f"Gallery metadata is missing {key}")
    return _coerce_int(meta[key], key)


def _optional_int(meta: Mapping[str, Any], key: str) -> int:
    value = meta.get(key, 0)
    if value in ("", None):
        return 0
    return _coerce_int(value, key)


def _coerce_int(value: Any, key: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise EHentaiParseError(f"Gallery metadata field {key} is not an integer") from exc


def _optional_float(meta: Mapping[str, Any], key: str) -> float:
    value = meta.get(key, 0)
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise EHentaiParseError(f"Gallery metadata field {key} is not a number") from exc


def _required_text(meta: Mapping[str, Any], key: str) -> str:
    value = _optional_text(meta, key)
    if not value:
        raise EHentaiParseError(f"Gallery metadata is missing {key}")
    return value


def _optional_text(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key, "")
    if value is None:
        return ""
    return str(value)


@dataclass(frozen=True)
class _ParsedGalleryImage:
    page_url: str
    filename: str | None = None


class _GalleryImageListParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._inside_gallery_container = 0
        self._inside_image_anchor = 0
        self._current_page_url = ""
        self._current_filename: str | None = None
        self.saw_gallery_container = False
        self.images: list[_ParsedGalleryImage] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}

        if self._inside_gallery_container:
            self._inside_gallery_container += 1
        if attr_map.get("id") == "gdt":
            self.saw_gallery_container = True
            self._inside_gallery_container = 1

        if not self._inside_gallery_container:
            return

        if tag == "a" and not self._inside_image_anchor:
            href = attr_map.get("href", "")
            if "/s/" in href:
                self._inside_image_anchor = 1
                self._current_page_url = urljoin(self._base_url, href)
                self._current_filename = None
            return

        if self._inside_image_anchor:
            self._inside_image_anchor += 1
            title = attr_map.get("title", "")
            if title.lower().startswith("page ") and ":" in title:
                self._current_filename = title.split(":", 1)[1].strip() or None

    def handle_endtag(self, tag: str) -> None:
        if self._inside_image_anchor:
            self._inside_image_anchor -= 1
            if self._inside_image_anchor == 0 and self._current_page_url:
                self.images.append(
                    _ParsedGalleryImage(
                        page_url=self._current_page_url,
                        filename=self._current_filename,
                    )
                )
                self._current_page_url = ""
                self._current_filename = None

        if self._inside_gallery_container:
            self._inside_gallery_container -= 1


class _ImagePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image_url = ""
        self.filename_from_info: str | None = None
        self._inside_image_info = 0
        self._image_info_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}

        if self._inside_image_info:
            self._inside_image_info += 1

        element_id = attr_map.get("id")
        if tag == "img" and element_id == "img" and attr_map.get("src"):
            self.image_url = attr_map["src"]
        if element_id == "i4":
            self._inside_image_info = 1
            self._image_info_text = []

    def handle_data(self, data: str) -> None:
        if self._inside_image_info:
            self._image_info_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._inside_image_info:
            return

        self._inside_image_info -= 1
        if self._inside_image_info == 0:
            filename = _filename_from_image_info("".join(self._image_info_text))
            self.filename_from_info = filename or self.filename_from_info
            self._image_info_text = []


def _filename_from_image_info(text: str) -> str:
    filename = text.split("::", 1)[0].strip()
    return filename


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    filename = unquote(path.rsplit("/", 1)[-1])
    return filename


class _TorrentCandidateParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._inside_row = 0
        self._inside_torrent_anchor = 0
        self._current_url = ""
        self._anchor_text: list[str] = []
        self._row_text: list[str] = []
        self.candidates: list[EHentaiTorrentCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "tr":
            self._inside_row = 1
            self._current_url = ""
            self._anchor_text = []
            self._row_text = []
            return

        if self._inside_row:
            self._inside_row += 1

        href = attr_map.get("href", "")
        if tag == "a" and _looks_like_torrent_url(href):
            self._inside_torrent_anchor = 1
            self._current_url = urljoin(self._base_url, href)
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._inside_row:
            self._row_text.append(data)
        if self._inside_torrent_anchor:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._inside_torrent_anchor:
            self._inside_torrent_anchor -= 1

        if not self._inside_row:
            return

        self._inside_row -= 1
        if self._inside_row == 0 and self._current_url:
            row_text = _normalize_space(" ".join(self._row_text))
            title = _normalize_space(" ".join(self._anchor_text)) or _filename_from_url(
                self._current_url
            )
            self.candidates.append(
                EHentaiTorrentCandidate(
                    url=self._current_url,
                    title=title,
                    size=_parse_size(row_text),
                    seeds=_parse_labeled_int(row_text, ("seed", "seeds", "seeders")),
                    peers=_parse_labeled_int(row_text, ("peer", "peers", "leech", "leeches")),
                    downloads=_parse_labeled_int(row_text, ("download", "downloads", "completed")),
                )
            )


def _looks_like_torrent_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    host = parsed.netloc.lower().split(":", 1)[0]
    return (
        "/torrent/" in path
        or "torrentid=" in query
        or path.endswith(".torrent")
        or (host == "ehtracker.org" and path.startswith("/t/"))
    )


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _parse_size(text: str) -> str:
    match = re.search(r"\b\d+(?:\.\d+)?\s*(?:B|KiB|MiB|GiB|TiB|KB|MB|GB|TB)\b", text, re.IGNORECASE)
    return match.group(0) if match else ""


def _parse_labeled_int(text: str, labels: tuple[str, ...]) -> int:
    for label in labels:
        match = re.search(rf"\b{re.escape(label)}\s*:?\s*(\d+)\b", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


@dataclass(frozen=True)
class _ListingLink:
    url: str
    title: str
    thumbnail_url: str = ""


class _ListingPageParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._inside_row = 0
        self._inside_gallery_anchor = 0
        self._current_url = ""
        self._current_title_attr = ""
        self._current_thumbnail_url = ""
        self._current_anchor_text: list[str] = []
        self._row_text: list[str] = []
        self._row_links: list[_ListingLink] = []
        self._seen_urls: set[str] = set()
        self.candidates: list[EHentaiListingCandidate] = []
        self.next_url: str | None = None
        self.prev_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href", "")

        if tag == "a" and attr_map.get("id") == "dnext" and href:
            self.next_url = urljoin(self._base_url, href)
        elif tag == "a" and attr_map.get("id") == "dprev" and href:
            self.prev_url = urljoin(self._base_url, href)

        if tag == "tr":
            self._inside_row = 1
            self._row_text = []
            self._row_links = []
        elif self._inside_row:
            self._inside_row += 1

        if tag == "a" and _gallery_url_parts(href) is not None:
            self._inside_gallery_anchor = 1
            self._current_url = urljoin(self._base_url, href)
            self._current_title_attr = attr_map.get("title", "")
            self._current_thumbnail_url = ""
            self._current_anchor_text = []
            return

        if self._inside_gallery_anchor:
            self._inside_gallery_anchor += 1
            if tag == "img":
                self._current_thumbnail_url = (
                    attr_map.get("data-src") or attr_map.get("src") or self._current_thumbnail_url
                )
                if not self._current_title_attr:
                    self._current_title_attr = attr_map.get("title", "") or attr_map.get("alt", "")

    def handle_data(self, data: str) -> None:
        if self._inside_row:
            self._row_text.append(data)
        if self._inside_gallery_anchor:
            self._current_anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._inside_gallery_anchor:
            self._inside_gallery_anchor -= 1
            if self._inside_gallery_anchor == 0 and self._current_url:
                title = _normalize_space(" ".join(self._current_anchor_text))
                thumbnail_url = (
                    urljoin(self._base_url, self._current_thumbnail_url)
                    if self._current_thumbnail_url
                    else ""
                )
                self._row_links.append(
                    _ListingLink(
                        url=self._current_url,
                        title=title or _normalize_space(self._current_title_attr),
                        thumbnail_url=thumbnail_url,
                    )
                )
                self._current_url = ""
                self._current_title_attr = ""
                self._current_thumbnail_url = ""
                self._current_anchor_text = []

        if not self._inside_row:
            return

        self._inside_row -= 1
        if self._inside_row == 0:
            self._flush_row()

    def close(self) -> None:
        if self._row_links:
            self._flush_row()
        super().close()

    def _flush_row(self) -> None:
        summary = _normalize_space(" ".join(self._row_text))
        links_by_url: dict[str, _ListingLink] = {}
        for link in self._row_links:
            previous = links_by_url.get(link.url)
            links_by_url[link.url] = _ListingLink(
                url=link.url,
                title=link.title or (previous.title if previous is not None else ""),
                thumbnail_url=link.thumbnail_url
                or (previous.thumbnail_url if previous is not None else ""),
            )
        for link in links_by_url.values():
            if link.url in self._seen_urls:
                continue
            parts = _gallery_url_parts(link.url)
            if parts is None:
                continue
            gid, token = parts
            self._seen_urls.add(link.url)
            self.candidates.append(
                EHentaiListingCandidate(
                    gid=gid,
                    token=token,
                    url=link.url,
                    title=link.title or f"Gallery #{gid}",
                    thumbnail_url=link.thumbnail_url,
                    summary=summary,
                )
            )
        self._row_text = []
        self._row_links = []


def _gallery_url_parts(url: str) -> tuple[int, str] | None:
    match = re.search(r"/g/(?P<gid>\d+)/(?P<token>[a-f0-9]+)/?", url, re.IGNORECASE)
    if match is None:
        return None
    return int(match.group("gid")), match.group("token").lower()
