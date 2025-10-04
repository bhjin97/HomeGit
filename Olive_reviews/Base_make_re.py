# -*- coding: utf-8 -*-
# pip install playwright
# playwright install

import asyncio, csv, random, re
from pathlib import Path
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
async def human_sleep(a=3, b=6):
    await asyncio.sleep(random.uniform(a, b))

async def human_scroll(page):
    try:
        await page.mouse.wheel(0, random.randint(400, 1200))
        await asyncio.sleep(random.uniform(1.0, 2.0))
    except:
        pass

async def safe_goto(page, url, selector, retries=3):
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_selector(selector, timeout=15000)
            return True
        except:
            if attempt < retries - 1:
                print(f"[WARN] {url} 로딩 실패 → 재시도 {attempt+1}/{retries}")
                await asyncio.sleep(8)
            else:
                print(f"[ERROR] {url} 로딩 완전 실패")
                return False

# ─────────────────────────────────────────────────────────────
# 상품 상세 리뷰 + 속성 수집
# ─────────────────────────────────────────────────────────────
async def scrape_product(context, product_link, product_counter, sem, failed_items, list_name=None):
    """
    반환값:
      (reviews_data, attrs_data)
      - reviews_data: [review_uid, brand, name, text, date, score]
      - attrs_data:   [review_uid, attr_name, attr_value]
    """
    async with sem:
        page = await context.new_page()
        reviews_data, attrs_data = [], []
        try:
            ok = await safe_goto(page, product_link, "p.prd_name, h3.prd_name, div.right_area h3", retries=3)
            if not ok:
                failed_items.append((product_counter, list_name or "알 수 없음"))
                return [], []

            await human_sleep()
            await human_scroll(page)

            # 브랜드명, 상품명
            brand = await page.locator("p.prd_brand").inner_text()
            name = await page.locator("p.prd_name, h3.prd_name, div.right_area h3").inner_text()
            print(f"[진행중] #{product_counter} → {brand} - {name}")

            # 리뷰 탭 클릭
            try:
                review_tab = page.locator("#reviewInfo > a").first
                await review_tab.click(timeout=5000)
                await human_sleep()
            except:
                # 리뷰 없음 처리
                reviews_data.append([f"{product_counter}-0", brand, name, None, None, None])
                return reviews_data, attrs_data

            # 도움순 정렬 클릭(가능 시)
            try:
                help_sort = page.locator("#gdasSort > li:nth-child(2) > a").first
                await help_sort.click(timeout=5000)
                await human_sleep()
            except:
                pass

            # 리뷰 최대 30개
            local_seq = 0
            while local_seq < 30:
                reviews = page.locator("#gdasList > li")
                count = await reviews.count()

                if count == 0 and local_seq == 0:
                    reviews_data.append([f"{product_counter}-0", brand, name, None, None, None])
                    print(f"  - [{product_counter}] {brand} {name}: 리뷰 없음")
                    break

                for i in range(count):
                    if local_seq >= 30:
                        break
                    r = reviews.nth(i)
                    try:
                        text = (await r.locator("div.review_cont > div.txt_inner").inner_text()).strip()
                    except:
                        text = None
                    try:
                        date = await r.locator("div.review_cont > div.score_area > span.date").inner_text()
                    except:
                        date = None
                    try:
                        score = await r.locator("div.review_cont > div.score_area > span.review_point > span").inner_text()
                    except:
                        score = None

                    local_seq += 1
                    review_uid = f"{product_counter}-{local_seq}"
                    try:
                        opt = r.locator("div.review_cont > p.item_option")
                        if await opt.count() > 0:
                            raw = (await opt.first.inner_text()).strip()
                            # "옵션 : ..." 같은 접두어 제거
                            cleaned = re.sub(r'^\s*옵션\s*[:：]\s*', '', raw).strip()
                            # 비어있거나 대시 같은 플레이스홀더면 None 처리
                            product_option = cleaned if cleaned and cleaned not in ('-', '--') else None
                        else:
                            product_option = None
                    except:
                        product_option = None

                    reviews_data.append([review_uid, brand, name, text, date, score, product_option])

                    # ── 속성 수집 (여기가 추가된 부분) ─────────────────────
                    # 기준: #gdasList > li > div.review_cont > div.poll_sample
                    try:
                        poll = r.locator("div.review_cont > div.poll_sample")
                        if await poll.count() > 0:
                            # dl 묶음 반복 (예: dl.poll_type1)
                            dls = poll.locator("dl")
                            dl_cnt = await dls.count()
                            for di in range(dl_cnt):
                                dl = dls.nth(di)
                                # 속성명 (dt > span)
                                try:
                                    attr_name = (await dl.locator("dt > span").inner_text()).strip()
                                except:
                                    attr_name = None
                                # 속성값 (dd 내부의 .txt들)
                                try:
                                    # 보통 dd 안에 <span class="txt">여러 값</span> 구조
                                    txt_nodes = dl.locator("dd .txt")
                                    if await txt_nodes.count() == 0:
                                        # 일부 페이지는 dd 바로 텍스트일 수 있음
                                        attr_value = (await dl.locator("dd").inner_text()).strip()
                                    else:
                                        vals = []
                                        for ti in range(await txt_nodes.count()):
                                            v = (await txt_nodes.nth(ti).inner_text()).strip()
                                            if v:
                                                vals.append(v)
                                        attr_value = " / ".join(vals) if vals else None
                                except:
                                    attr_value = None

                                # 정제(선택): "에 좋아요" 같은 접미어 제거
                                if attr_value:
                                    attr_value = (
                                        attr_value.replace("에 좋아요", "")
                                                  .replace("에 안 맞아요", "")
                                                  .strip()
                                    )

                                if attr_name and attr_value:
                                    attrs_data.append([review_uid, attr_name, attr_value])
                    except:
                        # 속성 블록이 없거나 파싱 실패 → 무시
                        pass
                    # ────────────────────────────────────────────────────

                if local_seq >= 30:
                    break

                # 페이지네이션 (다음 페이지)
                try:
                    current_page = await page.locator("#gdasContentsArea .pageing > strong").inner_text()
                    next_btn = page.locator(f"#gdasContentsArea .pageing > a:has-text('{int(current_page)+1}')")
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await page.wait_for_selector("#gdasList > li", timeout=10000)
                        await human_sleep()
                    else:
                        break
                except:
                    break

            print(f"  - [{product_counter}] {brand} {name}: 리뷰 {local_seq}개 완료")
            return reviews_data, attrs_data

        except Exception:
            failed_items.append((product_counter, list_name or "알 수 없음"))
            return [], []
        finally:
            await page.close()

