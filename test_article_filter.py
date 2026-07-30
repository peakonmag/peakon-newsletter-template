import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from article_filter import ArticleMatch, filter_articles
from naver_news import NewsItem


KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 27, 16, 0, tzinfo=KST)


def make_news(
    title: str,
    published_datetime: datetime,
    *,
    summary: str = "요약",
    originallink: str = "",
    link: str = "",
) -> NewsItem:
    return NewsItem(
        title=title,
        summary=summary,
        published_at=published_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        original_link=originallink or link or "링크 없음",
        published_datetime=published_datetime,
        originallink=originallink,
        link=link,
    )


def make_match(
    news: NewsItem,
    *,
    query: str = "AI 에이전트",
    lookback_hours: float | None = None,
) -> ArticleMatch:
    return ArticleMatch(
        news=news,
        query=query,
        lookback_hours=lookback_hours,
    )


class ArticleFilterTests(unittest.TestCase):
    def test_each_keyword_can_use_its_own_lookback_hours(self) -> None:
        matches = [
            make_match(
                make_news("세 시간 전 기사", NOW - timedelta(hours=3)),
                lookback_hours=2,
            )
        ]

        result = filter_articles(
            matches,
            lookback_hours=24,
            max_articles=10,
            now=NOW,
        )

        self.assertEqual(result.articles, [])
        self.assertEqual(result.statistics.time_excluded_count, 1)

    def test_recent_and_old_articles_are_distinguished(self) -> None:
        recent_naive = (NOW - timedelta(hours=1)).replace(tzinfo=None)
        old_aware = NOW - timedelta(hours=25)
        matches = [
            make_match(make_news("최근 기사", recent_naive)),
            make_match(make_news("오래된 기사", old_aware)),
        ]

        result = filter_articles(matches, lookback_hours=24, max_articles=10, now=NOW)

        self.assertEqual([article.news.title for article in result.articles], ["최근 기사"])
        self.assertEqual(result.statistics.time_excluded_count, 1)

    def test_same_originallink_is_deduplicated(self) -> None:
        shared_url = "https://news.example/shared"
        matches = [
            make_match(
                make_news(
                    "첫 번째 제목",
                    NOW - timedelta(minutes=5),
                    originallink=shared_url,
                ),
                query="AI 에이전트",
            ),
            make_match(
                make_news(
                    "두 번째 제목",
                    NOW - timedelta(minutes=4),
                    originallink=shared_url,
                ),
                query="Claude Code",
            ),
        ]

        result = filter_articles(matches, lookback_hours=24, max_articles=10, now=NOW)

        self.assertEqual(len(result.articles), 1)
        self.assertEqual(result.statistics.duplicate_count, 1)

    def test_same_normalized_title_is_deduplicated(self) -> None:
        matches = [
            make_match(
                make_news("<b>AI</b>   에이전트 뉴스", NOW - timedelta(minutes=5)),
                query="AI 에이전트",
            ),
            make_match(
                make_news("AI 에이전트 뉴스", NOW - timedelta(minutes=4)),
                query="Codex",
            ),
        ]

        result = filter_articles(matches, lookback_hours=24, max_articles=10, now=NOW)

        self.assertEqual(len(result.articles), 1)
        self.assertEqual(result.statistics.duplicate_count, 1)

    def test_queries_are_merged_for_duplicate_article(self) -> None:
        shared_url = "https://news.example/merged"
        matches = [
            make_match(
                make_news(
                    "공통 기사",
                    NOW - timedelta(minutes=5),
                    link=shared_url,
                ),
                query="AI 에이전트",
            ),
            make_match(
                make_news(
                    "공통 기사",
                    NOW - timedelta(minutes=5),
                    link=shared_url,
                ),
                query="Claude Code",
            ),
            make_match(
                make_news(
                    "공통 기사",
                    NOW - timedelta(minutes=5),
                    link=shared_url,
                ),
                query="Codex",
            ),
        ]

        result = filter_articles(matches, lookback_hours=24, max_articles=10, now=NOW)
        article = result.articles[0]

        self.assertEqual(
            article.matched_queries,
            ["AI 에이전트", "Claude Code", "Codex"],
        )
        self.assertEqual(result.statistics.duplicate_count, 2)

    def test_max_articles_is_applied_after_filtering_deduplication_and_sorting(
        self,
    ) -> None:
        matches = [
            make_match(
                make_news(
                    "세 번째 최신",
                    NOW - timedelta(hours=3),
                    originallink="https://news.example/third",
                )
            ),
            make_match(
                make_news(
                    "가장 최신",
                    NOW - timedelta(minutes=1),
                    originallink="https://news.example/first",
                ),
                query="AI 에이전트",
            ),
            make_match(
                make_news(
                    "가장 최신 중복",
                    NOW - timedelta(minutes=1),
                    originallink="https://news.example/first",
                ),
                query="Codex",
            ),
            make_match(
                make_news(
                    "두 번째 최신",
                    NOW - timedelta(hours=2),
                    originallink="https://news.example/second",
                )
            ),
        ]

        result = filter_articles(matches, lookback_hours=24, max_articles=2, now=NOW)

        self.assertEqual(
            [article.news.title for article in result.articles],
            ["가장 최신", "두 번째 최신"],
        )
        self.assertEqual(result.statistics.fetched_count, 4)
        self.assertEqual(result.statistics.duplicate_count, 1)
        self.assertEqual(result.statistics.final_count, 2)


if __name__ == "__main__":
    unittest.main()
