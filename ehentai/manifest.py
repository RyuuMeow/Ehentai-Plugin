from __future__ import annotations

from cli_downloader.sites.manifest import (
    InputKind,
    NetworkPolicySchema,
    OperationSchema,
    ParameterSchema,
    SettingSchema,
    SiteManifest,
    UrlRule,
)


def get_ehentai_manifest() -> SiteManifest:
    return SiteManifest(
        site_id="ehentai",
        display_name="E-Hentai / ExHentai",
        domains=("e-hentai.org", "exhentai.org"),
        url_rules=(
            UrlRule(
                name="gallery",
                pattern=(
                    r"^https?://(?P<host>e-hentai|exhentai)\.org/g/"
                    r"(?P<gallery_id>\d+)/(?P<token>[a-f0-9]+)(?:[/?].*)?$"
                ),
                input_kind=InputKind.SINGLE,
                operation="single_download",
                description="Gallery detail page.",
            ),
            UrlRule(
                name="image_page",
                pattern=(
                    r"^https?://(?P<host>e-hentai|exhentai)\.org/s/"
                    r"(?P<page_token>[A-Za-z0-9]+)/(?P<gallery_id>\d+)-(?P<page>\d+)(?:[/?].*)?$"
                ),
                input_kind=InputKind.PAGE,
                operation="page_download",
                description="Single image viewer page.",
            ),
            UrlRule(
                name="tag_listing",
                pattern=r"^https?://(?P<host>e-hentai|exhentai)\.org/tag/(?P<tag>[^/?#]+).*$",
                input_kind=InputKind.BATCH,
                operation="batch_download",
                description="Tag listing page.",
            ),
            UrlRule(
                name="uploader_listing",
                pattern=(
                    r"^https?://(?P<host>e-hentai|exhentai)\.org/uploader/"
                    r"(?P<uploader>[^/?#]+).*$"
                ),
                input_kind=InputKind.BATCH,
                operation="batch_download",
                description="Uploader listing page.",
            ),
            UrlRule(
                name="search_result",
                pattern=r"^https?://(?P<host>e-hentai|exhentai)\.org/(?:\?.*)?$",
                input_kind=InputKind.BATCH,
                operation="batch_download",
                description="Front page or search result listing.",
            ),
            UrlRule(
                name="named_listing",
                pattern=(
                    r"^https?://(?P<host>e-hentai|exhentai)\.org/"
                    r"(?P<listing>favorites|watched|popular|toplists).*$"
                ),
                input_kind=InputKind.BATCH,
                operation="batch_download",
                description="Named gallery listing page.",
            ),
        ),
        operations={
            "single_download": OperationSchema(
                name="single_download",
                supported=True,
                requires_live_network_confirmation=True,
                params={
                    "strategy": ParameterSchema(
                        type="string",
                        enum=("auto", "direct", "torrent"),
                        default="auto",
                        editable=True,
                    ),
                },
            ),
            "page_download": OperationSchema(
                name="page_download",
                supported=False,
                requires_live_network_confirmation=True,
                params={
                    "page_start": ParameterSchema(
                        type="integer",
                        min=1,
                        editable=False,
                        description="Page-level downloads are not implemented yet.",
                    ),
                    "page_end": ParameterSchema(
                        type="integer",
                        min=1,
                        editable=False,
                        description="Page-level downloads are not implemented yet.",
                    ),
                },
            ),
            "batch_download": OperationSchema(
                name="batch_download",
                supported=True,
                requires_live_network_confirmation=True,
                params={
                    "page": ParameterSchema(
                        type="integer",
                        min=1,
                        default=1,
                        editable=False,
                        visible=False,
                    ),
                    "max_items": ParameterSchema(
                        type="integer",
                        min=1,
                        max=500,
                        default=50,
                        editable=True,
                        description="Maximum gallery candidates to show from the current listing page.",
                    ),
                    "strategy": ParameterSchema(
                        type="string",
                        enum=("auto", "direct", "torrent"),
                        default="auto",
                        editable=True,
                        description="Download strategy used for selected galleries.",
                    ),
                    "include_tags": ParameterSchema(
                        type="string_list",
                        editable=False,
                        description="Batch filters are pending implementation.",
                    ),
                    "exclude_tags": ParameterSchema(
                        type="string_list",
                        editable=False,
                        description="Batch filters are pending implementation.",
                    ),
                },
            ),
        },
        settings={
            "http.user_agent": SettingSchema(
                type="string",
                default="CLI-Downloader/0.1",
            ),
            "http.timeout_seconds": SettingSchema(
                type="number",
                min=0.01,
                default=30.0,
            ),
            "http.retry_attempts": SettingSchema(
                type="integer",
                min=0,
                default=2,
            ),
            "http.delay_seconds": SettingSchema(
                type="number",
                min=0,
                max=30,
                default=1.5,
                editable=True,
            ),
        },
        secrets={
            "cookies.ipb_member_id": SettingSchema(
                type="string",
                required=False,
                secret=True,
            ),
            "cookies.ipb_pass_hash": SettingSchema(
                type="string",
                required=False,
                secret=True,
            ),
        },
        network=NetworkPolicySchema(
            max_concurrency=2,
            min_interval_seconds=1.5,
            retryable_status_codes=(429, 502, 503),
            max_attempts=5,
            max_backoff_seconds=300.0,
        ),
    )
