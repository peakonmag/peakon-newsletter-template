import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import main as app_main
from article_filter import (
    DiscoveredArticle,
    build_article_key,
)
from main import redact_secrets
from naver_news import NewsItem
from notion_service import (
    ARCHIVE_SCHEMA,
    KEYWORD_SCHEMA,
    DataSource,
    NotionClient,
    NOTION_API_VERSION,
    NotionError,
    NotionStructureError,
    build_archive_properties,
    build_archive_page_children,
    discover_data_sources,
    exclude_existing_articles,
    load_active_keywords,
    parse_keyword_pages,
    parse_root_page_id,
    update_keyword_last_run,
    validate_schema,
)


KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 27, 17, 0, tzinfo=KST)


def text_items(value: str) -> list[dict]:
    return [{"type": "text", "plain_text": value, "text": {"content": value}}]


def make_keyword_page(
    *,
    page_id: str = "keyword-row",
    keyword: str = " AI 에이전트 ",
    enabled: bool = True,
    lookback_hours: float | None = None,
    max_articles: float | None = None,
) -> dict:
    return {
        "id": page_id,
        "properties": {
            "키워드": {"type": "title", "title": text_items(keyword)},
            "사용": {"type": "checkbox", "checkbox": enabled},
            "최근 시간 (Hour)": {
                "type": "number",
                "number": lookback_hours,
            },
            "최대 기사 수": {"type": "number", "number": max_articles},
            "마지막 실행": {"type": "date", "date": None},
        },
    }


def make_article(
    title: str,
    *,
    originallink: str = "",
    link: str = "",
) -> DiscoveredArticle:
    return DiscoveredArticle(
        news=NewsItem(
            title=title,
            summary="네이버 검색 description",
            published_at="2026-07-27 17:00:00 KST",
            original_link=originallink or link or "링크 없음",
            published_datetime=NOW,
            originallink=originallink,
            link=link,
        ),
        matched_queries=["AI 에이전트"],
    )


