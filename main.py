import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from article_filter import (
    ArticleMatch,
    DiscoveredArticle,
    FilterResult,
    build_article_key,
    filter_articles,
)
from naver_news import NaverNewsError, fetch_latest_news
from notion_service import (
    ARCHIVE_DATA_SOURCE_NAME,
    KEYWORD_DATA_SOURCE_NAME,
    KeywordSetting,
    NotionClient,
    NotionError,
    archive_articles,
    discover_data_sources,
    exclude_existing_articles,
    find_existing_article_keys,
    load_active_keywords,
    parse_root_page_id,
    update_keyword_last_run,
    validate_required_schemas,
)


KST = ZoneInfo("Asia/Seoul")
REQUIRED_ENVIRONMENT_VARIABLES = (
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "NOTION_TOKEN",
    "NOTION_ROOT_PAGE_URL",
)


@dataclass(frozen=True)
class CollectionRun:
    result: FilterResult
    fetched_by_keyword: dict[str, int]


def get_environment() -> dict[str, str]:
    values = {
        name: os.getenv(name, "").strip()
        for name in REQUIRED_ENVIRONMENT_VARIABLES
    }
    missing = [
        name for name in REQUIRED_ENVIRONMENT_VARIABLES if not values[name]
    ]
    if missing:
        raise ValueError(
            f".env에 {', '.join(missing)}을(를) 설정해 주세요."
        )
    return values


def redact_secrets(message: str, secret_values: Iterable[str]) -> str:
    redacted = message
    for value in secret_values:
        if value:
            redacted = redacted.replace(value, "[비밀값 숨김]")
    return redacted


def fetch_article_matches(
    settings: Iterable[KeywordSetting],
    client_id: str,
    client_secret: str,
) -> CollectionRun:
    matches: list[ArticleMatch] = []
    fetched_by_keyword: dict[str, int] = {}

    for setting in settings:
        news_items = fetch_latest_news(
            client_id=client_id,
            client_secret=client_secret,
            query=setting.keyword,
            count=setting.max_articles,
        )
        fetched_by_keyword[setting.keyword] = len(news_items)
        matches.extend(
            ArticleMatch(
                news=news,
                query=setting.keyword,
                lookback_hours=setting.lookback_hours,
            )
            for news in news_items
        )

    return CollectionRun(
        result=filter_articles(
            matches=matches,
            lookback_hours=24,
            max_articles=None,
        ),
        fetched_by_keyword=fetched_by_keyword,
    )


def print_filter_statistics(
    result: FilterResult,
    *,
    existing_count: int,
    new_count: int,
) -> None:
    statistics = result.statistics
    print("\n필터링 통계")
    print(f"- API에서 가져온 전체 기사 수: {statistics.fetched_count}")
    print(f"- 시간 조건으로 제외된 기사 수: {statistics.time_excluded_count}")
    print(f"- 실행 내 중복으로 병합된 기사 수: {statistics.duplicate_count}")
    print(f"- 뉴스 아카이브에 이미 있던 기사 수: {existing_count}")
    print(f"- 뉴스 아카이브에 새로 저장한 기사 수: {new_count}")


def update_keyword_last_runs(
    notion: NotionClient,
    settings: Iterable[KeywordSetting],
    executed_at: datetime,
) -> None:
    for setting in settings:
        update_keyword_last_run(
            notion,
            setting,
            executed_at=executed_at,
        )


def main() -> int:
    load_dotenv()
    environment: dict[str, str] = {}

    try:
        environment = get_environment()
        root_page_id = parse_root_page_id(
            environment["NOTION_ROOT_PAGE_URL"]
        )
        notion = NotionClient(environment["NOTION_TOKEN"])

        notion.retrieve_page(root_page_id)
        data_sources = discover_data_sources(notion, root_page_id)
        validate_required_schemas(data_sources)

        keyword_source = data_sources[KEYWORD_DATA_SOURCE_NAME]
        archive_source = data_sources[ARCHIVE_DATA_SOURCE_NAME]
        settings = load_active_keywords(notion, keyword_source.id)
        print(f"활성 키워드: {len(settings)}개")
        if not settings:
            print(
                "사용 체크박스가 켜진 유효한 키워드가 없습니다. "
                "Notion의 '키워드 설정'을 확인해 주세요."
            )
            return 0

        executed_at = datetime.now(KST)
        collection = fetch_article_matches(
            settings,
            client_id=environment["NAVER_CLIENT_ID"],
            client_secret=environment["NAVER_CLIENT_SECRET"],
        )
        article_keys = [
            build_article_key(article.news)
            for article in collection.result.articles
        ]
        existing_keys = find_existing_article_keys(
            notion,
            archive_source.id,
            article_keys,
        )
        new_articles, existing_count = exclude_existing_articles(
            collection.result.articles,
            existing_keys,
        )
        archived_count = archive_articles(
            notion,
            archive_source.id,
            new_articles,
            collected_at=executed_at,
        )
        update_keyword_last_runs(
            notion,
            settings,
            executed_at,
        )
        print_filter_statistics(
            collection.result,
            existing_count=existing_count,
            new_count=archived_count,
        )

        if not archived_count:
            print("조건에 맞는 새 기사가 없습니다.")
    except (ValueError, NotionError, NaverNewsError) as error:
        secret_values = (
            environment.get("NAVER_CLIENT_ID", ""),
            environment.get("NAVER_CLIENT_SECRET", ""),
            environment.get("NOTION_TOKEN", ""),
        )
        print(
            f"오류: {redact_secrets(str(error), secret_values)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
