import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

from article_filter import DiscoveredArticle, build_article_key


NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2026-03-11"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_ARTICLES = 10
MAX_NAVER_RESULTS = 100
RICH_TEXT_LIMIT = 2000

KEYWORD_DATA_SOURCE_NAME = "키워드 설정"
ARCHIVE_DATA_SOURCE_NAME = "뉴스 아카이브"

KEYWORD_SCHEMA = {
    "키워드": "title",
    "사용": "checkbox",
    "최근 시간 (Hour)": "number",
    "최대 기사 수": "number",
    "마지막 실행": "date",
}

ARCHIVE_SCHEMA = {
    "제목": "title",
    "기사 키": "rich_text",
    "원문 URL": "url",
    "네이버 링크": "url",
    "발행 시각": "date",
    "수집 시각": "date",
    "검색 키워드": "multi_select",
    "검색 요약": "rich_text",
    "상태": "select",
}


class NotionError(Exception):
    pass


class NotionStructureError(NotionError):
    pass


@dataclass(frozen=True)
class DataSource:
    id: str
    name: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class KeywordSetting:
    page_id: str
    keyword: str
    lookback_hours: float
    max_articles: int


def parse_root_page_id(root_page_url: str) -> str:
    value = root_page_url.strip()
    if not value:
        raise NotionStructureError(
            "NOTION_ROOT_PAGE_URL이 비어 있습니다. Notion 대시보드 페이지의 "
            "전체 URL을 입력해 주세요."
        )

    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise NotionStructureError(
            "NOTION_ROOT_PAGE_URL 형식이 올바르지 않습니다."
        ) from error

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NotionStructureError(
            "NOTION_ROOT_PAGE_URL에는 https://로 시작하는 Notion 페이지 URL을 "
            "입력해 주세요."
        )

    candidates = re.findall(
        r"(?i)(?<![0-9a-f])(?:[0-9a-f]{32}|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12})(?![0-9a-f])",
        f"{parsed.path}?{parsed.query}",
    )
    if not candidates:
        raise NotionStructureError(
            "NOTION_ROOT_PAGE_URL에서 페이지 ID를 찾지 못했습니다. "
            "브라우저에서 대시보드 페이지의 링크를 다시 복사해 주세요."
        )

    try:
        return str(UUID(candidates[-1]))
    except ValueError as error:
        raise NotionStructureError(
            "NOTION_ROOT_PAGE_URL의 페이지 ID가 올바르지 않습니다."
        ) from error


