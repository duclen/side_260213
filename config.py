"""K-APT 장기수선계획서 크롤러 설정"""
from pathlib import Path

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
CHECKPOINT_FILE = BASE_DIR / "checkpoint.json"

# K-APT URLs
BASE_URL = "https://www.k-apt.go.kr"
BOARD_LIST_URL = f"{BASE_URL}/web/board/webRepairPlan/boardList.do"
BOARD_VIEW_URL = f"{BASE_URL}/web/board/webRepairPlan/boardView.do"
FILE_DOWNLOAD_URL = f"{BASE_URL}/board/getFileDownload.do"

BOARD_TYPE = "15"  # 장기수선계획서

# 크롤링 설정
REQUEST_DELAY = 1.0        # 요청 간 딜레이 (초)
PAGE_SIZE = 10             # 페이지당 게시글 수
MAX_RETRIES = 3            # 최대 재시도 횟수
HEADLESS = True            # 브라우저 숨김 여부
