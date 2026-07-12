from __future__ import annotations

from typing import Any, Mapping

from ehentai.http_client import EHentaiHttpOptions


class FakeMetadataClient:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.requests: list[tuple[int, str]] = []

    async def fetch_gallery_metadata(
        self,
        *,
        gid: int,
        token: str,
    ) -> Mapping[str, Any]:
        self.requests.append((gid, token))
        return self.payload


class FakeGalleryPageClient:
    def __init__(self, pages: Mapping[int, str]) -> None:
        self.pages = pages
        self.requests: list[tuple[str, int]] = []

    async def fetch_gallery_page_html(
        self,
        *,
        gallery_url: str,
        page: int,
    ) -> str:
        self.requests.append((gallery_url, page))
        return self.pages[page]


class FakeTorrentPageClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.requests: list[str] = []

    async def fetch_torrent_page_html(self, gallery_url: str) -> str:
        self.requests.append(gallery_url)
        return self.html


class FakeListingPageClient:
    def __init__(self, pages: Mapping[str, str]) -> None:
        self.pages = pages
        self.requests: list[str] = []

    async def fetch_listing_page_html(self, listing_url: str) -> str:
        self.requests.append(listing_url)
        return self.pages[listing_url]


class FakeImagePageClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.requests: list[str] = []

    async def fetch_image_page_html(self, image_page_url: str) -> str:
        self.requests.append(image_page_url)
        return self.html


class FakeBinaryClient:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.requests: list[str] = []

    async def fetch_bytes(self, url: str) -> bytes:
        self.requests.append(url)
        return self.content


class FakeLiveTransport:
    def __init__(self) -> None:
        self.options: list[EHentaiHttpOptions] = []
        self.post_json_requests: list[tuple[str, Mapping[str, object]]] = []
        self.get_text_requests: list[str] = []
        self.get_bytes_requests: list[str] = []

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]:
        self.options.append(options)
        self.post_json_requests.append((url, payload))
        return {
            "gmetadata": [
                {
                    "gid": "123",
                    "token": "abcdef",
                    "title": "Live Builder Sample",
                    "title_jpn": "",
                    "category": "Manga",
                    "uploader": "sample",
                    "tags": ["artist:builder"],
                    "filecount": "1",
                }
            ]
        }

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str:
        self.options.append(options)
        self.get_text_requests.append(url)
        if "f_search=" in url:
            return """
            <table class="itg">
              <tr>
                <td class="glthumb"><a href="/g/123/abcdef/">
                  <img data-src="https://ehgt.org/thumb.jpg" title="Live Builder Sample">
                </a></td>
                <td><a href="/g/123/abcdef/"><div class="glink">Live Builder Sample</div></a></td>
              </tr>
            </table>
            """
        if "/s/" in url:
            return """
            <img id="img" src="https://ehgt.org/fullimg/001.jpg">
            <div id="i4">001.jpg :: 1280 x 1791 :: 332.9 KiB</div>
            """
        return """
        <div id="gdt">
          <a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>
        </div>
        """

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes:
        self.options.append(options)
        self.get_bytes_requests.append(url)
        return b"image-bytes"
