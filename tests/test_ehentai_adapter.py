import asyncio
from unittest import TestCase

from cli_downloader.core.errors import AdapterResolutionError
from cli_downloader.core.models import AssetKind, DownloadStrategy, ResolveRequest, ResolvedItem
from cli_downloader.core.operations import ListPageData, OperationRequest, ResultKind
from ehentai.adapter import EHentaiAdapter
from .ehentai_fakes import (
    FakeGalleryPageClient,
    FakeListingPageClient,
    FakeMetadataClient,
    FakeTorrentPageClient,
)


class EHentaiAdapterResolveTest(TestCase):
    def test_resolves_gallery_url_with_injected_metadata_client(self) -> None:
        client = FakeMetadataClient(
            {
                "gmetadata": [
                    {
                        "gid": "123",
                        "token": "abcdef",
                        "title": "Sample Gallery",
                        "title_jpn": "Sample Gallery JP",
                        "category": "Manga",
                        "uploader": "sample-uploader",
                        "tags": ["artist:alice", "female:maid"],
                        "filecount": "42",
                        "filesize": "120 MiB",
                        "posted": "1710000000",
                        "rating": "4.75",
                        "torrentcount": "3",
                        "thumb": "https://ehgt.org/thumb.jpg",
                    }
                ]
            }
        )
        adapter = EHentaiAdapter(metadata_client=client)

        item = asyncio.run(
            adapter.resolve(
                ResolveRequest(
                    url="https://e-hentai.org/g/123/abcdef/",
                    profile="portable",
                )
            )
        )

        self.assertEqual(client.requests, [(123, "abcdef")])
        self.assertEqual(item.site_id, "ehentai")
        self.assertEqual(item.source_url, "https://e-hentai.org/g/123/abcdef/")
        self.assertEqual(item.title, "Sample Gallery JP")
        self.assertEqual(item.tags, ("artist:alice", "female:maid"))
        self.assertEqual(item.metadata["gid"], 123)
        self.assertEqual(item.metadata["token"], "abcdef")
        self.assertEqual(item.metadata["site"], "e-hentai")
        self.assertEqual(item.metadata["file_count"], 42)
        self.assertEqual(item.metadata["torrent_count"], 3)
        self.assertEqual(item.metadata["profile"], "portable")

    def test_resolve_rejects_image_page_until_gallery_lookup_exists(self) -> None:
        adapter = EHentaiAdapter(metadata_client=FakeMetadataClient({"gmetadata": []}))

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(
                adapter.resolve(ResolveRequest(url="https://e-hentai.org/s/PageToken123/123-4"))
            )

    def test_default_metadata_client_does_not_perform_live_fetching(self) -> None:
        adapter = EHentaiAdapter()

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(adapter.resolve(ResolveRequest(url="https://e-hentai.org/g/123/abcdef/")))


