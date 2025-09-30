# pip install playwright
# playwright install

import asyncio, re, csv
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright

# ── 설정 ─────────────────────────────────────────────────────
# pageIdx=1이 포함된 스킨/토너 카테고리 URL
START_URL = (
    "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
    "?dispCatNo=100000100010013&fltDispCatNo=&prdSort=01&pageIdx=1&rowsPerPage=24"
    "&searchTypeSort=btn_thumb&plusButtonFlag=N&isLoginCnt=0&aShowCnt=0&bShowCnt=0&cShowCnt=0"
    "&trackingCd=Cat100000100010013_Small&amplitudePageGubun=&t_page=%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC%EA%B4%80&t_click=%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC%ED%83%AD_%EC%A4%91%EC%B9%B4%ED%85%8C%EA%B3%A0%EB%A6%AC"
    "&midCategory=%EC%8A%A4%ED%82%A8%2F%ED%86%A0%EB%84%88&smallCategory=%EC%A0%84%EC%B2%B4&checkBrnds=&lastChkBrnd="
    "&t_1st_category_type=%EB%8C%80_%EC%8A%A4%ED%82%A8%EC%BC%80%EC%96%B4&t_2nd_category_type=%EC%A4%91_%EC%8A%A4%ED%82%A8%2F%ED%86%A0%EB%84%88"
)
MAX_PAGES_TO_SCRAP = 10 # 수집할 카테고리 페이지 수
MAX_CONCURRENT_PAGES = 10 # 상세 페이지 동시 로드 개수 (속도 핵심)

# 셀렉터
ROW_SEL_ALL   = "#Contents > ul.cate_prd_list.gtm_cate_list"
ITEMS_IN_ROW  = ":scope > li"
ANCHOR_SEL    = "a.prd_info, div > a, a"
SEL_TOP = {
    "name":        "#Contents > div.prd_detail_box.renew > div.right_area > div > p.prd_name",
    "price":       "#Contents > div.prd_detail_box.renew > div.right_area > div > div.price > span.price-2 > strong",
    "image":       "#mainImg",
    "review_cnt": "#repReview > em",
}
TAB_BTN_INFO = "ul#tabList li#buyinfo a, div.prd_tab li a:has-text('구매정보'), a[role='tab']:has-text('구매정보')"

# 키워드 목록
CAPACITY_KEYS = ["용량", "용량/중량", "내용량", "중량", "내용물의 용량 또는 중량"]
EXPIRY_KEYS   = ["사용기한", "사용기간", "개봉후사용기간", "사용기한(또는 개봉 후 사용기간)"]
MANUFACTURER_KEYS = ["제조회사", "제조업자", "책임판매업자", "화장품제조업자", "화장품책임판매업자", "제조회사 및 책임판매업자"] 
COUNTRY_OF_ORIGIN_KEYS = ["제조국", "제조국가", "원산지", "원산국", "제조국 및 제조사"] 
INGREDIENT_KEYS   = ["성분", "전성분", "원료명", "주요성분", "화장품법에 따라 기재해야 하는 모든 성분", "화장품법에따라기재표시해야하는모든성분"] 
ALL_KEYS = CAPACITY_KEYS + EXPIRY_KEYS + MANUFACTURER_KEYS + COUNTRY_OF_ORIGIN_KEYS + INGREDIENT_KEYS

# 저장 경로
SAVE_DIR = Path(r"C:\githome\GROW")
SAVE_NAME = "oliveyoung_final_V9_fast.csv"

# ── 유틸리티 ─────────────────────────────────────────────────────

