"""상세 페이지의 파일 다운로드 메커니즘을 파악하기 위한 스크립트.
네트워크 요청을 인터셉트하여 DextUpload의 실제 API 호출을 캡처한다.
"""
import asyncio
import json
from playwright.async_api import async_playwright

BOARD_LIST_URL = "https://www.k-apt.go.kr/web/board/webRepairPlan/boardList.do"


async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # 네트워크 요청 캡처
        captured_requests = []

        async def on_request(request):
            url = request.url
            if any(kw in url.lower() for kw in ["file", "dext", "upload", "download"]):
                captured_requests.append({
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                })
                print(f"  [REQ] {request.method} {url}")
                if request.post_data:
                    print(f"        body: {request.post_data[:300]}")

        captured_responses = []

        async def on_response(response):
            url = response.url
            if any(kw in url.lower() for kw in ["file", "dext", "upload", "download"]):
                body = ""
                try:
                    body = await response.text()
                except Exception:
                    body = "<binary>"
                captured_responses.append({
                    "url": url,
                    "status": response.status,
                    "body_preview": body[:500] if body else "",
                })
                print(f"  [RES] {response.status} {url}")
                if body and body != "<binary>":
                    print(f"        body: {body[:300]}")

        page.on("request", on_request)
        page.on("response", on_response)

        # 목록 페이지 접근
        print("[1] 목록 페이지...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 첫 번째 게시글 상세 페이지 진입
        print("\n[2] 첫 번째 게시글 진입...")
        await page.evaluate("""() => {
            const links = document.querySelectorAll('a.headLine');
            if (links.length > 0) {
                const onclick = links[0].getAttribute('onclick');
                const match = onclick.match(/goCheck\\((\\d+)\\s*,\\s*(\\d+)\\)/);
                if (match) {
                    document.listForm.seq.value = match[1];
                    document.listForm.boardSecret.value = match[2];
                    document.listForm.action = '/web/board/webRepairPlan/boardView.do';
                    document.listForm.submit();
                }
            }
        }""")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)  # DextUpload 로딩 대기

        # 추가 대기 — DextUpload SVG가 로드된 후 파일 목록 요청이 올 수 있음
        await page.wait_for_timeout(5000)

        # 결과 덤프
        print("\n=== 캡처된 요청 ===")
        for r in captured_requests:
            print(json.dumps(r, indent=2, ensure_ascii=False))

        print("\n=== 캡처된 응답 ===")
        for r in captured_responses:
            print(json.dumps(r, indent=2, ensure_ascii=False))

        # 현재 페이지의 iframe/object 내부 확인
        print("\n[3] 페이지 내 파일 관련 요소 확인...")
        file_info = await page.evaluate("""() => {
            const result = {};
            // fileContainer 확인
            const fc = document.getElementById('fileContainer');
            result.fileContainer = fc ? fc.innerHTML.substring(0, 500) : 'NOT FOUND';
            // DextUpload 객체 확인
            result.hasDextUpload = typeof FileDextUploadManager !== 'undefined';
            // form 확인
            const form = document.listForm;
            if (form) {
                result.formData = {};
                for (let el of form.elements) {
                    if (el.name) result.formData[el.name] = el.value;
                }
            }
            return result;
        }""")
        print(json.dumps(file_info, indent=2, ensure_ascii=False))

        # DextUpload에서 파일 목록 직접 가져오기 시도
        print("\n[4] DextUpload 파일 목록 가져오기...")
        file_list = await page.evaluate("""() => {
            try {
                if (typeof FileDextUploadManager !== 'undefined') {
                    // DextUpload의 파일 목록 접근
                    const mgr = FileDextUploadManager;
                    return JSON.stringify(mgr);
                }
                return 'FileDextUploadManager not available';
            } catch(e) {
                return 'Error: ' + e.message;
            }
        }""")
        print(f"    DextUpload: {str(file_list)[:500]}")

        # 파일 다운로드 버튼 존재 확인
        print("\n[5] 다운로드 버튼 확인...")
        buttons = await page.evaluate("""() => {
            const btns = document.querySelectorAll('[onclick*="fileDownload"], [onclick*="FileDown"], button[id*="file"]');
            return Array.from(btns).map(b => ({
                id: b.id,
                text: b.textContent.trim(),
                onclick: b.getAttribute('onclick'),
            }));
        }""")
        print(json.dumps(buttons, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect())