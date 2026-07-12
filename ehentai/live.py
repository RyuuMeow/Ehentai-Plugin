from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cli_downloader.config.loader import ConfigLoader, LoadedConfig
from cli_downloader.config.schema import SettingsRegistry
from ehentai.adapter import EHentaiAdapter
from ehentai.fetcher import EHentaiAssetFetcher
from ehentai.http_client import (
    EHentaiHttpClient,
    EHentaiHttpOptions,
    EHentaiHttpTransport,
    StdlibEHentaiHttpTransport,
)
from ehentai.manifest import get_ehentai_manifest


@dataclass(frozen=True)
class EHentaiLiveComponents:
    options: EHentaiHttpOptions
    http_client: EHentaiHttpClient
    adapter: EHentaiAdapter
    fetcher: EHentaiAssetFetcher
    transport_name: str


def build_live_ehentai_components(
    *,
    config: LoadedConfig | None = None,
    transport: EHentaiHttpTransport | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> EHentaiLiveComponents:
    if config is None:
        registry = SettingsRegistry()
        registry.register_plugin("ehentai", get_ehentai_manifest())
        config = ConfigLoader(registry=registry).load()
    loaded = config
    options = EHentaiHttpOptions.from_config(loaded.values, secrets=loaded.secrets)
    http_transport = transport or StdlibEHentaiHttpTransport()
    http_client = EHentaiHttpClient(
        transport=http_transport,
        options=options,
    )
    return EHentaiLiveComponents(
        options=options,
        http_client=http_client,
        adapter=EHentaiAdapter(
            metadata_client=http_client,
            gallery_page_client=http_client,
            torrent_page_client=http_client,
            listing_page_client=http_client,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
            auto_torrent_enabled=loaded.values.get("torrent.client") == "qbittorrent",
        ),
        fetcher=EHentaiAssetFetcher(
            image_page_client=http_client,
            binary_client=http_client,
        ),
        transport_name=type(http_transport).__name__,
    )
