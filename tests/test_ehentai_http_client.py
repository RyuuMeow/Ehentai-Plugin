import asyncio
from typing import Any, Mapping
import urllib.error
from unittest import TestCase

from cli_downloader.core.errors import AdapterResolutionError
from ehentai.http_client import (
    API_URL,
    EHentaiHttpClient,
    EHentaiHttpOptions,
    StdlibEHentaiHttpTransport,
)


class FakeHttpTransport:
    def __init__(
        self,
        *,
        json_response: Mapping[str, Any] | None = None,
        text_response: str = "",
        bytes_response: bytes = b"",
    ) -> None:
        self.json_response = json_response or {}
        self.text_response = text_response
        self.bytes_response = bytes_response
        self.post_json_requests: list[tuple[str, Mapping[str, object]]] = []
        self.get_text_requests: list[str] = []
        self.get_bytes_requests: list[str] = []
        self.options: list[EHentaiHttpOptions] = []

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]:
        self.post_json_requests.append((url, payload))
        self.options.append(options)
        return self.json_response

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str:
        self.get_text_requests.append(url)
        self.options.append(options)
        return self.text_response

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes:
        self.get_bytes_requests.append(url)
        self.options.append(options)
        return self.bytes_response


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self._content


class FakeOpener:
    def __init__(self, responses: list[bytes | BaseException]) -> None:
        self.responses = responses
        self.requests: list[tuple[Any, float]] = []

    def open(self, request: Any, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)


class EHentaiHttpClientTest(TestCase):
    def test_fetch_gallery_metadata_posts_gdata_payload(self) -> None:
        transport = FakeHttpTransport(json_response={"gmetadata": []})
        client = EHentaiHttpClient(transport=transport)

        payload = asyncio.run(client.fetch_gallery_metadata(gid=123, token="abcdef"))

        self.assertEqual(payload, {"gmetadata": []})
        self.assertEqual(
            transport.post_json_requests,
            [
                (
                    API_URL,
                    {
                        "method": "gdata",
                        "gidlist": [[123, "abcdef"]],
                        "namespace": 1,
                    },
                )
            ],
        )

    def test_fetch_gallery_metadata_passes_http_options_to_transport(self) -> None:
        transport = FakeHttpTransport(json_response={"gmetadata": []})
        options = EHentaiHttpOptions(
            user_agent="Custom Agent",
            timeout_seconds=12.5,
            retry_attempts=4,
            headers={"Accept-Language": "en-US"},
            cookies={"ipb_member_id": "123", "ipb_pass_hash": "secret"},
        )
        client = EHentaiHttpClient(transport=transport, options=options)

        asyncio.run(client.fetch_gallery_metadata(gid=123, token="abcdef"))

        self.assertEqual(transport.options, [options])
        self.assertEqual(
            transport.options[0].request_headers(),
            {
                "User-Agent": "Custom Agent",
                "Accept-Language": "en-US",
                "Cookie": "ipb_member_id=123; ipb_pass_hash=secret",
            },
        )

    def test_http_options_can_be_built_from_config_and_secrets(self) -> None:
        options = EHentaiHttpOptions.from_config(
            {
                "plugins.ehentai.http.user_agent": "Config Agent",
                "plugins.ehentai.http.timeout_seconds": 45,
                "plugins.ehentai.http.retry_attempts": 3,
                "plugins.ehentai.http.headers.Accept-Language": "ja-JP",
            },
            secrets={
                "plugins.ehentai.cookies.ipb_member_id": "123",
                "plugins.ehentai.cookies.ipb_pass_hash": "secret",
            },
        )

        self.assertEqual(options.user_agent, "Config Agent")
        self.assertEqual(options.timeout_seconds, 45.0)
        self.assertEqual(options.retry_attempts, 3)
        self.assertEqual(options.headers, {"Accept-Language": "ja-JP"})
        self.assertEqual(
            options.request_headers()["Cookie"],
            "ipb_member_id=123; ipb_pass_hash=secret",
        )

    def test_http_options_reject_invalid_direct_values(self) -> None:
        with self.assertRaises(AdapterResolutionError):
            EHentaiHttpOptions(timeout_seconds=0)

        with self.assertRaises(AdapterResolutionError):
            EHentaiHttpOptions(retry_attempts=-1)

        with self.assertRaises(AdapterResolutionError):
            EHentaiHttpOptions(headers={"Accept-Language": 123})  # type: ignore[dict-item]

    def test_fetch_gallery_page_html_adds_page_query(self) -> None:
        transport = FakeHttpTransport(text_response="<div id='gdt'></div>")
        client = EHentaiHttpClient(transport=transport)

        html = asyncio.run(
            client.fetch_gallery_page_html(
                gallery_url="https://e-hentai.org/g/123/abcdef/",
                page=2,
            )
        )

        self.assertEqual(html, "<div id='gdt'></div>")
        self.assertEqual(
            transport.get_text_requests,
            ["https://e-hentai.org/g/123/abcdef/?p=2"],
        )

    def test_fetch_gallery_page_html_replaces_existing_page_query(self) -> None:
        transport = FakeHttpTransport(text_response="<div id='gdt'></div>")
        client = EHentaiHttpClient(transport=transport)

        asyncio.run(
            client.fetch_gallery_page_html(
                gallery_url="https://e-hentai.org/g/123/abcdef/?inline_set=dm_l&p=0",
                page=3,
            )
        )

        self.assertEqual(
            transport.get_text_requests,
            ["https://e-hentai.org/g/123/abcdef/?inline_set=dm_l&p=3"],
        )

    def test_fetch_torrent_page_html_uses_gallery_torrent_endpoint(self) -> None:
        transport = FakeHttpTransport(text_response="<table></table>")
        client = EHentaiHttpClient(transport=transport)

        html = asyncio.run(
            client.fetch_torrent_page_html("https://e-hentai.org/g/123/abcdef/?inline_set=dm_l")
        )

        self.assertEqual(html, "<table></table>")
        self.assertEqual(
            transport.get_text_requests,
            ["https://e-hentai.org/gallerytorrents.php?gid=123&t=abcdef"],
        )

    def test_fetch_image_page_html_gets_image_page_url(self) -> None:
        transport = FakeHttpTransport(text_response="<img id='img'>")
        client = EHentaiHttpClient(transport=transport)

        html = asyncio.run(client.fetch_image_page_html("https://e-hentai.org/s/PageTokenA/123-1"))

        self.assertEqual(html, "<img id='img'>")
        self.assertEqual(transport.get_text_requests, ["https://e-hentai.org/s/PageTokenA/123-1"])

    def test_fetch_bytes_gets_binary_url(self) -> None:
        transport = FakeHttpTransport(bytes_response=b"image-bytes")
        client = EHentaiHttpClient(transport=transport)

        content = asyncio.run(client.fetch_bytes("https://ehgt.org/fullimg/001.jpg"))

        self.assertEqual(content, b"image-bytes")
        self.assertEqual(transport.get_bytes_requests, ["https://ehgt.org/fullimg/001.jpg"])

    def test_default_transport_does_not_perform_live_fetching(self) -> None:
        client = EHentaiHttpClient()

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(client.fetch_gallery_metadata(gid=123, token="abcdef"))


