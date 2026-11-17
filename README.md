# 쇼핑 리스트

아이템 추가 / 수정 / 삭제 / 체크 기능이 있는 간단한 웹 앱. Python + Streamlit 단일 파일(`app.py`).
요구사항은 [PRD.md](PRD.md)를 참고한다.

## 실행

```
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속한다. Python 3.12, Streamlit 1.62.0에서 개발·검증했고,
`requirements.txt`의 최소 버전(1.46)에서는 동작 테스트(`AppTest`)까지 확인했다. 화면(CSS) 확인은 1.62.0에서만 했다.

## 데이터 저장

- `app.py` 옆의 `data.json`에 저장한다 (git 제외). 새로고침·서버 재시작 후에도 유지된다.
- 파일이 유일한 원본이다. 모든 변경은 락 안에서 "읽기 → 수정 → 쓰기"로 처리해서, 여러 탭에서 동시에 써도 서로의 변경을 덮어쓰지 않는다. 다른 탭의 변경은 해당 탭의 다음 조작 때 반영된다.
- 접속한 모든 사람이 **같은 목록**을 공유한다 (로그인/사용자 구분 없음).
- 같은 이름의 아이템을 여러 개 추가할 수 있다.

## 배포 (Streamlit Community Cloud)

1. 이 폴더를 GitHub 저장소로 올린다 (`data.json`은 `.gitignore`로 제외됨).
2. https://share.streamlit.io 에서 저장소를 연결하고 메인 파일로 `app.py`를 지정한다.

**주의 — 데이터가 사라질 수 있다.** 공식 문서에서 파일 영속성을 직접 설명하는 페이지는 찾지 못했다
(2026-11-17 기준). 다만 커뮤니티 포럼 답변들은 Community Cloud에서 실행 중에 만든 파일이
앱 재시작·재배포 시 사라진다고 설명한다
(예: [Files lost after reboot in Streamlit Cloud](https://discuss.streamlit.io/t/files-lost-after-reboot-in-streamlit-cloud/33917)).
따라서 배포 후에도 목록을 유지하려면 외부 저장소(DB, Google Sheets 등)로 바꿔야 할 수 있고,
배포 전에 최신 공식 문서를 확인할 것. 저장 코드는 `app.py`의 `load_data` / `write_data` 두 함수에 모여 있다.
