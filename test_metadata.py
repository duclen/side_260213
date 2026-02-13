"""메타데이터 수집 테스트 — 3페이지만 수집"""
import asyncio
import re
from playwright.async_api import async_playwright

BOARD_LIST_URL = "https://www.k-apt.go.kr/web/board/webRepairPlan/boardList.do"


def parse_list_page(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("ul.boardList > li"):
        num_div = li.select_one("div.num")
        display_num = num_div.get_text(strip=True) if num_div else ""
        link = li.select_one("a.headLine")
        if not link:
            continue
        title = link.get_text(strip=True)
        onclick = link.get("onclick", "")
        m = re.search(r"goCheck\((\d+)\s*,\s*(\d+)\)", onclick)
        if not m:
            continue
        seq = m.group(1)
        date_span = li.select_one("span.boardDate")
        date = date_span.get_text(strip=True) if date_span else ""
        items.append({"seq": seq, "display_num": display_num, "title": title, "date": date})
    return items


async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("[1] 목록 1페이지 접근...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 최대 페이지 확인
        html = await page.content()
        pages = [int(x) for x in re.findall(r"goList\((\d+)\)", html)]
        max_page = max(pages) if pages else 1
        print(f"    총 {max_page}페이지")

        for pg in range(1, 4):
            if pg > 1:
                await page.evaluate(f"""() => {{
                    document.listForm.pageNo.value = {pg};
                    document.listForm.action = '/web/board/webRepairPlan/boardList.do';
                    document.listForm.submit();
                }}""")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(500)
                html = await page.content()

            items = parse_list_page(html)
            print(f"\n[페이지 {pg}] {len(items)}건:")
            for item in items:
                print(f"  seq={item['seq']}  {item['date']}  {item['title'][:50]}")

        # 상세 페이지 테스트 — 첫 번째 게시글
        first_seq = parse_list_page(await page.content())[0]["seq"]
        print(f"\n[상세 테스트] seq={first_seq} 진입...")

        await page.evaluate(f"""() => {{
            document.listForm.seq.value = {first_seq};
            document.listForm.boardSecret.value = 0;
            document.listForm.action = '/web/board/webRepairPlan/boardView.do';
            document.listForm.submit();
        }}""")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)

        detail_html = await page.content()

        # 파일 목록 API 호출 시도
        cookies = await context_cookies(page)
        csrf = await page.evaluate("() => document.querySelector('meta[name=_csrf]')?.content")
        print(f"    CSRF: {csrf[:20]}...")

        # fileListData.do API 확인
        file_data = await page.evaluate("""() => {
            return new Promise((resolve) => {
                $.ajax({
                    url: '/web/board/webRepairPlan/fileListData.do',
                    type: 'POST',
                    data: $('#listForm').serialize(),
                    success: (data) => resolve(JSON.stringify(data)),
                    error: (e) => resolve('ERROR: ' + e.status)
                });
            });
        }""")
        print(f"    파일 목록 API 응답: {file_data[:500]}")

        await browser.close()


async def context_cookies(page):
    return await page.context.cookies()


if __name__ == "__main__":
    asyncio.run(test())