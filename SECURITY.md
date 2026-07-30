# 보안 정책

## 지원 범위

기본 브랜치의 최신 버전만 보안 수정 대상입니다. 템플릿으로 만든 개별 저장소는
각 저장소 소유자가 Secrets와 Notion 권한을 관리해야 합니다.

## 취약점 신고

Token이나 Client Secret을 공개 Issue에 올리지 마세요. 저장소에서
Private vulnerability reporting이 활성화되어 있다면 `Security` 탭의
`Report a vulnerability`를 사용하세요. 사용할 수 없다면 저장소 소유자에게
공개되지 않는 방법으로 연락하되, 실제 비밀값은 보내지 마세요.

다음 정보만 전달하면 조사에 도움이 됩니다.

- 문제가 발생한 워크플로와 단계 이름
- 비밀값을 지운 오류 메시지
- 예상한 동작과 실제 동작
- 재현 시각과 실행 링크

## 비밀값 관리

이 프로젝트에서 사용하는 비밀값은 다음 네 개뿐입니다.

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `NOTION_TOKEN`
- `NOTION_ROOT_PAGE_URL`

GitHub Actions에서는 모두 Repository Secrets로 저장합니다. 실제 값은 코드,
README, Issue, 테스트, 스크린샷에 넣지 않습니다. `NOTION_ROOT_PAGE_URL`은
일반적으로 인증 비밀은 아니지만, 개인 워크스페이스 구조가 드러날 수 있으므로
이 템플릿에서는 다른 값과 함께 Secret으로 관리합니다.

## 최소 권한

- Notion Integration은 복제한 부모 대시보드에만 연결합니다.
- Integration에는 콘텐츠 읽기, 추가, 업데이트에 필요한 권한만 허용합니다.
- GitHub Actions의 `GITHUB_TOKEN` 권한은 `contents: read`로 제한합니다.
- 외부 기여자의 Pull Request에서 Repository Secrets를 사용하지 않습니다.

## 노출되었을 때

1. 노출된 Notion Token 또는 NAVER API HUB Client Secret을 즉시
   재발급합니다.
2. GitHub Repository Secrets를 새 값으로 교체합니다.
3. 노출된 값을 코드에서 지우는 것만으로 끝내지 말고 Git 기록과 Actions
   로그의 공개 범위도 확인합니다.
4. Notion과 네이버 클라우드 플랫폼의 NAVER API HUB 이용량에서 예상하지 못한
   호출이 있는지 확인합니다.
5. `1. 설정 연결 검사`를 다시 실행합니다.

GitHub는 등록한 Secrets를 로그에서 마스킹하지만, 애플리케이션도 오류 메시지의
비밀값을 별도로 숨깁니다. 그래도 비밀값을 출력하는 디버그 코드를 추가해서는
안 됩니다.
