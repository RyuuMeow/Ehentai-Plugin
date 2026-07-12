from __future__ import annotations

from typing import Protocol

from cli_downloader.core.errors import AdapterResolutionError
from cli_downloader.core.models import Asset, AssetKind
from ehentai.parser import parse_image_page_html


class EHentaiImagePageClient(Protocol):
    async def fetch_image_page_html(self, image_page_url: str) -> str: ...


class BinaryContentClient(Protocol):
    async def fetch_bytes(self, url: str) -> bytes: ...


class UnavailableEHentaiImagePageClient:
    async def fetch_image_page_html(self, image_page_url: str) -> str:
        raise AdapterResolutionError("E-Hentai live image page fetching is not implemented yet.")


class UnavailableBinaryContentClient:
    async def fetch_bytes(self, url: str) -> bytes:
        raise AdapterResolutionError("E-Hentai live binary fetching is not implemented yet.")


class EHentaiAssetFetcher:
    def __init__(
        self,
        *,
        image_page_client: EHentaiImagePageClient | None = None,
        binary_client: BinaryContentClient | None = None,
    ) -> None:
        self._image_page_client = image_page_client or UnavailableEHentaiImagePageClient()
        self._binary_client = binary_client or UnavailableBinaryContentClient()

    async def fetch(self, asset: Asset) -> bytes:
        if asset.kind == AssetKind.TORRENT:
            return await self._binary_client.fetch_bytes(asset.url)
        if asset.kind != AssetKind.IMAGE:
            raise AdapterResolutionError(
                "E-Hentai asset fetcher supports image and torrent assets only."
            )

        stage = asset.metadata.get("asset_stage")
        if stage != "image_page":
            raise AdapterResolutionError("E-Hentai image asset is not an image page asset.")

        html = await self._image_page_client.fetch_image_page_html(asset.url)
        resolved = parse_image_page_html(
            html,
            fallback_filename=asset.filename,
            index=_asset_index(asset),
        )
        return await self._binary_client.fetch_bytes(resolved.image_url)


def _asset_index(asset: Asset) -> int | None:
    index = asset.metadata.get("index")
    if isinstance(index, bool):
        return None
    if isinstance(index, int):
        return index
    return None
