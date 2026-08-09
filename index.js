const puppeteer = require('puppeteer');

// LINK WEBHOOK APPS SCRIPT LẤY TỪ BIẾN MÔI TRƯỜNG TRÊN RENDER
const GAS_WEBHOOK_URL = process.env.GAS_WEBHOOK_URL; 

// LINK CSV THỰC TẾ TỪ GOOGLE SHEETS BẠN CUNG CẤP
const SHEET_CSV_URL = process.env.SHEET_CSV_URL || "https://docs.google.com/spreadsheets/d/e/2PACX-1vSyGWxMCOKAobWEZ11jnlPOfRCfikB77SSYPMeLINstAaDJYldDJIv4MXVMvSmqFCtNj8T8hFIeBgUU/pub?gid=0&single=true&output=csv"; 

// HÀM CHUYỂN TÊN PHIM THÀNH SLUG BOVN
function convertToBOVNSlug(title) {
  if (!title) return "";
  let clean = title.split(":")[0].split("-")[0].split("(")[0].trim();
  clean = clean.toLowerCase();
  clean = clean.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  clean = clean.replace(/đ/g, "d").replace(/Đ/g, "d");
  clean = clean.replace(/[^a-z0-9\s]/g, "");
  clean = clean.replace(/\s+/g, "-");
  return clean;
}

// HÀM PARSE CHUỖI CSV CHUẨN XÁC KỂ CẢ Ô CÓ NỔI DẤU XUỐNG DÒNG VÀ DẤU PHẨY
function parseCSV(text) {
  let p = '', c = '', r = [];
  let q = false;
  let row = [''];
  for (let i = 0; i < text.length; i++) {
    c = text[i];
    p = text[i - 1];
    if (c === '"') {
      if (q && text[i + 1] === '"') { row[row.length - 1] += '"'; i++; }
      else { q = !q; }
    } else if (c === ',' && !q) {
      row.push('');
    } else if ((c === '\r' || c === '\n') && !q) {
      if (c === '\r' && text[i + 1] === '\n') { i++; }
      r.push(row);
      row = [''];
    } else {
      row[row.length - 1] += c;
    }
  }
  if (row.length > 1 || row[0] !== '') { r.push(row); }
  return r;
}

// BÓC TÁCH DANH SÁCH PHIM DỰA TRÊN HEADER DỮ LIỆU
async function getMoviesFromCSV() {
  try {
    const response = await fetch(SHEET_CSV_URL);
    const csvText = await response.text();
    const rows = parseCSV(csvText);

    if (rows.length <= 1) return [];

    // Tìm chỉ số cột theo tên Header
    const headers = rows[0].map(h => String(h).trim().toUpperCase());
    
    let idxTitle = headers.indexOf("TÊN PHIM");
    if (idxTitle === -1) idxTitle = 0; // Mặc định Cột A

    let idxDate = headers.indexOf("RELEASE_DATE");
    if (idxDate === -1) idxDate = 6;  // Mặc định Cột G

    const movies = [];
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      if (row.length > idxTitle) {
        const title = String(row[idxTitle] || '').trim();
        const releaseDate = row.length > idxDate ? String(row[idxDate] || '').trim() : '';
        if (title) {
          movies.push({ title, releaseDate });
        }
      }
    }
    return movies;
  } catch (e) {
    console.error("❌ Lỗi đọc dữ liệu từ CSV:", e.message);
    return [];
  }
}

async function runCrawler() {
  console.log('🚀 Bắt đầu chạy Bot Chrome Render bóc tách Doanh Thu...');

  if (!GAS_WEBHOOK_URL) {
    console.error('❌ CẢNH BÁO: Chưa thiết lập biến môi trường GAS_WEBHOOK_URL trên Render.com!');
  }

  // 1. TẢI DỮ LIỆU PHIM TỪ SHEET CSV
  const movies = await getMoviesFromCSV();
  console.log(`📊 Tải thành công ${movies.length} phim từ đường dẫn Google Sheets CSV.`);

  if (movies.length === 0) {
    console.log('⚠️ Không có dữ liệu phim nào để xử lý.');
    return;
  }

  // 2. KHỞI TẠO CHROME ẨN DANH (CẤU HÌNH TỐI ƯU CHO RENDER)
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--single-process'
    ]
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  const TODAY = new Date();

  for (const m of movies) {
    // TÍNH NGÀY KHỞI CHIẾU ĐỂ LỌC ƯU TIÊN PHIM ĐANG CHIẾU
    const releaseDate = m.releaseDate ? new Date(m.releaseDate) : new Date(0);
    const diffDays = Math.ceil((TODAY - releaseDate) / (1000 * 60 * 60 * 24));

    // Lọc ưu tiên phim Đang chiếu (trong khoảng 30 ngày từ ngày ra mắt)
    if (diffDays < 0 || diffDays > 30) {
      continue; 
    }

    const slug = convertToBOVNSlug(m.title);
    const movieUrl = `https://v1.boxofficevietnam.com/movie/${slug}/`;

    console.log(`🔎 [Đang chiếu ${diffDays} ngày] Đang cào phim: [${m.title}] -> ${movieUrl}`);

    try {
      // Mở trang phim và đợi Chrome biên dịch xong Render DOM
      await page.goto(movieUrl, { waitUntil: 'networkidle2', timeout: 30000 });

      // Đọc trực tiếp con số doanh thu thực tế sau khi đã qua Chrome Render
      const revenueText = await page.evaluate(() => {
        const bodyText = document.body.innerText || '';
        const match = bodyText.match(/Doanh\s*thu[^0-9]*([\d\.]+)\s*(?:₫|VND|VNĐ)/i);
        return match ? match[1] : null;
      });

      if (revenueText) {
        const revenueNum = parseInt(revenueText.replace(/\./g, ''), 10);
        
        // BẮN KẾT QUẢ VỀ APPS SCRIPT WEBHOOK ĐỂ TỰ ĐỘNG GHI CỘT R (REVENUEVN)
        if (GAS_WEBHOOK_URL) {
          await fetch(GAS_WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: m.title, revenue: revenueNum })
          });
        }
        
        console.log(`✅ CẬP NHẬT THÀNH CÔNG: [${m.title}] = ${revenueNum.toLocaleString('vi-VN')} VNĐ`);
      } else {
        console.log(`⚠️ Không tìm thấy ô doanh thu hợp lệ cho: ${m.title}`);
      }

      // Nghỉ 1.5 giây giữa các lượt cào
      await new Promise(r => setTimeout(r, 1500));

    } catch (err) {
      console.log(`❌ Lỗi khi xử lý phim ${m.title}: ${err.message}`);
    }
  }

  await browser.close();
  console.log('🎉 Hoàn tất tiến trình cào và cập nhật doanh thu!');
}

runCrawler();
