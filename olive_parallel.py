# -*- coding: utf-8 -*-
# pip install playwright
# playwright install

import asyncio, re, csv, random
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── 설정 ─────────────────────────────────────────────────────
# 🌟 START_URL을 pageIdx=1이 포함된 안정적인 URL 구조로 변경했습니다.
START_URL = (
    "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
    # pageIdx=1을 기준으로 prdSort, rowsPerPage 등의 필수 파라미터를 추가하여 안정적인 페이지네이션 URL로 만듦
    "?dispCatNo=100000100010013&fltDispCatNo=&prdSort=01&pageIdx=1&rowsPerPage=24"
    "&searchTypeSort=btn_thumb&plusButtonFlag=N&isLoginCnt=0&aShowCnt=0&bShowCnt=0&cShowCnt=0"
    "&trackingCd=Cat100000100010013_Small&amplitudePageGubun=&t_page=%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC%EA%B4%80&t_click=%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC%ED%83%AD_%EC%A4%91%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC"
    "&midCategory=%EC%8A%A4%ED%82%A8%2F%ED%86%A0%EB%84%88&smallCategory=%EC%A0%84%EC%B2%B4&checkBrnds=&lastChkBrnd="
    "&t_1st_category_type=%EB%8C%80_%EC%8A%A4%ED%82%A8%EC%BC%80%EC%96%B4&t_2nd_category_type=%EC%A4%91_%EC%8A%A4%ED%82%A8%2F%ED%86%A0%EB%84%88"
)
CATEGORY_PAGE_URL = START_URL 
MAX_PAGES_TO_SCRAPE = 10 
# 🌟 병렬 처리 설정: 최대 5개의 상세 페이지를 동시에 스크래핑합니다. (적절히 조정 가능)
MAX_CONCURRENT_PAGES = 5 

# 리스트(카테고리) 구조
ROW_SEL_ALL = "#Contents > ul.cate_prd_list.gtm_cate_list"
ITEMS_IN_ROW = ":scope > li"
ANCHOR_SEL = "a.prd_info, div > a, a"

# 상세 상단(상품명/가격/대표이미지/리뷰수)
SEL_TOP = {
    "name": "#Contents > div.prd_detail_box.renew > div.right_area > div > p.prd_name",
    "price": "#Contents > div.prd_detail_box.renew > div.right_area > div > div.price > span.price-2 > strong",
    "image": "#mainImg",
    "review_cnt": "#repReview > em",
}

# '구매정보' 탭 버튼 (이전과 동일)
TAB_BTN_INFO = (
    "ul#tabList li#productInfo a, div.prd_tab li a:has-text('상품정보'), "
    "a[role='tab']:has-text('상품정보'), ul#tabList li#buyinfo a, " 
    "div.prd_tab li a:has-text('구매정보'), a[role='tab']:has-text('구매정보')"
)

# 🌟 키워드 목록
CAPACITY_KEYS = ["용량", "용량/중량", "내용량", "중량", "내용물의 용량 또는 중량"]
EXPIRY_KEYS = ["사용기한", "사용기간", "개봉후사용기간", "사용기한(또는 개봉 후 사용기간)"]
USAGE_KEYS = ["사용방법", "사용법", "용법"]
CAUTION_KEYS = ["주의사항", "사용시의주의사항", "사용상의주의사항", "사용할 때의 주의사항"]
MANUFACTURER_KEYS = ["제조회사", "제조업자", "책임판매업자", "화장품제조업자", "화장품책임판매업자", "제조회사 및 책임판매업자"] 
COUNTRY_OF_ORIGIN_KEYS = ["제조국", "제조국가", "원산지", "원산국", "제조국 및 제조사"] 
INGREDIENT_KEYS = [
    "성분", "전성분", "원료명", "주요성분", 
    "화장품법에 따라 기재해야 하는 모든 성분", 
    "화장품법에따라기재표시해야하는모든성분" 
] 

# 모든 키워드를 하나로 통합 (정규식 구분자 생성을 위함)
ALL_KEYS = (
    CAPACITY_KEYS + EXPIRY_KEYS + USAGE_KEYS + CAUTION_KEYS + 
    MANUFACTURER_KEYS + COUNTRY_OF_ORIGIN_KEYS + INGREDIENT_KEYS
)

# 타임슬립
SLEEP_BASE = 0.25
SLEEP_JITTER = (0.10, 0.35)
ROW_PAUSE_SEC = 0.6
DETAIL_PAUSE_SEC = 0.6 

