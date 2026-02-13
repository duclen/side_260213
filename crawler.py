"""
K-APT 장기수선계획서 크롤러
메타데이터 CSV를 읽어 각 게시글의 상세 페이지에 진입하고,
DextUpload 네트워크 인터셉트로 파일 목록을 수집,
전체 다운로드 버튼을 클릭해 파일을 다운로드한다.
"""
import asyncio
import csv
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

# ── 설정 ──
BASE_URL = "https://www.k-apt.go.kr"
BOARD_LIST_URL = f"{BASE_URL}/web/board/webRepairPlan/boardList.do"
BOARD_TYPE = "15"

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
METADATA_CSV = OUTPUT_DIR / "metadata.csv"
RESULT_CSV = OUTPUT_DIR / "result.csv"
CHECKPOINT_FILE = BASE_DIR / "checkpoint_crawl.json"

REQUEST_DELAY = 1.5  # 요청 간 딜레이 (초)

DOWNLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ── 체크포인트 ──

def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return set(str(s) for s in data.get("done_seqs", []))
    return set()


def save_checkpoint(done_seqs: set):
    CHECKPOINT_FILE.write_text(
        json.dumps({"done_seqs": sorted(done_seqs)}, ensure_ascii=False),
        encoding="utf-8",
    )


# ── 메타데이터 로드 ──

def load_metadata() -> list[dict]:
    if not METADATA_CSV.exists():
        raise FileNotFoundError(f"{METADATA_CSV} 없음. 먼저 collect_metadata.py 실행 필요.")
    rows = []
    with open(METADATA_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("board_secret", "0") != "0":
                continue
            rows.append(row)
    return rows


# ── 단지 정보 추출 ──

APT_PATTERNS = [
    r"([\w가-힣]+(?:아파트|단지|맨션|빌라|타운|파크|힐스|캐슬|자이|래미안|e편한세상|푸르지오|더샵|롯데캐슬|코아루|한신더휴|포레나)[\w가-힣]*)",
    r"([\w가-힣]+\d+단지)",
]


def extract_apt_name(title: str, content_text: str = "") -> str:
    for text in [title, content_text]:
        for pat in APT_PATTERNS:
            m = re.search(pat, text)
            if m:
                return m.group(1)
    return title  # fallback


# ── 메인 크롤링 루프 ──

async def crawl():
    metadata = load_metadata()
    done_seqs = load_checkpoint()
    remaining = [m for m in metadata if m["seq"] not in done_seqs]

    print(f"[시작] 전체 {len(metadata)}건, 완료 {len(done_seqs)}건, 남은 {len(remaining)}건")
    if not remaining:
        print("처리할 게시글이 없습니다.")
        return

    # 결과 CSV
    result_fields = [
        "seq", "display_num", "title", "date", "apt_name",
        "file_count", "file_names", "file_paths", "download_status",
    ]
    csv_mode = "a" if RESULT_CSV.exists() and len(done_seqs) > 0 else "w"
    csv_file = open(RESULT_CSV, csv_mode, newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(csv_file, fieldnames=result_fields)
    if csv_mode == "w":
        writer.writeheader()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.on("dialog", lambda d: d.dismiss())

        # ── 파일 목록 네트워크 인터셉트 ──
        captured_files = {}

        async def on_response(response):
            if "fileListData.do" in response.url:
                try:
                    body = await response.json()
                    if body.get("code") == "SCC":
                        captured_files["data"] = body.get("data", [])
                except Exception:
                    pass

        page.on("response", on_response)

        # 세션 확보
        print("[1] 세션 확보 중...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")
        await page.wait_for_selector("div.pagination", timeout=10000)
        await page.wait_for_timeout(2000)

        processed = 0
        errors = 0

        for item in remaining:
            seq = item["seq"]
            title = item["title"]
            captured_files.clear()

            try:
                # ── 상세 페이지 진입 ──
                await page.evaluate(f"""() => {{
                    document.listForm.seq.value = '{seq}';
                    document.listForm.boardSecret.value = '0';
                    document.listForm.action = '/web/board/webRepairPlan/boardView.do';
                    document.listForm.submit();
                }}""")
                await page.wait_for_load_state("networkidle")

                # DextUpload 파일 목록 로딩 대기 (최대 15초)
                for _ in range(30):
                    if "data" in captured_files:
                        break
                    await page.wait_for_timeout(500)

                # 단지명 추출
                content_text = await page.evaluate("""() => {
                    const el = document.querySelector('.boardV_cont');
                    return el ? el.textContent : '';
                }""")
                apt_name = extract_apt_name(title, content_text)

                files = captured_files.get("data", [])
                file_names = []
                file_paths = []
                status = "NO_FILE"

                if files:
                    for f in files:
                        fname = f.get("fileName", "unknown")
                        fseq = f.get("seq", 1)
                        bseq = f.get("boardSeq", seq)
                        file_names.append(fname)

                        safe_name = re.sub(r'[<>:"/\\|?*]', '_', fname)
                        dest = DOWNLOAD_DIR / f"{bseq}_{fseq}_{safe_name}"

                        if dest.exists() and dest.stat().st_size > 0:
                            file_paths.append(str(dest))
                            status = "OK"
                            continue

                        # 다운로드: 전체 다운로드 버튼 클릭
                        try:
                            async with page.expect_download(timeout=30000) as dl_info:
                                await page.click("#btn-all-files")
                            download = await dl_info.value
                            await download.save_as(str(dest))
                            file_paths.append(str(dest))
                            status = "OK"
                        except Exception:
                            # fallback: a 태그 생성
                            try:
                                async with page.expect_download(timeout=30000) as dl_info:
                                    await page.evaluate(f"""() => {{
                                        const a = document.createElement('a');
                                        a.href = '/board/getFileDownload.do?seq={bseq}&boardType={BOARD_TYPE}&file_num={fseq}';
                                        a.download = '';
                                        document.body.appendChild(a);
                                        a.click();
                                        a.remove();
                                    }}""")
                                download = await dl_info.value
                                await download.save_as(str(dest))
                                file_paths.append(str(dest))
                                status = "OK"
                            except Exception:
                                file_paths.append("")
                                status = "FAIL"

                writer.writerow({
                    "seq": seq,
                    "display_num": item.get("display_num", ""),
                    "title": title,
                    "date": item.get("date", ""),
                    "apt_name": apt_name,
                    "file_count": len(files),
                    "file_names": " | ".join(file_names),
                    "file_paths": " | ".join(file_paths),
                    "download_status": status,
                })
                csv_file.flush()

                done_seqs.add(seq)
                processed += 1

                if processed % 5 == 0:
                    save_checkpoint(done_seqs)
                    print(f"    [{processed}/{len(remaining)}] {title[:50]} → {status}")

                # 목록 페이지로 복귀
                await page.evaluate("""() => {
                    document.listForm.action = '/web/board/webRepairPlan/boardList.do';
                    document.listForm.submit();
                }""")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(500)

            except Exception as e:
                errors += 1
                print(f"    [에러 {errors}] seq={seq}: {e}")
                try:
                    await page.goto(BOARD_LIST_URL, wait_until="networkidle")
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
                continue

            await asyncio.sleep(REQUEST_DELAY)

        save_checkpoint(done_seqs)
        await browser.close()

    csv_file.close()
    print(f"\n[완료] {processed}건 처리, {errors}건 에러 → {RESULT_CSV}")


if __name__ == "__main__":
    asyncio.run(crawl())