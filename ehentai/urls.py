from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class EHentaiSite(StrEnum):
    E_HENTAI = "e-hentai"
    EX_HENTAI = "exhentai"


class EHentaiUrlKind(StrEnum):
    GALLERY = "gallery"
    IMAGE_PAGE = "image_page"
    LISTING = "listing"


@dataclass(frozen=True)
class EHentaiUrlInfo:
    site: EHentaiSite
    kind: EHentaiUrlKind
    original_url: str
    gid: int | None = None
    token: str | None = None
    page_token: str | None = None
    page: int | None = None
    listing_label: str | None = None


_GALLERY_URL_PATTERN = re.compile(
    r"^https?://(?P<site>e-hentai|exhentai)\.org/g/(?P<gid>\d+)/(?P<token>[a-f0-9]+)/?$",
    re.IGNORECASE,
)
_IMAGE_PAGE_URL_PATTERN = re.compile(
    r"^https?://(?P<site>e-hentai|exhentai)\.org/s/(?P<page_token>[A-Za-z0-9]+)/(?P<gid>\d+)-(?P<page>\d+)/?$",
    re.IGNORECASE,
)
_DOMAIN_URL_PATTERN = re.compile(
    r"^https?://(?P<site>e-hentai|exhentai)\.org(?P<path>.*)$",
    re.IGNORECASE,
)


def parse_ehentai_url(url: str) -> EHentaiUrlInfo | None:
    normalized = url.strip()

    gallery = _GALLERY_URL_PATTERN.match(normalized)
    if gallery:
        return EHentaiUrlInfo(
            site=_parse_site(gallery.group("site")),
            kind=EHentaiUrlKind.GALLERY,
            original_url=normalized,
            gid=int(gallery.group("gid")),
            token=gallery.group("token").lower(),
        )

    image_page = _IMAGE_PAGE_URL_PATTERN.match(normalized)
    if image_page:
        return EHentaiUrlInfo(
            site=_parse_site(image_page.group("site")),
            kind=EHentaiUrlKind.IMAGE_PAGE,
            original_url=normalized,
            gid=int(image_page.group("gid")),
            page_token=image_page.group("page_token"),
            page=int(image_page.group("page")),
        )

    domain = _DOMAIN_URL_PATTERN.match(normalized)
    if not domain:
        return None

    label = _listing_label(domain.group("path"))
    if label is None:
        return None

    return EHentaiUrlInfo(
        site=_parse_site(domain.group("site")),
        kind=EHentaiUrlKind.LISTING,
        original_url=normalized,
        listing_label=label,
    )


def build_gallery_url(gid: int, token: str, site: EHentaiSite) -> str:
    return f"{base_url(site)}/g/{gid}/{token}/"


def base_url(site: EHentaiSite) -> str:
    if site == EHentaiSite.EX_HENTAI:
        return "https://exhentai.org"
    return "https://e-hentai.org"


def _parse_site(site: str) -> EHentaiSite:
    if site.lower() == "exhentai":
        return EHentaiSite.EX_HENTAI
    return EHentaiSite.E_HENTAI


def _listing_label(path: str) -> str | None:
    if path.startswith("/g/") or path.startswith("/s/") or path.startswith("/api"):
        return None
    if path.startswith("/tag/"):
        return "tag"
    if path.startswith("/uploader/"):
        return "uploader"
    if path.startswith("/favorites"):
        return "favorites"
    if path.startswith("/watched"):
        return "watched"
    if path.startswith("/popular"):
        return "popular"
    if path.startswith("/toplists"):
        return "toplists"
    if "f_search=" in path:
        return "search"
    if path in {"", "/"} or path.startswith("/?"):
        return "search"
    return "listing"