# 🌟 저장 경로 수정: 현재 실행 폴더에 저장하도록 기본값 변경
SAVE_DIR = Path.cwd() 
SAVE_NAME = "oliveyoung_rows_with_details_10pages_url_pagination_PARALLEL.csv" 

# ── 유틸 ─────────────────────────────────────────────────────
def clean(t): 
    if t is None: return None
    # HTML 줄바꿈/공백 문자를 일반 공백으로 치환 후, 과도한 공백 제거
    t = re.sub(r"<\s*br\s*/?>|\&nbsp\;|\u00A0", " ", t, flags=re.IGNORECASE)
    # 텍스트 추출 시 <p>, <li> 등의 태그가 텍스트에 포함되지 않도록 inner_html 대신 inner_text 사용을 전제로 함
    return re.sub(r"\s+", " ", t).strip() if t else None

def parse_price(t): t = re.sub(r"[^\d]", "", t or ""); return int(t) if t else None
def parse_int(t): t = re.sub(r"[^\d]", "", t or ""); return int(t) if t else None
def goods_no_from(href):
    if not href: return None
    qs = parse_qs(urlparse(href).query)
    if qs.get("goodsNo"): return qs["goodsNo"][0]
    m = re.search(r"(?:goodsNo|goodsCd)=(\d+)", href, re.I)
    return m.group(1) if m else None

async def nap(sec=None):
    # 병렬 처리 환경에서는 상세 스크래핑 대기 시간은 scrape_detail 함수 내에서만 적용
    # 목록 수집 시의 nap 시간은 짧게 유지
    await asyncio.sleep(sec if sec is not None else (SLEEP_BASE + random.uniform(*SLEEP_JITTER)))

async def get_text_or_none(ctx, selector, timeout=8000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout) 
        return clean(await loc.inner_text())
    except Exception:
        return None

async def get_attr_or_none(ctx, selector, attr, timeout=4000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="attached", timeout=timeout)
        return await loc.get_attribute(attr)
    except Exception:
        return None

def _norm(t: str) -> str:
    """모든 공백, 줄바꿈, 특수문자 등을 제거하고 소문자로 변환하여 비교 유연성 강화"""
    # 콜론, 슬래시, 괄호 등도 제거하여 '용량/중량' == '용량'으로 매칭되도록 함
    t = re.sub(r"[\s\:\u00A0·\/\(\)\-]+", "", (t or "")).lower()
    return t

def _has_key(label: str, keys: list[str]) -> bool:
    """레이블에 키워드가 포함되어 있는지 확인 (모든 공백/특수문자 제거 후 비교)"""
    normalized_label = _norm(label)
    return any(_norm(k) in normalized_label for k in keys)

# 🌟 정규식 구분자 목록 (정규화 및 Escape 처리)
REGEX_SEPARATORS = sorted(list(set([re.escape(_norm(k)) for k in ALL_KEYS if _norm(k)])), key=len, reverse=True)
REGEX_SEP_PATTERN = "|".join(REGEX_SEPARATORS)

