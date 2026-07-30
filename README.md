# 네이버 뉴스 → Notion 자동 수집기

개발 경험이 없어도 Notion에서 검색 키워드만 관리하면 GitHub Actions가
매일 새 네이버 뉴스를 찾아 `뉴스 아카이브`에 저장해요.

## 1. 최종 결과 미리보기

설정을 마치면 다음과 같이 작동해요.

- 매일 오전 8시 7분(Asia/Seoul)에 자동으로 뉴스를 수집해요.
- 필요할 때 GitHub의 `Run workflow` 버튼으로 즉시 실행할 수 있어요.
- `키워드 설정`에서 `사용`이 켜진 키워드만 검색해요.
- 키워드별 최근 시간과 최대 기사 수를 적용해요.
- 같은 기사는 실행 중에도, 이전 실행과 비교할 때도 한 번만 저장해요.
- 여러 키워드에서 발견된 기사는 `검색 키워드` 태그를 합쳐 저장해요.
- 기사 행을 열면 검색 요약과 원문·네이버 링크를 확인할 수 있어요.

`검색 요약`은 네이버 뉴스 검색 API가 제공한 description이에요. 기사 본문이나
AI가 작성한 요약이 아니에요. Discord 전송과 AI 요약 기능은 포함하지 않아요.

## 2. 준비물

아래 계정이 필요해요. 설치 프로그램이나 터미널은 필요하지 않아요.

- GitHub 계정
- Notion 계정
- 네이버 클라우드 플랫폼 계정

먼저, 메모장을 열어서 다음 내용을 기입해주세요.

NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
NOTION_TOKEN=
NOTION_ROOT_PAGE_URL=

4개의 항목에 들어갈 내용은 아래에서 차근차근 설명해드릴게요.

