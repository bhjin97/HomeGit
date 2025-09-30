# -*- coding: utf-8 -*-
# pip install playwright
# playwright install

import asyncio, re, csv, random, traceback
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── 설정 ─────────────────────────────────────────────────────
START_URL = (
    "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
    "?dispCatNo=100000100010015&isLoginCnt=1&aShowCnt=0&bShowCnt=0&cShowCnt=0"
    "&gateCd=Drawer&trackingCd=Cat100000100010015_MID"
    "&t_page=%EB%93%9C%EB%A1%9C%EC%9A%B0_%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC"
    "&t_click=%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC%ED%83%AD_%EC%A4%91%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC"
    "&t_1st_category_type=%EB%8C%80_%EC%8A%A4%ED%82%A8%EC%BC%80%EC%96%B4"
    "&t_2nd_category_type=%EC%A4%91_%ED%81%AC%EB%A6%BC"
    "&pageIdx=1&rowsPerPage=24&prdSort=01&searchTypeSort=btn_thumb&plusButtonFlag=N"
)
CATEGORY_PAGE_URL = START_URL
MAX_PAGES_TO_SCRAPE = 31
MAX_CONCURRENT_PAGES = 5

# 동시성 제어 (세마포어)
SEM = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

# 리스트(카테고리) 구조
ROW_SEL_ALL = "#Contents > ul.cate_prd_list.gtm_cate_list"
ITEMS_IN_ROW = ":scope > li"
ANCHOR_SEL = "a.prd_info, div > a, a"

# 상세 상단(상품명/가격/대표이미지/리뷰수/카테고리)
SEL_TOP = {
    "name": "#Contents > div.prd_detail_box.renew > div.right_area > div > p.prd_name, "
            "#Contents > div.prd_detail_box.renew > div.right_area h3.prd_name, "
            "p.prd_name",
    "price": "#Contents > div.prd_detail_box.renew > div.right_area > div > div.price > span.price-2 > strong",
    "image": "#mainImg",
    "review_cnt": "#repReview > em",
    # 요청 셀렉터 + 안전한 폴백 몇 개 추가
    "category": "#Contents > div.page_location > ul > li:nth-child(3) #dtlCatNm, "
                "#Contents div.page_location #dtlCatNm, "
                "#dtlCatNm"
}

# 탭 후보 셀렉터(기존 유지)
TAB_BTN_INFO = (
    "ul#tabList li#productInfo a, div.prd_tab li a:has-text('상품정보'), "
    "a[role='tab']:has-text('상품정보'), ul#tabList li#buyinfo a, "
    "div.prd_tab li a:has-text('구매정보'), a[role='tab']:has-text('구매정보')"
)

# ── 키워드 (수정 불필요 영역) ──
CAPACITY_KEYS = ["내용물의 용량 또는 중량"]
EXPIRY_KEYS = ["사용기한(또는 개봉 후 사용기간)"]
USAGE_KEYS = ["사용방법"]
CAUTION_KEYS = ["사용할 때의 주의사항"]
MANUFACTURER_KEYS = ["화장품제조업자", "화장품책임판매업자", "제조회사 및 책임판매업자"]
COUNTRY_OF_ORIGIN_KEYS = ["제조국"]
INGREDIENT_KEYS = ["화장품법에 따라 기재해야 하는 모든 성분"]

ALL_KEYS = (
    CAPACITY_KEYS + EXPIRY_KEYS + USAGE_KEYS + CAUTION_KEYS +
    MANUFACTURER_KEYS + COUNTRY_OF_ORIGIN_KEYS + INGREDIENT_KEYS
)

# 타임슬립
SLEEP_BASE = 0.25
SLEEP_JITTER = (0.10, 0.35)
ROW_PAUSE_SEC = 0.6
DETAIL_PAUSE_SEC = 0.6

# 저장 경로
SAVE_DIR = Path.cwd()
SAVE_NAME = "Olive_Cream.csv"

