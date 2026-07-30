# Template repository 공개 전 체크리스트

GitHub 저장소를 Template repository로 전환하기 전에 저장소 소유자가 직접
확인할 항목입니다.

## Notion 템플릿

- [ ] 공개용 원본 대시보드에는 `키워드 설정`과 `뉴스 아카이브`만 필요한
      구조로 들어 있다.
- [ ] 실제 뉴스, 개인 이름, 내부 링크 등 공개하면 안 되는 데이터가 없다.
- [ ] 공개 페이지에서 `Duplicate as template`이 켜져 있다.
- [ ] 다른 Notion 워크스페이스로 직접 복제해 두 데이터 소스와 속성이 유지되는지
      확인했다.
- [ ] 복제본의 데이터 소스 ID가 원본과 달라도 Setup Check가 통과한다.
- [ ] README의 `{{NOTION_TEMPLATE_URL}}`을 실제 공개 복제 링크로 교체했다.
- [ ] 공개 링크를 로그아웃 창에서 열어도 복제 버튼이 보인다.

## GitHub 저장소

- [ ] 기본 브랜치에 `.github/workflows/setup-check.yml`과
      `.github/workflows/news-briefing.yml`이 있다.
- [ ] `Settings`에서 Actions 사용이 허용되어 있다.
- [ ] README의 모든 링크를 눌러 보고 잘못된 링크가 없는지 확인했다.
- [ ] 저장소 설명, 공개 범위, 라이선스를 결정했다.
- [ ] `.env`, `sent_articles.json`, 실제 API 응답 파일이 커밋되지 않았다.
- [ ] Git 기록에도 실제 Token, Client Secret, 개인 Notion URL이 없다.
- [ ] GitHub의 Secret scanning과 Private vulnerability reporting 사용 여부를
      결정했다.

## 새 사용자처럼 전체 점검

- [ ] `Use this template`로 새 저장소를 만들었다.
- [ ] 새 Notion 워크스페이스에 템플릿을 복제했다.
- [ ] 새 Notion Integration을 만들고 복제한 부모 페이지에 연결했다.
- [ ] NAVER API HUB에서 뉴스 검색 API를 선택한 Application을 등록했다.
- [ ] 기존 NAVER Developers Center가 아닌 NAVER API HUB의 인증 정보를
      사용했다.
- [ ] Repository Secrets 네 개만 등록했다.
- [ ] `1. 설정 연결 검사`를 버튼으로 실행해 성공 Summary를 확인했다.
- [ ] Notion에서 키워드 하나와 `사용`만 바꾼 뒤 `2. 뉴스 수집`을 실행했다.
- [ ] 새 기사만 저장되고, 같은 기사를 다시 실행해도 중복 저장되지 않았다.
- [ ] 뉴스 행의 `검색 키워드` 태그와 원문 링크가 정상적으로 보인다.
- [ ] `기사 키`는 데이터 소스에 존재하지만 기본 보기에서는 숨겨져 있다.
- [ ] 실패 사례 하나를 만들어 한국어 오류 안내가 이해하기 쉬운지 확인했다.
- [ ] 예약 실행 시간이 매일 오전 8시 7분(Asia/Seoul)으로 표시된다.

## Template repository 전환

모든 확인이 끝나면 GitHub 저장소에서 `Settings` → `General`로 이동해
`Template repository`를 선택합니다. 전환 후 실제 사용자 계정 또는 별도
테스트 저장소에서 마지막으로 `Use this template` 흐름을 확인합니다.