class StdlibEHentaiHttpTransportTest(TestCase):
    def test_post_json_sends_payload_headers_and_timeout(self) -> None:
        opener = FakeOpener([b'{"gmetadata": []}'])
        transport = StdlibEHentaiHttpTransport(opener=opener)
        options = EHentaiHttpOptions(
            user_agent="Test Agent",
            timeout_seconds=9.5,
            headers={"Accept-Language": "en-US"},
            cookies={"ipb_member_id": "123"},
        )

        payload = asyncio.run(
            transport.post_json(
                API_URL,
                {"method": "gdata"},
                options,
            )
        )

        request, timeout = opener.requests[0]
        headers = _request_headers(request)
        self.assertEqual(payload, {"gmetadata": []})
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.data, b'{"method": "gdata"}')
        self.assertEqual(timeout, 9.5)
        self.assertEqual(headers["user-agent"], "Test Agent")
        self.assertEqual(headers["accept-language"], "en-US")
        self.assertEqual(headers["cookie"], "ipb_member_id=123")
        self.assertEqual(headers["content-type"], "application/json")

    def test_get_text_decodes_utf8_response(self) -> None:
        opener = FakeOpener(["gallery page".encode("utf-8")])
        transport = StdlibEHentaiHttpTransport(opener=opener)

        content = asyncio.run(
            transport.get_text(
                "https://e-hentai.org/g/123/abcdef/",
                EHentaiHttpOptions(),
            )
        )

        self.assertEqual(content, "gallery page")
        self.assertEqual(opener.requests[0][0].get_method(), "GET")

    def test_get_bytes_returns_binary_response(self) -> None:
        opener = FakeOpener([b"image-bytes"])
        transport = StdlibEHentaiHttpTransport(opener=opener)

        content = asyncio.run(
            transport.get_bytes(
                "https://ehgt.org/fullimg/001.jpg",
                EHentaiHttpOptions(),
            )
        )

        self.assertEqual(content, b"image-bytes")

    def test_transport_retries_transient_open_errors(self) -> None:
        opener = FakeOpener([urllib.error.URLError("temporary"), b"ok"])
        transport = StdlibEHentaiHttpTransport(opener=opener)

        content = asyncio.run(
            transport.get_bytes(
                "https://ehgt.org/fullimg/001.jpg",
                EHentaiHttpOptions(retry_attempts=1),
            )
        )

        self.assertEqual(content, b"ok")
        self.assertEqual(len(opener.requests), 2)

    def test_transport_wraps_failed_requests(self) -> None:
        opener = FakeOpener([urllib.error.URLError("no route")])
        transport = StdlibEHentaiHttpTransport(opener=opener)

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(
                transport.get_text(
                    "https://e-hentai.org/g/123/abcdef/",
                    EHentaiHttpOptions(retry_attempts=0),
                )
            )

    def test_post_json_rejects_non_json_response(self) -> None:
        opener = FakeOpener([b"not json"])
        transport = StdlibEHentaiHttpTransport(opener=opener)

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(transport.post_json(API_URL, {"method": "gdata"}, EHentaiHttpOptions()))


def _request_headers(request: Any) -> dict[str, str]:
    return {key.lower(): value for key, value in request.header_items()}
