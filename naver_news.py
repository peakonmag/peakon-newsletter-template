import json
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"

HTTP_ERROR_CAUSES = {
    400: "검색어 또는 요청 파라미터가 올바르지 않습니다.",
    401: (
        "클라이언트 ID 또는 클라이언트 시크릿이 올바르지 않거나, "
        "애플리케이션에 뉴스 검색 API 권한이 없습니다."
    ),
    403: "허용되지 않은 호출입니다. HTTPS 주소와 요청 파라미터를 확인해 주세요.",
    404: "API 주소를 찾을 수 없습니다.",
    429: "NAVER API HUB 뉴스 검색의 하루 호출 한도를 초과했습니다.",
}

NAVER_ERROR_CAUSES = {
    "SE01": "검색어 형식이 올바르지 않습니다.",
    "SE02": "검색 결과 개수 설정이 올바르지 않습니다.",
    "SE03": "검색 시작 위치 설정이 올바르지 않습니다.",
    "SE04": "정렬 방식 설정이 올바르지 않습니다.",
    "SE05": "지원하지 않는 검색 API 요청입니다.",
    "SE06": "요청 문자열의 인코딩이 올바르지 않습니다.",
    "SE99": "네이버 검색 서버 내부 오류입니다. 잠시 후 다시 시도해 주세요.",
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    published_at: str
    original_link: str
    published_datetime: datetime | None = None
    originallink: str = ""
    link: str = ""


class NaverNewsError(Exception):
    pass


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(unescape("".join(parser.parts)).split())


def parse_published_at(value: str) -> datetime | None:
    try:
        published_at = parsedate_to_datetime(value)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        else:
            published_at = published_at.astimezone(ZoneInfo("Asia/Seoul"))
        return published_at
    except (TypeError, ValueError):
        return None


def format_published_at(
    value: str,
    published_datetime: datetime | None = None,
) -> str:
    parsed_datetime = published_datetime or parse_published_at(value)
    if parsed_datetime is None:
        return value or "제공 시각 없음"
    return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_error_response(error: HTTPError) -> tuple[str | None, str | None]:
    try:
        body = error.read().decode("utf-8")
        payload = json.loads(body)
        gateway_error = payload.get("error")
        if isinstance(gateway_error, dict):
            return gateway_error.get("errorCode"), gateway_error.get("message")
        return payload.get("errorCode"), payload.get("errorMessage")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None, None


def explain_http_error(status_code: int, error_code: str | None) -> str:
    if error_code in NAVER_ERROR_CAUSES:
        return NAVER_ERROR_CAUSES[error_code]
    if status_code >= 500:
        return "네이버 API 서버에 일시적인 문제가 있습니다. 잠시 후 다시 시도해 주세요."
    return HTTP_ERROR_CAUSES.get(
        status_code,
        "네이버 API가 요청을 거부했습니다. 애플리케이션 설정과 요청 내용을 확인해 주세요.",
    )


def format_http_error(error: HTTPError) -> str:
    error_code, error_message = parse_error_response(error)
    lines = [
        f"네이버 API 요청 실패 (HTTP {error.code})",
        f"원인: {explain_http_error(error.code, error_code)}",
    ]
    if error_code or error_message:
        details = " - ".join(
            value for value in (error_code, error_message) if value
        )
        lines.append(f"네이버 응답: {details}")
    return "\n".join(lines)


def fetch_latest_news(
    client_id: str,
    client_secret: str,
    query: str,
    count: int,
) -> list[NewsItem]:
    query_string = urlencode(
        {
            "query": query,
            "display": count,
            "start": 1,
            "sort": "date",
            "format": "json",
        }
    )
    request = Request(
        f"{API_URL}?{query_string}",
        headers={
            "X-NCP-APIGW-API-KEY-ID": client_id,
            "X-NCP-APIGW-API-KEY": client_secret,
            "User-Agent": "naver-news-briefing/0.1",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise NaverNewsError(format_http_error(error)) from error
    except URLError as error:
        raise NaverNewsError(
            f"네이버 API 연결 실패: 네트워크 상태를 확인해 주세요. ({error.reason})"
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NaverNewsError(
            "네이버 API 응답을 JSON 형식으로 해석할 수 없습니다."
        ) from error

    news_items: list[NewsItem] = []
    for item in payload.get("items", []):
        published_value = item.get("pubDate", "")
        published_datetime = parse_published_at(published_value)
        originallink = item.get("originallink", "").strip()
        link = item.get("link", "").strip()
        news_items.append(
            NewsItem(
                title=clean_html(item.get("title", "")) or "제목 없음",
                summary=(
                    clean_html(item.get("description", "")) or "요약문 없음"
                ),
                published_at=format_published_at(
                    published_value,
                    published_datetime,
                ),
                original_link=originallink or link or "링크 없음",
                published_datetime=published_datetime,
                originallink=originallink,
                link=link,
            )
        )
    return news_items
