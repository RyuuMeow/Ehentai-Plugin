from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest import TestCase

from cli_downloader.config.schema import SettingsRegistry
from cli_downloader.core.models import DownloadStrategy, ResolveRequest
from .ehentai_fakes import FakeLiveTransport


def _load_plugin_type():
    path = Path(__file__).parents[1] / "plugin.py"
    spec = importlib.util.spec_from_file_location("external_ehentai_plugin", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load external E-Hentai plugin")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Plugin


class TorrentPluginTransport(FakeLiveTransport):
    async def post_json(self, url, payload, options):
        self.options.append(options)
        self.post_json_requests.append((url, payload))
        return {
            "gmetadata": [
                {
                    "gid": "123",
                    "token": "abcdef",
                    "title": "Plugin Gallery",
                    "category": "Manga",
                    "filecount": "1",
                    "torrentcount": "1",
                }
            ]
        }

    async def get_text(self, url, options):
        self.options.append(options)
        self.get_text_requests.append(url)
        if "gallerytorrents.php?gid=123&t=abcdef" in url:
            return """
            <table>
              <tr>
                <td><a href="/torrent/123/sample.torrent">Sample Torrent</a></td>
                <td>Size: 1.5 MiB Seeds: 7 Peers: 3 Downloads: 20</td>
              </tr>
            </table>
            """
        return ""


class ExternalEHentaiPluginTest(TestCase):
    def test_manifest_declares_download_folder_template(self) -> None:
        manifest = _load_plugin_type()().get_manifest()

        self.assertEqual(manifest.output.default_folder_template, "{gallery_id}-{title}")
        self.assertIn("artist", manifest.output.fields)

        registry = SettingsRegistry()
        registry.register_plugin("ehentai", manifest)
        field = registry.field("plugins.ehentai.download.folder_template")
        self.assertIsNone(field.default)
        field.validate("{artist}/{gallery_id}-{title}")

    def test_classification_matches_manifest_contract(self) -> None:
        plugin = _load_plugin_type()()

        route = plugin.classify_url("https://e-hentai.org/g/123/abcdef/")

        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route.operation_id, "single_download")
        self.assertEqual(
            route.parameter_schema["strategy"]["enum"],
            ("auto", "direct", "torrent"),
        )

    def test_configured_plugin_wires_torrent_page_client_and_strategy(self) -> None:
        plugin = _load_plugin_type()()
        transport = TorrentPluginTransport()
        plugin._transport = transport
        plugin.configure(
            {"http.user_agent": "test-agent"},
            {"cookies.ipb_member_id": "member"},
        )

        item = asyncio.run(
            plugin.resolve(
                ResolveRequest(
                    url="https://e-hentai.org/g/123/abcdef/",
                    strategy=DownloadStrategy.TORRENT,
                )
            )
        )
        plan = asyncio.run(plugin.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
        self.assertEqual(len(plan.assets.assets), 1)
        self.assertIn(
            "https://e-hentai.org/gallerytorrents.php?gid=123&t=abcdef",
            transport.get_text_requests,
        )
        self.assertEqual(transport.options[-1].cookies, {"ipb_member_id": "member"})

    def test_configured_global_torrent_client_enables_auto_selection(self) -> None:
        plugin = _load_plugin_type()()
        transport = TorrentPluginTransport()
        plugin._transport = transport
        plugin.configure(
            {
                "http.user_agent": "test-agent",
                "torrent.client": "qbittorrent",
            },
            {},
        )

        item = asyncio.run(
            plugin.resolve(
                ResolveRequest(
                    url="https://e-hentai.org/g/123/abcdef/",
                    strategy=DownloadStrategy.AUTO,
                )
            )
        )
        plan = asyncio.run(plugin.choose_strategy(item))

        self.assertEqual(plan.strategy, DownloadStrategy.TORRENT)
