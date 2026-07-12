from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from cli_downloader.core.errors import AdapterResolutionError
from ehentai.adapter import EHentaiAdapter
from ehentai.http_client import API_URL, EHentaiHttpClient, EHentaiHttpOptions


SAMPLE_EHENTAI_GALLERY_URL = "https://e-hentai.org/g/123/abcdef/"


def build_offline_ehentai_adapter() -> EHentaiAdapter:
    client = EHentaiHttpClient(transport=StaticEHentaiHttpTransport())
    return EHentaiAdapter(
        metadata_client=client,
        gallery_page_client=client,
    )


class StaticEHentaiHttpTransport:
    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]:
        if url != API_URL:
            raise AdapterResolutionError(f"Unexpected offline E-Hentai API URL: {url}")

        gid, token = _gid_token_from_payload(payload)
        return {
            "gmetadata": [
                {
                    "gid": str(gid),
                    "token": token,
                    "title": "Offline EHentai Sample",
                    "title_jpn": "Offline EHentai Sample JP",
                    "category": "Manga",
                    "uploader": "cli-downloader-fixture",
                    "tags": ["artist:sample", "language:translated", "misc:offline"],
                    "filecount": "2",
                    "filesize": "4 MiB",
                    "posted": "1710000000",
                    "rating": "4.5",
                    "torrentcount": "0",
                    "thumb": "https://ehgt.org/offline/thumb.jpg",
                }
            ]
        }

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str:
        page = _page_from_url(url)
        if page != 0:
            return '<div id="gdt"></div>'

        gid = _gid_from_gallery_url(url)
        return f"""
        <div id="gdt">
          <a href="/s/OfflinePageA/{gid}-1"><div title="Page 1: 001.jpg"></div></a>
          <a href="/s/OfflinePageB/{gid}-2"><div title="Page 2: 002.png"></div></a>
        </div>
        """

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes:
        return f"offline bytes for {url}".encode("utf-8")


def _gid_token_from_payload(payload: Mapping[str, object]) -> tuple[int, str]:
    gidlist = payload.get("gidlist")
    if not isinstance(gidlist, list) or not gidlist:
        raise AdapterResolutionError("Offline E-Hentai metadata payload is missing gidlist")

    first = gidlist[0]
    if not isinstance(first, list) or len(first) < 2:
        raise AdapterResolutionError("Offline E-Hentai metadata payload gidlist is invalid")

    try:
        gid = int(first[0])
    except (TypeError, ValueError) as exc:
        raise AdapterResolutionError("Offline E-Hentai metadata payload gid is invalid") from exc

    token = str(first[1])
    if not token:
        raise AdapterResolutionError("Offline E-Hentai metadata payload token is invalid")
    return gid, token


def _page_from_url(url: str) -> int:
    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    try:
        return int(query.get("p", "0"))
    except ValueError:
        return 0


def _gid_from_gallery_url(url: str) -> int:
    path_parts = [part for part in urlsplit(url).path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "g":
        try:
            return int(path_parts[1])
        except ValueError:
            pass
    return 123
