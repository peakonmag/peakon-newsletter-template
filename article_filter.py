import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from naver_news import NewsItem, clean_html


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class ArticleMatch:
    news: NewsItem
    query: str
    lookback_hours: float | None = None


@dataclass
class DiscoveredArticle:
    news: NewsItem
    matched_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FilterStatistics:
    fetched_count: int
    time_excluded_count: int
    duplicate_count: int
    final_count: int


@dataclass(frozen=True)
class FilterResult:
    articles: list[DiscoveredArticle]
    statistics: FilterStatistics


def normalize_datetime_to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def get_published_datetime(news: NewsItem) -> datetime | None:
    if news.published_datetime is None:
        return None
    return normalize_datetime_to_kst(news.published_datetime)


def is_recent_article(news: NewsItem, cutoff: datetime) -> bool:
    published_datetime = get_published_datetime(news)
    if published_datetime is None:
        return False
    return published_datetime >= normalize_datetime_to_kst(cutoff)


def normalize_title(title: str) -> str:
    return clean_html(title).casefold()


def build_duplicate_key(news: NewsItem) -> tuple[str, str]:
    originallink = news.originallink.strip()
    link = news.link.strip()

    if originallink:
        return "originallink", originallink
    if link:
        return "link", link
    return "title", normalize_title(news.title)


def build_article_key(news: NewsItem) -> str:
    _, key_value = build_duplicate_key(news)
    return hashlib.sha256(key_value.encode("utf-8")).hexdigest()


def append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def merge_match(
    article: DiscoveredArticle,
    match: ArticleMatch,
) -> None:
    append_unique(article.matched_queries, match.query)

    existing_datetime = get_published_datetime(article.news)
    matched_datetime = get_published_datetime(match.news)
    if (
        matched_datetime is not None
        and (existing_datetime is None or matched_datetime > existing_datetime)
    ):
        article.news = match.news


def filter_articles(
    matches: list[ArticleMatch],
    lookback_hours: int,
    max_articles: int | None,
    now: datetime | None = None,
) -> FilterResult:
    current_time = normalize_datetime_to_kst(now or datetime.now(KST))
    cutoff = current_time - timedelta(hours=lookback_hours)

    time_excluded_count = 0
    duplicate_count = 0
    articles_by_key: dict[tuple[str, str], DiscoveredArticle] = {}

    for match in matches:
        match_cutoff = (
            current_time - timedelta(hours=match.lookback_hours)
            if match.lookback_hours is not None
            else cutoff
        )
        if not is_recent_article(match.news, match_cutoff):
            time_excluded_count += 1
            continue
        duplicate_key = build_duplicate_key(match.news)
        existing_article = articles_by_key.get(duplicate_key)
        if existing_article is not None:
            duplicate_count += 1
            merge_match(existing_article, match)
            continue

        articles_by_key[duplicate_key] = DiscoveredArticle(
            news=match.news,
            matched_queries=[match.query],
        )

    filtered_articles = list(articles_by_key.values())
    filtered_articles.sort(
        key=lambda article: get_published_datetime(article.news)
        or datetime.min.replace(tzinfo=KST),
        reverse=True,
    )
    final_articles = (
        filtered_articles
        if max_articles is None
        else filtered_articles[:max_articles]
    )

    return FilterResult(
        articles=final_articles,
        statistics=FilterStatistics(
            fetched_count=len(matches),
            time_excluded_count=time_excluded_count,
            duplicate_count=duplicate_count,
            final_count=len(final_articles),
        ),
    )