def _notion_error_message(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    return "Notion이 요청을 처리하지 못했습니다."


class NotionClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{NOTION_API_BASE_URL}{path}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        request = Request(
            url,
            data=(
                json.dumps(body, ensure_ascii=False).encode("utf-8")
                if body is not None
                else None
            ),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
                "User-Agent": "naver-news-notion/1.0",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            message = _notion_error_message(error)
            raise NotionError(
                f"Notion API 요청 실패 (HTTP {error.code}): {message}"
            ) from error
        except URLError as error:
            raise NotionError(
                "Notion API에 연결하지 못했습니다. 네트워크 상태를 확인해 주세요."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NotionError(
                "Notion API 응답을 JSON으로 해석하지 못했습니다."
            ) from error

    def retrieve_bot_user(self) -> dict[str, Any]:
        return self.request("GET", "/users/me")

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self.request("GET", f"/pages/{page_id}")

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query: dict[str, Any] = {"page_size": 100}
            if cursor:
                query["start_cursor"] = cursor
            response = self.request(
                "GET",
                f"/blocks/{block_id}/children",
                query=query,
            )
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
            if not cursor:
                break
        return results

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self.request("GET", f"/databases/{database_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self.request("GET", f"/data_sources/{data_source_id}")

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter_body: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        filter_properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if filter_body is not None:
                body["filter"] = filter_body
            if sorts is not None:
                body["sorts"] = sorts
            if cursor:
                body["start_cursor"] = cursor
            query = (
                {"filter_properties[]": filter_properties}
                if filter_properties
                else None
            )
            response = self.request(
                "POST",
                f"/data_sources/{data_source_id}/query",
                body=body,
                query=query,
            )
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
            if not cursor:
                break
        return results

    def create_page(
        self,
        data_source_id: str,
        properties: dict[str, Any],
        *,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": data_source_id,
            },
            "properties": properties,
        }
        if children:
            body["children"] = children
        return self.request(
            "POST",
            "/pages",
            body=body,
        )

    def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/pages/{page_id}",
            body={"properties": properties},
        )

    def append_block_children(
        self,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/blocks/{block_id}/children",
            body={"children": children},
        )


def _find_database_ids(client: NotionClient, root_page_id: str) -> list[str]:
    pending_block_ids = [root_page_id]
    visited_block_ids: set[str] = set()
    database_ids: list[str] = []
    known_database_ids: set[str] = set()

    while pending_block_ids:
        block_id = pending_block_ids.pop()
        if block_id in visited_block_ids:
            continue
        visited_block_ids.add(block_id)

        for block in client.list_block_children(block_id):
            block_type = block.get("type")
            child_id = block.get("id")
            database_id = ""
            if block_type == "child_database" and isinstance(child_id, str):
                database_id = child_id
            elif block_type == "link_to_page":
                link = block.get("link_to_page", {})
                if link.get("type") == "database_id":
                    database_id = link.get("database_id", "")

            if database_id and database_id not in known_database_ids:
                known_database_ids.add(database_id)
                database_ids.append(database_id)

            if (
                block.get("has_children")
                and isinstance(child_id, str)
                and block_type != "child_database"
            ):
                pending_block_ids.append(child_id)

    return database_ids


def discover_data_sources(
    client: NotionClient,
    root_page_id: str,
    required_names: Iterable[str] = (
        KEYWORD_DATA_SOURCE_NAME,
        ARCHIVE_DATA_SOURCE_NAME,
    ),
) -> dict[str, DataSource]:
    required = tuple(required_names)
    matches: dict[str, list[dict[str, str]]] = {name: [] for name in required}

    for database_id in _find_database_ids(client, root_page_id):
        database = client.retrieve_database(database_id)
        for item in database.get("data_sources", []):
            name = item.get("name")
            data_source_id = item.get("id")
            if (
                isinstance(name, str)
                and name.strip() in matches
                and isinstance(data_source_id, str)
            ):
                matches[name.strip()].append(
                    {"id": data_source_id, "database_id": database_id}
                )

    problems: list[str] = []
    for name, items in matches.items():
        unique_ids = {item["id"] for item in items}
        if not unique_ids:
            problems.append(f"'{name}' 데이터 소스를 찾지 못했습니다.")
        elif len(unique_ids) > 1:
            problems.append(
                f"'{name}' 데이터 소스가 {len(unique_ids)}개 발견되었습니다. "
                "이름을 고유하게 바꿔 주세요."
            )
    if problems:
        raise NotionStructureError("\n".join(problems))

    discovered: dict[str, DataSource] = {}
    for name, items in matches.items():
        data_source_id = items[0]["id"]
        payload = client.retrieve_data_source(data_source_id)
        discovered[name] = DataSource(
            id=data_source_id,
            name=name,
            properties=payload.get("properties", {}),
        )
    return discovered


def validate_schema(
    data_source: DataSource,
    expected_schema: dict[str, str],
) -> None:
    problems: list[str] = []
    for property_name, expected_type in expected_schema.items():
        property_schema = data_source.properties.get(property_name)
        if not isinstance(property_schema, dict):
            problems.append(
                f"- '{data_source.name}.{property_name}' 속성이 없습니다. "
                f"필요한 유형: {expected_type}"
            )
            continue
        actual_type = property_schema.get("type")
        if actual_type != expected_type:
            problems.append(
                f"- '{data_source.name}.{property_name}' 유형이 잘못되었습니다. "
                f"필요: {expected_type}, 현재: {actual_type or '알 수 없음'}"
            )
    if problems:
        raise NotionStructureError(
            "Notion 데이터 소스 구조를 확인해 주세요.\n" + "\n".join(problems)
        )


def validate_required_schemas(data_sources: dict[str, DataSource]) -> None:
    validate_schema(data_sources[KEYWORD_DATA_SOURCE_NAME], KEYWORD_SCHEMA)
    validate_schema(data_sources[ARCHIVE_DATA_SOURCE_NAME], ARCHIVE_SCHEMA)


def rich_text_to_plain_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str):
            parts.append(plain_text)
            continue
        text_content = item.get("text", {}).get("content")
        if isinstance(text_content, str):
            parts.append(text_content)
    return "".join(parts)


def _property_value(
    page: dict[str, Any],
    property_name: str,
    expected_type: str,
) -> Any:
    properties = page.get("properties", {})
    prop = properties.get(property_name, {})
    if prop.get("type") != expected_type:
        page_id = page.get("id", "알 수 없는 행")
        raise NotionStructureError(
            f"키워드 설정의 '{property_name}' 값을 읽을 수 없습니다. "
            f"행 ID: {page_id}"
        )
    return prop.get(expected_type)


def _positive_number_or_default(
    value: Any,
    *,
    default: float,
    property_name: str,
    keyword: str,
) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise NotionStructureError(
            f"키워드 '{keyword}'의 '{property_name}'은(는) 0보다 큰 숫자여야 "
            f"합니다. 현재 값: {value!r}"
        )
    return float(value)


def parse_keyword_pages(pages: Iterable[dict[str, Any]]) -> list[KeywordSetting]:
    settings: list[KeywordSetting] = []
    seen_keywords: set[str] = set()

    for page in pages:
        enabled = _property_value(page, "사용", "checkbox")
        if enabled is not True:
            continue

        keyword = rich_text_to_plain_text(
            _property_value(page, "키워드", "title")
        ).strip()
        if not keyword:
            continue
        normalized_keyword = keyword.casefold()
        if normalized_keyword in seen_keywords:
            continue

        lookback_hours = _positive_number_or_default(
            _property_value(page, "최근 시간 (Hour)", "number"),
            default=DEFAULT_LOOKBACK_HOURS,
            property_name="최근 시간 (Hour)",
            keyword=keyword,
        )
        max_articles_number = _positive_number_or_default(
            _property_value(page, "최대 기사 수", "number"),
            default=DEFAULT_MAX_ARTICLES,
            property_name="최대 기사 수",
            keyword=keyword,
        )
        if not max_articles_number.is_integer():
            raise NotionStructureError(
                f"키워드 '{keyword}'의 '최대 기사 수'는 정수여야 합니다. "
                f"현재 값: {max_articles_number:g}"
            )
        max_articles = int(max_articles_number)
        if max_articles > MAX_NAVER_RESULTS:
            raise NotionStructureError(
                f"키워드 '{keyword}'의 '최대 기사 수'는 네이버 API 제한에 맞게 "
                f"{MAX_NAVER_RESULTS} 이하여야 합니다. 현재 값: {max_articles}"
            )

        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id:
            raise NotionStructureError(
                f"키워드 '{keyword}' 행의 Notion 페이지 ID를 찾지 못했습니다."
            )

        seen_keywords.add(normalized_keyword)
        settings.append(
            KeywordSetting(
                page_id=page_id,
                keyword=keyword,
                lookback_hours=lookback_hours,
                max_articles=max_articles,
            )
        )

    return settings


def load_active_keywords(
    client: NotionClient,
    keyword_data_source_id: str,
) -> list[KeywordSetting]:
    pages = client.query_data_source(
        keyword_data_source_id,
        filter_body={
            "property": "사용",
            "checkbox": {"equals": True},
        },
        sorts=[{"timestamp": "created_time", "direction": "ascending"}],
    )
    return parse_keyword_pages(pages)


def find_existing_article_keys(
    client: NotionClient,
    archive_data_source_id: str,
    article_keys: Iterable[str],
) -> set[str]:
    unique_keys = list(dict.fromkeys(article_keys))
    existing: set[str] = set()
    batch_size = 50
    for index in range(0, len(unique_keys), batch_size):
        batch = unique_keys[index : index + batch_size]
        if not batch:
            continue
        filters = [
            {
                "property": "기사 키",
                "rich_text": {"equals": article_key},
            }
            for article_key in batch
        ]
        filter_body = filters[0] if len(filters) == 1 else {"or": filters}
        pages = client.query_data_source(
            archive_data_source_id,
            filter_body=filter_body,
            filter_properties=["기사 키"],
        )
        for page in pages:
            value = page.get("properties", {}).get("기사 키", {})
            article_key = rich_text_to_plain_text(value.get("rich_text")).strip()
            if article_key:
                existing.add(article_key)
    return existing


def exclude_existing_articles(
    articles: Iterable[DiscoveredArticle],
    existing_keys: set[str],
) -> tuple[list[DiscoveredArticle], int]:
    new_articles: list[DiscoveredArticle] = []
    existing_count = 0
    for article in articles:
        if build_article_key(article.news) in existing_keys:
            existing_count += 1
        else:
            new_articles.append(article)
    return new_articles, existing_count


def _text_property(content: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": content[:RICH_TEXT_LIMIT]}}]


def build_archive_properties(
    article: DiscoveredArticle,
    collected_at: datetime,
) -> dict[str, Any]:
    news = article.news
    properties: dict[str, Any] = {
        "제목": {"title": _text_property(news.title)},
        "기사 키": {"rich_text": _text_property(build_article_key(news))},
        "원문 URL": {"url": news.originallink.strip() or None},
        "네이버 링크": {"url": news.link.strip() or None},
        "수집 시각": {"date": {"start": collected_at.isoformat()}},
        "검색 키워드": {
            "multi_select": [
                {"name": keyword[:100]} for keyword in article.matched_queries
            ]
        },
        "검색 요약": {"rich_text": _text_property(news.summary)},
        "상태": {"select": {"name": "신규"}},
    }
    if news.published_datetime is not None:
        properties["발행 시각"] = {
            "date": {"start": news.published_datetime.isoformat()}
        }
    return properties


def _linked_text(label: str, url: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": {
                "content": label,
                "link": {"url": url},
            },
        }
    ]


