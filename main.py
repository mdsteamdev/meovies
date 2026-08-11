import json
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách tên phim từ Google Sheets (?action=get_showtime_ids hoặc endpoint phim)
    try:
        get_url = f"{WEB_APP_URL}?action=get_showtime_ids"
        res = requests.get(get_url)
        movies_data = res.json().get("movies", []) or res.json().get("showtimeIds", [])
        print(f"📋 Danh sách phim cần cào doanh thu BOVN: {movies_data}")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách từ Sheets: {e}")
        return

    if not movies_data:
        print("ℹ️ Không có tên phim nào cần cào.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )

        for item in movies_data:
            movie_title = str(item).strip() if isinstance(item, str) else str(item.get("title", "")).strip()
            if not movie_title:
                continue

            print(f"\n🔍 Đang tìm trên Box Office VN: {movie_title}")
            page = context.new_page()

            search_query = urllib.parse.quote(movie_title)
            search_url = f"https://boxofficevietnam.com/?s={search_query}"

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Chọn kết quả phim đầu tiên
                first_result = page.query_selector("article a, .post-title a, h2.entry-title a")
                if first_result:
                    detail_url = first_result.get_attribute("href")
                    print(f"  🌐 Vào trang chi tiết: {detail_url}")
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    # TÁCH LẤY DOANH THU TỔNG VÀ DOANH THU TRONG NGÀY TỪ DOM
                    revenue_data = page.evaluate("""
                        () => {
                            let total = 0;
                            let today = 0;
                            
                            // Bắt các khối hiển thị số tiền trên BOVN
                            const elements = document.querySelectorAll('.revenue-box, .stat-item, .revenue-value, .elementor-counter-number-wrapper');
                            
                            elements.forEach(el => {
                                const text = el.innerText || "";
                                const parentText = el.parentElement ? el.parentElement.innerText : "";
                                
                                // Bốc số nguyên từ chuỗi
                                const digits = text.replace(/[^0-9]/g, '');
                                const num = parseInt(digits, 10) || 0;

                                if (parentText.includes("Trong ngày") || parentText.includes("Hôm nay")) {
                                    today = num;
                                } else if (parentText.includes("Tổng") || parentText.includes("Doanh thu")) {
                                    if (num > total) total = num;
                                }
                            });

                            // Fallback nếu không gom được theo class: Lấy tất cả các số tiền ₫ trên trang
                            if (total === 0) {
                                const allText = document.body.innerText;
                                const matches = allText.match(/([0-9\\.,]+)\\s*₫/g) || [];
                                const nums = matches.map(m => parseInt(m.replace(/[^0-9]/g, ''), 10) || 0);
                                if (nums.length > 0) {
                                    total = Math.max(...nums);
                                    today = nums.length > 1 ? Math.min(...nums) : 0;
                                }
                            }

                            return { totalRevenue: total, todayRevenue: today };
                        }
                    """)

                    total_rev = revenue_data.get("totalRevenue", 0)
                    today_rev = revenue_data.get("todayRevenue", 0)

                    print(f"  🎉 Doanh thu Tổng: {total_rev:,} VNĐ")
                    print(f"  🔥 Doanh thu Hôm nay: {today_rev:,} VNĐ")

                    # Gửi kết quả về Google Sheets qua doPost
                    if total_rev > 0:
                        payload = {
                            "title": movie_title,
                            "revenueVN": total_rev,
                            "revenueTodayVN": today_rev
                        }
                        post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
                        print(f"  💾 Google Sheets Update: {post_res.text}")
                    else:
                        print("  ⚠️ Không bốc được số liệu doanh thu.")

                else:
                    print("  ⚠️ Không tìm thấy phim này trên BOVN.")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý phim {movie_title}: {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
