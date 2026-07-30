import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from main import REQUIRED_ENVIRONMENT_VARIABLES, redact_secrets
from naver_news import NaverNewsError, fetch_latest_news
from notion_service import (
    ARCHIVE_DATA_SOURCE_NAME,
    KEYWORD_DATA_SOURCE_NAME,
    NotionClient,
    NotionError,
    discover_data_sources,
    load_active_keywords,
    parse_root_page_id,
    validate_required_schemas,
)


def success(message: str) -> None:
    print(f"[성공] {message}")


def failure(message: str) -> None:
    print(f"[실패] {message}")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    values = {
        name: os.getenv(name, "").strip()
        for name in REQUIRED_ENVIRONMENT_VARIABLES
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        failure(
            "필수 환경 변수가 비어 있습니다: "
            f"{', '.join(missing)}. 프로젝트의 .env 파일을 확인해 주세요."
        )
        return 1
    success("필수 환경 변수 4개가 모두 설정되어 있습니다.")
    secret_values = (
        values["NAVER_CLIENT_ID"],
        values["NAVER_CLIENT_SECRET"],
        values["NOTION_TOKEN"],
    )

    def safe_error(error: Exception) -> str:
        return redact_secrets(str(error), secret_values)

    try:
        fetch_latest_news(
            client_id=values["NAVER_CLIENT_ID"],
            client_secret=values["NAVER_CLIENT_SECRET"],
            query="네이버",
            count=1,
        )
    except NaverNewsError as error:
        failure(
            "NAVER API HUB 인증 또는 연결을 확인해 주세요. "
            f"{safe_error(error)}"
        )
        return 1
    success("NAVER API HUB 뉴스 검색 API 인증에 성공했습니다.")

    notion = NotionClient(values["NOTION_TOKEN"])
    try:
        bot = notion.retrieve_bot_user()
    except NotionError as error:
        failure(
            "Notion 인증에 실패했습니다. 토큰과 연결 권한을 확인해 주세요. "
            f"{safe_error(error)}"
        )
        return 1
    bot_name = bot.get("name")
    success(
        "Notion 인증에 성공했습니다."
        + (f" 연결 이름: {bot_name}" if isinstance(bot_name, str) else "")
    )

    try:
        root_page_id = parse_root_page_id(values["NOTION_ROOT_PAGE_URL"])
        notion.retrieve_page(root_page_id)
    except NotionError as error:
        failure(
            "Notion 루트 페이지에 접근하지 못했습니다. 해당 페이지를 "
            f"Integration에 공유했는지 확인해 주세요. {safe_error(error)}"
        )
        return 1
    success("NOTION_ROOT_PAGE_URL의 루트 페이지에 접근했습니다.")

    try:
        data_sources = discover_data_sources(notion, root_page_id)
    except NotionError as error:
        failure(
            "루트 페이지 아래의 데이터 소스를 찾지 못했습니다. "
            f"{safe_error(error)}"
        )
        return 1
    success("'키워드 설정'과 '뉴스 아카이브' 데이터 소스를 찾았습니다.")

    try:
        validate_required_schemas(data_sources)
    except NotionError as error:
        failure(safe_error(error))
        return 1
    success("두 데이터 소스의 속성명과 속성 유형이 모두 올바릅니다.")

    try:
        settings = load_active_keywords(
            notion,
            data_sources[KEYWORD_DATA_SOURCE_NAME].id,
        )
    except NotionError as error:
        failure(f"활성 키워드를 읽지 못했습니다. {safe_error(error)}")
        return 1

    success(f"활성 키워드 {len(settings)}개를 읽었습니다.")
    if not settings:
        print(
            "[안내] 수집할 뉴스가 없습니다. '키워드 설정'에서 키워드를 입력하고 "
            "'사용' 체크박스를 켜 주세요."
        )
    print(
        f"[완료] 설정 검사가 끝났습니다. 저장 대상은 "
        f"'{data_sources[ARCHIVE_DATA_SOURCE_NAME].name}'입니다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