# ─────────────────────────────────────────────────────────────
# 카테고리 크롤러
# ─────────────────────────────────────────────────────────────
async def scrape_category(base_url: str, save_prefix: str, max_pages: int, concurrency: int = 5):
    all_reviews, all_attrs = [], []
    product_links = []
    product_counter = 0
    sem = asyncio.Semaphore(concurrency)
    failed_items = []

    Path(".").mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=700)
        context = await browser.new_context(
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121 Safari/537.36"),
            extra_http_headers={"Referer": base_url}
        )
        page = await context.new_page()

        # 카테고리 페이지 순회
        for page_num in range(1, max_pages + 1):
            url = base_url.format(page=page_num)
            print(f"\n===== {page_num} 페이지 크롤링 중 =====")

            ok = await safe_goto(page, url, "li > div > div > a", retries=3)
            if not ok:
                continue

            await human_sleep()
            await human_scroll(page)

            products = page.locator("li > div > div > a")
            for i in range(await products.count()):
                href = await products.nth(i).get_attribute("href")
                name = await products.nth(i).inner_text()
                if href:
                    product_counter += 1
                    product_links.append((product_counter, href, name))

            progress = (product_counter / (max_pages * 24)) * 100
            print(f"[PAGE {page_num}] 현재까지 {product_counter}개 수집 ({progress:.2f}%)")

        # 병렬 상세 수집
        tasks = [scrape_product(context, link, idx, sem, failed_items, list_name=name) 
                 for idx, link, name in product_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                rvs, ats = res
                all_reviews.extend(rvs)
                all_attrs.extend(ats)

        await browser.close()

    # ── CSV 저장
    reviews_csv = f"{save_prefix}_reviews.csv"
    attrs_csv   = f"{save_prefix}_review_attributes.csv"

    with open(reviews_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["review_uid", "brand", "name", "review_text", "date", "score", "product_option"])
        writer.writerows(all_reviews)

    with open(attrs_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["review_uid", "attr_name", "attr_value"])
        writer.writerows(all_attrs)

    print(f"\n[완료] 리뷰 {len(all_reviews)}건 → {reviews_csv}")
    print(f"[완료] 속성 {len(all_attrs)}건 → {attrs_csv}")

    if failed_items:
        print("\n[수집 실패한 상품]")
        for num, name in failed_items:
            print(f"- #{num} {name}")

# ▶ 실행
if __name__ == "__main__":
    # 카테고리 URL (pageIdx만 {page}로 포맷)
    url = (
        "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
        "?dispCatNo=100000100020001"      # 베이스 메이크업 카테고리
        "&isLoginCnt=2"                   # 로그인 카운트(고정값)
        "&aShowCnt=0&bShowCnt=0&cShowCnt=0"
        "&gateCd=Drawer"                  # 진입경로 구분
        "&pageIdx={page}"                 # ✅ 페이지 번호 포맷
        "&rowsPerPage=24"                 # 한 페이지당 24개 상품
        "&prdSort=01"                     # 정렬 기준 (01 = 인기순)
        "&searchTypeSort=btn_thumb"
        "&plusButtonFlag=N"
    )
    save_prefix = "Base_make_reviews"   # 파일명 접두사
    max_page = 36

    asyncio.run(scrape_category(url, save_prefix, max_page, concurrency=5))
