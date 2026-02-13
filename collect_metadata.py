"""
K-APT 장기수선계획서 메타데이터 수집기
목록 페이지(683페이지)를 순회하며 전체 게시글 메타데이터를 CSV로 저장한다.
"""
import asyncio
import csv
import json
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright

# ── 설정 ──
BASE_URL = "https://www.k-apt.go.kr"
BOARD_LIST_URL = f"{BASE_URL}/web/board/webRepairPlan/boardList.do"

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

METADATA_CSV = OUTPUT_DIR / "metadata.csv"
CHECKPOINT_FILE = Path(__file__).parent / "checkpoint_meta.json"

REQUEST_DELAY = 0.8  # 페이지 간 딜레이 (초)


def load_checkpoint() -> int:
    """마지막으로 완료한 페이지 번호를 반환. 없으면 0."""
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return data.get("last_page", 0)
    return 0


def save_checkpoint(page_no: int):
    CHECKPOINT_FILE.write_text(
        json.dumps({"last_page": page_no}, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_list_page(html: str) -> list[dict]:
    """목록 페이지 HTML에서 게시글 메타데이터를 추출한다."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    items = []

    for li in soup.select("ul.boardList > li"):
        # 표시 번호
        num_div = li.select_one("div.num")
        display_num = num_div.get_text(strip=True) if num_div else ""

        # seq, boardSecret — onclick="javascript:goCheck(128980, 0);"
        link = li.select_one("a.headLine")
        if not link:
            continue

        title = link.get_text(strip=True)
        onclick = link.get("onclick", "")
        m = re.search(r"goCheck\((\d+)\s*,\s*(\d+)\)", onclick)
        if not m:
            continue
        seq = m.group(1)
        board_secret = m.group(2)

        # 날짜
        date_span = li.select_one("span.boardDate")
        date = date_span.get_text(strip=True) if date_span else ""

        # 조회수
        info_p = li.select_one("p.info")
        views = ""
        if info_p:
            spans = info_p.select("span")
            if len(spans) >= 2:
                views = spans[1].get_text(strip=True).replace("\xa0", "").strip()
                # "0" or number after eye icon
                views = re.sub(r"[^\d]", "", views)

        items.append({
            "seq": seq,
            "display_num": display_num,
            "title": title,
            "date": date,
            "views": views,
            "board_secret": board_secret,
        })

    return items


def get_max_page(html: str) -> int:
    """pagination에서 최대 페이지 번호를 추출한다."""
    # 방법1: "끝 페이지" 링크에서 추출
    m = re.search(r'goList\((\d+)\)[^"]*"[^>]*>.*?끝', html, re.DOTALL)
    if m:
        return int(m.group(1))
    # 방법2: class="last" 링크에서 추출
    m = re.search(r'class="last"[^>]*href="javascript:goList\((\d+)\)', html)
    if m:
        return int(m.group(1))
    # 방법3: 가장 큰 goList 숫자 (href 안의 것만)
    pages = [int(x) for x in re.findall(r'href="javascript:goList\((\d+)\)', html)]
    if pages:
        return max(pages)
    # 방법4: 모든 goList 숫자
    pages = [int(x) for x in re.findall(r"goList\((\d+)\)", html)]
    return max(pages) if pages else 1


def get_total_count(html: str) -> int:
    """'총 N건' 텍스트에서 전체 게시글 수를 추출한다."""
    m = re.search(r"총\s*[\s<>/\w=\"]*?(\d[\d,]*)\s*건", html)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


async def collect_all_metadata():
    last_done = load_checkpoint()
    print(f"[시작] 체크포인트: {last_done}페이지까지 완료")

    # CSV 파일 준비 (이어쓰기 또는 새로 생성)
    csv_mode = "a" if last_done > 0 and METADATA_CSV.exists() else "w"
    csv_file = open(METADATA_CSV, csv_mode, newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(
        csv_file,
        fieldnames=["seq", "display_num", "title", "date", "views", "board_secret"],
    )
    if csv_mode == "w":
        writer.writeheader()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 팝업/alert 자동 닫기
        page.on("dialog", lambda dialog: dialog.dismiss())

        # 첫 페이지 접근 → 세션 + CSRF 확보
        print("[1] 첫 페이지 접근 중...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")

        # pagination이 렌더링될 때까지 대기
        try:
            await page.wait_for_selector("div.pagination", timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        # "오늘 하루 보지 않기" 팝업 닫기 시도
        for selector in [".popup_close", ".bClose", "[onclick*='closePopup']", ".close"]:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(300)
            except Exception:
                pass

        html = await page.content()
        max_page = get_max_page(html)
        total_count = get_total_count(html)

        if max_page <= 1:
            # fallback: JavaScript로 직접 확인
            max_page = await page.evaluate("""() => {
                const last = document.querySelector('.pagination .last');
                if (last) {
                    const m = last.getAttribute('href')?.match(/goList\\((\\d+)\\)/);
                    return m ? parseInt(m[1]) : 1;
                }
                return 1;
            }""")

        print(f"    총 {max_page} 페이지, {total_count}건 확인")

        # 첫 페이지 데이터 수집 (체크포인트 이후부터)
        start_page = last_done + 1 if last_done > 0 else 1
        total_collected = 0

        if start_page == 1:
            items = parse_list_page(html)
            for item in items:
                writer.writerow(item)
            total_collected += len(items)
            save_checkpoint(1)
            print(f"    [1/{max_page}] {len(items)}건 수집 (누적: {total_collected})")
            start_page = 2

        # 나머지 페이지 순회
        for page_no in range(start_page, max_page + 1):
            try:
                # goList(pageNo) 시뮬레이션: hidden input에 값 세팅 후 form submit
                await page.evaluate(f"""() => {{
                    document.listForm.pageNo.value = {page_no};
                    document.listForm.action = '/web/board/webRepairPlan/boardList.do';
                    document.listForm.submit();
                }}""")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(500)

                html = await page.content()
                items = parse_list_page(html)

                for item in items:
                    writer.writerow(item)
                csv_file.flush()

                total_collected += len(items)
                save_checkpoint(page_no)

                if page_no % 50 == 0 or page_no == max_page:
                    print(f"    [{page_no}/{max_page}] {len(items)}건 수집 (누적: {total_collected})")

            except Exception as e:
                print(f"    [에러] {page_no}페이지: {e}")
                # 페이지 복구 시도
                try:
                    await page.goto(BOARD_LIST_URL, wait_until="networkidle")
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
                continue

            await asyncio.sleep(REQUEST_DELAY)

        await browser.close()

    csv_file.close()
    print(f"\n[완료] 총 {total_collected}건 → {METADATA_CSV}")


if __name__ == "__main__":
    asyncio.run(collect_all_metadata())