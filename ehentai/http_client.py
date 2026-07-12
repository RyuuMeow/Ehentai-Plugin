from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cli_downloader.core.errors import AdapterResolutionError


API_URL = "https://api.e-hentai.org/api.php"
DEFAULT_USER_AGENT = "CLI-Downloader/0.1"


@dataclass(frozen=True)
class EHentaiHttpOptions:
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = 30.0
    retry_attempts: int = 2
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.user_agent, str) or not self.user_agent.strip():
            raise AdapterResolutionError("E-Hentai HTTP option user_agent must be non-empty text")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise AdapterResolutionError("E-Hentai HTTP option timeout_seconds must be positive")
        if (
            isinstance(self.retry_attempts, bool)
            or not isinstance(self.retry_attempts, int)
            or self.retry_attempts < 0
        ):
            raise AdapterResolutionError("E-Hentai HTTP option retry_attempts must be non-negative")
        _validate_text_mapping(self.headers, "headers")
        _validate_text_mapping(self.cookies, "cookies")

    @classmethod
    def from_config(
        cls,
        values: Mapping[str, Any],
        *,
        secrets: Mapping[str, Any] | None = None,
    ) -> EHentaiHttpOptions:
        return cls(
            user_agent=_text_value(
                values,
                "plugins.ehentai.http.user_agent",
                legacy_key="ehentai.http.user_agent",
                default=DEFAULT_USER_AGENT,
            ),
            timeout_seconds=_float_value(
                values,
                "plugins.ehentai.http.timeout_seconds",
                legacy_key="ehentai.http.timeout_seconds",
                default=30.0,
            ),
            retry_attempts=_int_value(
                values,
                "plugins.ehentai.http.retry_attempts",
                legacy_key="ehentai.http.retry_attempts",
                default=2,
            ),
            headers={
                **_prefixed_text_map(values, "ehentai.http.headers."),
                **_prefixed_text_map(values, "plugins.ehentai.http.headers."),
            },
            cookies={
                **_prefixed_text_map(secrets or {}, "ehentai.cookies."),
                **_prefixed_text_map(secrets or {}, "ehentai.http.cookies."),
                **_prefixed_text_map(secrets or {}, "plugins.ehentai.cookies."),
            },
        )

    def request_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            **dict(self.headers),
        }
        if self.cookies:
            headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in sorted(self.cookies.items())
            )
        return headers


class EHentaiHttpTransport(Protocol):
    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]: ...

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str: ...

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes: ...


class UnavailableEHentaiHttpTransport:
    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]:
        raise AdapterResolutionError("E-Hentai live HTTP JSON transport is disabled by default.")

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str:
        raise AdapterResolutionError("E-Hentai live HTTP text transport is disabled by default.")

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes:
        raise AdapterResolutionError("E-Hentai live HTTP binary transport is disabled by default.")


