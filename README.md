# 🐍 side_260213
개요: 📦 Python 기반 메타데이터 수집 및 처리 파이프라인 프로젝트
목적: 다양한 소스에서 데이터를 수집(crawl)하고, 파싱(parse) → 정규화 → 저장(save)까지 일관된 흐름으로 처리하는 구조를 제공

## 🚀 프로젝트 개요
Python으로 작성된 크롤러/파서 기반 데이터 수집 파이프라인
✔ 다양한 소스에서 데이터 수집  
✔ 파싱 로직 분리  
✔ 구조화된 메타데이터 처리  
✔ 테스트 코드 포함  


## 📁 각 파일 기능
├── main.py # 실행 진입점
├── crawler.py # 크롤러 로직
├── parsers.py # 파서(파싱) 로직
├── config.py # 설정값 관리
├── inspect_files.py # 파일 검사 유틸리티
├── inspect_detail.py # 상세 검사 도구
├── collect_metadata.py # 메타데이터 수집 스크립트
├── output/ # 수집된 결과물 디렉토리
├── requirements.txt # 프로젝트 의존성 리스트
├── test_download.py # 다운로드 기능 테스트
├── test_metadata.py # 메타데이터 처리 테스트
└── checkpoint_meta.json # 체크포인트/상태 저장
