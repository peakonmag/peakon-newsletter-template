import os
import sys
import json
import unittest
from unittest.mock import patch

from dotenv import load_dotenv

from naver_news import API_URL, NaverNewsError, fetch_latest_news

SEARCH_QUERY = "AI 에이전트"
RESULT_COUNT = 5


class NaverApiHubRequestTests(unittest.TestCase):
    def test_news_request_uses_naver_api_hub_endpoint_and_headers(self) -> None:
        captured_request = None

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps({"items": []}).encode("utf-8")

        def fake_urlopen(request, timeout):
            nonlocal captured_request
            captured_request = request
            self.assertEqual(timeout, 10)
            return FakeResponse()

        with patch("naver_news.urlopen", side_effect=fake_urlopen):
            result = fetch_latest_news(
                client_id="api-hub-client-id",
                client_secret="api-hub-client-secret",
                query="AI 에이전트",
                count=10,
            )

        self.assertEqual(result, [])
        self.assertIsNotNone(captured_request)
        self.assertTrue(
            captured_request.full_url.startswith(
                "https://naverapihub.apigw.ntruss.com/search/v1/news?"
            )
        )
        self.assertNotIn("openapi.naver.com", captured_request.full_url)

        headers = {
            name.lower(): value
            for name, value in captured_request.header_items()
        }
        self.assertEqual(
            headers["x-ncp-apigw-api-key-id"],
            "api-hub-client-id",
        )
        self.assertEqual(
            headers["x-ncp-apigw-api-key"],
            "api-hub-client-secret",
        )
        self.assertNotIn("x-naver-client-id", headers)
        self.assertNotIn("x-naver-client-secret", headers)

    def test_api_url_is_the_naver_api_hub_news_endpoint(self) -> None:
        self.assertEqual(
            API_URL,
            "https://naverapihub.apigw.ntruss.com/search/v1/news",
        )


def main() -> int:
    load_dotenv()
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    missing_variables = [
        name
        for name, value in (
            ("NAVER_CLIENT_ID", client_id),
            ("NAVER_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing_variables:
        print(
            f"오류: .env에 {', '.join(missing_variables)}을(를) 설정해 주세요.",
            file=sys.stderr,
        )
        return 1

    try:
        news_items = fetch_latest_news(
            client_id=client_id,
            client_secret=client_secret,
            query=SEARCH_QUERY,
            count=RESULT_COUNT,
        )
    except NaverNewsError as error:
        print(error, file=sys.stderr)
        return 1

    print(f'검색어: "{SEARCH_QUERY}"')
    print(f"검색 결과: {len(news_items)}개 (최신순)")

    for index, news in enumerate(news_items, start=1):
        print(f"\n[{index}]")
        print(f"제목: {news.title}")
        print(f"검색 요약: {news.summary}")
        print(f"제공 시각: {news.published_at}")
        print(f"원문 링크: {news.original_link}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
