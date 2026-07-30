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
    KEYWORD_DATA_SOURCE_NAME,
    DataSource,
    NotionClient,
    NotionError,
    NotionStructureError,
    discover_data_sources,
    parse_root_page_id,
    validate_required_schemas,
)


INTRO_MARKER = "네이버 뉴스 수집 대시보드 사용 안내"


def rich_text(content: str, *, bold: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": {"content": content},
            "annotations": {"bold": bold},
        }
    ]


def block_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    value = block.get(block_type, {}) if isinstance(block_type, str) else {}
    items = value.get("rich_text", [])
    return "".join(
        item.get("plain_text", "")
        for item in items
        if isinstance(item, dict)
    )


def append_dashboard_guide(client: NotionClient, root_page_id: str) -> None:
    existing_blocks = client.list_block_children(root_page_id)
    if any(INTRO_MARKER in block_text(block) for block in existing_blocks):
        return

    client.request(
        "PATCH",
        f"/blocks/{root_page_id}/children",
        body={
            "position": {"type": "end"},
            "children": [
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "📰"},
                        "color": "green_background",
                        "rich_text": rich_text(
                            f"{INTRO_MARKER}\n"
                            "아래 '키워드 설정'에서 검색 조건을 관리하면 "
                            "'뉴스 아카이브'에 새 기사만 자동 저장됩니다.",
                            bold=True,
                        ),
                    },
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": rich_text("사용 방법"),
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text(
                            "'키워드 설정'에 검색어를 추가합니다."
                        ),
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text(
                            "검색할 행의 '사용' 체크박스를 켭니다."
                        ),
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text(
                            "'최근 시간 (Hour)'은 시간 단위입니다. 24를 입력하면 "
                            "실행 시점 기준 최근 24시간 이내 기사만 수집합니다."
                        ),
                    },
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text(
                            "'최대 기사 수'에는 키워드별로 가져올 기사 수를 "
                            "입력합니다. 비어 있으면 10개입니다."
                        ),
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": rich_text(
                            "주의: '검색 요약'은 네이버 뉴스 검색 API의 "
                            "description이며, AI 요약이나 기사 본문 요약이 아닙니다."
                        ),
                        "color": "gray",
                    },
                },
                {"object": "block", "type": "divider", "divider": {}},
            ],
        },
    )


def keyword_schema() -> dict[str, Any]:
    return {
        "키워드": {"title": {}},
        "사용": {"checkbox": {}},
        "최근 시간 (Hour)": {"number": {"format": "number"}},
        "최대 기사 수": {"number": {"format": "number"}},
        "마지막 실행": {"date": {}},
    }


def archive_schema() -> dict[str, Any]:
    return {
        "제목": {"title": {}},
        "기사 키": {"rich_text": {}},
        "원문 URL": {"url": {}},
        "네이버 링크": {"url": {}},
        "발행 시각": {"date": {}},
        "수집 시각": {"date": {}},
        "검색 키워드": {"multi_select": {"options": []}},
        "검색 요약": {"rich_text": {}},
        "상태": {
            "select": {
                "options": [
                    {"name": "신규", "color": "blue"},
                    {"name": "검토 중", "color": "yellow"},
                    {"name": "보관", "color": "green"},
                ]
            }
        },
    }


def find_named_data_sources(
    client: NotionClient,
    root_page_id: str,
) -> dict[str, DataSource]:
    pending = [root_page_id]
    visited: set[str] = set()
    database_ids: set[str] = set()

    while pending:
        block_id = pending.pop()
        if block_id in visited:
            continue
        visited.add(block_id)
        for block in client.list_block_children(block_id):
            block_type = block.get("type")
            child_id = block.get("id")
            if block_type == "child_database" and isinstance(child_id, str):
                database_ids.add(child_id)
            elif (
                block.get("has_children")
                and isinstance(child_id, str)
                and block_type != "child_database"
            ):
                pending.append(child_id)

    matches: dict[str, list[DataSource]] = {
        KEYWORD_DATA_SOURCE_NAME: [],
        ARCHIVE_DATA_SOURCE_NAME: [],
    }
    for database_id in database_ids:
        database = client.retrieve_database(database_id)
        for summary in database.get("data_sources", []):
            name = summary.get("name")
            data_source_id = summary.get("id")
            if name in matches and isinstance(data_source_id, str):
                payload = client.retrieve_data_source(data_source_id)
                matches[name].append(
                    DataSource(
                        id=data_source_id,
                        name=name,
                        properties=payload.get("properties", {}),
                    )
                )

    duplicates = [
        name for name, sources in matches.items() if len(sources) > 1
    ]
    if duplicates:
        raise NotionStructureError(
            "같은 이름의 데이터 소스가 여러 개 있습니다: "
            + ", ".join(duplicates)
        )
    return {
        name: sources[0]
        for name, sources in matches.items()
        if sources
    }


def create_database(
    client: NotionClient,
    root_page_id: str,
    *,
    name: str,
    description: str,
    properties: dict[str, Any],
    icon: str,
) -> DataSource:
    database = client.request(
        "POST",
        "/databases",
        body={
            "parent": {"type": "page_id", "page_id": root_page_id},
            "title": rich_text(name),
            "description": rich_text(description),
            "is_inline": True,
            "icon": {"type": "emoji", "emoji": icon},
            "initial_data_source": {"properties": properties},
        },
    )
    database_id = database.get("id")
    if not isinstance(database_id, str):
        raise NotionError(f"'{name}' 데이터베이스 ID를 받지 못했습니다.")

    retrieved = client.retrieve_database(database_id)
    summaries = retrieved.get("data_sources", [])
    if len(summaries) != 1 or not isinstance(summaries[0].get("id"), str):
        raise NotionError(
            f"'{name}'의 초기 데이터 소스를 확인하지 못했습니다."
        )
    data_source_id = summaries[0]["id"]
    if summaries[0].get("name") != name:
        client.request(
            "PATCH",
            f"/data_sources/{data_source_id}",
            body={"title": rich_text(name)},
        )
    payload = client.retrieve_data_source(data_source_id)
    return DataSource(
        id=data_source_id,
        name=name,
        properties=payload.get("properties", {}),
    )


def create_example_keyword(
    client: NotionClient,
    keyword_data_source_id: str,
) -> None:
    existing = client.query_data_source(
        keyword_data_source_id,
        filter_body={
            "property": "키워드",
            "title": {"equals": "AI 에이전트"},
        },
    )
    if existing:
        return
    client.create_page(
        keyword_data_source_id,
        {
            "키워드": {"title": rich_text("AI 에이전트")},
            "사용": {"checkbox": False},
            "최근 시간 (Hour)": {"number": 24},
            "최대 기사 수": {"number": 10},
        },
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
        client.retrieve_page(root_page_id)
        existing = find_named_data_sources(client, root_page_id)

        append_dashboard_guide(client, root_page_id)

        keyword_source = existing.get(KEYWORD_DATA_SOURCE_NAME)
        if keyword_source is None:
            keyword_source = create_database(
                client,
                root_page_id,
                name=KEYWORD_DATA_SOURCE_NAME,
                description=(
                    "검색 키워드와 필터 조건을 관리합니다. "
                    "'사용'이 켜진 행만 검색합니다."
                ),
                properties=keyword_schema(),
                icon="🔎",
            )

        archive_source = existing.get(ARCHIVE_DATA_SOURCE_NAME)
        if archive_source is None:
            archive_source = create_database(
                client,
                root_page_id,
                name=ARCHIVE_DATA_SOURCE_NAME,
                description=(
                    "중복 검사를 통과한 새 네이버 뉴스가 자동으로 저장됩니다."
                ),
                properties=archive_schema(),
                icon="🗂️",
            )
        create_example_keyword(client, keyword_source.id)

        data_sources = discover_data_sources(client, root_page_id)
        validate_required_schemas(data_sources)
        print(
            "완료: 루트 페이지 안에 사용 안내, '키워드 설정', "
            "'뉴스 아카이브' 템플릿을 만들고 구조를 검증했습니다."
        )
        return 0
    except NotionError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
