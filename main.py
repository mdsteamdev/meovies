import json
import requests
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách ID từ Google Sheets qua doGet (?action=get_showtime_ids)
    try:
        get_url = f"{WEB_APP_URL}?action=get_showtime_ids"
        res = requests.get(get_url)
        showtime_ids = res.json().get("showtimeIds", [])
        print(f"📋 Danh sách Showtime IDs cần cào: {showtime_ids}")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách ID từ Sheets: {e}")
        return

    if not showtime_ids:
        print("ℹ️ Không có ID nào cần cào.")
        return

    # 2. Chạy Playwright với cấu hình giả lập trình duyệt thật
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1366, 'height': 768}
        )

        for showtime_id in showtime_ids:
            print(f"\n🔍 Đang xử lý Showtime ID: {showtime_id}")
            page = context.new_page()
            booking_url = f"https://moveek.com/mua-ve/{showtime_id}/seats"
            
            try:
                # Mở trang mua vé Moveek
                page.goto(booking_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(3000)

                # Bấm qua popup xác nhận độ tuổi nếu xuất hiện
                try:
                    agree_btn = page.query_selector("button:has-text('Tôi đã hiểu'), button:has-text('Đồng ý')")
                    if agree_btn:
                        agree_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

                # CÁCH 1: Đọc dữ liệu từ biến window state ngầm của Moveek (Chính xác 100%)
                seat_data = page.evaluate("""
                    () => {
                        try {
                            if (window.__NEXT_DATA__ && window.__NEXT_DATA__.props.pageProps) {
                                return window.__NEXT_DATA__.props.pageProps.seats || window.__NEXT_DATA__.props.pageProps.showtime.seats;
                            }
                        } catch (e) {}
                        return null;
                    }
                """)

                total_seats = 0
                booked_seats = 0

                if seat_data and isinstance(seat_data, list):
                    for seat in seat_data:
                        if seat.get("type") != "empty" and seat.get("status") != "blocked":
                            total_seats += 1
                            if seat.get("status") in ["booked", 1] or seat.get("taken") is True:
                                booked_seats += 1
                    print("  💡 Đã quét thành công dữ liệu từ Window State!")

                else:
                    # CÁCH 2: Quét trực tiếp các phần tử DOM trên màn hình nếu không lấy được State
                    page.wait_for_selector(".seat, .seat-item, [data-seat]", timeout=10000)
                    seats_elements = page.query_selector_all(".seat, .seat-item, [data-seat]")
                    
                    for el in seats_elements:
                        class_name = el.get_attribute("class") or ""
                        if "empty" not in class_name and "blocked" not in class_name:
                            total_seats += 1
                            if "booked" in class_name or "taken" in class_name or "occupied" in class_name:
                                booked_seats += 1
                    print("  💡 Đã quét thành công dữ liệu từ DOM Elements!")

                print(f"  🎉 Kết quả thực tế: Đã bán {booked_seats}/{total_seats} vé.")

                # 3. Gửi số vé về Google Sheets qua doPost
                if total_seats > 0:
                    payload = {
                        "showtimeId": showtime_id,
                        "totalSeats": total_seats,
                        "bookedSeats": booked_seats
                    }
                    post_res = requests.post(WEB_APP_URL, data=json.dumps(payload))
                    print(f"  💾 Google Sheets Update: {post_res.text}")
                else:
                    print("  ⚠️ Không tìm thấy ghế (Suất chiếu có thể đã hết giờ/đổi ID).")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý ID {showtime_id}: {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