def clean(t): 
    if t is None: return None
    t = re.sub(r"<\s*br\s*/?>|\&nbsp\;|\u00A0", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip() if t else None

def parse_price(t): t = re.sub(r"[^\d]", "", t or ""); return int(t) if t else None
def parse_int(t):   t = re.sub(r"[^\d]", "", t or ""); return int(t) if t else None
def goods_no_from(href):
    if not href: return None
    qs = parse_qs(urlparse(href).query)
    if qs.get("goodsNo"): return qs["goodsNo"][0]
    m = re.search(r"(?:goodsNo|goodsCd)=(\d+)", href, re.I)
    return m.group(1) if m else None

async def get_text_or_none(ctx, selector, timeout=5000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout) 
        return clean(await loc.inner_text())
    except Exception:
        return None

async def get_attr_or_none(ctx, selector, attr, timeout=3000):
    try:
        loc = ctx.locator(selector).first
        await loc.wait_for(state="attached", timeout=timeout)
        return await loc.get_attribute(attr)
    except Exception:
        return None

def _norm(t: str) -> str:
    t = re.sub(r"[\s\:\u00A0·\/\(\)\-]+", "", (t or "")).lower()
    return t

def _has_key(label: str, keys: list[str]) -> bool:
    normalized_label = _norm(label)
    return any(_norm(k) in normalized_label for k in keys)

REGEX_SEPARATORS = sorted(list(set([re.escape(_norm(k)) for k in ALL_KEYS if _norm(k)])), key=len, reverse=True)
REGEX_SEP_PATTERN = "|".join(REGEX_SEPARATORS)


async def extract_from_artcinfo(page_scope) -> dict:
    # 상세 페이지 정보 추출 로직 (DL/DD, TABLE, REGEX 폴백)
    out = {
        "capacity": None, "expiry": None, "manufacturer": None, 
        "country_of_origin": None, "ingredients": None
    }
    
    def _assign_field(field, value):
        nonlocal out
        cleaned_value = clean(value)
        if out[field] is not None or not cleaned_value: return False
        out[field] = cleaned_value
        return True

    # 1. 구조적 추출
    artc_scope = page_scope.locator("#artcInfo").first
    artc_loaded = await artc_scope.count() > 0 and clean(await artc_scope.inner_text(timeout=2000) or "")

    if artc_loaded:
        dls = artc_scope.locator("dl.detail_info_list")
        for i in range(await dls.count()):
            dl = dls.nth(i)
            try:
                dt_txt = clean(await dl.locator("dt").first.inner_text())
                dd_html = await dl.locator("dd").first.inner_html() 
            except Exception: continue
            if not dt_txt or not dd_html: continue
            
            if _has_key(dt_txt, CAPACITY_KEYS): _assign_field("capacity", dd_html)
            elif _has_key(dt_txt, EXPIRY_KEYS): _assign_field("expiry", dd_html)
            elif _has_key(dt_txt, MANUFACTURER_KEYS): _assign_field("manufacturer", dd_html)
            elif _has_key(dt_txt, COUNTRY_OF_ORIGIN_KEYS): _assign_field("country_of_origin", dd_html)
            elif _has_key(dt_txt, INGREDIENT_KEYS): _assign_field("ingredients", dd_html)

        rows = artc_scope.locator("table tr, .tbl_prd_info tr")
        for i in range(await rows.count()):
            tr = rows.nth(i)
            try:
                th_txt = clean(await tr.locator("th").first.inner_text())
                td_txt = await tr.locator("td").first.inner_text() 
            except Exception: continue
            if not th_txt or not td_txt: continue
                
            if _has_key(th_txt, CAPACITY_KEYS): _assign_field("capacity", td_txt)
            elif _has_key(th_txt, EXPIRY_KEYS): _assign_field("expiry", td_txt)
            elif _has_key(th_txt, MANUFACTURER_KEYS): _assign_field("manufacturer", td_txt)
            elif _has_key(th_txt, COUNTRY_OF_ORIGIN_KEYS): _assign_field("country_of_origin", td_txt)
            elif _has_key(th_txt, INGREDIENT_KEYS): _assign_field("ingredients", td_txt)

    # 2. 최종 폴백: 페이지 전체 텍스트 스캔
    if None in out.values():
        full_page_text = clean(await page_scope.inner_text("body", timeout=5000) or "")
        
        if out["ingredients"] is None:
            ingredients_pattern = fr'(?:{"|".join([re.escape(k) for k in INGREDIENT_KEYS])})[\s\:\/\(\)·\u00A0\-]*([\s\S]{{50,}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
            match = re.search(ingredients_pattern, full_page_text, re.IGNORECASE | re.DOTALL)
            if match and clean(match.group(1)): _assign_field("ingredients", match.group(1))

        for key_list, field_name in [
            (CAPACITY_KEYS, "capacity"), 
            (EXPIRY_KEYS, "expiry"), 
            (MANUFACTURER_KEYS, "manufacturer"), 
            (COUNTRY_OF_ORIGIN_KEYS, "country_of_origin")
        ]:
            if out[field_name] is None:
                pattern_str = fr'(?:{"|".join([re.escape(k) for k in key_list])})[\s\:\/\(\)·\u00A0\-]*([\s\S]{{5,100}}?)(?=\s*(?:{REGEX_SEP_PATTERN})|$)'
                match = re.search(pattern_str, full_page_text, re.IGNORECASE | re.DOTALL)
                
                if match and clean(match.group(1)): _assign_field(field_name, match.group(1))
    
    return out


async def scrape_detail(context, product_data: dict) -> dict:
    """단일 상품의 상세 정보를 스크래핑 (병렬 처리 가능)"""
    page = await context.new_page()
    url = product_data["product_url"]
    name = product_data["product_name"]
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000) 

        # 상단 정보 추출 (재확인)
        product_data["product_name"] = (await get_text_or_none(page, SEL_TOP["name"], 5000)) or name
        product_data["price_krw"] = (parse_price(await get_text_or_none(page, SEL_TOP["price"], 5000))) or product_data["price_krw"]
        product_data["image_url"] = urljoin(page.url, await get_attr_or_none(page, SEL_TOP["image"], "src", 3000))
        product_data["review_count"] = parse_int(await get_text_or_none(page, SEL_TOP["review_cnt"], 3000))

        # 구매정보 탭 활성화 시도
        buyinfo_tab_loc = page.locator("a:has-text('구매정보')").first
        
        if await buyinfo_tab_loc.count() > 0:
            await buyinfo_tab_loc.scroll_into_view_if_needed(timeout=1000)
            await page.wait_for_timeout(100)
            try:
                await buyinfo_tab_loc.click(timeout=3000, force=True) 
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                try:
                    await page.locator(TAB_BTN_INFO).first.click(timeout=2000, force=True)
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                     pass 

        # 추출 실행
        info = await extract_from_artcinfo(page) 

        # 결과 병합
        product_data.update(info)

        print(f"[SUCCESS] 상세 정보 추출 완료 ({product_data['global_index']}): {name or url}")

    except Exception as e:
        print(f"[ERROR] 상세 스크래핑 실패 ({product_data['global_index']}): {name or url}: {e}")

    finally:
        await page.close()
        return product_data

