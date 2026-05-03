# PDF Manual Optimizer

PDF를 AI 검색/RAG에 적합한 로컬 패키지로 변환하는 Windows용 GUI 프로그램입니다.

## 주요 기능

- 여러 PDF 파일 일괄 변환
- 페이지별 텍스트 추출 및 기본 정리
- 제목 패턴 기반 섹션 분리
- AI 검색용 `chunks.jsonl` 생성
- 사람이 읽기 쉬운 `manual.md` 생성
- 문서별 `index.json` 및 통합 `all_manuals_index.json` 생성
- 가능한 경우 PDF 표를 CSV로 저장
- 가능한 경우 PDF 이미지를 PNG로 저장
- GUI에서 표 추출과 이미지 추출을 켜거나 끌 수 있음
- 목차 페이지는 `manual.md`와 `index.json`의 `toc` 필드에는 보존하되 기본적으로 `chunks.jsonl`에는 제외
- `chunks.jsonl`을 로드해 관련 chunk를 검색하고 AI 붙여넣기용 프롬프트 생성
- 관련성이 낮은 검색어는 경고하거나 결과 없음으로 처리
- 외부 AI API 호출 없이 로컬에서 동작

## 설치 방법

Windows PowerShell에서 프로젝트 폴더로 이동한 뒤 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행 방법

```powershell
python -m app.main
```

프로그램 창에서 PDF 파일을 선택하고 저장 위치를 지정한 뒤 `변환 시작`을 누르면 됩니다.

## 검색/프롬프트 생성

`검색/프롬프트 생성` 탭에서 변환 결과 폴더 또는 `chunks.jsonl` 파일을 선택하면 chunk를 로드할 수 있습니다.

- 변환 결과 폴더 선택 시 하위 `chunks.jsonl`을 자동 탐색합니다.
- 로드된 chunk 수, 파일 수, 문서 목록을 표시합니다.
- 단일 `chunks.jsonl`만 로드한 경우 전체 매뉴얼 검색 안내를 표시합니다.
- 질문 또는 검색어를 입력하면 관련 chunk를 점수순으로 표시합니다.
- 검색어의 핵심 단어가 섹션, 요약, 본문에 직접 포함된 chunk를 우선합니다.
- 검색 결과를 기반으로 ChatGPT, Claude, Gemini 등에 붙여넣을 수 있는 프롬프트를 생성합니다.
- 생성된 프롬프트는 클립보드로 복사할 수 있습니다.
- 외부 AI API 호출 없이 로컬 파일만 사용합니다.

## 출력 구조

```text
선택한_저장위치/
  converted_manuals/
    문서명/
      manual.md
      chunks.jsonl
      index.json
      tables/
        page_009_table_01.csv
      images/
        page_007_image_01.png
    all_manuals_index.json
```

## 출력 파일 설명

- `manual.md`: 사람이 읽기 쉬운 Markdown 정리본
- `chunks.jsonl`: AI 검색/RAG용 chunk 데이터
- `index.json`: 문서 메타데이터, 실제 본문 섹션, 목차(`toc`), 표, 이미지 색인
- `tables/*.csv`: PDF에서 추출한 표
- `images/*.png`: PDF에서 추출한 이미지
- `all_manuals_index.json`: 여러 PDF 전체 통합 색인

## 안정화된 변환 기준

- 반복 헤더/푸터와 페이지 번호를 제거합니다.
- 목차 페이지는 `manual.md`와 `index.json`의 `toc` 필드에 보존합니다.
- 목차 줄은 기본적으로 `chunks.jsonl`과 `index.sections`에 넣지 않습니다.
- 점선 리더(`.......... 101`)가 포함된 목차 항목은 실제 섹션 제목으로 만들지 않습니다.
- 실제 본문에서 다시 등장한 장/절 제목만 섹션으로 생성합니다.
- 같은 섹션 제목이 페이지 상단 반복 헤더로 다시 등장하면 중복 섹션으로 만들지 않습니다.
- `2.1.1.1. Features` 같은 개발자/API 문서의 세부 항목은 유지합니다.
- 기본값으로 1~2행의 작은 표와 32x32 미만의 작은 이미지는 제외합니다.
- 디버그 추적 로그는 개발 모드(`ConvertOptions(debug=True)`)에서만 출력됩니다.

최근 검증 기준:

- `AdministratorsManual.ko`: `section_count` 55, `2.1. 그룹 관리` 섹션 생성
- `DevelopersManual.ko`: `section_count` 약 570, `2.1. 데이터 형식` 반복 섹션 없음
- `UsersManual.ko`: `section_count` 45, `4.1. 페이지 작성` page range 63-92
- 중복 섹션명 상위 10개 없음
- 점선 목차 줄은 `index.sections`에 없음

## exe 빌드 방법

의존성을 설치한 뒤 아래 배치 파일을 실행합니다.

```powershell
.\build_exe.bat
```

빌드 결과는 기본적으로 `dist/` 폴더에 생성됩니다.

```text
dist/
  PDF Manual Optimizer.exe
```

## 현재 버전 범위

- OCR은 구현하지 않습니다.
- 외부 서버나 OpenAI API를 호출하지 않습니다.
- 키워드와 요약은 규칙 기반으로 생성합니다.
- 변환 중 일부 PDF 또는 표/이미지 추출 오류가 발생해도 로그에 기록하고 가능한 처리를 계속합니다.