class EHentaiAdapterListingTest(TestCase):
    def test_supported_listing_forms_use_the_batch_operation(self) -> None:
        html = '<a href="/g/123/abcdef/"><div class="glink">Sample Gallery</div></a>'
        urls = (
            "https://e-hentai.org/?f_search=sample",
            "https://e-hentai.org/tag/female:maid",
            "https://e-hentai.org/uploader/example",
            "https://e-hentai.org/favorites.php",
        )
        client = FakeListingPageClient(dict.fromkeys(urls, html))
        adapter = EHentaiAdapter(listing_page_client=client)

        for index, url in enumerate(urls):
            with self.subTest(url=url):
                route = adapter.classify_url(url)
                self.assertIsNotNone(route)
                result = asyncio.run(
                    adapter.execute(
                        OperationRequest(
                            request_id=f"request-{index}",
                            plugin_id="ehentai",
                            site_id="ehentai",
                            operation_id="batch_download",
                            source_url=url,
                            route=route,
                            params={"page": 1, "max_items": 50},
                            confirmations=("live_network",),
                        )
                    )
                )
                self.assertEqual(result.result_kind, ResultKind.LIST_PAGE)

    def test_executes_batch_download_as_list_page(self) -> None:
        url = "https://e-hentai.org/?f_search=sample"
        client = FakeListingPageClient(
            {
                url: """
                <table class="itg">
                  <tr>
                    <td><a href="/g/123/abcdef/"><img src="/thumb.jpg"></a></td>
                    <td><a href="/g/123/abcdef/"><div class="glink">Sample Gallery</div></a></td>
                  </tr>
                </table>
                <a id="dnext" href="/?f_search=sample&page=1">Next</a>
                """,
            }
        )
        adapter = EHentaiAdapter(listing_page_client=client)
        route = adapter.classify_url(url)
        self.assertIsNotNone(route)

        result = asyncio.run(
            adapter.execute(
                OperationRequest(
                    request_id="request-1",
                    plugin_id="ehentai",
                    site_id="ehentai",
                    operation_id="batch_download",
                    source_url=url,
                    route=route,
                    params={"page": 1, "max_items": 50},
                    confirmations=("live_network",),
                )
            )
        )

        self.assertEqual(client.requests, [url])
        self.assertEqual(result.result_kind, ResultKind.LIST_PAGE)
        self.assertIsInstance(result.data, ListPageData)
        data = result.data
        self.assertEqual(data.items[0].item_id, "123-abcdef")
        self.assertEqual(data.items[0].source_url, "https://e-hentai.org/g/123/abcdef/")
        self.assertEqual(data.items[0].title, "Sample Gallery")
        self.assertIn("download_selected", result.available_actions)
        self.assertIn("next_page", result.available_actions)


class EHentaiAdapterListAssetsTest(TestCase):
    def test_lists_gallery_image_page_assets_with_injected_page_client(self) -> None:
        gallery_page_client = FakeGalleryPageClient(
            {
                0: """
                <div id="gdt">
                  <a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>
                  <a href="/s/PageTokenB/123-2"><div title="Page 2: 002.png"></div></a>
                </div>
                """,
            }
        )
        adapter = EHentaiAdapter(gallery_page_client=gallery_page_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 2,
            },
        )

        assets = asyncio.run(adapter.list_assets(item))

        self.assertEqual(
            gallery_page_client.requests,
            [("https://e-hentai.org/g/123/abcdef/", 0)],
        )
        self.assertEqual(len(assets.assets), 2)
        self.assertEqual(assets.assets[0].url, "https://e-hentai.org/s/PageTokenA/123-1")
        self.assertEqual(assets.assets[0].kind, AssetKind.IMAGE)
        self.assertEqual(assets.assets[0].filename, "001.jpg")
        self.assertEqual(assets.assets[0].metadata["index"], 1)
        self.assertEqual(assets.assets[0].metadata["asset_stage"], "image_page")
        self.assertEqual(assets.assets[1].url, "https://e-hentai.org/s/PageTokenB/123-2")
        self.assertEqual(assets.assets[1].filename, "002.png")

    def test_lists_gallery_assets_across_multiple_pages_until_file_count(self) -> None:
        gallery_page_client = FakeGalleryPageClient(
            {
                0: "<div id='gdt'>"
                + "".join(
                    f"<a href='/s/PageToken{index}/123-{index}'><div title='Page {index}: {index:03}.jpg'></div></a>"
                    for index in range(1, 21)
                )
                + "</div>",
                1: """
                <div id="gdt">
                  <a href="/s/PageToken21/123-21"><div title="Page 21: 021.jpg"></div></a>
                </div>
                """,
            }
        )
        adapter = EHentaiAdapter(gallery_page_client=gallery_page_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 21,
            },
        )

        assets = asyncio.run(adapter.list_assets(item))

        self.assertEqual(len(assets.assets), 21)
        self.assertEqual(
            gallery_page_client.requests,
            [
                ("https://e-hentai.org/g/123/abcdef/", 0),
                ("https://e-hentai.org/g/123/abcdef/", 1),
            ],
        )
        self.assertEqual(assets.assets[-1].metadata["index"], 21)
        self.assertEqual(assets.assets[-1].filename, "021.jpg")

    def test_list_assets_returns_empty_when_file_count_is_zero(self) -> None:
        adapter = EHentaiAdapter(gallery_page_client=FakeGalleryPageClient({}))
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 0,
            },
        )

        assets = asyncio.run(adapter.list_assets(item))

        self.assertEqual(assets.assets, ())

    def test_list_assets_requires_gallery_metadata(self) -> None:
        adapter = EHentaiAdapter(gallery_page_client=FakeGalleryPageClient({}))
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={},
        )

        with self.assertRaises(AdapterResolutionError):
            asyncio.run(adapter.list_assets(item))