[NAVER API HUB](https://www.ncloud.com/product/applicationService/naverApiHub)에서
`콘솔`을 열고 다음 순서로 준비해요.

1. `All Services` → `Application Services` → `NAVER API HUB`로 이동해요.
2. `Subscription`에서 서비스 이용을 신청해요.
3. `Application` → `Application 등록`을 눌러요.
4. 뉴스 검색 API가 포함되도록 API를 선택하고 Application 이름을 입력해요.
5. 등록된 Application의 `인증 정보`에서 Client ID와 Client Secret을
   확인해요.

기존 NAVER Developers Center에서 발급한 인증 정보는 사용할 수 없어요.
반드시 NAVER API HUB에서 새로 발급한 값을 사용하세요.

## 3. Notion 템플릿 복제

[PEAKON](https://app.notion.com/p/PEAKON-3acaafd5210e8088a695ce265980526b?source=copy_link)

1. 링크를 열고 Notion에 로그인해요.
2. 오른쪽 위의 `•••`를 눌러요.
3. '복제' 혹은 'Duplicate'를 눌러요.
4. 복제된 페이지를 열어요.
5. `공유`에서 이 페이지의 링크를 복사해 둬요. 이 값이 나중에
   `NOTION_ROOT_PAGE_URL`이 돼요.

복제 후 `키워드 설정`, `뉴스 아카이브`의 이름이나 속성명을 바꾸지 마세요.
정확한 구조는 [notion-template-spec.md](notion-template-spec.md)에 있어요.

## 4. Notion Integration 생성

1. [Notion Connections](https://app.notion.com/developers/connections)에서
   새 Integration 또는 새 내부 연결을 만들어요.
2. 이름은 알아보기 쉽게 `newsletter`처럼 입력해요.
3. 템플릿을 복제한 워크스페이스를 선택해요.
4. 콘텐츠 읽기, 콘텐츠 추가, 콘텐츠 업데이트 권한을 허용해요.
5. 생성된 내부 Integration Token을 복사해 안전한 곳에 잠시 보관해요.
   이 값이 `NOTION_TOKEN`이에요.

토큰은 비밀번호와 같아요. 메모를 공개 공유하거나 GitHub 파일에 붙여 넣지
마세요.

## 5. Notion 페이지에 Integration 연결

1. 복제한 부모 대시보드 페이지를 열어요.
2. 오른쪽 위 `•••` 메뉴를 눌러요.
3. `연결 추가` 또는 `Add connections`를 선택해요.
4. 앞에서 만든 `네이버 뉴스 수집기` Integration을 선택해요.
5. 부모 페이지와 하위 페이지에 접근한다는 안내를 확인하고 연결해요.

반드시 `키워드 설정`과 `뉴스 아카이브`를 모두 포함하는 부모 페이지에서
연결해야 해요.

## 6. GitHub 템플릿 복제

1. 이 GitHub 저장소 위쪽의 `Use this template`을 눌러요.
2. `Create a new repository`를 선택해요.
3. 저장소 이름을 정해요.
4. 공개 범위를 선택하고 `Create repository`를 눌러요.

`Fork` 버튼이 아니라 `Use this template`을 사용하세요. 파일을 내려받거나
Git 명령어를 실행할 필요가 없어요.

## 7. Repository Secrets 네 개 등록

복제한 GitHub 저장소에서 `Settings` → `Secrets and variables` → `Actions`로
이동해요. `New repository secret`을 눌러 아래 네 개를 정확한 이름으로
하나씩 등록해요.

| Secret 이름 | 넣을 값 |
| --- | --- |
| `NAVER_CLIENT_ID` | NAVER API HUB Application의 Client ID |
| `NAVER_CLIENT_SECRET` | NAVER API HUB Application의 Client Secret |
| `NOTION_TOKEN` | Notion Integration의 내부 Token |
| `NOTION_ROOT_PAGE_URL` | 복제한 부모 대시보드의 전체 URL |

앞뒤 공백이 들어가지 않게 복사하세요. `NOTION_ROOT_PAGE_URL`은 데이터베이스
행이나 보기 링크가 아니라 두 데이터 소스를 포함하는 부모 페이지 링크예요.

## 8. Setup Check 실행

1. GitHub 저장소의 `Actions` 탭을 열어요.
2. 왼쪽에서 `1. 설정 연결 검사`를 선택해요.
3. `Run workflow` → `Run workflow`를 눌러요.
4. 완료된 실행을 열고 Summary를 확인해요.

`✅ 설정 연결 검사 성공`이 나오면 네이버 인증, Notion 인증, 부모 페이지,
두 데이터 소스, 속성 구조가 모두 확인된 상태예요. 실패하면 Summary에
표시된 한국어 안내부터 수정하세요.

## 9. 첫 뉴스 수집

1. Notion의 `키워드 설정`을 열어요.
2. 예시 행의 키워드를 원하는 검색어로 바꿔요.
3. `사용` 체크박스를 켜요.
4. GitHub `Actions` 탭에서 `2. 뉴스 수집`을 선택해요.
5. `Run workflow` → `Run workflow`를 눌러요.
6. 실행이 끝나면 Notion의 `뉴스 아카이브`를 새로고침해요.

조건에 맞는 새 기사가 없으면 실행은 성공해도 새 행이 생기지 않을 수 있어요.

## 10. Notion에서 키워드 변경

이후에는 코드를 수정하지 않아요. `키워드 설정` 표만 변경하세요.

- `키워드`: 검색어를 입력해요.
- `사용`: 켜진 행만 다음 실행에서 검색해요.
- `최근 시간 (Hour)`: `24`이면 실행 시점 기준 최근 24시간 기사만 남겨요.
- `최대 기사 수`: 키워드별 네이버 검색 결과 수예요. 비어 있으면 10,
  최댓값은 100이에요.

최근 시간과 최대 기사 수가 비어 있으면 각각 24시간과 10개가 적용돼요.
영문 대소문자만 다른 같은 키워드는 한 번만 검색해요. 표를 저장한 뒤 별도
동기화 버튼을 누를 필요 없이 다음 실행부터 적용돼요.

## 11. 예약 실행 확인

`2. 뉴스 수집`은 매일 오전 8시 7분(Asia/Seoul)에 실행돼요.

- GitHub의 `Actions` → `2. 뉴스 수집`에서 실행 기록을 확인해요.
- 예약 실행은 기본 브랜치에 워크플로 파일이 있어야 작동해요.
- GitHub Actions 상황에 따라 시작이 몇 분 늦어질 수 있어요.
- 워크플로가 비활성화된 경우 해당 화면의 `Enable workflow`를 눌러요.
- 공개 저장소에 60일 동안 활동이 없으면 GitHub가 예약 실행을 자동으로
  비활성화할 수 있어요.

예약 실행과 버튼 실행이 겹치면 먼저 시작된 실행이 끝날 때까지 다음 실행이
대기하므로 동시에 같은 기사를 저장하지 않아요.

## 12. 오류 해결

자주 발생하는 문제는 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)에 정리되어
있어요.

- Secret 이름과 값이 정확한지 확인해요.
- Notion 부모 페이지에 Integration이 연결되었는지 확인해요.
- 데이터 소스 이름과 속성 유형이 바뀌지 않았는지 확인해요.
- `사용`이 켜진 유효한 키워드가 있는지 확인해요.
- 먼저 `1. 설정 연결 검사`를 다시 실행해요.

해결되지 않으면 실패한 Actions 실행을 열어 Secret 값 자체가 아닌
오류 메시지와 실패한 단계 이름만 저장소 관리자에게 전달하세요.

## 13. 보안 주의사항

- `.env`, Token, Client Secret을 GitHub 파일이나 Issue에 올리지 마세요.
- 네 가지 값은 반드시 Repository Secrets에 저장하세요.
- Actions 로그에 비밀값을 직접 출력하지 마세요.
- 화면 공유나 캡처 전에 Secrets 입력 화면과 Notion Token을 가리세요.
- 토큰이 노출되었다면 Notion Token과 NAVER API HUB Client Secret을 즉시
  재발급하고 GitHub Secrets를 교체하세요.
- 더 자세한 내용과 신고 방법은 [SECURITY.md](SECURITY.md)를 확인하세요.

GitHub의 Repository Secrets는 워크플로에 환경변수로 전달되며, 이 프로젝트는
비밀값을 코드나 결과 페이지에 저장하지 않아요.
