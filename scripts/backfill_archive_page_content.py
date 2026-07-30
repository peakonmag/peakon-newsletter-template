import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from notion_service import (
    ARCHIVE_DATA_SOURCE_NAME,
    NotionClient,
    NotionError,
    build_archive_page_children,
    discover_data_sources,
    parse_root_page_id,
    rich_text_to_plain_text,
)


def block_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    value = block.get(block_type, {}) if isinstance(block_type, str) else {}
    return rich_text_to_plain_text(value.get("rich_text", []))


def has_archive_content(blocks: list[dict[str, Any]]) -> bool:
    return any(
        block.get("type") == "heading_2"
        and block_text(block).strip() == "검색 요약"
        for block in blocks
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("NOTION_TOKEN", "").strip()
    root_url = os.getenv("NOTION_ROOT_PAGE_URL", "").strip()
    if not token or not root_url:
        print(
            "오류: .env에 NOTION_TOKEN과 NOTION_ROOT_PAGE_URL을 설정해 주세요.",
            file=sys.stderr,
        )
        return 1

    try:
        client = NotionClient(token)
        root_page_id = parse_root_page_id(root_url)
        data_sources = discover_data_sources(client, root_page_id)
        archive_source = data_sources[ARCHIVE_DATA_SOURCE_NAME]
        pages = client.query_data_source(archive_source.id)

        updated_count = 0
        skipped_count = 0
        for page in pages:
            page_id = page.get("id")
            if not isinstance(page_id, str) or not page_id:
                continue
            if has_archive_content(client.list_block_children(page_id)):
                skipped_count += 1
                continue

            properties = page.get("properties", {})
            summary = rich_text_to_plain_text(
                properties.get("검색 요약", {}).get("rich_text", [])
            )
            original_link = properties.get("원문 URL", {}).get("url") or ""
            naver_link = properties.get("네이버 링크", {}).get("url") or ""
            client.append_block_children(
                page_id,
                build_archive_page_children(
                    summary=summary,
                    original_link=original_link,
                    naver_link=naver_link,
                ),
            )
            updated_count += 1

        print(
            f"완료: 기존 기사 {updated_count}개에 페이지 본문을 추가했고, "
            f"이미 정리된 기사 {skipped_count}개는 건너뛰었습니다."
        )
        return 0
    except NotionError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
