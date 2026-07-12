import asyncio
from unittest import TestCase

from cli_downloader.core.errors import AdapterResolutionError
from cli_downloader.core.models import Asset, AssetKind
from ehentai.fetcher import EHentaiAssetFetcher
from .ehentai_fakes import FakeBinaryClient, FakeImagePageClient


class EHentaiAssetFetcherTest(TestCase):
    def test_fetches_torrent_binary_directly(self) -> None:
        binary_client = FakeBinaryClient(b"torrent-bytes")
        fetcher = EHentaiAssetFetcher(binary_client=binary_client)
        asset = Asset(
            url="https://e-hentai.org/torrent/123/sample.torrent",
            kind=AssetKind.TORRENT,
            filename="sample.torrent",
            metadata={"asset_stage": "torrent_candidate"},
        )

        content = asyncio.run(fetcher.fetch(asset))

        self.assertEqual(content, b"torrent-bytes")
        self.assertEqual(binary_client.requests, [asset.url])

    def test_fetches_binary_content_from_resolved_image_url(self) -> None:
        image_page_client = FakeImagePageClient(
            """
            <html>
              <body>
                <img id="img" src="https://ehgt.org/fullimg/001.jpg?token=abc">
                <div id="i4">001.jpg :: 1280 x 1791 :: 332.9 KiB</div>
              </body>
            </html>
            """
        )
        binary_client = FakeBinaryClient(b"image-bytes")
        fetcher = EHentaiAssetFetcher(
            image_page_client=image_page_client,
            binary_client=binary_client,
        )
        asset = Asset(
            url="https://e-hentai.org/s/PageTokenA/123-1",
            kind=AssetKind.IMAGE,
            filename="thumbnail-name.jpg",
            metadata={
                "index": 1,
                "asset_stage": "image_page",
            },
        )

        content = asyncio.run(fetcher.fetch(asset))

        self.assertEqual(content, b"image-bytes")
        self.assertEqual(image_page_client.requests, ["https://e-hentai.org/s/PageTokenA/123-1"])
        self.assertEqual(binary_client.requests, ["https://ehgt.org/fullimg/001.jpg?token=abc"])

    def test_rejects_non_image_assets(self) -> None:
        fetcher = EHentaiAssetFetcher(
            image_page_client=FakeImagePageClient(""),
            binary_client=FakeBinaryClient(b""),
        )
        asset = Asset(
            url="https://e-hentai.org/s/PageTokenA/123-1",
            kind=AssetKind.FILE,
            metadata={"asset_stage": "image_page"},
        )

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(fetcher.fetch(asset))

    def test_rejects_image_assets_without_image_page_stage(self) -> None:
        fetcher = EHentaiAssetFetcher(
            image_page_client=FakeImagePageClient(""),
            binary_client=FakeBinaryClient(b""),
        )
        asset = Asset(
            url="https://ehgt.org/fullimg/001.jpg",
            kind=AssetKind.IMAGE,
            metadata={},
        )

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(fetcher.fetch(asset))

    def test_default_clients_do_not_perform_live_fetching(self) -> None:
        fetcher = EHentaiAssetFetcher()
        asset = Asset(
            url="https://e-hentai.org/s/PageTokenA/123-1",
            kind=AssetKind.IMAGE,
            metadata={"asset_stage": "image_page"},
        )

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(fetcher.fetch(asset))
