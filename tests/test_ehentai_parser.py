from unittest import TestCase

from ehentai.parser import (
    EHentaiGalleryImage,
    EHentaiParseError,
    EHentaiResolvedImage,
    EHentaiTag,
    EHentaiTorrentCandidate,
    parse_gallery_image_list_html,
    parse_gallery_metadata_response,
    parse_image_page_html,
    parse_listing_page_html,
    parse_torrent_candidates_html,
)
from ehentai.urls import EHentaiSite


class EHentaiMetadataParserTest(TestCase):
    def test_parses_gallery_metadata_response(self) -> None:
        metadata = parse_gallery_metadata_response(
            {
                "gmetadata": [
                    {
                        "gid": "123",
                        "token": "abcdef",
                        "title": "Sample Gallery",
                        "title_jpn": "Sample Gallery JP",
                        "category": "Manga",
                        "uploader": "sample-uploader",
                        "tags": ["artist:alice", "group:demo circle", "uncategorized"],
                        "filecount": "2",
                        "filesize": "12.3 MiB",
                        "posted": "1710000000",
                        "rating": "4.50",
                        "torrentcount": "1",
                        "thumb": "https://ehgt.org/thumb.jpg",
                    }
                ]
            },
            site=EHentaiSite.E_HENTAI,
        )

        self.assertEqual(metadata.gid, 123)
        self.assertEqual(metadata.token, "abcdef")
        self.assertEqual(metadata.url, "https://e-hentai.org/g/123/abcdef/")
        self.assertEqual(metadata.title, "Sample Gallery")
        self.assertEqual(metadata.file_count, 2)
        self.assertEqual(metadata.rating, 4.5)
        self.assertEqual(metadata.torrent_count, 1)
        self.assertEqual(metadata.thumbnail_url, "https://ehgt.org/thumb.jpg")
        self.assertEqual(
            metadata.tags,
            (
                EHentaiTag(namespace="artist", value="alice"),
                EHentaiTag(namespace="group", value="demo circle"),
                EHentaiTag(namespace="misc", value="uncategorized"),
            ),
        )

    def test_rejects_missing_metadata(self) -> None:
        with self.assertRaises(EHentaiParseError):
            parse_gallery_metadata_response({"gmetadata": []}, site=EHentaiSite.E_HENTAI)

    def test_rejects_api_error_metadata(self) -> None:
        with self.assertRaises(EHentaiParseError):
            parse_gallery_metadata_response(
                {"gmetadata": [{"error": "Gallery not found"}]},
                site=EHentaiSite.E_HENTAI,
            )


class EHentaiImageListParserTest(TestCase):
    def test_parses_gallery_image_list_html(self) -> None:
        images = parse_gallery_image_list_html(
            """
            <html>
              <body>
                <div id="gdt">
                  <div class="gdtm">
                    <a href="https://e-hentai.org/s/PageTokenA/123-1">
                      <div title="Page 1: 001.jpg"></div>
                    </a>
                  </div>
                  <a class="gt200" href="/s/PageTokenB/123-2">
                    <div title="Page 2: 002.png"></div>
                  </a>
                  <a href="https://example.com/not-an-image-page">ignored</a>
                </div>
              </body>
            </html>
            """,
            base_url="https://e-hentai.org/g/123/abcdef/",
        )

        self.assertEqual(
            images,
            (
                EHentaiGalleryImage(
                    index=1,
                    page_url="https://e-hentai.org/s/PageTokenA/123-1",
                    filename="001.jpg",
                ),
                EHentaiGalleryImage(
                    index=2,
                    page_url="https://e-hentai.org/s/PageTokenB/123-2",
                    filename="002.png",
                ),
            ),
        )

    def test_limits_gallery_image_list(self) -> None:
        images = parse_gallery_image_list_html(
            """
            <div id="gdt">
              <a href="/s/PageTokenA/123-1"><div title="Page 1: 001.jpg"></div></a>
              <a href="/s/PageTokenB/123-2"><div title="Page 2: 002.png"></div></a>
            </div>
            """,
            base_url="https://e-hentai.org/g/123/abcdef/",
            limit=1,
        )

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].filename, "001.jpg")

    def test_rejects_html_without_gallery_container(self) -> None:
        with self.assertRaises(EHentaiParseError):
            parse_gallery_image_list_html("<html><title>Content Warning</title></html>")


