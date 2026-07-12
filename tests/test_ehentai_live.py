import asyncio
from pathlib import Path
from unittest import TestCase

from cli_downloader.config.loader import LoadedConfig
from cli_downloader.core.models import ResolveRequest
from ehentai.live import build_live_ehentai_components
from ehentai.http_client import API_URL
from .ehentai_fakes import FakeLiveTransport


class EHentaiLiveBuilderTest(TestCase):
    def test_builds_adapter_and_fetcher_from_configured_live_client(self) -> None:
        transport = FakeLiveTransport()
        config = LoadedConfig(
            values={
                "ehentai.http.user_agent": "Builder Agent",
                "ehentai.http.timeout_seconds": 15,
                "ehentai.http.retry_attempts": 1,
                "ehentai.http.headers.Accept-Language": "en-US",
            },
            secrets={
                "ehentai.cookies.ipb_member_id": "123",
            },
            sources=(Path("config.toml"), Path("secrets.toml")),
        )

        components = build_live_ehentai_components(
            config=config,
            transport=transport,
        )
        item = asyncio.run(
            components.adapter.resolve(ResolveRequest(url="https://e-hentai.org/g/123/abcdef/"))
        )
        plan = asyncio.run(components.adapter.choose_strategy(item))
        content = asyncio.run(components.fetcher.fetch(plan.assets.assets[0]))

        self.assertEqual(components.transport_name, "FakeLiveTransport")
        self.assertEqual(components.options.user_agent, "Builder Agent")
        self.assertEqual(components.options.timeout_seconds, 15.0)
        self.assertEqual(components.options.retry_attempts, 1)
        self.assertEqual(components.options.headers, {"Accept-Language": "en-US"})
        self.assertEqual(components.options.cookies, {"ipb_member_id": "123"})
        self.assertEqual(transport.post_json_requests[0][0], API_URL)
        self.assertEqual(transport.get_text_requests[0], "https://e-hentai.org/g/123/abcdef/?p=0")
        self.assertEqual(transport.get_text_requests[1], "https://e-hentai.org/s/PageTokenA/123-1")
        self.assertEqual(transport.get_bytes_requests, ["https://ehgt.org/fullimg/001.jpg"])
        self.assertEqual(content, b"image-bytes")
        self.assertTrue(all(option is components.options for option in transport.options))