# ── 메인 ─────────────────────────────────────────────────────
async def main():
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        out_csv = (SAVE_DIR / SAVE_NAME).resolve()
    except Exception:
        out_csv = (Path.cwd() / SAVE_NAME).resolve()
    print("Save to:", out_csv)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            slow_mo=0
        )
        context = await browser.new_context(
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121 Safari/537.36"),
        )
        page = await context.new_page()

        
        all_product_data = []
        global_index = 0
        url_base = START_URL 
        
        # 🌟 1. 다중 페이지 로딩 및 리스트 데이터 수집 (URL 파라미터 변경 방식)
        for page_num in range(1, MAX_PAGES_TO_SCRAP + 1):
            # pageIdx를 현재 루프 번호(page_num)로 변경하여 새 URL 생성
            new_url = re.sub(r"pageIdx=\d+", f"pageIdx={page_num}", url_base)
            
            print(f"\n--- Loading Category Page {page_num} (URL: {new_url[:100]}...) ---")
            
            try:
                await page.goto(new_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_selector(ROW_SEL_ALL, timeout=10000)
                await page.wait_for_timeout(500) 
                
            except Exception as e:
                print(f"[ERROR] Failed to load page {page_num} via URL: {e}")
                break

            # 상품 그룹 수집 및 페이지 존재 여부 확인
            rows_all = page.locator(ROW_SEL_ALL)
            total_rows = await rows_all.count()
            
            if total_rows == 0:
                 print(f"[INFO] Page {page_num} loaded but contains no product groups. Stopping iteration.")
                 break
                 
            print(f"Products group loaded in page {page_num}: {total_rows} groups.")

            for r in range(total_rows):
                row = rows_all.nth(r)
                cards = row.locator(ITEMS_IN_ROW)
                cnt = await cards.count()

                for i in range(cnt):
                    li = cards.nth(i)
                    a = li.locator(ANCHOR_SEL).first

                    href = await a.get_attribute("href")
                    product_url = urljoin(page.url, href) if href else None
                    goods_no = goods_no_from(href)

                    product_name = await get_text_or_none(li, ".prd_name, .tx_name", 1000)
                    brand = await get_text_or_none(li, ".tx_brand, .brand, .brandNm", 1000)
                    price_krw = parse_price(await get_text_or_none(li, ".price .num, .tx_cur, .cur_price, .price", 1000))
                    
                    if not product_url: continue

                    all_product_data.append({
                        "row": page_num, "col": (i % 4 + 1), "global_index": global_index,
                        "goods_no": goods_no, "brand_name": brand,
                        "product_name": product_name, "price_krw": price_krw,
                        "product_url": product_url, 
                    })
                    global_index += 1
            
        await page.close() 
        print(f"\n[INFO] List scraping finished. Total {len(all_product_data)} items collected.")
        
        # 🌟 2. 상세 스크래핑 (병렬 처리)
        print(f"Starting detail scraping with concurrency: {MAX_CONCURRENT_PAGES}...")
        
        tasks = []
        final_results = []
        
        for item in all_product_data:
            tasks.append(scrape_detail(context, item))
            
            if len(tasks) >= MAX_CONCURRENT_PAGES:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                final_results.extend(results)
                tasks = []
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            final_results.extend(results)

        # 3. 저장
        clean_results = [r for r in final_results if isinstance(r, dict)]
        
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "row","col","global_index","goods_no","brand_name","product_name","price_krw",
                "product_url","image_url","review_count",
                "capacity","expiry","manufacturer", "country_of_origin", "ingredients" 
            ])
            writer.writeheader()
            writer.writerows(clean_results)

        print(f"Saved {len(clean_results)} items -> {out_csv}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())