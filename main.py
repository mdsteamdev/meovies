import os
import json
import requests
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

def match_movies_with_gemini(bovn_movies, sheet_movies):
    if not GEMINI_API_KEY:
        print("⚠️ Không tìm thấy GEMINI_API_KEY trong environment variable.")
        return []

    prompt = f"""
Bạn là chuyên gia đối soát dữ liệu điện ảnh.
Dưới đây là 2 danh sách phim:

DANH SÁCH A (Trích xuất từ Box Office Vietnam):
{json.dumps(bovn_movies, ensure_ascii=False)}

DANH SÁCH B (Cơ sở dữ liệu của tôi):
{json.dumps(sheet_movies, ensure_ascii=False)}

Nhiệm vụ: Dựa vào Tên tiếng Việt, Tên tiếng Anh, hoặc ngữ cảnh (dễ thấy 'Spider Man' = 'Người Nhện'), hãy khớp các phim ở DANH SÁCH A với DANH SÁCH B.

Trả về duy nhất 1 mảng JSON chuẩn (không chứa markdown ```json):
[
  {{
    "matched_sheet_title": "Tên exact trong danh sách B",
    "revenueVN": 12345678,
    "revenueTodayVN": 123456
  }}
]
    """
    
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=){GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            result_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(result_text)
        else:
            print(f"❌ Lỗi gọi Gemini AI ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ Lỗi Exception Gemini AI: {e}")
    
    return []

def run():
    # 1. Lấy danh sách phim trên Google Sheets
    try:
        get_url = f"{WEB_APP_URL.strip()}?action=get_movie_titles"
        res = requests.get(get_url)
        sheet_movies = res.json().get("movies", [])
        print(f"📋 Danh sách DB ({len(sheet_movies)} phim): {[m.get('title') for m in sheet_movies]}")
    except Exception as e:
        print(f"❌ Lỗi lấy DB: {e}")
        return

    # 2. Playwright mở TRANG CHỦ BOVN
    bovn_scraped_data = []
    target_url = "[https://boxofficevietnam.com](https://boxofficevietnam.com)".strip()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1366, 'height': 768}
        )
        page = context.new_page()

        print(f"\n🌐 Đang mở Trang Chủ Box Office Vietnam: {target_url}")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(4000)

            bovn_scraped_data = page.evaluate("""
                () => {
                    const list = [];
                    const rows = document.querySelectorAll('table tbody tr, .movie-card, .revenue-item, [class*="movie"]');
                    
                    rows.forEach(row => {
                        const txt = row.innerText || "";
                        const lines = txt.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                        
                        if (lines.length >= 2) {
                            const nums = txt.match(/([0-9\\.,]+)\\s*₫/g) || [];
                            const parsedNums = nums.map(n => parseInt(n.replace(/[^0-9]/g, ''), 10) || 0);

                            if (parsedNums.length > 0) {
                                list.push({
                                    raw_text: lines[0],
                                    revenue_total: Math.max(...parsedNums),
                                    revenue_today: parsedNums.length > 1 ? Math.min(...parsedNums) : 0
                                });
                            }
                        }
                    });
                    return list;
                }
            """)

            print(f"🎉 Cào thành công {len(bovn_scraped_data)} phim từ Trang chủ BOVN!")

        except Exception as e:
            print(f"❌ Lỗi cào trang chủ BOVN: {e}")
        finally:
            page.close()
            browser.close()

    if not bovn_scraped_data:
        print("⚠️ Không lấy được dữ liệu từ Trang chủ BOVN.")
        return

    # 3. Gửi Gemini AI đối soát mờ
    print("\n🤖 Đang nhờ Gemini AI đối soát tên phim...")
    matched_results = match_movies_with_gemini(bovn_scraped_data, sheet_movies)
    print(f"🎯 AI đã ghép nối thành công {len(matched_results)} phim!")

    # 4. Gửi kết quả về Google Sheets
    for item in matched_results:
        title = item.get("matched_sheet_title")
        rev_total = item.get("revenueVN", 0)
        rev_today = item.get("revenueTodayVN", 0)

        if title and rev_total > 0:
            payload = {
                "title": title,
                "revenueVN": rev_total,
                "revenueTodayVN": rev_today
            }
            post_res = requests.post(WEB_APP_URL.strip(), data=json.dumps(payload))
            print(f"  💾 Cập nhật '{title}': {rev_total:,} VNĐ -> {post_res.text}")

if __name__ == "__main__":
    run()