class KeywordParsingTests(unittest.TestCase):
    def test_each_collection_load_reads_current_notion_rows_again(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.pages = [
                    make_keyword_page(page_id="first", keyword="Codex")
                ]
                self.query_count = 0

            def query_data_source(self, *args, **kwargs) -> list[dict]:
                self.query_count += 1
                return self.pages

        client = FakeClient()
        first = load_active_keywords(client, "keyword-source")
        client.pages = [
            make_keyword_page(page_id="second", keyword="Claude Code")
        ]
        second = load_active_keywords(client, "keyword-source")

        self.assertEqual([setting.keyword for setting in first], ["Codex"])
        self.assertEqual(
            [setting.keyword for setting in second],
            ["Claude Code"],
        )
        self.assertEqual(client.query_count, 2)

    def test_notion_keyword_is_trimmed_and_parsed(self) -> None:
        settings = parse_keyword_pages(
            [
                make_keyword_page(
                    keyword="  Claude Code  ",
                    lookback_hours=12,
                    max_articles=25,
                )
            ]
        )

        self.assertEqual(len(settings), 1)
        self.assertEqual(settings[0].keyword, "Claude Code")
        self.assertEqual(settings[0].lookback_hours, 12)
        self.assertEqual(settings[0].max_articles, 25)

    def test_disabled_keyword_is_excluded(self) -> None:
        settings = parse_keyword_pages(
            [make_keyword_page(enabled=False, keyword="사용 안 함")]
        )

        self.assertEqual(settings, [])

    def test_empty_keyword_is_excluded(self) -> None:
        settings = parse_keyword_pages([make_keyword_page(keyword=" \n ")])

        self.assertEqual(settings, [])

    def test_empty_numbers_use_defaults(self) -> None:
        settings = parse_keyword_pages([make_keyword_page()])

        self.assertEqual(settings[0].lookback_hours, 24)
        self.assertEqual(settings[0].max_articles, 10)

    def test_case_insensitive_duplicate_keyword_is_searched_once(self) -> None:
        settings = parse_keyword_pages(
            [
                make_keyword_page(page_id="one", keyword="Codex"),
                make_keyword_page(page_id="two", keyword="codex"),
            ]
        )

        self.assertEqual([setting.keyword for setting in settings], ["Codex"])

    def test_keyword_schema_has_no_exclusions_or_result_text(self) -> None:
        self.assertNotIn("제외어", KEYWORD_SCHEMA)
        self.assertNotIn("실행 결과", KEYWORD_SCHEMA)

    def test_only_last_run_is_updated_after_collection(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.updated_properties = None

            def update_page(self, page_id: str, properties: dict) -> dict:
                self.assert_page_id = page_id
                self.updated_properties = properties
                return {"id": page_id}

        client = FakeClient()
        setting = parse_keyword_pages([make_keyword_page()])[0]

        update_keyword_last_run(client, setting, executed_at=NOW)

        self.assertEqual(client.assert_page_id, "keyword-row")
        self.assertEqual(
            client.updated_properties,
            {"마지막 실행": {"date": {"start": NOW.isoformat()}}},
        )


class ArticleArchiveTests(unittest.TestCase):
    def test_archive_page_content_contains_summary_and_article_links(self) -> None:
        children = build_archive_page_children(
            summary="네이버 검색 description",
            original_link="https://news.example/original",
            naver_link="https://n.news.naver.com/article/1",
        )

        self.assertEqual(children[0]["type"], "heading_2")
        self.assertEqual(
            children[0]["heading_2"]["rich_text"][0]["text"]["content"],
            "검색 요약",
        )
        self.assertEqual(
            children[1]["paragraph"]["rich_text"][0]["text"]["content"],
            "네이버 검색 description",
        )
        link_urls = [
            block["bulleted_list_item"]["rich_text"][0]["text"]["link"]["url"]
            for block in children
            if block["type"] == "bulleted_list_item"
        ]
        self.assertEqual(
            link_urls,
            [
                "https://news.example/original",
                "https://n.news.naver.com/article/1",
            ],
        )

    def test_search_keywords_are_saved_as_multi_select_tags(self) -> None:
        article = make_article(
            "공통 기사",
            originallink="https://news.example/shared",
        )
        article.matched_queries = ["AI 에이전트", "Codex", "Claude Code"]

        properties = build_archive_properties(article, NOW)

        self.assertEqual(
            properties["검색 키워드"],
            {
                "multi_select": [
                    {"name": "AI 에이전트"},
                    {"name": "Codex"},
                    {"name": "Claude Code"},
                ]
            },
        )

    def test_archive_uses_search_summary_property_name(self) -> None:
        article = make_article(
            "기사",
            originallink="https://news.example/article",
        )

        properties = build_archive_properties(article, NOW)

        self.assertIn("검색 요약", properties)
        self.assertNotIn("AI 요약", properties)
        self.assertNotIn("기사 전문 요약", properties)

    def test_article_key_is_sha256_of_preferred_original_link(self) -> None:
        article = make_article(
            "기사",
            originallink="https://news.example/original",
            link="https://n.news.naver.com/article/1",
        )

        expected = hashlib.sha256(
            b"https://news.example/original"
        ).hexdigest()

        self.assertEqual(build_article_key(article.news), expected)
        self.assertEqual(len(build_article_key(article.news)), 64)

    def test_article_key_falls_back_to_normalized_title(self) -> None:
        first = make_article("<b>AI</b>   NEWS")
        second = make_article("ai news")

        self.assertEqual(
            build_article_key(first.news),
            build_article_key(second.news),
        )

    def test_existing_article_is_excluded(self) -> None:
        old_article = make_article(
            "기존 기사",
            originallink="https://news.example/old",
        )
        new_article = make_article(
            "새 기사",
            originallink="https://news.example/new",
        )

        selected, existing_count = exclude_existing_articles(
            [old_article, new_article],
            {build_article_key(old_article.news)},
        )

        self.assertEqual(selected, [new_article])
        self.assertEqual(existing_count, 1)


class NotionStructureTests(unittest.TestCase):
    def test_duplicate_data_source_name_is_not_selected_arbitrarily(self) -> None:
        class FakeClient:
            def list_block_children(self, block_id: str) -> list[dict]:
                if block_id != "root":
                    return []
                return [
                    {
                        "id": "database-one",
                        "type": "child_database",
                        "has_children": False,
                    },
                    {
                        "id": "database-two",
                        "type": "child_database",
                        "has_children": False,
                    },
                    {
                        "id": "database-archive",
                        "type": "child_database",
                        "has_children": False,
                    },
                ]

            def retrieve_database(self, database_id: str) -> dict:
                if database_id == "database-archive":
                    return {
                        "data_sources": [
                            {"id": "archive", "name": "뉴스 아카이브"}
                        ]
                    }
                return {
                    "data_sources": [
                        {"id": f"source-{database_id}", "name": "키워드 설정"}
                    ]
                }

            def retrieve_data_source(self, data_source_id: str) -> dict:
                raise AssertionError("중복 오류 전에 호출되면 안 됩니다.")

        with self.assertRaises(NotionStructureError) as caught:
            discover_data_sources(FakeClient(), "root")

        self.assertIn("'키워드 설정' 데이터 소스가 2개", str(caught.exception))

    def test_wrong_notion_schema_lists_missing_and_wrong_types(self) -> None:
        schema = {
            name: {"type": property_type}
            for name, property_type in ARCHIVE_SCHEMA.items()
        }
        schema.pop("검색 요약")
        schema["기사 키"] = {"type": "url"}
        source = DataSource(
            id="archive",
            name="뉴스 아카이브",
            properties=schema,
        )

        with self.assertRaises(NotionStructureError) as caught:
            validate_schema(source, ARCHIVE_SCHEMA)

        message = str(caught.exception)
        self.assertIn("뉴스 아카이브.검색 요약", message)
        self.assertIn("필요한 유형: rich_text", message)
        self.assertIn("뉴스 아카이브.기사 키", message)
        self.assertIn("필요: rich_text, 현재: url", message)

    def test_root_page_id_is_extracted_from_notion_url(self) -> None:
        page_id = parse_root_page_id(
            "https://www.notion.so/workspace/"
            "Dashboard-1234567890abcdef1234567890abcdef?pvs=4"
        )

        self.assertEqual(
            page_id,
            "12345678-90ab-cdef-1234-567890abcdef",
        )

    def test_secret_values_are_redacted_from_error_log_text(self) -> None:
        token = "test-token-value-that-must-not-be-logged"
        client_secret = "test-client-secret-that-must-not-be-logged"
        message = f"연결 실패: {token} / {client_secret}"

        redacted = redact_secrets(message, [token, client_secret])

        self.assertNotIn(token, redacted)
        self.assertNotIn(client_secret, redacted)
        self.assertEqual(redacted.count("[비밀값 숨김]"), 2)

    def test_main_error_log_does_not_expose_secret_values(self) -> None:
        environment = {
            "NAVER_CLIENT_ID": "fake-client-id-for-redaction-test",
            "NAVER_CLIENT_SECRET": "fake-client-secret-for-redaction-test",
            "NOTION_TOKEN": "fake-notion-token-for-redaction-test",
            "NOTION_ROOT_PAGE_URL": (
                "https://www.notion.so/"
                "1234567890abcdef1234567890abcdef"
            ),
        }

        class FailingNotionClient:
            def __init__(self, token: str) -> None:
                self.token = token

            def retrieve_page(self, page_id: str) -> dict:
                raise NotionError(
                    "인증 실패: "
                    f"{self.token} / {environment['NAVER_CLIENT_ID']} / "
                    f"{environment['NAVER_CLIENT_SECRET']}"
                )

        error_output = io.StringIO()
        with (
            patch.object(app_main, "load_dotenv"),
            patch.object(
                app_main,
                "get_environment",
                return_value=environment,
            ),
            patch.object(app_main, "NotionClient", FailingNotionClient),
            redirect_stderr(error_output),
        ):
            exit_code = app_main.main()

        logged_text = error_output.getvalue()
        self.assertEqual(exit_code, 1)
        for secret_name in (
            "NAVER_CLIENT_ID",
            "NAVER_CLIENT_SECRET",
            "NOTION_TOKEN",
        ):
            self.assertNotIn(environment[secret_name], logged_text)
        self.assertEqual(logged_text.count("[비밀값 숨김]"), 3)


class NotionApiTests(unittest.TestCase):
    def test_current_data_source_query_endpoint_is_used(self) -> None:
        captured_request = None

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "object": "list",
                        "results": [],
                        "has_more": False,
                        "next_cursor": None,
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            nonlocal captured_request
            captured_request = request
            self.assertEqual(timeout, 15)
            return FakeResponse()

        with patch("notion_service.urlopen", side_effect=fake_urlopen):
            NotionClient("test-notion-token").query_data_source(
                "source-id",
                filter_body={
                    "property": "사용",
                    "checkbox": {"equals": True},
                },
            )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.get_method(), "POST")
        self.assertIn(
            "/v1/data_sources/source-id/query",
            captured_request.full_url,
        )
        self.assertNotIn("/databases/source-id/query", captured_request.full_url)
        self.assertEqual(
            captured_request.get_header("Notion-version"),
            NOTION_API_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
