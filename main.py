import json
import requests
from playwright.sync_api import sync_playwright

# DÁN LINK WEB APP CỦA BẠN VÀO ĐÂY
WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách showtimeId từ Google Sheets qua Web App
    try:
        res = requests.get(WEB_APP_URL)
        showtime_ids = res.json().get("showtimeIds", [])
        print(f"📋 Danh sách Showtime IDs cần cào: {showtime_ids}")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách ID từ Sheets: {e}")
        return

    if not showtime_ids:
        print("ℹ️ Không có ID nào cần cào.")
        return

    # 2. Khởi chạy Playwright (Trình duyệt Chromium thật)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for showtime_id in showtime_ids:
            print(f"\n🔍 Đang xử lý Showtime ID: {showtime_id}")
            page = context.new_page()

            # Mở trang đặt vé thật để tự động qua mặt Cloudflare & tạo Session
            booking_url = f"https://moveek.com/mua-ve/{showtime_id}/seats"
            
            try:
                page.goto(booking_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Bấm qua popup cảnh báo độ tuổi nếu xuất hiện
                agree_btn = page.query_selector("button:has-text('Tôi đã hiểu và đồng ý')")
                if agree_btn:
                    agree_btn.click()
                    page.wait_for_timeout(1000)

                # Gọi API /seats ngay bên trong ngữ cảnh trình duyệt đã có Token
                api_url = f"https://moveek.com/api/booking/v1/showtimes/{showtime_id}/seats"
                
                # Fetch trực tiếp từ Javascript context của trang
                response_data = page.evaluate(f"""
                    async () => {{
                        const res = await fetch('{api_url}');
                        return await res.json();
                    }}
                """)

                seats = response_data.get("data") or response_data.get("seats") or []
                total_seats = 0
                booked_seats = 0

                for seat in seats:
                    if seat.get("type") != "empty" and seat.get("status") != "blocked":
                        total_seats += 1
                        if seat.get("status") in ["booked", 1] or seat.get("taken") is True:
                            booked_seats += 1

                print(f"  🎉 Kết quả: Đã bán {booked_seats}/{total_seats} vé.")

                # 3. Đẩy kết quả về Google Sheets qua Web App
                payload = {
                    "showtimeId": showtime_id,
                    "totalSeats": total_seats,
                    "bookedSeats": booked_seats
                }
                post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
                print(f"  💾 Google Sheets Update: {post_res.text}")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý ID {showtime_id}: {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