class StdlibEHentaiHttpTransport:
    def __init__(self, *, opener: Any | None = None) -> None:
        self._opener = opener or urllib.request.build_opener()

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        options: EHentaiHttpOptions,
    ) -> Mapping[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        content = await self._request_bytes(
            method="POST",
            url=url,
            options=options,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            decoded = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterResolutionError(
                f"E-Hentai HTTP JSON response could not be decoded for {url}"
            ) from exc
        if not isinstance(decoded, Mapping):
            raise AdapterResolutionError(f"E-Hentai HTTP JSON response is not an object for {url}")
        return decoded

    async def get_text(self, url: str, options: EHentaiHttpOptions) -> str:
        content = await self._request_bytes(method="GET", url=url, options=options)
        return content.decode("utf-8", errors="replace")

    async def get_bytes(self, url: str, options: EHentaiHttpOptions) -> bytes:
        return await self._request_bytes(method="GET", url=url, options=options)

    async def _request_bytes(
        self,
        *,
        method: str,
        url: str,
        options: EHentaiHttpOptions,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        return await asyncio.to_thread(
            self._request_bytes_sync,
            method=method,
            url=url,
            options=options,
            body=body,
            headers=headers or {},
        )

    def _request_bytes_sync(
        self,
        *,
        method: str,
        url: str,
        options: EHentaiHttpOptions,
        body: bytes | None,
        headers: Mapping[str, str],
    ) -> bytes:
        merged_headers = {
            **options.request_headers(),
            **dict(headers),
        }

        attempts = options.retry_attempts + 1
        for attempt in range(attempts):
            request = urllib.request.Request(
                url,
                data=body,
                headers=merged_headers,
                method=method,
            )
            try:
                with self._opener.open(request, timeout=options.timeout_seconds) as response:
                    return response.read()
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                if attempt >= attempts - 1:
                    raise AdapterResolutionError(
                        f"E-Hentai HTTP {method} failed for {url}: {exc}"
                    ) from exc

        raise AdapterResolutionError(f"E-Hentai HTTP {method} failed for {url}")


class EHentaiHttpClient:
    def __init__(
        self,
        *,
        transport: EHentaiHttpTransport | None = None,
        options: EHentaiHttpOptions | None = None,
    ) -> None:
        self._transport = transport or UnavailableEHentaiHttpTransport()
        self._options = options or EHentaiHttpOptions()

    async def fetch_gallery_metadata(
        self,
        *,
        gid: int,
        token: str,
    ) -> Mapping[str, Any]:
        return await self._transport.post_json(
            API_URL,
            {
                "method": "gdata",
                "gidlist": [[gid, token]],
                "namespace": 1,
            },
            self._options,
        )

    async def fetch_gallery_page_html(
        self,
        *,
        gallery_url: str,
        page: int,
    ) -> str:
        return await self._transport.get_text(_with_page_query(gallery_url, page), self._options)

    async def fetch_torrent_page_html(self, gallery_url: str) -> str:
        return await self._transport.get_text(_with_torrent_query(gallery_url), self._options)

    async def fetch_listing_page_html(self, listing_url: str) -> str:
        return await self._transport.get_text(listing_url, self._options)

    async def fetch_image_page_html(self, image_page_url: str) -> str:
        return await self._transport.get_text(image_page_url, self._options)

    async def fetch_bytes(self, url: str) -> bytes:
        return await self._transport.get_bytes(url, self._options)


def _with_page_query(gallery_url: str, page: int) -> str:
    parts = urlsplit(gallery_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["p"] = str(page)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _with_torrent_query(gallery_url: str) -> str:
    parts = urlsplit(gallery_url)
    gallery_match = re.fullmatch(r"/g/(\d+)/([a-f0-9]+)/?", parts.path, re.IGNORECASE)
    if gallery_match is not None:
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                "/gallerytorrents.php",
                urlencode({"gid": gallery_match.group(1), "t": gallery_match.group(2)}),
                "",
            )
        )
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["t"] = "1"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _text_value(values: Mapping[str, Any], key: str, *, legacy_key: str, default: str) -> str:
    value = values.get(key, values.get(legacy_key, default))
    if not isinstance(value, str):
        raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be text")
    return value


def _float_value(values: Mapping[str, Any], key: str, *, legacy_key: str, default: float) -> float:
    value = values.get(key, values.get(legacy_key, default))
    if isinstance(value, bool):
        raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be a number") from exc


def _int_value(values: Mapping[str, Any], key: str, *, legacy_key: str, default: int) -> int:
    value = values.get(key, values.get(legacy_key, default))
    if isinstance(value, bool):
        raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be an integer") from exc


def _prefixed_text_map(values: Mapping[str, Any], prefix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        if not key.startswith(prefix):
            continue
        name = key[len(prefix) :]
        if not name:
            continue
        if not isinstance(value, str):
            raise AdapterResolutionError(f"E-Hentai HTTP option {key} must be text")
        result[name] = value
    return result


def _validate_text_mapping(values: Mapping[str, str], label: str) -> None:
    for key, value in values.items():
        if not isinstance(key, str) or not key:
            raise AdapterResolutionError(
                f"E-Hentai HTTP option {label} keys must be non-empty text"
            )
        if not isinstance(value, str):
            raise AdapterResolutionError(f"E-Hentai HTTP option {label}.{key} must be text")
