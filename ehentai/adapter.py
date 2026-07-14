from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from cli_downloader.core.errors import AdapterResolutionError
from cli_downloader.core.operations import (
    AssetData,
    GalleryData,
    ListItemData,
    ListPageData,
    OperationRequest,
    OperationResult,
    PageInfo,
    ResultKind,
    RouteMatch,
)
from cli_downloader.core.widgets import (
    Action,
    ActionKind,
    Button,
    ListItem,
    ListView,
    Page,
    Pagination,
    SelectionMode,
    Text,
    Title,
)
from cli_downloader.core.models import (
    Asset,
    AssetKind,
    AssetList,
    DownloadStrategy,
    DownloadStrategyPlan,
    ResolveRequest,
    ResolvedItem,
)
from ehentai.parser import (
    EHentaiGalleryImage,
    EHentaiGalleryMetadata,
    EHentaiListingCandidate,
    EHentaiTorrentCandidate,
    parse_gallery_image_list_html,
    parse_gallery_metadata_response,
    parse_listing_page_html,
    parse_torrent_candidates_html,
)
from ehentai.manifest import get_ehentai_manifest
from ehentai.urls import EHentaiUrlKind
from ehentai.urls import parse_ehentai_url
from cli_downloader.sites.manifest import SiteManifest


class EHentaiMetadataClient(Protocol):
    async def fetch_gallery_metadata(
        self,
        *,
        gid: int,
        token: str,
    ) -> Mapping[str, Any]: ...


class EHentaiGalleryPageClient(Protocol):
    async def fetch_gallery_page_html(
        self,
        *,
        gallery_url: str,
        page: int,
    ) -> str: ...


class EHentaiTorrentPageClient(Protocol):
    async def fetch_torrent_page_html(self, gallery_url: str) -> str: ...


class EHentaiListingPageClient(Protocol):
    async def fetch_listing_page_html(self, listing_url: str) -> str: ...


class UnavailableEHentaiMetadataClient:
    async def fetch_gallery_metadata(
        self,
        *,
        gid: int,
        token: str,
    ) -> Mapping[str, Any]:
        raise AdapterResolutionError("E-Hentai live metadata fetching is not implemented yet.")


class UnavailableEHentaiGalleryPageClient:
    async def fetch_gallery_page_html(
        self,
        *,
        gallery_url: str,
        page: int,
    ) -> str:
        raise AdapterResolutionError("E-Hentai live gallery page fetching is not implemented yet.")


class UnavailableEHentaiTorrentPageClient:
    async def fetch_torrent_page_html(self, gallery_url: str) -> str:
        raise AdapterResolutionError("E-Hentai live torrent page fetching is not implemented yet.")


class UnavailableEHentaiListingPageClient:
    async def fetch_listing_page_html(self, listing_url: str) -> str:
        raise AdapterResolutionError("E-Hentai live listing page fetching is not implemented yet.")


