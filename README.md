# ⚖️ Balance Game (밸런스 게임 커뮤니티 플랫폼)

> **사용자들이 흥미로운 질문을 생성하고 투표하며 의견을 나누는 웹 커뮤니티 플랫폼입니다.** > Flask 프레임워크를 기반으로 하며, JWT 인증과 MongoDB(GridFS)를 활용하여 유연한 데이터 관리 및 미디어 업로드를 지원합니다.

---

## 🚀 주요 기능 (Key Features)

### 👤 사용자 관리 (User Management)
- **회원가입 및 로그인**
  - `Werkzeug`를 이용한 안전한 비밀번호 단방향 해싱 암호화.
  - `Flask-JWT-Extended` 기반의 JWT 토큰 인증 방식 및 Flask 내장 `session` 로그인 방식 동시 지원 (통합 가동).
- **프로필 관리**
  - 회원가입 시 프로필 이미지 업로드 지원.
  - 대용량 파일 관리를 위한 MongoDB **GridFS** 연동으로 바이너리 이미지 데이터 직접 저장 및 서빙.
  - 마이페이지/타인 프로필 조회 및 최근 투표 이력(최근 5개) 확인 기능.

### 🎮 밸런스 게임 카드 (Balance Cards)
- **질문 카드 생성**
  - 사용자가 두 가지 선택지(`Option 1`, `Option 2`)를 가진 밸런스 게임 카드 등록.
  - 카드 작성 시 **익명 여부 선택** 가능 (익명 선택 시 작성자 이름이 '익명'으로 제한되며 보안 유지).
- **실시간 투표 시스템**
  - 동일 옵션 재클릭 시 투표 취소, 다른 옵션 클릭 시 기존 투표 차감 후 신규 투표 반영.
- **좋아요(Like) 및 필터링**
  - 카드별 좋아요 추천 기능 및 내가 좋아요 한 카드만 모아보는 필터링 기능.
  - **인기 카드 노출**: 좋아요를 1개 이상 받은 카드 중 최다 좋아요 카드를 실시간 1위로 선정하여 반환.

### 💬 커뮤니티 & 조회 (Community & Search)
- **댓글 시스템 (Comments)**
  - 각 카드 상세 정보와 연동된 실시간 댓글 등록. 댓글 작성 시에도 **익명/기명** 선택 가능.
  - 권한 검증을 통해 익명 댓글이라도 **작성자 본인만 삭제** 가능하도록 구현.
- **다기능 검색**
  - `Option 1`, `Option 2`, `작성자(Writer)` 또는 전체 항목 기준의 MongoDB `$regex` 부분 일치 검색 지원.
- **하이브리드 렌더링**
  - 일반 웹 사용자를 위한 **SSR(Jinja2 템플릿 엔진)** 기반 게시판 페이지네이션(페이지당 10개) 처리.
  - 클라이언트 앱 및 비동기 통신을 위한 **RESTful API Endpoint** 전면 개방.

---

## 🛠 기술 스택 (Tech Stack)

| 분류 | 기술 기술 (Tech Specification) |
| :--- | :--- |
| **Backend** | ![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white) ![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=flat-square&logo=flask&logoColor=white) |
| **Database** | ![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?style=flat-square&logo=mongodb&logoColor=white) (PyMongo, GridFS) |
| **Auth** | ![JWT](https://img.shields.io/badge/JWT-Authentication-000000?style=flat-square&logo=json-web-tokens&logoColor=white) (Flask-JWT-Extended), Werkzeug Security |
| **Frontend** | Jinja2 Template Engine, HTML5, CSS3, JavaScript (Fetch API) |

---

## 📂 프로젝트 구조 (Directory Structure)

```text
.
├── static/              # 정적 자원 관리 (CSS, JavaScript, 기본 프로필 이미지 등)
│   └── uploads/         # (자동 생성) 파일 업로드 임시 폴더
├── templates/           # Jinja2 HTML 템플릿 파일 (board.html, login.html, signup.html)
├── app.py               # 메인 Flask 애플리케이션 핵심 로직 및 라우팅 설정
└── README.md            # 프로젝트 가이드 문서
