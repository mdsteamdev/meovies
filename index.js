const puppeteer = require('puppeteer');

const GAS_WEBHOOK_URL = process.env.GAS_WEBHOOK_URL; 
const SHEET_CSV_URL = process.env.SHEET_CSV_URL || "https://docs.google.com/spreadsheets/d/e/2PACX-1vSyGWxMCOKAobWEZ11jnlPOfRCfikB77SSYPMeLINstAaDJYldDJIv4MXVMvSmqFCtNj8T8hFIeBgUU/pub?gid=0&single=true&output=csv"; 

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

async function getMoviesFromCSV() {
  try {
    const response = await fetch(SHEET_CSV_URL);
    const csvText = await response.text();
    const rows = parseCSV(csvText);

    if (rows.length <= 1) return [];

    const headers = rows[0].map(h => String(h).trim().toUpperCase());
    let idxTitle = headers.indexOf("TÊN PHIM") !== -1 ? headers.indexOf("TÊN PHIM") : 0;

    const movies = [];
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      if (row.length > idxTitle) {
        const title = String(row[idxTitle] || '').trim();
        if (title) movies.push({ title });
      }
    }
    return movies;
  } catch (e) {
    console.error("❌ Lỗi đọc CSV:", e.message);
    return [];
  }
}

async function runCrawler() {
  console.log('🚀 Bắt đầu chạy Bot GitHub Actions...');

  const movies = await getMoviesFromCSV();
  console.log(`📊 Đã đọc được ${movies.length} phim từ Google Sheet CSV.`);

  if (movies.length === 0) {
    console.log('⚠️ Không lấy được tên phim nào từ file CSV.');
    return;
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  for (const m of movies) {
    const slug = convertToBOVNSlug(m.title);
    const movieUrl = `https://v1.boxofficevietnam.com/movie/${slug}/`;

    console.log(`🔎 [Xử lý] Phim: [${m.title}] -> URL: ${movieUrl}`);

    try {
      await page.goto(movieUrl, { waitUntil: 'networkidle2', timeout: 30000 });

      const pageTitle = await page.title();
      console.log(`📄 Title trang: "${pageTitle}"`);

      // Quét chuỗi số doanh thu đa định dạng từ Rendered DOM
      const revenueText = await page.evaluate(() => {
        const bodyText = document.body.innerText || '';
        // Pattern 1: Doanh thu: 123.456.789 ₫
        let match = bodyText.match(/Doanh\s*thu[^0-9]*([\d\.]+)\s*(?:₫|VND|VNĐ)/i);
        if (match) return match[1];

        // Pattern 2: Tìm chuỗi số định dạng XXX.XXX.XXX đ
        match = bodyText.match(/([\d\.]{6,15})\s*(?:₫|VND|VNĐ)/i);
        if (match) return match[1];

        return null;
      });

      if (revenueText) {
        const revenueNum = parseInt(revenueText.replace(/\./g, ''), 10);
        console.log(`💰 Tìm thấy Doanh thu: ${revenueNum.toLocaleString('vi-VN')} VNĐ`);

        if (GAS_WEBHOOK_URL) {
          const res = await fetch(GAS_WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: m.title, revenue: revenueNum })
          });
          const resText = await res.text();
          console.log(`📡 Phản hồi từ Google Sheet Webhook: ${resText}`);
        } else {
          console.log(`⚠️ Chưa cấu hình GAS_WEBHOOK_URL trong Secrets.`);
        }
      } else {
        console.log(`⚠️ Không tìm thấy ô số doanh thu cho phim: ${m.title}`);
      }

      await new Promise(r => setTimeout(r, 1500));

    } catch (err) {
      console.log(`❌ Lỗi khi tải phim ${m.title}: ${err.message}`);
    }
  }

  await browser.close();
  console.log('🎉 Hoàn tất toàn bộ tiến trình!');
}

runCrawler();
