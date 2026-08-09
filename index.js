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
    let idxDate = headers.indexOf("RELEASE_DATE") !== -1 ? headers.indexOf("RELEASE_DATE") : 6;

    const movies = [];
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      if (row.length > idxTitle) {
        const title = String(row[idxTitle] || '').trim();
        const releaseDate = row.length > idxDate ? String(row[idxDate] || '').trim() : '';
        if (title) movies.push({ title, releaseDate });
      }
    }
    return movies;
  } catch (e) {
    console.error("❌ Lỗi đọc CSV:", e.message);
    return [];
  }
}

async function runCrawler() {
  console.log('🚀 Bắt đầu chạy Bot GitHub Actions bóc tách Doanh Thu...');

  const movies = await getMoviesFromCSV();
  console.log(`📊 Tải thành công ${movies.length} phim từ Google Sheets CSV.`);

  if (movies.length === 0) {
    console.log('⚠️ Không có dữ liệu phim nào.');
    return;
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  const TODAY = new Date();

  for (const m of movies) {
    const releaseDate = m.releaseDate ? new Date(m.releaseDate) : new Date(0);
    const diffDays = Math.ceil((TODAY - releaseDate) / (1000 * 60 * 60 * 24));

    if (diffDays < 0 || diffDays > 30) continue;

    const slug = convertToBOVNSlug(m.title);
    const movieUrl = `https://v1.boxofficevietnam.com/movie/${slug}/`;

    console.log(`🔎 [Đang chiếu ${diffDays} ngày] Cào phim: [${m.title}] -> ${movieUrl}`);

    try {
      await page.goto(movieUrl, { waitUntil: 'networkidle2', timeout: 30000 });

      // In Tiêu đề trang để kiểm tra xem có bị dính Cloudflare anti-bot hay không
      const pageTitle = await page.title();
      console.log(`📄 Page Title: "${pageTitle}"`);

      const revenueText = await page.evaluate(() => {
        const bodyText = document.body.innerText || '';
        const match = bodyText.match(/Doanh\s*thu[^0-9]*([\d\.]+)\s*(?:₫|VND|VNĐ)/i);
        return match ? match[1] : null;
      });

      if (revenueText) {
        const revenueNum = parseInt(revenueText.replace(/\./g, ''), 10);
        
        if (GAS_WEBHOOK_URL) {
          await fetch(GAS_WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: m.title, revenue: revenueNum })
          });
        }
        console.log(`✅ CẬP NHẬT THÀNH CÔNG: [${m.title}] = ${revenueNum.toLocaleString('vi-VN')} VNĐ`);
      } else {
        console.log(`⚠️ Không tìm thấy ô doanh thu: ${m.title}`);
      }

      await new Promise(r => setTimeout(r, 1500));

    } catch (err) {
      console.log(`❌ Lỗi phim ${m.title}: ${err.message}`);
    }
  }

  await browser.close();
  console.log('🎉 Hoàn tất tiến trình!');
}

runCrawler();
