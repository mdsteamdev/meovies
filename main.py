import json
import requests
from playwright.sync_api import sync_playwright

WEB_APP_URL = "https://script.google.com/macros/s/AKfycby2csvwi9GJJ5L3fCNa9O4DqZxG50R-jk8o5c6uV7ltmZpM10Hbdd4paG3G4PoiQm39/exec"

def run():
    # 1. Lấy danh sách ID từ Google Sheets
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

    with sync_playwright() as p:
        # Giả lập trình duyệt Chrome thật
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )

        for showtime_id in showtime_ids:
            print(f"\n🔍 Đang xử lý Showtime ID: {showtime_id}")
            page = context.new_page()
            
            # Biến hứng dữ liệu JSON ghế
            seat_data_res = {"seats": []}

            # LẮNG NGHE MỌI RESPONSE CỦA BẤT KỲ API NÀO TRẢ VỀ DẠNG JSON
            def intercept_response(response):
                try:
                    if "application/json" in response.headers.get("content-type", ""):
                        res_json = response.json()
                        # Tìm mảng chứa thông tin ghế trong JSON
                        if isinstance(res_json, dict):
                            data = res_json.get("data") or res_json.get("seats") or res_json.get("items")
                            if isinstance(data, list) and len(data) > 0:
                                # Kiểm tra xem mảng này có phải là danh sách ghế không
                                if "status" in data[0] or "type" in data[0] or "price" in data[0]:
                                    seat_data_res["seats"] = data
                                    print(f"  🎯 Bắt được JSON sơ đồ ghế từ API: {response.url}")
                except Exception:
                    pass

            page.on("response", intercept_response)

            booking_url = f"https://moveek.com/mua-ve/{showtime_id}/seats"
            
            try:
                page.goto(booking_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(2000)

                # NÚT 1: Bấm "Tôi đã hiểu / Đồng ý" (Nếu có)
                try:
                    for btn_text in ["Tôi đã hiểu", "Đồng ý", "Tiếp tục"]:
                        btn = page.query_selector(f"button:has-text('{btn_text}')")
                        if btn and btn.is_visible():
                            btn.click()
                            page.wait_for_timeout(1000)
                except Exception:
                    pass

                # NÚT 2: Nếu bị kẹt ở bước Chọn Số Lượng Vé -> Bấm cộng 1 vé & Bấm "Chọn ghế" / "Tiếp tục"
                try:
                    plus_btn = page.query_selector(".btn-plus, button:has-text('+'), [data-type='plus']")
                    if plus_btn and plus_btn.is_visible():
                        plus_btn.click()
                        page.wait_for_timeout(500)
                        
                        continue_btn = page.query_selector("button:has-text('Chọn ghế'), button:has-text('Tiếp tục')")
                        if continue_btn and continue_btn.is_visible():
                            continue_btn.click()
                            page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Đợi 3s cho dữ liệu đổ về
                page.wait_for_timeout(3000)

                seats = seat_data_res["seats"]
                total_seats = 0
                booked_seats = 0

                # Nếu bắt được JSON API
                if seats:
                    for seat in seats:
                        s_type = str(seat.get("type", "")).lower()
                        s_status = str(seat.get("status", "")).lower()
                        
                        if s_type != "empty" and s_status != "blocked":
                            total_seats += 1
                            if s_status in ["booked", "1", "taken", "occupied"] or seat.get("taken") is True:
                                booked_seats += 1

                # Nếu vẫn không thấy API, đếm số lượng class phần tử sơ đồ ghế trên trang
                else:
                    seat_nodes = page.query_selector_all("div[class*='seat'], span[class*='seat'], svg [class*='seat']")
                    for node in seat_nodes:
                        c_name = node.get_attribute("class") or ""
                        if "empty" not in c_name and "blocked" not in c_name and "legend" not in c_name:
                            total_seats += 1
                            if "booked" in c_name or "taken" in c_name or "sold" in c_name or "active" in c_name:
                                booked_seats += 1

                print(f"  🎉 Kết quả cào thực tế: Đã bán {booked_seats}/{total_seats} vé.")

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
                    print("  ⚠️ Không bắt được số ghế. Kiểm tra xem Suất chiếu có bị hủy/hết giờ không.")

            except Exception as e:
                print(f"  ❌ Lỗi xử lý ID {showtime_id}: {e}")
            finally:
                page.close()

        browser.close()

if __name__ == "__main__":
    run()
