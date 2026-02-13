"""파일 다운로드 메커니즘 테스트 — 네트워크 인터셉트 방식"""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "https://www.k-apt.go.kr"
BOARD_LIST_URL = f"{BASE_URL}/web/board/webRepairPlan/boardList.do"
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


async def test_download():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.on("dialog", lambda d: d.dismiss())

        # 파일 목록 API 응답 캡처
        file_list_data = {}

        async def capture_file_list(response):
            if "fileListData.do" in response.url:
                try:
                    body = await response.json()
                    file_list_data["result"] = body
                    print(f"    [캡처] fileListData 응답: {json.dumps(body, ensure_ascii=False)[:200]}")
                except Exception:
                    pass

        page.on("response", capture_file_list)

        # 1) 목록 페이지 → 세션 확보
        print("[1] 목록 페이지...")
        await page.goto(BOARD_LIST_URL, wait_until="networkidle")
        await page.wait_for_selector("div.pagination", timeout=10000)
        await page.wait_for_timeout(2000)

        seq = await page.evaluate("""() => {
            const link = document.querySelector('a.headLine');
            const m = link?.getAttribute('onclick')?.match(/goCheck\\((\\d+)/);
            return m ? m[1] : null;
        }""")
        print(f"    seq = {seq}")

        # 2) 상세 페이지 진입
        print("[2] 상세 페이지 진입...")
        await page.evaluate(f"""() => {{
            document.listForm.seq.value = '{seq}';
            document.listForm.boardSecret.value = '0';
            document.listForm.action = '/web/board/webRepairPlan/boardView.do';
            document.listForm.submit();
        }}""")
        await page.wait_for_load_state("networkidle")

        # DextUpload가 파일 목록을 로드할 때까지 대기
        print("[3] DextUpload 파일 목록 로딩 대기...")
        for _ in range(20):
            if "result" in file_list_data:
                break
            await page.wait_for_timeout(500)

        if "result" not in file_list_data:
            print("    파일 목록 캡처 실패 — 더 기다립니다...")
            await page.wait_for_timeout(10000)

        if "result" in file_list_data:
            data = file_list_data["result"]
            files = data.get("data", [])
            print(f"    파일 {len(files)}개 발견")

            for f in files:
                fname = f.get("fileName", "unknown")
                fseq = f.get("seq", 1)
                bseq = f.get("boardSeq", seq)
                print(f"    → {fname} (boardSeq={bseq}, fileSeq={fseq})")

                safe_name = re.sub(r'[<>:"/\\|?*]', '_', fname)
                dest = DOWNLOAD_DIR / f"{bseq}_{fseq}_{safe_name}"

                # 다운로드 시도: DextUpload 전체 다운로드 클릭
                print(f"[4] 다운로드 시도...")
                try:
                    async with page.expect_download(timeout=30000) as dl_info:
                        await page.click("#btn-all-files")
                    download = await dl_info.value
                    print(f"    suggested_filename: {download.suggested_filename}")
                    await download.save_as(str(dest))
                    size = dest.stat().st_size
                    print(f"    성공: {dest.name} ({size:,} bytes)")
                except Exception as e:
                    print(f"    DextUpload 다운로드 실패: {e}")

                    # fallback: a 태그 다운로드
                    try:
                        async with page.expect_download(timeout=30000) as dl_info:
                            await page.evaluate(f"""() => {{
                                const a = document.createElement('a');
                                a.href = '/board/getFileDownload.do?seq={bseq}&boardType=15&file_num={fseq}';
                                a.download = '{safe_name}';
                                document.body.appendChild(a);
                                a.click();
                                a.remove();
                            }}""")
                        download = await dl_info.value
                        await download.save_as(str(dest))
                        size = dest.stat().st_size
                        print(f"    getFileDownload 성공: {dest.name} ({size:,} bytes)")
                    except Exception as e2:
                        print(f"    getFileDownload도 실패: {e2}")
        else:
            print("    파일 목록을 가져오지 못했습니다.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_download())