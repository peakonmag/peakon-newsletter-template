# Repository instructions

## Product invariants

- Notion의 `키워드 설정`이 검색 설정의 단일 원본이다.
- `config.json`, `sent_articles.json`, Discord 전송 기능을 다시 도입하지 않는다.
- 사용자가 코드를 수정하지 않고 Notion의 키워드 행만 바꿔 운영할 수 있어야 한다.
- 환경변수는 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `NOTION_TOKEN`,
  `NOTION_ROOT_PAGE_URL` 네 개만 사용한다.
- 실제 비밀값을 코드, 테스트, 로그, 문서에 넣지 않는다.
- 뉴스 검색은 네이버 클라우드 플랫폼의 NAVER API HUB를 사용한다.
- 기존 NAVER Developers Center의 호출 주소나 인증 헤더를 사용하지 않는다.

## NAVER API HUB

- 뉴스 검색 주소는
  `https://naverapihub.apigw.ntruss.com/search/v1/news`이다.
- Client ID는 `X-NCP-APIGW-API-KEY-ID`, Client Secret은
  `X-NCP-APIGW-API-KEY` 헤더로 전달한다.
- `https://openapi.naver.com`, `X-Naver-Client-Id`,
  `X-Naver-Client-Secret`을 다시 도입하지 않는다.
- 환경변수 이름은 기존의 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을
  유지한다.

## Notion API

- 데이터 소스 ID나 페이지 ID를 하드코딩하지 않는다.
- `NOTION_ROOT_PAGE_URL`에서 부모 페이지 ID를 추출하고 이름으로
  `키워드 설정`, `뉴스 아카이브`를 찾는다.
- 현재 `/data_sources/{id}/query` API를 사용하고 오래된
  `/databases/{id}/query`에 의존하지 않는다.
- 속성명과 유형은 `notion-template-spec.md` 및 `notion_service.py`의 스키마와
  일치시킨다.
- `기사 키`는 중복 제거에 필요하므로 삭제하지 않는다. 사용자 보기에서 숨기는
  것은 허용한다.
- `검색 요약`은 네이버 검색 API description이다. AI 요약이나 기사 본문
  요약으로 표현하지 않는다.

## Changes and verification

- 검증된 네이버 API 호출과 기사 필터링 로직은 요청 범위 밖에서 변경하지 않는다.
- 사용자에게 보이는 오류와 GitHub Actions Summary는 쉬운 한국어로 작성한다.
- 기능 변경에는 해당 동작의 단위 테스트를 추가한다.
- 완료 전 `python -m unittest discover -v`를 실행한다.
- 워크플로 변경 시 두 YAML 파일의 문법과 수동·예약 실행 조건을 확인한다.
- README는 터미널이나 Git 명령어 없이 GitHub와 Notion 웹 화면만으로
  설치할 수 있게 유지한다.
