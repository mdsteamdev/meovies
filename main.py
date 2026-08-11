import json
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

# Link Web App duy nhất của bạn
WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách phim từ Google Sheets (?action=get_movie_titles)
    try:
        get_url = f"{WEB_APP_URL}?action=get_movie_titles"
        res = requests.get(get_url)
        movies_list = res.json().get("movies", [])
        print(f"📋 Danh sách phim cần cào BOVN ({len(movies_list)} phim):")
        for m in movies_list:
            print(f"  - Tên VN: '{m.get('title')}' | Tên Gốc: '{m.get('originalTitle')}'")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách phim từ Sheets: {e}")
        return

    if not movies_list:
        print("ℹ️ Không có danh sách phim nào cần cào.")
        return

    # 2. Khởi chạy Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1366, 'height': 768}
        )

        for item in movies_list:
            movie_title = str(item.get("title", "")).strip()
            orig_title = str(item.get("originalTitle", "")).strip()

            if not movie_title and not orig_title:
                continue

            # Ưu tiên từ khóa tìm kiếm: Tên Việt trước, nếu không có thì tìm theo Tên Gốc
            search_key = movie_title if movie_title else orig_title
            print(f"\n🔍 Đang cào BOVN cho: '{movie_title}' (Gốc: '{orig_title}')")

            page = context.new_page()
            search_query = urllib.parse.quote(search_key)
            search_url = f"https://boxofficevietnam.com/?s={search_query}"

            try:
                # Mở trang Search
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Chọn kết quả phim đầu tiên
                first_link = page.query_selector("article a, .post-title a, h2.entry-title a")
                if first_link:
                    detail_url = first_link.get_attribute("href")
                    print(f"  🌐 Mở trang chi tiết: {detail_url}")
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    # BẮT ELEMENT H1 (TÊN VN) VÀ THẺ P NGAY DƯỚI H1 (TÊN GỐC - ORIGINAL TITLE)
                    bovn_info = page.evaluate("""
                        () => {
                            const h1 = document.querySelector('h1');
                            const titleVN = h1 ? h1.innerText.trim() : "";
                            
                            let origTitle = "";
                            if (h1 && h1.nextElementSibling && h1.nextElementSibling.tagName === 'P') {
                                origTitle = h1.nextElementSibling.innerText.trim();
                            }

                            return { titleVN, origTitle };
                        }
                    """)

                    bovn_title_vn = bovn_info.get("titleVN", "").lower()
                    bovn_orig_title = bovn_info.get("origTitle", "").lower()

                    print(f"  📌 BOVN Render -> Title VN: '{bovn_info.get('titleVN')}' | Original Title: '{bovn_info.get('origTitle')}'")

                    # KIỂM TRA ĐỐI SOÁT (DUAL-MATCHING)
                    is_match = False
                    if movie_title and movie_title.lower() in bovn_title_vn:
                        is_match = True
                    elif orig_title and (orig_title.lower() in bovn_orig_title or bovn_orig_title in orig_title.lower()):
                        is_match = True

                    if is_match:
                        print("  🎯 MATCH TÊN THÀNH CÔNG! Bắt đầu trích xuất doanh thu...")

                        # BỐC DOANH THU TỪ API NỘI BỘ HOẶC THẺ DOM
                        revenue_data = page.evaluate("""
                            async () => {
                                let total = 0;
                                let today = 0;

                                try {
                                    // 1. Thử gọi API nội bộ BOVN nếu tìm thấy bov_id
                                    let bovId = null;
                                    const scripts = Array.from(document.querySelectorAll('script'));
                                    for (let s of scripts) {
                                        if (s.innerText.includes('bov_id')) {
                                            const match = s.innerText.match(/bov_id["']?:\\s*["']?(\\d+)["']?/);
                                            if (match) { bovId = match[1]; break; }
                                        }
                                    }

                                    if (bovId) {
                                        const res = await fetch(`/api/movie?bov_id=${bovId}`);
                                        const json = await res.json();
                                        if (json) {
                                            total = int(json.total_gross || json.revenue || 0);
                                            today = int(json.today_gross || json.today_revenue || 0);
                                        }
                                    }
                                } catch (e) {}

                                // 2. Fallback: Đọc trực tiếp các con số tiền mặt hiển thị trên DOM
                                if (total === 0) {
                                    const revBoxes = document.querySelectorAll('.revenue-box, .stat-item, .revenue-value, .elementor-counter-number-wrapper');
                                    revBoxes.forEach(el => {
                                        const txt = el.innerText || "";
                                        const parentTxt = el.parentElement ? el.parentElement.innerText : "";
                                        const num = parseInt(txt.replace(/[^0-9]/g, ''), 10) || 0;

                                        if (parentTxt.includes("Trong ngày") || parentTxt.includes("Hôm nay")) {
                                            today = num;
                                        } else if (parentTxt.includes("Tổng") || parentTxt.includes("Doanh thu")) {
                                            if (num > total) total = num;
                                        }
                                    });

                                    // Nếu vẫn chưa tìm thấy, lọc tất cả chuỗi có ký hiệu ₫
                                    if (total === 0) {
                                        const matches = document.body.innerText.match(/([0-9\\.,]+)\\s*₫/g) || [];
                                        const nums = matches.map(m => parseInt(m.replace(/[^0-9]/g, ''), 10) || 0);
                                        if (nums.length > 0) {
                                            total = Math.max(...nums);
                                            today = nums.length > 1 ? Math.min(...nums) : 0;
                                        }
                                    }
                                }

                                return { total, today };
                            }
                        """)

                        total_rev = revenue_data.get("total", 0)
                        today_rev = revenue_data.get("today", 0)

                        print(f"  🎉 Doanh thu Tổng: {total_rev:,} VNĐ")
                        print(f"  🔥 Doanh thu Hôm nay: {today_rev:,} VNĐ")

                        # Gửi dữ liệu về Google Sheets qua doPost
                        if total_rev > 0:
                            payload = {
                                "title": movie_title,
                                "originalTitle": orig_title,
                                "revenueVN": total_rev,
                                "revenueTodayVN": today_rev
                            }
                            post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
                            print(f"  💾 Google Sheets Update: {post_res.text}")
                        else:
                            print("  ⚠️ Không trích xuất được con số doanh thu.")

                    else:
                        print("  ❌ Tên phim trên BOVN không trùng khớp với Tên VN lẫn Original Title.")

                else:
                    print("  ⚠️ Không tìm thấy phim trên Box Office Vietnam.")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý phim '{movie_title}': {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