class EHentaiImagePageParserTest(TestCase):
    def test_parses_image_url_and_filename_from_image_info(self) -> None:
        resolved = parse_image_page_html(
            """
            <html>
              <body>
                <img id="img" src="https://ehgt.org/fullimg/real-name.jpg?token=abc">
                <div id="i4">001.jpg :: 1280 x 1791 :: 332.9 KiB</div>
              </body>
            </html>
            """
        )

        self.assertEqual(
            resolved,
            EHentaiResolvedImage(
                image_url="https://ehgt.org/fullimg/real-name.jpg?token=abc",
                filename="001.jpg",
            ),
        )

    def test_falls_back_to_filename_from_image_url(self) -> None:
        resolved = parse_image_page_html(
            """
            <html>
              <body>
                <img id="img" src="https://ehgt.org/fullimg/encoded%20name.png?token=abc">
              </body>
            </html>
            """
        )

        self.assertEqual(resolved.filename, "encoded name.png")

    def test_uses_numbered_filename_when_url_has_no_filename(self) -> None:
        resolved = parse_image_page_html(
            """
            <html>
              <body>
                <img id="img" src="https://ehgt.org/fullimg/">
              </body>
            </html>
            """,
            index=7,
        )

        self.assertEqual(resolved.filename, "0007.jpg")

    def test_prefers_existing_fallback_filename_over_url_filename(self) -> None:
        resolved = parse_image_page_html(
            """
            <html>
              <body>
                <img id="img" src="https://ehgt.org/fullimg/real-name.jpg?token=abc">
              </body>
            </html>
            """,
            fallback_filename="thumbnail-name.jpg",
        )

        self.assertEqual(resolved.filename, "thumbnail-name.jpg")

    def test_rejects_image_page_without_main_image(self) -> None:
        with self.assertRaises(EHentaiParseError):
            parse_image_page_html("<html><div id='i4'>001.jpg :: 100 KiB</div></html>")


class EHentaiTorrentParserTest(TestCase):
    def test_parses_torrent_candidates_html(self) -> None:
        candidates = parse_torrent_candidates_html(
            """
            <table>
              <tr>
                <td><a href="/torrent/123/sample.torrent">Sample Torrent</a></td>
                <td>Size: 12.3 MiB</td>
                <td>Seeds: 5</td>
                <td>Peers: 2</td>
                <td>Downloads: 42</td>
              </tr>
              <tr>
                <td><a href="https://example.test/not-a-torrent">ignored</a></td>
              </tr>
            </table>
            """,
            base_url="https://e-hentai.org/g/123/abcdef/",
        )

        self.assertEqual(
            candidates,
            (
                EHentaiTorrentCandidate(
                    url="https://e-hentai.org/torrent/123/sample.torrent",
                    title="Sample Torrent",
                    size="12.3 MiB",
                    seeds=5,
                    peers=2,
                    downloads=42,
                ),
            ),
        )

    def test_parses_ehtracker_torrent_links_with_query_parameters(self) -> None:
        candidates = parse_torrent_candidates_html(
            """
            <table>
              <tr>
                <td><a href="https://ehtracker.org/t/abc123.torrent?p=public">Public torrent</a></td>
                <td>Size: 1.2 GiB</td>
              </tr>
            </table>
            """,
            base_url="https://e-hentai.org/gallerytorrents.php?gid=123&t=abcdef",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://ehtracker.org/t/abc123.torrent?p=public")

    def test_returns_empty_tuple_when_no_torrents_exist(self) -> None:
        self.assertEqual(parse_torrent_candidates_html("<table></table>"), ())


class EHentaiListingParserTest(TestCase):
    def test_parses_listing_gallery_candidates(self) -> None:
        page = parse_listing_page_html(
            """
            <table class="itg">
              <tr>
                <td class="glthumb">
                  <a href="/g/123/abcdef/">
                    <img data-src="/thumb.jpg" title="Ignored Thumbnail Title">
                  </a>
                </td>
                <td>
                  <a href="https://e-hentai.org/g/123/abcdef/">
                    <div class="glink">Sample Gallery</div>
                  </a>
                  <div>Manga 2 pages uploader</div>
                </td>
              </tr>
            </table>
            <a id="dnext" href="/?f_search=sample&page=1">Next</a>
            """,
            base_url="https://e-hentai.org/?f_search=sample",
        )

        self.assertEqual(len(page.candidates), 1)
        candidate = page.candidates[0]
        self.assertEqual(candidate.gid, 123)
        self.assertEqual(candidate.token, "abcdef")
        self.assertEqual(candidate.url, "https://e-hentai.org/g/123/abcdef/")
        self.assertEqual(candidate.title, "Sample Gallery")
        self.assertEqual(candidate.thumbnail_url, "https://e-hentai.org/thumb.jpg")
        self.assertIn("Manga 2 pages uploader", candidate.summary)
        self.assertEqual(page.next_url, "https://e-hentai.org/?f_search=sample&page=1")

    def test_parses_cursor_pagination_links(self) -> None:
        page = parse_listing_page_html(
            """
            <table class="itg">
              <tr><td><a href="/g/123/abc/"><div class="glink">Test</div></a></td></tr>
            </table>
            <a id="dprev" href="/?f_search=tag&prev=abc123">Prev</a>
            <a id="dnext" href="/?f_search=tag&next=def456">Next</a>
            """,
            base_url="https://e-hentai.org/?f_search=tag",
        )

        self.assertEqual(page.prev_url, "https://e-hentai.org/?f_search=tag&prev=abc123")
        self.assertEqual(page.next_url, "https://e-hentai.org/?f_search=tag&next=def456")

    def test_no_cursor_links_when_absent(self) -> None:
        page = parse_listing_page_html(
            """
            <table class="itg">
              <tr><td><a href="/g/123/abc/"><div class="glink">Test</div></a></td></tr>
            </table>
            """,
            base_url="https://e-hentai.org/?f_search=tag",
        )

        self.assertIsNone(page.prev_url)
        self.assertIsNone(page.next_url)
