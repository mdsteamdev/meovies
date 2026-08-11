import os
import json
import requests
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

def match_movies_with_gemini(bovn_movies, sheet_movies):
    if not GEMINI_API_KEY:
        print("⚠️ Không tìm thấy GEMINI_API_KEY. Bỏ qua bước đối soát AI.")
        return []

    prompt = f"""
Bạn là chuyên gia đối soát dữ liệu điện ảnh.
Khớp danh sách A (từ Box Office VN) với danh sách B (từ Database của tôi).

DANH SÁCH A:
{json.dumps(bovn_movies, ensure_ascii=False)}

DANH SÁCH B:
{json.dumps(sheet_movies, ensure_ascii=False)}

Yêu cầu:
1. So sánh Tên tiếng Việt / Tên tiếng Anh / Ngữ cảnh (ví dụ: 'Spider Man 4' = 'Người Nhện: Khởi Đầu Mới', 'Conan Movie 29' = 'Thám Tử Lừng Danh Conan...').
2. Trả về mảng JSON chuẩn (KHÔNG DÙNG MARKDOWN ```json):
[
  {{
    "matched_sheet_title": "Tên chính xác trong Danh sách B",
    "revenueTodayVN": 12345678
  }}
]
    """
    
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key=){GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            result_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(result_text)
    except Exception as e:
        print(f"❌ Lỗi Gemini AI: {e}")
    
    return []

def run():
    # 1. Lấy DB từ Google Sheets
    try:
        res = requests.get(f"{WEB_APP_URL}?action=get_movie_titles")
        sheet_movies = res.json().get("movies", [])
        print(f"📋 Danh sách DB ({len(sheet_movies)} phim): {[m.get('title') for m in sheet_movies]}")
    except Exception as e:
        print(f"❌ Lỗi lấy DB: {e}")
        return

    # 2. Quét bảng Doanh thu trên v1.boxofficevietnam.com
    bovn_scraped_data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("\n🌐 Đang mở [https://v1.boxofficevietnam.com](https://v1.boxofficevietnam.com)...")
        try:
            page.goto("[https://v1.boxofficevietnam.com](https://v1.boxofficevietnam.com)", wait_until="domcontentloaded", timeout=40000)
            page.wait_for_selector("table tbody tr", timeout=10000)

            # Bốc trực tiếp từ các hàng <tr> trong <table>
            bovn_scraped_data = page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('table tbody tr'));
                    return rows.map(row => {
                        const cols = row.querySelectorAll('td');
                        const aTag = row.querySelector('a');
                        if (cols.length >= 2) {
                            const title = aTag ? aTag.innerText.trim() : cols[0].innerText.trim();
                            const revenueStr = cols[1] ? cols[1].innerText.replace(/[^0-9]/g, '') : "0";
                            return {
                                title: title,
                                revenueToday: parseInt(revenueStr, 10) || 0
                            };
                        }
                        return null;
                    }).filter(Boolean);
                }
            """)

            print(f"🎉 Cào thành công {len(bovn_scraped_data)} phim từ Bảng Trang chủ BOVN!")
            for item in bovn_scraped_data:
                print(f"  - {item['title']}: {item['revenueToday']:,} VNĐ")

        except Exception as e:
            print(f"❌ Lỗi cào bảng BOVN: {e}")
        finally:
            page.close()
            browser.close()

    if not bovn_scraped_data:
        print("⚠️ Không lấy được bảng dữ liệu.")
        return

    # 3. Cho Gemini AI đối soát tên phim
    print("\n🤖 Đang nhờ Gemini AI đối soát tên phim...")
    matched_results = match_movies_with_gemini(bovn_scraped_data, sheet_movies)
    print(f"🎯 Ghép nối thành công {len(matched_results)} phim!")

    # 4. Gửi Doanh thu trong ngày về Google Sheets
    for item in matched_results:
        title = item.get("matched_sheet_title")
        rev_today = item.get("revenueTodayVN", 0)

        if title and rev_today > 0:
            payload = {
                "title": title,
                "revenueTodayVN": rev_today
            }
            post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
            print(f"  💾 Cập nhật '{title}': {rev_today:,} VNĐ -> {post_res.text}")

if __name__ == "__main__":
    run()
