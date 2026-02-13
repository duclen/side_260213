"""상세 페이지 구조를 파악하기 위한 탐색 스크립트"""
import asyncio
from playwright.async_api import async_playwright

BOARD_LIST_URL = "https://www.k-apt.go.kr/web/board/webRepairPlan/boardList.do"


async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # 1) 목록 페이지 접근
        print("[1] 목록 페이지 접근...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 목록 HTML 구조 저장
        list_html = await page.content()
        with open("_debug_list.html", "w", encoding="utf-8") as f:
            f.write(list_html)
        print("    → _debug_list.html 저장 완료")

        # 2) 첫 번째 공개 게시글 클릭해서 상세 페이지 진입
        print("[2] 첫 번째 게시글 클릭...")
        # 게시글 제목 링크들 찾기
        links = await page.query_selector_all("a[href*='goCheck']")
        if not links:
            # onclick 방식일 수 있음
            links = await page.query_selector_all("[onclick*='goCheck']")

        if not links:
            # 다른 선택자 시도
            print("    → goCheck 링크를 찾지 못함, 다른 선택자 시도...")
            links = await page.query_selector_all(".bbsV_list li a, .board_list td a, table tbody tr td a")

        if links:
            print(f"    → {len(links)}개 링크 발견, 첫 번째 클릭")
            await links[0].click()
            await page.wait_for_timeout(3000)

            # alert 처리
            page.on("dialog", lambda dialog: dialog.accept())

            detail_html = await page.content()
            with open("_debug_detail.html", "w", encoding="utf-8") as f:
                f.write(detail_html)
            print("    → _debug_detail.html 저장 완료")
        else:
            print("    → 게시글 링크를 찾지 못함")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect())
