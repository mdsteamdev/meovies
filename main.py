import json
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách tên phim từ Google Sheets
    try:
        get_url = f"{WEB_APP_URL}?action=get_movie_titles"
        res = requests.get(get_url)
        movies_list = res.json().get("movies", [])
        print(f"📋 Danh sách phim cần cập nhật Doanh Thu: {[m.get('title') for m in movies_list]}")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách phim từ Sheets: {e}")
        return

    if not movies_list:
        print("ℹ️ Không có tên phim nào cần cào.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )

        for item in movies_list:
            movie_title = item.get("title", "").strip()
            if not movie_title:
                continue

            print(f"\n🔍 Đang cào doanh thu BOVN cho phim: {movie_title}")
            page = context.new_page()

            search_query = urllib.parse.quote(movie_title)
            search_url = f"https://boxofficevietnam.com/?s={search_query}"

            try:
                # Mở trang search để vượt Cloudflare & tạo Session Cookie hợp lệ
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Tìm link chi tiết phim để lấy BOVN Slug / ID
                first_link = page.query_selector("article a, .post-title a, h2.entry-title a")
                if first_link:
                    detail_url = first_link.get_attribute("href")
                    print(f"  🌐 Mở trang phim: {detail_url}")
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    # Bắt bovi_id từ nguồn DOM hoặc gọi API nội bộ bằng evaluate
                    api_data = page.evaluate("""
                        async () => {
                            try {
                                // Tìm ID từ thẻ script hoặc element chứa data-id/bov_id
                                let bovId = null;
                                const scripts = Array.from(document.querySelectorAll('script'));
                                for (let s of scripts) {
                                    if (s.innerText.includes('bov_id')) {
                                        const match = s.innerText.match(/bov_id["']?:\\s*["']?(\\d+)["']?/);
                                        if (match) { bovId = match[1]; break; }
                                    }
                                }
                                
                                if (!bovId) {
                                    const el = document.querySelector('[data-bovid], [data-id]');
                                    if (el) bovId = el.getAttribute('data-bovid') || el.getAttribute('data-id');
                                }

                                // Nếu lấy được bov_id, gọi trực tiếp API nội bộ BOVN bằng Cookie sẵn có
                                if (bovId) {
                                    const res = await fetch(`/api/movie?bov_id=${bovId}`);
                                    const json = await res.json();
                                    return { success: true, bovId: bovId, data: json };
                                }
                            } catch (e) {}

                            // Fallback: Lấy số liệu trực tiếp hiển thị trên DOM nếu API không trả về
                            const bodyText = document.body.innerText;
                            return { success: false, rawText: bodyText };
                        }
                    """)

                    total_rev = 0
                    today_rev = 0

                    if api_data and api_data.get("success") and api_data.get("data"):
                        res_json = api_data.get("data")
                        # Trích xuất dữ liệu từ API JSON chính chủ BOVN
                        total_rev = int(res_json.get("total_gross") or res_json.get("revenue") or 0)
                        today_rev = int(res_json.get("today_gross") or res_json.get("today_revenue") or 0)
                        print(f"  🎯 Bắt thành công từ API BOVN (bov_id={api_data.get('bovId')})")
                    else:
                        # Parsing con số từ DOM fallback
                        rev_nodes = page.query_selector_all(".revenue-value, [class*='revenue'], .stat-item")
                        nums = []
                        for node in rev_nodes:
                            txt = "".join(filter(str.isdigit, node.inner_text()))
                            if txt:
                                nums.append(int(txt))
                        if nums:
                            total_rev = max(nums)
                            today_rev = min(nums) if len(nums) > 1 else 0

                    print(f"  🎉 Doanh thu Tổng: {total_rev:,} VNĐ")
                    print(f"  🔥 Doanh thu Hôm nay: {today_rev:,} VNĐ")

                    # Gửi Doanh thu về Google Sheets qua doPost
                    if total_rev > 0:
                        payload = {
                            "title": movie_title,
                            "revenueVN": total_rev,
                            "revenueTodayVN": today_rev
                        }
                        post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
                        print(f"  💾 Google Sheets Update: {post_res.text}")
                    else:
                        print("  ⚠️ Không bắt được con số doanh thu.")

                else:
                    print("  ⚠️ Không tìm thấy phim trên Box Office Vietnam.")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý phim {movie_title}: {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
