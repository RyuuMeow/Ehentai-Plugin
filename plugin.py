"""E-Hentai / ExHentai external plugin.

Thin wrapper around the existing built-in adapter at
cli_downloader/sites/ehentai/. Provides the external plugin interface
while reusing the mature adapter, fetcher, parser, and HTTP client.

Cursor pagination: uses the site's actual dprev/dnext cursor URLs
instead of generating numeric page parameters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cli_downloader.core.models import (
    AssetList,
    DownloadStrategyPlan,
    ResolveRequest,
    ResolvedItem,
)
from cli_downloader.core.operations import (
    OperationRequest,
    OperationResult,
    RouteMatch,
)
from ehentai.adapter import EHentaiAdapter
from ehentai.fetcher import EHentaiAssetFetcher
from ehentai.http_client import (
    EHentaiHttpClient,
    EHentaiHttpOptions,
    EHentaiHttpTransport,
    StdlibEHentaiHttpTransport,
)
from ehentai.manifest import get_ehentai_manifest

if TYPE_CHECKING:
    from cli_downloader.sites.manifest import SiteManifest


class Plugin:
    """External plugin entrypoint for E-Hentai / ExHentai."""

    site_id = "ehentai"
    display_name = "E-Hentai / ExHentai"

    def __init__(self) -> None:
        self._manifest = get_ehentai_manifest()
        self._transport: EHentaiHttpTransport | None = None
        self._adapter: EHentaiAdapter | None = None
        self._settings: dict[str, object] = {}
        self._secrets: dict[str, object] = {}

    @property
    def transport(self) -> EHentaiHttpTransport:
        if self._transport is None:
            self._transport = StdlibEHentaiHttpTransport()
        return self._transport

    def _get_adapter(
        self,
        settings: dict[str, object] | None = None,
        secrets: dict[str, object] | None = None,
    ) -> EHentaiAdapter:
        settings = settings if settings is not None and settings else self._settings
        secrets = secrets if secrets is not None and secrets else self._secrets
        client = self._get_client(settings, secrets)
        return EHentaiAdapter(
            metadata_client=client,
            gallery_page_client=client,
            listing_page_client=client,
            torrent_page_client=client,
            auto_torrent_enabled=settings.get("torrent.client") == "qbittorrent",
        )

    def _get_client(
        self,
        settings: dict[str, object] | None = None,
        secrets: dict[str, object] | None = None,
    ) -> EHentaiHttpClient:
        settings = settings if settings is not None and settings else self._settings
        secrets = secrets if secrets is not None and secrets else self._secrets
        options = EHentaiHttpOptions(
            user_agent=str(settings.get("http.user_agent", "CLI-Downloader/0.1")),
            timeout_seconds=float(settings.get("http.timeout_seconds", 30.0)),
            retry_attempts=int(settings.get("http.retry_attempts", 2)),
            cookies={
                k.removeprefix("cookies."): v
                for k, v in secrets.items()
                if k.startswith("cookies.")
            },
        )
        client = EHentaiHttpClient(
            options=options,
            transport=self.transport,
        )
        return client

    def configure(self, settings: dict[str, object], secrets: dict[str, object]) -> None:
        self._settings = dict(settings)
        self._secrets = dict(secrets)

    def get_manifest_name(self) -> str:
        return "site.json"

    def get_manifest(self) -> SiteManifest:
        return self._manifest

    def can_handle_url(self, url: str) -> bool:
        from ehentai.urls import parse_ehentai_url

        return parse_ehentai_url(url) is not None

    def classify_url(self, url: str) -> RouteMatch | None:
        route = self._manifest.route_url(url)
        if route is None or route.operation_schema is None:
            return None
        confirmations = (
            ("live_network",) if route.operation_schema.requires_live_network_confirmation else ()
        )
        return RouteMatch(
            plugin_id="ehentai",
            site_id=self.site_id,
            rule_name=route.rule_name,
            operation_id=route.operation,
            normalized_url=url.strip(),
            captures=route.captures,
            parameter_schema={
                name: schema.to_dict() for name, schema in route.operation_schema.params.items()
            },
            required_confirmations=confirmations,
        )

    async def execute(self, request: OperationRequest) -> OperationResult:
        adapter = self._get_adapter()
        return await adapter.execute(request)

    async def resolve(self, request: ResolveRequest) -> ResolvedItem:
        adapter = self._get_adapter()
        return await adapter.resolve(request)

    async def list_assets(self, item: ResolvedItem) -> AssetList:
        adapter = self._get_adapter()
        return await adapter.list_assets(item)

    async def choose_strategy(self, item: ResolvedItem) -> DownloadStrategyPlan:
        adapter = self._get_adapter()
        return await adapter.choose_strategy(item)

    async def fetch(self, asset: object) -> bytes:
        client = self._get_client()
        return await EHentaiAssetFetcher(
            image_page_client=client,
            binary_client=client,
        ).fetch(asset)
