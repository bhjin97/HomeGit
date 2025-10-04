# -*- coding: utf-8 -*-
# pip install playwright
# playwright install

import asyncio, csv, random
from playwright.async_api import async_playwright

# ── 유틸 함수 ──────────────────────────────────────────────
async def human_sleep(a=3, b=6):
    """사람처럼 랜덤 대기"""
    await asyncio.sleep(random.uniform(a, b))

async def human_scroll(page):
    """스크롤을 사람처럼 내리기"""
    try:
        await page.mouse.wheel(0, random.randint(400, 1200))
        await asyncio.sleep(random.uniform(1.0, 2.0))
    except:
        pass

async def safe_goto(page, url, selector, retries=3):
    """페이지 이동 + 로딩 확인 (재시도 포함)"""
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

# ── 상품 상세 리뷰 수집 ─────────────────────────────────────
async def scrape_product(context, product_link, product_counter, sem, failed_items, list_name=None):
    async with sem:
        page = await context.new_page()
        reviews_data = []
        try:
            ok = await safe_goto(page, product_link, "p.prd_name, h3.prd_name, div.right_area h3", retries=3)
            if not ok:
                failed_items.append((product_counter, list_name or "알 수 없음"))
                return []

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
                reviews_data.append([brand, name, None, None, None])
                return reviews_data

            # 도움순 정렬 클릭
            try:
                help_sort = page.locator("#gdasSort > li:nth-child(2) > a").first
                await help_sort.click(timeout=5000)
                await human_sleep()
            except:
                pass

            # 리뷰 최대 30개 수집
            reviews_collected = 0
            while reviews_collected < 30:
                reviews = page.locator("#gdasList > li")
                count = await reviews.count()

                # 리뷰가 아예 없는 경우
                if count == 0 and reviews_collected == 0:
                    reviews_data.append([brand, name, None, None, None])
                    print(f"  - [{product_counter}] {brand} {name}: 리뷰 없음")
                    break

                # 현재 페이지 리뷰 반복
                for i in range(count):
                    if reviews_collected >= 30:
                        break
                    try:
                        r = reviews.nth(i)
                        text = (await r.locator("div.review_cont > div.txt_inner").inner_text()).strip()
                        date = await r.locator("div.review_cont > div.score_area > span.date").inner_text()
                        score = await r.locator("div.review_cont > div.score_area > span.review_point > span").inner_text()
                        reviews_data.append([brand, name, text, date, score])
                        reviews_collected += 1
                    except:
                        continue

                if reviews_collected >= 30:
                    break

                # 페이지네이션 (다음 페이지 클릭)
                try:
                    current_page = await page.locator("#gdasContentsArea .pageing > strong").inner_text()
                    next_btn = page.locator(
                        f"#gdasContentsArea .pageing > a:has-text('{int(current_page)+1}')"
                    )
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await page.wait_for_selector("#gdasList > li", timeout=10000)
                        await human_sleep()
                    else:
                        break
                except:
                    break

            print(f"  - [{product_counter}] {brand} {name}: 리뷰 {reviews_collected}개 완료")

            return reviews_data

        except Exception:
            failed_items.append((product_counter, list_name or "알 수 없음"))
            return []
        finally:
            await page.close()

# ── 카테고리 크롤러 ─────────────────────────────────────────
async def scrape_category(base_url: str, save_file: str, max_pages: int, concurrency: int = 5):
    all_reviews = []
    product_links = []
    product_counter = 0
    sem = asyncio.Semaphore(concurrency)
    failed_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=700
        )
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

            # 페이지 단위 진행률
            progress = (product_counter / (max_pages * 24)) * 100
            print(f"[PAGE {page_num}] 현재까지 {product_counter}개 수집 ({progress:.2f}%)")

        # 병렬 처리 (결과는 product_links 순서대로 반환됨)
        tasks = [scrape_product(context, link, idx, sem, failed_items, list_name=name) 
                 for idx, link, name in product_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                all_reviews.extend(res)

        await browser.close()

    # CSV 저장 (리뷰 단위)
    with open(save_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["brand", "name", "review_text", "date", "score"])
        writer.writerows(all_reviews)

    print(f"\n총 {len(all_reviews)} 개 리뷰 저장 완료 → {save_file}")

    # 실패 상품 출력
    if failed_items:
        print("\n[수집 실패한 상품]")
        for num, name in failed_items:
            print(f"- #{num} {name}")

# ▶ 실행
if __name__ == "__main__":
    url = (
        "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
        "?dispCatNo=100000100080013"
        "&isLoginCnt=2&aShowCnt=0&bShowCnt=0&cShowCnt=0&gateCd=Drawer"
        "&pageIdx={page}&rowsPerPage=24&prdSort=01&searchTypeSort=btn_thumb&plusButtonFlag=N"
    )
    save_name = "Derma_skincare_reviews.csv"
    max_page = 20

    asyncio.run(scrape_category(url, save_name, max_page, concurrency=5))