# ── 유틸 ─────────────────────────────────────────────────────
def clean(t):
    if t is None:
        return None
    t = re.sub(r"<\s*br\s*/?>|\&nbsp\;|\u00A0", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip() if t else None

def parse_price(t):
    t = re.sub(r"[^\d]", "", t or "")
    return int(t) if t else None

def parse_int(t):
    t = re.sub(r"[^\d]", "", t or "")
    return int(t) if t else None

def goods_no_from(href):
    if not href:
        return None
    qs = parse_qs(urlparse(href).query)
    if qs.get("goodsNo"):
        return qs["goodsNo"][0]
    m = re.search(r"(?:goodsNo|goodsCd)=(\d+)", href, re.I)
    return m.group(1) if m else None

async def nap(sec=None):
    await asyncio.sleep(sec if sec is not None else (SLEEP_BASE + random.uniform(*SLEEP_JITTER)))

# 기본 타임아웃 상향
async def get_text_or_none(ctx, selector, timeout=5000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout)
        return clean(await loc.inner_text())
    except Exception:
        return None

async def get_attr_or_none(ctx, selector, attr, timeout=8000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout)
        return await loc.get_attribute(attr)
    except Exception:
        return None

def _norm(t: str) -> str:
    t = re.sub(r"[\s\:\u00A0·\/\(\)\-]+", "", (t or "")).lower()
    return t

def _has_key(label: str, keys: list[str]) -> bool:
    normalized_label = _norm(label)
    return any(_norm(k) in normalized_label for k in keys)

# 경계 패턴: 원문 키워드
REGEX_SEP_PATTERN = "|".join([re.escape(k) for k in ALL_KEYS])

async def extract_from_artcinfo(page_scope) -> dict:
    out = {
        "capacity": None, "expiry": None, "usage": None, "caution": None,
        "manufacturer": None, "country_of_origin": None, "ingredients": None
    }

    def _assign(field, value):
        nonlocal out
        cleaned_value = clean(value)
        if out[field] is not None or not cleaned_value:
            return False
        out[field] = cleaned_value
        return True

    # 1) 구조적 추출
    artc_scope = page_scope.locator("#artcInfo").first
    if await artc_scope.count() > 0:
        try:
            await artc_scope.wait_for(state="visible", timeout=8000)
        except Exception:
            pass

        dls = artc_scope.locator("dl.detail_info_list")
        for i in range(await dls.count()):
            dl = dls.nth(i)
            try:
                dt_txt = clean(await dl.locator("dt").first.inner_text())
                dd_html = await dl.locator("dd").first.inner_html()
            except Exception:
                continue
            if not dt_txt or not dd_html:
                continue

            if _has_key(dt_txt, CAPACITY_KEYS): _assign("capacity", dd_html)
            elif _has_key(dt_txt, EXPIRY_KEYS): _assign("expiry", dd_html)
            elif _has_key(dt_txt, USAGE_KEYS): _assign("usage", dd_html)
            elif _has_key(dt_txt, CAUTION_KEYS): _assign("caution", dd_html)
            elif _has_key(dt_txt, MANUFACTURER_KEYS): _assign("manufacturer", dd_html)
            elif _has_key(dt_txt, COUNTRY_OF_ORIGIN_KEYS): _assign("country_of_origin", dd_html)
            elif _has_key(dt_txt, INGREDIENT_KEYS): _assign("ingredients", dd_html)

        rows = artc_scope.locator("table tr, .tbl_prd_info tr")
        for i in range(await rows.count()):
            tr = rows.nth(i)
            try:
                th_txt = clean(await tr.locator("th").first.inner_text())
                td_html = await tr.locator("td").first.inner_html()
                td_txt = clean(td_html)
            except Exception:
                continue
            if not th_txt or not td_txt:
                continue

            if _has_key(th_txt, CAPACITY_KEYS): _assign("capacity", td_txt)
            elif _has_key(th_txt, EXPIRY_KEYS): _assign("expiry", td_txt)
            elif _has_key(th_txt, USAGE_KEYS): _assign("usage", td_txt)
            elif _has_key(th_txt, CAUTION_KEYS): _assign("caution", td_txt)
            elif _has_key(th_txt, MANUFACTURER_KEYS): _assign("manufacturer", td_txt)
            elif _has_key(th_txt, COUNTRY_OF_ORIGIN_KEYS): _assign("country_of_origin", td_txt)
            elif _has_key(th_txt, INGREDIENT_KEYS): _assign("ingredients", td_txt)

    # 2) 폴백: 페이지 전체 텍스트 스캔
    if None in out.values():
        try:
            full_page_text = clean(await page_scope.inner_text("body")) or ""
        except Exception:
            full_page_text = ""

        if out["ingredients"] is None:
            ingredients_pattern = fr'(?:{"|".join([re.escape(k) for k in INGREDIENT_KEYS])})' \
                                  fr'[\s:/()\u00A0·\-]*([\s\S]{{30,}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
            match = re.search(ingredients_pattern, full_page_text, re.IGNORECASE | re.DOTALL)
            if match and clean(match.group(1)):
                _assign("ingredients", match.group(1))

        for key_list, field_name in [
            (CAPACITY_KEYS, "capacity"),
            (EXPIRY_KEYS, "expiry"),
            (MANUFACTURER_KEYS, "manufacturer"),
            (COUNTRY_OF_ORIGIN_KEYS, "country_of_origin"),
        ]:
            if out[field_name] is None:
                pattern_str = fr'(?:{"|".join([re.escape(k) for k in key_list])})' \
                              fr'[\s:/()\u00A0·\-]*([\s\S]{{5,800}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
                match = re.search(pattern_str, full_page_text, re.IGNORECASE | re.DOTALL)
                if match and clean(match.group(1)):
                    _assign(field_name, match.group(1))

    return out

async def scrape_detail(context, url: str) -> dict:
    """단일 상품 상세 페이지 스크래핑"""
    page = await context.new_page()
    name = None
    try:
        await nap(DETAIL_PAUSE_SEC + random.uniform(0.1, 0.5))
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 상단 정보
        name = await get_text_or_none(page, SEL_TOP["name"], 15000)
        price = parse_price(await get_text_or_none(page, SEL_TOP["price"], 8000))
        imgsrc = await get_attr_or_none(page, SEL_TOP["image"], "src", 8000)
        image = urljoin(page.url, imgsrc) if imgsrc else None
        rev = parse_int(await get_text_or_none(page, SEL_TOP["review_cnt"], 5000))

        # ⬇⬇⬇ 카테고리(요청 셀렉터) 추가 추출 ⬇⬇⬇
        category = await get_text_or_none(page, SEL_TOP["category"], 5000)

        # 탭 전환: '구매정보' 우선 → 후보 셀렉터
        buyinfo_tab_loc = page.locator("a:has-text('구매정보')").first
        try:
            if await buyinfo_tab_loc.count() > 0:
                await buyinfo_tab_loc.scroll_into_view_if_needed(timeout=3000)
                await page.wait_for_timeout(300)
                await buyinfo_tab_loc.click(timeout=5000, force=True)
            else:
                await page.locator(TAB_BTN_INFO).first.click(timeout=3000, force=True)
        except Exception:
            print(f"[WARN: TAB_FAIL] '{name or url}' - 탭 클릭 실패. 현재 페이지에서 추출 시도.")

        # 실제 콘텐츠 등장 대기
        try:
            await page.wait_for_selector("#artcInfo", state="visible", timeout=10000)
            await page.wait_for_selector("#artcInfo dl.detail_info_list, #artcInfo table", timeout=8000)
        except Exception:
            pass

        info = await extract_from_artcinfo(page)

        if not (info.get("capacity") or info.get("expiry") or info.get("ingredients") or info.get("country_of_origin")):
            print(f"[WARN: KEYWORD_MATCH_FAIL] '{name or url}' - 핵심 상세 정보 미검출.")

        return {
            "product_name": name,
            "price_krw": price,
            "image_url": image,
            "review_count": rev,
            "category": category,  # ← 추가
            "capacity": info.get("capacity"),
            "expiry": info.get("expiry"),
            "usage": info.get("usage"),
            "caution": info.get("caution"),
            "manufacturer": info.get("manufacturer"),
            "country_of_origin": info.get("country_of_origin"),
            "ingredients": info.get("ingredients"),
        }
    finally:
        await page.close()

async def scrape_detail_limited(context, url: str) -> dict:
    async with SEM:
        return await scrape_detail(context, url)

# ── 메인 ─────────────────────────────────────────────────────
async def main():
    # 저장 경로 설정
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        out_csv = (SAVE_DIR / SAVE_NAME).resolve()
    except Exception as e:
        print(f"[WARN] 지정 경로 ({SAVE_DIR}) 실패. 현재 폴더 저장:", e)
        out_csv = (Path.cwd() / SAVE_NAME).resolve()
    print("Save to:", out_csv)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 운영시 True 권장
            slow_mo=500      # 운영시 제거 권장
        )
        context = await browser.new_context(
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121 Safari/537.36"),
            extra_http_headers={"Referer": CATEGORY_PAGE_URL}
        )
        page = await context.new_page()

        # 1) 리스트 수집
        all_product_data = []
        global_index = 0
        url_base = START_URL

        for page_num in range(1, MAX_PAGES_TO_SCRAPE + 1):
            new_url = re.sub(r"pageIdx=\d+", f"pageIdx={page_num}", url_base)
            print(f"\n--- Loading Category Page {page_num} (URL: {new_url[:100]}...) ---")

            try:
                await page.goto(new_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector(ROW_SEL_ALL, timeout=10000)
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"[ERROR] Failed to load page {page_num} via URL. Stopping iteration: {e}")
                break

            rows_all = page.locator(ROW_SEL_ALL)
            total_rows = await rows_all.count()

            if total_rows == 0 and page_num > 1:
                print(f"[INFO] Page {page_num} loaded but contains no product groups. Stopping iteration.")
                break
            elif total_rows == 0:
                print(f"[ERROR] Failed to load product list on page 1. Check selectors or URL.")
                continue

            print(f"Products group loaded in page {page_num}: {total_rows} groups.")

            for r in range(total_rows):
                row = rows_all.nth(r)
                await row.scroll_into_view_if_needed()
                await page.wait_for_timeout(450)

                cards = row.locator(ITEMS_IN_ROW)
                cnt = await cards.count()

                for i in range(cnt):
                    li = cards.nth(i)
                    await li.wait_for(state="visible", timeout=4000)
                    a = li.locator(ANCHOR_SEL).first

                    href = await a.get_attribute("href")
                    product_url = urljoin(page.url, href) if href else None

                    name_loc = a.locator(".prd_name, .tx_name")
                    product_name = clean(await name_loc.first.inner_text()) if await name_loc.count() else None
                    if not product_name:
                        t = await a.get_attribute("title") or await a.inner_text()
                        product_name = clean(t)

                    brand = None
                    brand_loc = li.locator(".tx_brand, .brand, .brandNm")
                    if await brand_loc.count():
                        brand = clean(await brand_loc.first.inner_text())

                    price_txt = None
                    for sel in (".price .num", ".tx_cur", ".cur_price", ".price"):
                        loc = li.locator(sel)
                        if await loc.count():
                            price_txt = clean(await loc.first.inner_text())
                            break
                    price_krw = parse_price(price_txt)

                    image_url = None
                    if await li.locator("img").count():
                        for attr in ("data-src", "data-original", "data-lazy", "src"):
                            src = await li.locator("img").first.get_attribute(attr)
                            if src:
                                image_url = urljoin(page.url, src)
                                break

                    goods_no = goods_no_from(href)
                    data_index = await li.get_attribute("data-index")
                    data_number = await li.get_attribute("data-number")
                    col_idx = (int(data_index) % 4 + 1) if data_index and data_index.isdigit() else (i % 4 + 1)

                    all_product_data.append({
                        "row": page_num, "col": col_idx, "global_index": global_index,
                        "li_data_index": data_index, "li_data_number": data_number,
                        "goods_no": goods_no, "brand_name": brand,
                        "category": None,  # ← 상세에서 채움
                        "product_name": product_name, "price_krw": price_krw,
                        "product_url": product_url, "image_url": image_url,
                        "review_count": None, "capacity": None, "expiry": None,
                        "usage": None, "caution": None, "manufacturer": None,
                        "country_of_origin": None, "ingredients": None,
                    })
                    global_index += 1

                    display_name_list = product_name or goods_no or 'Unknown Product (List)'
                    print(f"[LIST {page_num}-{col_idx}] {display_name_list}")
                    await nap()

                await nap(ROW_PAUSE_SEC)

        await page.close()
        print(f"\n[INFO] List scraping finished. Total {len(all_product_data)} items collected.")

        # 2) 상세 스크래핑 (세마포어로 동시성 제어, zip 매칭)
        items_to_scrape = [item for item in all_product_data if item['product_url']]
        print(f"\nStarting detail scraping for {len(items_to_scrape)} items with concurrency: {MAX_CONCURRENT_PAGES}...")

        tasks = [scrape_detail_limited(context, it['product_url']) for it in items_to_scrape]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for original_item, detail_result in zip(items_to_scrape, results):
            display_name = original_item.get('product_name') or original_item.get('goods_no') or 'Unknown Product'
            if isinstance(detail_result, dict):
                if detail_result.get('product_name'):
                    original_item['product_name'] = detail_result['product_name']

                # 카테고리 포함해서 상세 필드 보강
                for k in ["category", "review_count", "capacity", "expiry", "usage",
                          "caution", "manufacturer", "country_of_origin", "ingredients"]:
                    if original_item.get(k) is None:
                        original_item[k] = detail_result.get(k)

                print(
                        f"[DETAIL OK] {original_item['global_index']}: "
                        f"{(original_item.get('product_name') or original_item.get('goods_no') or 'Unknown Product')[:30]}..."
                    )

            else:
                print(f"[DETAIL FAIL] {original_item['global_index']}: {display_name[:30]}... ({detail_result.__class__.__name__})")
                if isinstance(detail_result, Exception):
                    traceback.print_exception(type(detail_result), detail_result, detail_result.__traceback__)

        # 3) 저장 (CSV에 category 컬럼 추가)
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "row","col","global_index","li_data_index","li_data_number",
                "goods_no","brand_name","category",  # ← 여기 추가
                "product_name","price_krw",
                "product_url","image_url","review_count","capacity","expiry",
                "usage","caution","manufacturer","country_of_origin","ingredients"
            ])
            writer.writeheader()
            writer.writerows(all_product_data)

        print(f"\nSaved {len(all_product_data)} items -> {out_csv}")
        await browser.close()

# ▶ .py 스크립트로 실행할 때:
if __name__ == "__main__":
    asyncio.run(main())
