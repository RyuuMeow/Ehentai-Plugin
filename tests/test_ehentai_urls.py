from unittest import TestCase

from ehentai.urls import (
    EHentaiSite,
    EHentaiUrlKind,
    base_url,
    build_gallery_url,
    parse_ehentai_url,
)


class EHentaiUrlParserTest(TestCase):
    def test_parses_gallery_url(self) -> None:
        info = parse_ehentai_url("https://e-hentai.org/g/123/abcdef/")

        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.site, EHentaiSite.E_HENTAI)
        self.assertEqual(info.kind, EHentaiUrlKind.GALLERY)
        self.assertEqual(info.gid, 123)
        self.assertEqual(info.token, "abcdef")

    def test_parses_exhentai_gallery_url(self) -> None:
        info = parse_ehentai_url("https://exhentai.org/g/456/012abc")

        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.site, EHentaiSite.EX_HENTAI)
        self.assertEqual(info.kind, EHentaiUrlKind.GALLERY)
        self.assertEqual(info.gid, 456)
        self.assertEqual(info.token, "012abc")

    def test_parses_image_page_url(self) -> None:
        info = parse_ehentai_url("https://e-hentai.org/s/PageToken123/123-4")

        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.kind, EHentaiUrlKind.IMAGE_PAGE)
        self.assertEqual(info.gid, 123)
        self.assertEqual(info.page_token, "PageToken123")
        self.assertEqual(info.page, 4)

    def test_parses_listing_labels(self) -> None:
        cases = {
            "https://e-hentai.org/tag/female:maid": "tag",
            "https://e-hentai.org/uploader/example": "uploader",
            "https://e-hentai.org/favorites.php": "favorites",
            "https://e-hentai.org/watched": "watched",
            "https://e-hentai.org/popular": "popular",
            "https://e-hentai.org/toplists.php": "toplists",
            "https://e-hentai.org/?f_search=maid": "search",
            "https://e-hentai.org/": "search",
            "https://e-hentai.org/category/misc": "listing",
        }

        for url, label in cases.items():
            with self.subTest(url=url):
                info = parse_ehentai_url(url)

                self.assertIsNotNone(info)
                assert info is not None
                self.assertEqual(info.kind, EHentaiUrlKind.LISTING)
                self.assertEqual(info.listing_label, label)

    def test_rejects_api_and_unknown_hosts(self) -> None:
        self.assertIsNone(parse_ehentai_url("https://e-hentai.org/g/123/not-a-hex-token/"))
        self.assertIsNone(parse_ehentai_url("https://api.e-hentai.org/api.php"))
        self.assertIsNone(parse_ehentai_url("https://example.com/g/123/abcdef/"))

    def test_build_gallery_url(self) -> None:
        self.assertEqual(base_url(EHentaiSite.EX_HENTAI), "https://exhentai.org")
        self.assertEqual(
            build_gallery_url(123, "abcdef", EHentaiSite.E_HENTAI),
            "https://e-hentai.org/g/123/abcdef/",
        )