class EHentaiAdapter:
    site_id = "ehentai"
    display_name = "E-Hentai / ExHentai"

    def __init__(
        self,
        *,
        metadata_client: EHentaiMetadataClient | None = None,
        gallery_page_client: EHentaiGalleryPageClient | None = None,
        torrent_page_client: EHentaiTorrentPageClient | None = None,
        listing_page_client: EHentaiListingPageClient | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        auto_torrent_enabled: bool = False,
    ) -> None:
        self._metadata_client = metadata_client or UnavailableEHentaiMetadataClient()
        self._gallery_page_client = gallery_page_client or UnavailableEHentaiGalleryPageClient()
        self._torrent_page_client = torrent_page_client or UnavailableEHentaiTorrentPageClient()
        self._listing_page_client = listing_page_client or UnavailableEHentaiListingPageClient()
        self._progress_callback = progress_callback
        self._cancel_requested = cancel_requested or (lambda: False)
        self._auto_torrent_enabled = auto_torrent_enabled

    def can_handle_url(self, url: str) -> bool:
        return parse_ehentai_url(url) is not None

    def get_manifest(self) -> SiteManifest:
        return get_ehentai_manifest()

    def classify_url(self, url: str) -> RouteMatch | None:
        manifest = self.get_manifest()
        route = manifest.route_url(url)
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
        if request.operation_id == "batch_download":
            return await self._list_result(request)
        if request.operation_id != "single_download":
            raise AdapterResolutionError(
                f"E-Hentai generic operation is not implemented: {request.operation_id}"
            )
        gallery_id = request.route.captures["gallery_id"]
        strategy = _request_strategy(request.params.get("strategy", DownloadStrategy.AUTO.value))
        return OperationResult(
            request_id=request.request_id,
            result_kind=ResultKind.GALLERY,
            data=GalleryData(
                source_url=request.source_url,
                site_id=self.site_id,
                gallery_id=gallery_id,
                title=f"E-Hentai Gallery #{gallery_id}",
                metadata={
                    "host": request.route.captures["host"],
                    "strategy": strategy.value,
                },
            ),
        )

    async def _list_result(self, request: OperationRequest) -> OperationResult:
        self._raise_if_cancelled()
        max_items = int(request.params["max_items"])
        current_page = int(request.params["page"])
        cursor = request.params.get("cursor")
        if cursor is not None and isinstance(cursor, str) and cursor:
            listing_url = cursor
        else:
            listing_url = _listing_url_for_page(request.source_url, current_page)
        html = await self._listing_page_client.fetch_listing_page_html(listing_url)
        listing = parse_listing_page_html(html, base_url=listing_url)
        strategy = _request_strategy(request.params.get("strategy", DownloadStrategy.AUTO.value))
        items = tuple(
            _list_item(candidate, strategy=strategy) for candidate in listing.candidates[:max_items]
        )
        previous_action = (
            Action(
                action_id="previous_page",
                kind=ActionKind.INVOKE_OPERATION,
                operation_id="batch_download",
                params={
                    "cursor": listing.prev_url,
                    "max_items": max_items,
                    "page": current_page,
                    "strategy": strategy.value,
                },
            )
            if listing.prev_url is not None
            else None
        )
        next_action = (
            Action(
                action_id="next_page",
                kind=ActionKind.INVOKE_OPERATION,
                operation_id="batch_download",
                params={
                    "cursor": listing.next_url,
                    "max_items": max_items,
                    "page": current_page,
                    "strategy": strategy.value,
                },
            )
            if listing.next_url is not None
            else None
        )
        title = _listing_title(request.source_url, current_page)
        return OperationResult(
            request_id=request.request_id,
            result_kind=ResultKind.LIST_PAGE,
            data=ListPageData(
                title=title,
                items=items,
                page_info=PageInfo(
                    current_page=current_page,
                    page_size=max(1, len(items)),
                    next_token=listing.next_url,
                    previous_token=listing.prev_url,
                ),
                active_filters={
                    "listing": _listing_label(request.source_url),
                    "max_items": max_items,
                    "strategy": strategy.value,
                },
            ),
            page=_listing_widget_page(
                title=title,
                items=items,
                current_page=current_page,
                previous_action=previous_action,
                next_action=next_action,
            ),
            available_actions=tuple(
                action.action_id for action in (previous_action, next_action) if action is not None
            )
            + ("download_selected",),
        )

    async def resolve(self, request: ResolveRequest) -> ResolvedItem:
        self._raise_if_cancelled()
        url_info = parse_ehentai_url(request.url)
        if url_info is None:
            raise AdapterResolutionError(f"E-Hentai adapter cannot handle URL: {request.url}")
        if (
            url_info.kind != EHentaiUrlKind.GALLERY
            or url_info.gid is None
            or url_info.token is None
        ):
            raise AdapterResolutionError(
                "E-Hentai resolve currently supports gallery URLs only; image pages and listings are pending."
            )

        payload = await self._metadata_client.fetch_gallery_metadata(
            gid=url_info.gid,
            token=url_info.token,
        )
        metadata = parse_gallery_metadata_response(payload, site=url_info.site)
        metadata_values = _metadata_dict(metadata, profile=request.profile)
        metadata_values["requested_strategy"] = request.strategy.value
        return ResolvedItem(
            site_id=self.site_id,
            source_url=metadata.url,
            title=_display_title(metadata),
            metadata=metadata_values,
            tags=tuple(f"{tag.namespace}:{tag.value}" for tag in metadata.tags),
        )

    async def list_assets(self, item: ResolvedItem) -> AssetList:
        gallery_url = _required_metadata_text(item, "gallery_url")
        file_count = _required_metadata_int(item, "file_count")
        if file_count <= 0:
            return AssetList(assets=())

        images: list[EHentaiGalleryImage] = []
        page_count = _gallery_page_count(file_count)
        self._report_progress(0, file_count)
        for page in range(page_count):
            self._raise_if_cancelled()
            html = await self._gallery_page_client.fetch_gallery_page_html(
                gallery_url=gallery_url,
                page=page,
            )
            remaining = file_count - len(images)
            images.extend(
                parse_gallery_image_list_html(
                    html,
                    base_url=gallery_url,
                    limit=remaining,
                )
            )
            if len(images) >= file_count:
                break
            self._report_progress(len(images), file_count)

        self._report_progress(len(images), file_count)

        return AssetList(
            assets=tuple(
                _asset_from_gallery_image(image, index=index)
                for index, image in enumerate(images, start=1)
            )
        )

    async def choose_strategy(self, item: ResolvedItem) -> DownloadStrategyPlan:
        strategy = _item_strategy(item)
        if strategy is DownloadStrategy.TORRENT:
            return await self.choose_torrent_strategy(item)
        if strategy is DownloadStrategy.AUTO and self._auto_torrent_enabled:
            try:
                torrent_assets = await self.list_torrent_assets(item)
            except AdapterResolutionError:
                torrent_assets = AssetList(assets=())
            selected_torrent = _most_seeded_torrent_asset(torrent_assets)
            if selected_torrent is not None and _torrent_seed_count(selected_torrent) > 0:
                return DownloadStrategyPlan(
                    strategy=DownloadStrategy.TORRENT,
                    reason="ehentai_auto_most_seeded_torrent",
                    assets=AssetList(assets=(selected_torrent,)),
                )
        if strategy not in {DownloadStrategy.AUTO, DownloadStrategy.DIRECT}:
            raise AdapterResolutionError(
                f"E-Hentai does not support download strategy: {strategy.value}"
            )
        assets = await self.list_assets(item)
        return DownloadStrategyPlan(
            strategy=DownloadStrategy.DIRECT,
            reason=(
                "ehentai_auto_direct_fallback"
                if strategy is DownloadStrategy.AUTO and self._auto_torrent_enabled
                else "ehentai_direct_image_page_assets"
            ),
            assets=assets,
        )

    async def list_torrent_assets(self, item: ResolvedItem) -> AssetList:
        torrent_count = _metadata_int(item, "torrent_count", default=0)
        if torrent_count <= 0:
            return AssetList(assets=())

        gallery_url = _required_metadata_text(item, "gallery_url")
        html = await self._torrent_page_client.fetch_torrent_page_html(gallery_url)
        candidates = parse_torrent_candidates_html(html, base_url=gallery_url)
        return AssetList(
            assets=tuple(
                _asset_from_torrent_candidate(candidate, index=index)
                for index, candidate in enumerate(candidates, start=1)
            )
        )

    async def choose_torrent_strategy(self, item: ResolvedItem) -> DownloadStrategyPlan:
        assets = await self.list_torrent_assets(item)
        selected_torrent = _most_seeded_torrent_asset(assets)
        if selected_torrent is None:
            raise AdapterResolutionError(
                "E-Hentai gallery does not provide any downloadable torrent candidates."
            )
        return DownloadStrategyPlan(
            strategy=DownloadStrategy.TORRENT,
            reason="ehentai_most_seeded_torrent",
            assets=AssetList(assets=(selected_torrent,)),
        )

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested():
            raise AdapterResolutionError("E-Hentai gallery enumeration was cancelled.")

    def _report_progress(self, current: int, total: int) -> None:
        if self._progress_callback is not None:
            self._progress_callback(current, total)


