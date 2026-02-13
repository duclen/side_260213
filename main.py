"""
K-APT 장기수선계획서 크롤러 — 메인 실행 스크립트

사용법:
    py -3 main.py metadata   # 1단계: 게시글 메타데이터 수집
    py -3 main.py crawl      # 2단계: 상세 진입 + 파일 다운로드
    py -3 main.py parse      # 3단계: 다운로드 파일 → CSV 변환
    py -3 main.py all        # 전체 실행
"""
import sys
import asyncio
from pathlib import Path


def run_metadata():
    from collect_metadata import collect_all_metadata
    asyncio.run(collect_all_metadata())


def run_crawl():
    from crawler import crawl
    asyncio.run(crawl())


def run_parse():
    """다운로드된 파일들을 CSV로 변환한다."""
    import csv
    import pandas as pd
    from parsers import parse_file, save_as_csv

    downloads_dir = Path(__file__).parent / "downloads"
    output_dir = Path(__file__).parent / "output"
    result_csv = output_dir / "result.csv"
    parsed_dir = output_dir / "parsed"
    parsed_dir.mkdir(exist_ok=True)

    if not result_csv.exists():
        print("result.csv가 없습니다. 먼저 crawl을 실행하세요.")
        return

    # result.csv에서 다운로드된 파일 목록 로드
    with open(result_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("download_status") == "OK" and r.get("file_path")]

    print(f"[파싱] 대상 파일 {len(rows)}개")

    success = 0
    fail = 0
    for row in rows:
        fpath = Path(row["file_path"])
        if not fpath.exists():
            continue

        seq = row["seq"]
        file_seq = row.get("file_seq", "1")
        apt_name = row.get("apt_name", "")
        title = row.get("title", "")

        df = parse_file(fpath)
        if df is not None and not df.empty:
            # 메타데이터 컬럼 추가
            df.insert(0, "_seq", seq)
            df.insert(1, "_apt_name", apt_name)
            df.insert(2, "_title", title)
            df.insert(3, "_date", row.get("date", ""))
            df.insert(4, "_file_name", row.get("file_name", ""))

            out_name = f"{seq}_{file_seq}.csv"
            save_as_csv(df, parsed_dir / out_name)
            success += 1
        else:
            fail += 1
            print(f"    [원본 보존] {fpath.name} — 파싱 불가")

    print(f"\n[완료] 파싱 성공: {success}, 원본 보존: {fail}")
    print(f"    CSV 파일: {parsed_dir}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "metadata":
        run_metadata()
    elif cmd == "crawl":
        run_crawl()
    elif cmd == "parse":
        run_parse()
    elif cmd == "all":
        run_metadata()
        run_crawl()
        run_parse()
    else:
        print(f"알 수 없는 명령: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()