async def extract_from_artcinfo(page_scope) -> dict:
    """구조적 추출을 시도하고, 실패하면 전체 텍스트 기반 정규식으로 폴백"""
    out = {
        "capacity": None, "expiry": None, "usage": None, "caution": None,
        "manufacturer": None, "country_of_origin": None, "ingredients": None
    }
    
    # 🌟 디버그 유틸리티
    def _assign_and_debug(field, value, source_label, extraction_method):
        nonlocal out
        cleaned_value = clean(value)
        if out[field] is not None or not cleaned_value:
            return False

        out[field] = cleaned_value
        return True

    # 1. 구조적 추출 (dl/dt/dd 및 table/th/td) - 가장 깨끗한 데이터를 얻기 위함
    artc_scope = page_scope.locator("#artcInfo").first
    artc_loaded = await artc_scope.count() > 0 and clean(await artc_scope.inner_text(timeout=3000) or "")

    if artc_loaded:
        # DL 순회
        dls = artc_scope.locator("dl.detail_info_list")
        for i in range(await dls.count()):
            dl = dls.nth(i)
            try:
                dt_txt = clean(await dl.locator("dt").first.inner_text())
                # inner_html을 가져와서 clean 함수로 처리 (HTML 노이즈 제거)
                dd_html = await dl.locator("dd").first.inner_html() 
            except Exception:
                continue
                
            if not dt_txt or not dd_html: continue
            
            if _has_key(dt_txt, CAPACITY_KEYS):
                _assign_and_debug("capacity", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, EXPIRY_KEYS):
                _assign_and_debug("expiry", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, USAGE_KEYS):
                _assign_and_debug("usage", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, CAUTION_KEYS):
                _assign_and_debug("caution", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, MANUFACTURER_KEYS):
                _assign_and_debug("manufacturer", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, COUNTRY_OF_ORIGIN_KEYS):
                _assign_and_debug("country_of_origin", dd_html, dt_txt, "DL/DD")
            elif _has_key(dt_txt, INGREDIENT_KEYS):
                _assign_and_debug("ingredients", dd_html, dt_txt, "DL/DD")

        # Table 순회
        rows = artc_scope.locator("table tr, .tbl_prd_info tr")
        for i in range(await rows.count()):
            tr = rows.nth(i)
            try:
                th_txt = clean(await tr.locator("th").first.inner_text())
                td_txt = await tr.locator("td").first.inner_text() 
            except Exception:
                continue
            if not th_txt or not td_txt: continue
                
            # 필드 채우기 (table/th/td)
            if _has_key(th_txt, CAPACITY_KEYS):
                _assign_and_debug("capacity", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, EXPIRY_KEYS):
                _assign_and_debug("expiry", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, USAGE_KEYS):
                _assign_and_debug("usage", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, CAUTION_KEYS):
                _assign_and_debug("caution", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, MANUFACTURER_KEYS):
                _assign_and_debug("manufacturer", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, COUNTRY_OF_ORIGIN_KEYS):
                _assign_and_debug("country_of_origin", td_txt, th_txt, "TABLE")
            elif _has_key(th_txt, INGREDIENT_KEYS):
                _assign_and_debug("ingredients", td_txt, th_txt, "TABLE")


    # 2. 🌟 최종 폴백: 페이지 전체 텍스트 스캔 (구조적 추출 실패 시)
    if None in out.values():
        full_page_text = clean(await page_scope.inner_text("body", timeout=5000) or "")
        
        # 성분 (INGREDIENTS) 추출 (가장 긴 텍스트 블록)
        if out["ingredients"] is None:
            # 성분 키워드 이후부터 다음 주요 키워드(용량, 제조국, 사용법 등)가 나타날 때까지 모두 잡는 패턴
            ingredients_pattern = fr'(?:{"|".join([re.escape(k) for k in INGREDIENT_KEYS])})[\s\:\/\(\)·\u00A0\-]*([\s\S]{{50,}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
            
            match = re.search(ingredients_pattern, full_page_text, re.IGNORECASE | re.DOTALL)
            if match and clean(match.group(1)):
                _assign_and_debug("ingredients", match.group(1), "전성분", "REGEX_LONG")

        # 용량/제조국/유통기한 추출 (나머지 짧은 텍스트 블록)
        for key_list, field_name in [
            (CAPACITY_KEYS, "capacity"), 
            (EXPIRY_KEYS, "expiry"), 
            (MANUFACTURER_KEYS, "manufacturer"), 
            (COUNTRY_OF_ORIGIN_KEYS, "country_of_origin")
        ]:
            if out[field_name] is None:
                # 짧은 키워드 매칭을 위해 조금 더 엄격한 패턴 사용
                pattern_str = fr'(?:{"|".join([re.escape(k) for k in key_list])})[\s\:\/\(\)·\u00A0\-]*([\s\S]{{5,100}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
                match = re.search(pattern_str, full_page_text, re.IGNORECASE | re.DOTALL)
                
                if match and clean(match.group(1)):
                    _assign_and_debug(field_name, match.group(1), key_list[0], "REGEX_SHORT")
    
    return out