def build_archive_page_children(
    *,
    summary: str,
    original_link: str,
    naver_link: str,
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": _text_property("검색 요약")},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": _text_property(
                    summary.strip() or "검색 요약이 제공되지 않았습니다."
                )
            },
        },
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "ℹ️"},
                "color": "gray_background",
                "rich_text": _text_property(
                    "검색 요약은 네이버 뉴스 검색 API의 description이며, "
                    "기사 본문이나 AI가 만든 요약이 아닙니다."
                ),
            },
        },
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": _text_property("기사 링크")},
        },
    ]

    links = (
        ("원문 기사 보기", original_link.strip()),
        ("네이버에서 보기", naver_link.strip()),
    )
    linked_items = [
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": _linked_text(label, url),
            },
        }
        for label, url in links
        if url
    ]
    if linked_items:
        children.extend(linked_items)
    else:
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": _text_property(
                        "제공된 기사 링크가 없습니다."
                    )
                },
            }
        )
    return children


def archive_articles(
    client: NotionClient,
    archive_data_source_id: str,
    articles: Iterable[DiscoveredArticle],
    collected_at: datetime,
) -> int:
    archived_count = 0
    for article in articles:
        page = client.create_page(
            archive_data_source_id,
            build_archive_properties(article, collected_at),
            children=build_archive_page_children(
                summary=article.news.summary,
                original_link=article.news.originallink,
                naver_link=article.news.link,
            ),
        )
        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id:
            raise NotionError(
                f"'{article.news.title}' 기사를 저장했지만 페이지 ID를 받지 못했습니다."
            )
        archived_count += 1
    return archived_count


def update_keyword_last_run(
    client: NotionClient,
    setting: KeywordSetting,
    *,
    executed_at: datetime,
) -> None:
    client.update_page(
        setting.page_id,
        {"마지막 실행": {"date": {"start": executed_at.isoformat()}}},
    )
