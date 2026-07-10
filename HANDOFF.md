# HANDOFF — BPT 수익화 인증글 생성기

> 여러 컴퓨터를 오갈 때 이 파일을 읽고 이어서 작업한다.
> **앉으면 pull, 뜨면 push.** (`worksync start` / `worksync end`)

## 현재 상태 (2026-07-10 기준)
- 프로젝트를 로컬(`OneDrive\Desktop\AI\Claude\수익인증자동화`)로 옮겨 로컬 작업 체제로 전환.
- GitHub 비공개 저장소 연결 완료: https://github.com/shortprologue-jpg/revenue-cert-generator
- `.gitignore` 적용 — `.env`(비밀키), `.omc/` 등 제외.
- 첫 커밋·push 완료. 코드 변경은 아직 없음(이관·세팅만 함).

## 다음 할 일
- 각 노트북에서 `.env` 직접 생성(`.env.example` 참고 또는 `초기설정.bat` 실행) — git에 안 올라가므로 노트북마다 필요.
- 앱 기능 개발/수정은 여기서부터 이어서.

## 주요 결정
- 저장소 이름은 영문 `revenue-cert-generator`(URL·클론 편의).
- 브랜치는 `main` 하나만 사용(혼자 두 노트북 오가는 구조).
- 비밀키는 절대 커밋하지 않음 — `.env`는 각 노트북 로컬 전용.