async def scrape_detail(context, url: str) -> dict:
    """단일 상품 상세 페이지를 스크래핑합니다. 병렬로 실행될 수 있습니다."""
    page = await context.new_page()
    name = None 
    try:
        # 🌟 상세 페이지당 개별적인 텀을 줍니다.
        await nap(DETAIL_PAUSE_SEC + random.uniform(0.1, 0.5)) 

        # URL 접근
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 상단 정보 추출 (이전과 동일)
        name = await get_text_or_none(page, SEL_TOP["name"], 8000)
        price = parse_price(await get_text_or_none(page, SEL_TOP["price"], 8000))
        imgsrc = await get_attr_or_none(page, SEL_TOP["image"], "src", 8000)
        image = urljoin(page.url, imgsrc) if imgsrc else None
        rev = parse_int(await get_text_or_none(page, SEL_TOP["review_cnt"], 5000))

        # ── 상품정보 탭 활성화 및 로드 대기 ──────────────────────────────────
        buyinfo_tab_loc = page.locator("a:has-text('구매정보')").first
        
        if await buyinfo_tab_loc.count() > 0:
            await buyinfo_tab_loc.scroll_into_view_if_needed(timeout=3000)
            await page.wait_for_timeout(300)

            try:
                await buyinfo_tab_loc.click(timeout=5000, force=True) 
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                try:
                    await page.locator(TAB_BTN_INFO).first.click(timeout=3000, force=True)
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    print(f"[WARN: TAB_FAIL] '{name or url}' - 탭 클릭 및 로드 실패. 현재 페이지에서 추출 시도.")
        
        # 4. 추출
        info = await extract_from_artcinfo(page) 

        # 🌟 핵심 필드 누락 경고 (디버그에 도움)
        if not (info.get("capacity") or info.get("expiry") or info.get("ingredients") or info.get("country_of_origin")):
            print(f"[WARN: KEYWORD_MATCH_FAIL] '{name or url}' - 핵심 상세 정보 추출 실패.")


        # 🌟 반환 딕셔너리의 키를 CSV fieldnames와 일치하도록 조정
        return {
            "product_name": name,             # 'product_name'으로 변경
            "price_krw": price,               # 'price_krw'로 변경
            "image_url": image,               # 'image_url'로 변경
            "review_count": rev,              # 'review_count'로 변경
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

# ── 메인 ─────────────────────────────────────────────────────
async def main():
    # 저장 경로 설정
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        out_csv = (SAVE_DIR / SAVE_NAME).resolve()
    except Exception as e:
        # 지정 경로 실패 시 현재 폴더 저장 (폴백)
        print(f"[WARN] 지정 경로 ({SAVE_DIR}) 실패. 현재 폴더 저장:", e)
        out_csv = (Path.cwd() / SAVE_NAME).resolve()
    print("Save to:", out_csv)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            # headless=False로 두면 탭이 MAX_CONCURRENT_PAGES 만큼 동시에 열립니다.
            headless=False,
            slow_mo=500 
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

        # 🌟 1. 리스트 수집 단계 (모든 정보를 all_product_data에 모으기)
        all_product_data = [] # 리스트 정보만 먼저 저장
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

            # 각 줄 처리
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

                    # 리스트 정보 추출 (기존 로직 유지)
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
                            price_txt = clean(await loc.first.inner_text()); break
                    price_krw = parse_price(price_txt)

                    image_url = None
                    if await li.locator("img").count():
                        for attr in ("data-src","data-original","data-lazy","src"):
                            src = await li.locator("img").first.get_attribute(attr)
                            if src:
                                image_url = urljoin(page.url, src); break
                        
                    goods_no = goods_no_from(href)
                    data_index = await li.get_attribute("data-index")
                    data_number = await li.get_attribute("data-number")
                    col_idx = (int(data_index) % 4 + 1) if data_index and data_index.isdigit() else (i % 4 + 1)

                    # 🌟 리스트 정보만 저장하고 상세 스크래핑은 건너뜁니다.
                    all_product_data.append({
                        "row": page_num, "col": col_idx, "global_index": global_index, 
                        "li_data_index": data_index, "li_data_number": data_number,
                        "goods_no": goods_no, "brand_name": brand,
                        "product_name": product_name, "price_krw": price_krw,
                        "product_url": product_url, "image_url": image_url,
                        # 상세 필드는 None으로 초기화
                        "review_count": None, "capacity": None, "expiry": None, 
                        "usage": None, "caution": None, "manufacturer": None, 
                        "country_of_origin": None, "ingredients": None, 
                    })
                    global_index += 1
                    
                    # 🌟 한글 깨짐 방지 출력
                    display_name_list = product_name or goods_no or 'Unknown Product (List)'
                    print(f"[LIST {page_num}-{col_idx}] {display_name_list}")
                    await nap()

                await nap(ROW_PAUSE_SEC)
        
        await page.close()
        print(f"\n[INFO] List scraping finished. Total {len(all_product_data)} items collected.")
        
        # 🌟 2. 상세 스크래핑 (병렬 처리)
        items_to_scrape = [item for item in all_product_data if item['product_url']]
        total_items = len(items_to_scrape)
        
        print(f"\nStarting detail scraping for {total_items} items with concurrency: {MAX_CONCURRENT_PAGES}...")
        
        tasks = []
        final_results = []
        
        for i, item in enumerate(items_to_scrape):
            tasks.append(scrape_detail(context, item['product_url']))
            
            if len(tasks) >= MAX_CONCURRENT_PAGES:
                print(f"[PARALLEL] Executing batch {len(final_results)//MAX_CONCURRENT_PAGES + 1} of {len(tasks)} tasks...")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                start_index = len(final_results) 
                
                for j, detail_result in enumerate(results):
                    original_item = items_to_scrape[start_index + j]
                    
                    # 🌟 안전한 이름 추출 (출력용)
                    display_name = original_item.get('product_name') or original_item.get('goods_no') or 'Unknown Product'
                    
                    if isinstance(detail_result, dict):
                        # 🌟🌟🌟 여기서 키 이름을 변경하여 병합합니다. 🌟🌟🌟
                        # scrape_detail에서 반환되는 키 이름이 이미 CSV fieldnames와 일치하므로, 
                        # 리스트 정보의 필드(product_name, price_krw, image_url, review_count)를 덮어쓰고, 
                        # 상세 정보 필드(capacity, expiry, ...)를 추가합니다.
                        
                        # (1) 리스트 정보에서 얻은 review_count가 None일 경우 상세 정보의 review_count로 업데이트
                        if original_item.get('review_count') is None:
                             original_item['review_count'] = detail_result.get('review_count')
                        
                        # (2) 나머지 상세 정보 필드를 업데이트 (이름, 가격, 이미지는 이미 리스트 단계에서 수집했으므로 상세 정보만 덮어씀)
                        original_item.update({
                            k: v for k, v in detail_result.items() 
                            if k not in ['product_name', 'price_krw', 'image_url', 'review_count']
                        })
                        
                        # 상세 스크래핑에서 이름, 가격, 이미지 URL을 가져왔지만, 
                        # 리스트 단계의 정보를 우선하고 상세 정보는 capacity 등 
                        # 누락된 필드만 채우도록 로직을 간소화했습니다. (중복키 방지)
                        original_item['capacity'] = detail_result.get('capacity')
                        original_item['expiry'] = detail_result.get('expiry')
                        original_item['usage'] = detail_result.get('usage')
                        original_item['caution'] = detail_result.get('caution')
                        original_item['manufacturer'] = detail_result.get('manufacturer')
                        original_item['country_of_origin'] = detail_result.get('country_of_origin')
                        original_item['ingredients'] = detail_result.get('ingredients')
                        
                        print(f"[DETAIL OK] {original_item['global_index']}: {display_name[:30]}...")
                    else:
                        print(f"[DETAIL FAIL] {original_item['global_index']}: {display_name[:30]}... ({detail_result.__class__.__name__})")
                    
                    final_results.append(original_item)
                    
                tasks = [] # 태스크 초기화

        # 남은 태스크 처리
        if tasks:
            print(f"[PARALLEL] Executing final batch of {len(tasks)} tasks...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            start_index = len(final_results)
            for j, detail_result in enumerate(results):
                original_item = items_to_scrape[start_index + j]
                
                # 🌟 안전한 이름 추출
                display_name = original_item.get('product_name') or original_item.get('goods_no') or 'Unknown Product'
                
                if isinstance(detail_result, dict):
                    # 🌟🌟🌟 여기서 키 이름을 변경하여 병합합니다. 🌟🌟🌟 (위와 동일)
                    if original_item.get('review_count') is None:
                             original_item['review_count'] = detail_result.get('review_count')
                             
                    original_item['capacity'] = detail_result.get('capacity')
                    original_item['expiry'] = detail_result.get('expiry')
                    original_item['usage'] = detail_result.get('usage')
                    original_item['caution'] = detail_result.get('caution')
                    original_item['manufacturer'] = detail_result.get('manufacturer')
                    original_item['country_of_origin'] = detail_result.get('country_of_origin')
                    original_item['ingredients'] = detail_result.get('ingredients')
                    
                    print(f"[DETAIL OK] {original_item['global_index']}: {display_name[:30]}...")
                else:
                    print(f"[DETAIL FAIL] {original_item['global_index']}: {display_name[:30]}... ({detail_result.__class__.__name__})")
                    
                final_results.append(original_item)


        # 3. 저장
        # final_results는 이미 리스트 정보와 상세 정보가 합쳐진 딕셔너리 리스트입니다.
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "row","col","global_index","li_data_index","li_data_number",
                "goods_no","brand_name","product_name","price_krw",
                "product_url","image_url","review_count","capacity","expiry",
                "usage","caution","manufacturer", "country_of_origin", "ingredients" 
            ])
            writer.writeheader()
            writer.writerows(final_results)

        print(f"\nSaved {len(final_results)} items -> {out_csv}")
        await browser.close()

# ▶ .py 스크립트로 실행할 때:
if __name__ == "__main__":
    asyncio.run(main())