def _display_title(metadata: EHentaiGalleryMetadata) -> str:
    return metadata.title_jpn or metadata.title or f"Gallery #{metadata.gid}"


def _metadata_dict(
    metadata: EHentaiGalleryMetadata,
    *,
    profile: str | None,
) -> dict[str, object]:
    artists = [tag.value for tag in metadata.tags if tag.namespace == "artist"]
    return {
        "gid": metadata.gid,
        "token": metadata.token,
        "site": metadata.site.value,
        "artist": ", ".join(artists) if artists else "unknown",
        "gallery_url": metadata.url,
        "title": metadata.title,
        "title_jpn": metadata.title_jpn,
        "category": metadata.category,
        "uploader": metadata.uploader,
        "file_count": metadata.file_count,
        "filesize": metadata.filesize,
        "posted": metadata.posted,
        "rating": metadata.rating,
        "torrent_count": metadata.torrent_count,
        "thumbnail_url": metadata.thumbnail_url,
        "profile": profile or "default",
    }


def _gallery_page_count(file_count: int) -> int:
    return max(1, (file_count + 19) // 20)


def _asset_from_gallery_image(image: EHentaiGalleryImage, *, index: int) -> Asset:
    return Asset(
        url=image.page_url,
        kind=AssetKind.IMAGE,
        filename=image.filename,
        metadata={
            "index": index,
            "asset_stage": "image_page",
        },
    )


def _asset_from_torrent_candidate(candidate: EHentaiTorrentCandidate, *, index: int) -> Asset:
    return Asset(
        url=candidate.url,
        kind=AssetKind.TORRENT,
        filename=_torrent_filename(candidate, index=index),
        metadata={
            "index": index,
            "title": candidate.title,
            "size": candidate.size,
            "seeds": candidate.seeds,
            "peers": candidate.peers,
            "downloads": candidate.downloads,
            "asset_stage": "torrent_candidate",
        },
    )


def _torrent_filename(candidate: EHentaiTorrentCandidate, *, index: int) -> str:
    filename = candidate.url.rstrip("/").rsplit("/", 1)[-1]
    if filename.lower().endswith(".torrent"):
        return filename
    return f"torrent-{index:03d}.torrent"


def _most_seeded_torrent_asset(assets: AssetList) -> Asset | None:
    if not assets.assets:
        return None
    return max(assets.assets, key=_torrent_seed_count)


def _torrent_seed_count(asset: Asset) -> int:
    value = asset.metadata.get("seeds", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _list_item(
    candidate: EHentaiListingCandidate,
    *,
    strategy: DownloadStrategy = DownloadStrategy.AUTO,
) -> ListItemData:
    item_id = f"{candidate.gid}-{candidate.token}"
    thumbnail = (
        AssetData(asset_id=f"{item_id}-thumb", url=candidate.thumbnail_url)
        if candidate.thumbnail_url
        else None
    )
    return ListItemData(
        item_id=item_id,
        source_url=candidate.url,
        title=candidate.title,
        thumbnail=thumbnail,
        summary=candidate.summary or None,
        metadata={
            "gid": candidate.gid,
            "token": candidate.token,
            "strategy": strategy.value,
        },
    )


def _listing_widget_page(
    *,
    title: str,
    items: tuple[ListItemData, ...],
    current_page: int,
    previous_action: Action | None,
    next_action: Action | None,
) -> Page:
    return Page(
        header=(
            Title(text=title),
            Text(text=f"{len(items)} galleries on this page."),
        ),
        content=(
            ListView(
                widget_id="results",
                items=tuple(
                    ListItem(
                        widget_id=item.item_id,
                        title=item.title,
                        text=item.summary,
                    )
                    for item in items
                ),
                selection_mode=SelectionMode.MULTIPLE,
            ),
            Pagination(
                widget_id="pagination",
                current_page=current_page,
                previous_action=previous_action,
                next_action=next_action,
            ),
        ),
        actions=(
            Button(
                widget_id="download_selected",
                text="Download selected",
                action=Action(
                    action_id="download_selected",
                    kind=ActionKind.DOWNLOAD,
                ),
            ),
        ),
    )


def _listing_url_for_page(url: str, page: int) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if page <= 1:
        query.pop("page", None)
    else:
        query["page"] = str(page - 1)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _listing_label(url: str) -> str:
    info = parse_ehentai_url(url)
    return info.listing_label if info is not None and info.listing_label else "listing"


def _listing_title(url: str, current_page: int) -> str:
    return f"E-Hentai {_listing_label(url).replace('_', ' ').title()} - Page {current_page}"


def _required_metadata_text(item: ResolvedItem, key: str) -> str:
    value = item.metadata.get(key)
    if not isinstance(value, str) or not value:
        raise AdapterResolutionError(f"E-Hentai resolved item metadata is missing {key}")
    return value


def _required_metadata_int(item: ResolvedItem, key: str) -> int:
    value = item.metadata.get(key)
    if isinstance(value, bool):
        raise AdapterResolutionError(
            f"E-Hentai resolved item metadata field {key} is not an integer"
        )
    if isinstance(value, int):
        return value
    raise AdapterResolutionError(f"E-Hentai resolved item metadata field {key} is not an integer")


def _metadata_int(item: ResolvedItem, key: str, *, default: int = 0) -> int:
    if key not in item.metadata:
        return default
    return _required_metadata_int(item, key)


def _request_strategy(value: object) -> DownloadStrategy:
    try:
        return DownloadStrategy(str(value))
    except ValueError as error:
        raise AdapterResolutionError(f"E-Hentai strategy is invalid: {value}") from error


def _item_strategy(item: ResolvedItem) -> DownloadStrategy:
    value = item.metadata.get("requested_strategy", item.metadata.get("strategy", "auto"))
    return _request_strategy(value)