class EHentaiAdapterStrategyTest(TestCase):
    def test_choose_strategy_uses_direct_image_page_assets(self) -> None:
        gallery_page_client = FakeGalleryPageClient(
            {
                0: """
                <div id="gdt">
                  <a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>
                  <a href="/s/PageTokenB/123-2"><div title="Page 2: 002.png"></div></a>
                </div>
                """,
            }
        )
        adapter = EHentaiAdapter(gallery_page_client=gallery_page_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 2,
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.DIRECT)
        self.assertEqual(plan.reason, "ehentai_direct_image_page_assets")
        self.assertEqual(len(plan.assets.assets), 2)
        self.assertEqual(plan.assets.assets[0].filename, "001.jpg")

    def test_choose_torrent_strategy_lists_torrent_candidates(self) -> None:
        torrent_client = FakeTorrentPageClient(
            """
            <table>
              <tr>
                <td><a href="/torrent/123/sample.torrent">Sample Torrent</a></td>
                <td>Size: 1.5 MiB Seeds: 7 Peers: 3 Downloads: 20</td>
              </tr>
            </table>
            """
        )
        adapter = EHentaiAdapter(torrent_page_client=torrent_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "torrent_count": 1,
            },
        )

        plan = asyncio.run(adapter.choose_torrent_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
        self.assertEqual(plan.reason, "ehentai_most_seeded_torrent")
        self.assertEqual(torrent_client.requests, ["https://e-hentai.org/g/123/abcdef/"])
        self.assertEqual(len(plan.assets.assets), 1)
        asset = plan.assets.assets[0]
        self.assertEqual(asset.kind, AssetKind.TORRENT)
        self.assertEqual(asset.url, "https://e-hentai.org/torrent/123/sample.torrent")
        self.assertEqual(asset.filename, "sample.torrent")
        self.assertEqual(asset.metadata["asset_stage"], "torrent_candidate")
        self.assertEqual(asset.metadata["seeds"], 7)

    def test_torrent_strategy_rejects_gallery_without_torrents(self) -> None:
        adapter = EHentaiAdapter(torrent_page_client=FakeTorrentPageClient(""))
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "torrent_count": 0,
            },
        )

        with self.assertRaisesRegex(AdapterResolutionError, "does not provide"):
            asyncio.run(adapter.choose_torrent_strategy(item))

    def test_choose_strategy_honors_requested_torrent_strategy(self) -> None:
        torrent_client = FakeTorrentPageClient(
            """
            <table>
              <tr>
                <td><a href="/torrent/123/sample.torrent">Sample Torrent</a></td>
                <td>Size: 1.5 MiB Seeds: 7 Peers: 3 Downloads: 20</td>
              </tr>
            </table>
            """
        )
        adapter = EHentaiAdapter(torrent_page_client=torrent_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "torrent_count": 1,
                "requested_strategy": "torrent",
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
        self.assertEqual(len(plan.assets.assets), 1)

    def test_auto_prefers_most_seeded_torrent_when_torrent_client_is_enabled(self) -> None:
        torrent_client = FakeTorrentPageClient(
            """
            <table>
              <tr>
                <td><a href="/torrent/123/low.torrent">Low Seed Torrent</a></td>
                <td>Size: 1.5 MiB Seeds: 2 Peers: 3 Downloads: 20</td>
              </tr>
              <tr>
                <td><a href="/torrent/123/high.torrent">High Seed Torrent</a></td>
                <td>Size: 1.5 MiB Seeds: 7 Peers: 3 Downloads: 20</td>
              </tr>
            </table>
            """
        )
        adapter = EHentaiAdapter(
            torrent_page_client=torrent_client,
            auto_torrent_enabled=True,
        )
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 1,
                "torrent_count": 2,
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
        self.assertEqual(plan.reason, "ehentai_auto_most_seeded_torrent")
        self.assertEqual(len(plan.assets.assets), 1)
        self.assertEqual(plan.assets.assets[0].filename, "high.torrent")
        self.assertEqual(plan.assets.assets[0].metadata["seeds"], 7)

    def test_requested_torrent_uses_most_seeded_candidate_even_when_seeds_are_zero(self) -> None:
        torrent_client = FakeTorrentPageClient(
            """
            <table>
              <tr>
                <td><a href="/torrent/123/first.torrent">First Torrent</a></td>
                <td>Seeds: 0</td>
              </tr>
              <tr>
                <td><a href="/torrent/123/second.torrent">Second Torrent</a></td>
                <td>Seeds: 0</td>
              </tr>
            </table>
            """
        )
        adapter = EHentaiAdapter(torrent_page_client=torrent_client)
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "torrent_count": 2,
                "requested_strategy": "torrent",
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
        self.assertEqual(len(plan.assets.assets), 1)
        self.assertEqual(plan.assets.assets[0].filename, "first.torrent")

    def test_auto_falls_back_to_direct_when_torrent_candidates_are_unavailable(self) -> None:
        gallery_client = FakeGalleryPageClient(
            {
                0: '<div id="gdt">'
                '<a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>'
                "</div>"
            }
        )
        adapter = EHentaiAdapter(
            gallery_page_client=gallery_client,
            torrent_page_client=FakeTorrentPageClient(""),
            auto_torrent_enabled=True,
        )
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 1,
                "torrent_count": 1,
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.DIRECT)
        self.assertEqual(plan.reason, "ehentai_auto_direct_fallback")

    def test_auto_falls_back_to_direct_when_best_torrent_has_zero_seeds(self) -> None:
        gallery_client = FakeGalleryPageClient(
            {
                0: '<div id="gdt">'
                '<a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>'
                "</div>"
            }
        )
        adapter = EHentaiAdapter(
            gallery_page_client=gallery_client,
            torrent_page_client=FakeTorrentPageClient(
                '<table><tr><td><a href="/torrent/123/idle.torrent">Idle</a></td>'
                '<td>Seeds: 0 Peers: 4 Downloads: 20</td></tr></table>'
            ),
            auto_torrent_enabled=True,
        )
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 1,
                "torrent_count": 1,
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.DIRECT)
        self.assertEqual(plan.reason, "ehentai_auto_direct_fallback")

    def test_auto_stays_direct_when_torrent_client_is_disabled(self) -> None:
        gallery_client = FakeGalleryPageClient(
            {
                0: '<div id="gdt">'
                '<a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>'
                "</div>"
            }
        )
        adapter = EHentaiAdapter(
            gallery_page_client=gallery_client,
            torrent_page_client=FakeTorrentPageClient(
                '<a href="/torrent/123/sample.torrent">Sample Torrent</a>'
            ),
        )
        item = ResolvedItem(
            site_id="ehentai",
            source_url="https://e-hentai.org/g/123/abcdef/",
            title="Sample Gallery",
            metadata={
                "gallery_url": "https://e-hentai.org/g/123/abcdef/",
                "file_count": 1,
                "torrent_count": 1,
            },
        )

        plan = asyncio.run(adapter.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.DIRECT)
        self.assertEqual(plan.reason, "ehentai_direct_image_page_assets")
        self.assertEqual(gallery_client.requests, [("https://e-hentai.org/g/123/abcdef/", 0)])
