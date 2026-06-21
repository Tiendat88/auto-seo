# AutoSEO — Tích hợp API Nhận bài tự động

> **Dành cho**: Nhà phát triển website muốn nhận bài viết tự động từ hệ thống AutoSEO.  
> **Phương pháp**: Cách 1 — Website expose API endpoint, AutoSEO gọi vào sau khi bài viết hoàn thành.

---

## 1. Tổng quan luồng hoạt động

```
[AutoSEO]                          [Website của bạn]
    │                                      │
    │  1. AI nghiên cứu + viết bài         │
    │     (mất ~5-10 phút)                 │
    │                                      │
    │  2. POST /your-endpoint              │
    │     Authorization: Bearer <SECRET>   │
    │     Content-Type: application/json   │
    │     { bài viết đầy đủ }  ──────────► │
    │                                      │  3. Xác thực SECRET
    │                                      │  4. Lưu bài vào DB
    │                                      │  5. Tạo slug URL
    │  6. { "success": true, "url": "..." }│
    │  ◄──────────────────────────────────  │
    │                                      │
    │  7. AutoSEO lưu URL bài đã đăng      │
```

---

## 2. Cấu hình phía AutoSEO (admin nhập)

Trong giao diện AutoSEO → **Đăng bài → Nền tảng → Thêm mới**, admin sẽ điền:

| Trường | Ví dụ | Mô tả |
|--------|-------|-------|
| Tên | "Website chính" | Tên hiển thị |
| Endpoint URL | `https://yoursite.com/api/autoseo/articles` | URL nhận bài |
| Secret Key | `sk_live_xxxxxxxxxxxxxxxx` | Dùng để xác thực |
| Chế độ mặc định | `draft` / `published` | Trạng thái bài sau khi đăng |

---

## 3. Request từ AutoSEO gửi đến

### Headers

```http
POST /api/autoseo/articles HTTP/1.1
Host: yoursite.com
Content-Type: application/json
Authorization: Bearer sk_live_xxxxxxxxxxxxxxxx
X-AutoSEO-Version: 1.0
X-AutoSEO-Job-ID: 3f2a1b4c-...
```

### Body (JSON)

```json
{
  "job_id": "3f2a1b4c-8e9d-4a2b-b1c3-d4e5f6a7b8c9",
  "title": "10 Chiến lược SEO hiệu quả năm 2025",
  "content_html": "<h1>...</h1><p>...</p>",
  "content_markdown": "# 10 Chiến lược SEO...\n\n...",
  "slug": "10-chien-luoc-seo-hieu-qua-nam-2025",
  "meta": {
    "title_tag": "10 Chiến lược SEO hiệu quả năm 2025 | Blog",
    "meta_description": "Khám phá 10 chiến lược SEO được chuyên gia kiểm chứng...",
    "primary_keyword": "chiến lược SEO",
    "secondary_keywords": ["SEO onpage", "tối ưu từ khóa", "link building"]
  },
  "schema_markup": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "10 Chiến lược SEO hiệu quả năm 2025",
    "author": { "@type": "Organization", "name": "AutoSEO" }
  },
  "faq": [
    {
      "question": "SEO mất bao lâu để có kết quả?",
      "answer": "Thông thường từ 3-6 tháng để thấy kết quả rõ rệt..."
    }
  ],
  "word_count": 2150,
  "language": "vi",
  "publish_mode": "draft",
  "created_at": "2025-06-20T15:22:00Z"
}
```

### Mô tả các trường

| Trường | Kiểu | Bắt buộc | Mô tả |
|--------|------|----------|-------|
| `job_id` | string (UUID) | ✅ | ID duy nhất của bài viết trong AutoSEO |
| `title` | string | ✅ | Tiêu đề bài viết |
| `content_html` | string | ✅ | Nội dung đầy đủ dạng HTML |
| `content_markdown` | string | ✅ | Nội dung dạng Markdown (backup) |
| `slug` | string | ✅ | URL-friendly, ví dụ: `ten-bai-viet` |
| `meta.title_tag` | string | ✅ | Thẻ `<title>` cho SEO (≤ 60 ký tự) |
| `meta.meta_description` | string | ✅ | Mô tả SEO (≤ 160 ký tự) |
| `meta.primary_keyword` | string | ✅ | Từ khóa chính |
| `meta.secondary_keywords` | string[] | ✅ | Danh sách từ khóa phụ |
| `schema_markup` | object | ✅ | JSON-LD Schema cho bài viết |
| `faq` | array | ⬜ | Danh sách Q&A (nếu có) |
| `word_count` | number | ⬜ | Số từ bài viết |
| `language` | string | ✅ | Mã ngôn ngữ (vi, en, ...) |
| `publish_mode` | string | ✅ | `draft` hoặc `published` |
| `created_at` | ISO 8601 | ✅ | Thời điểm tạo bài |

---

## 4. Response website phải trả về

### ✅ Thành công — HTTP 201

```json
{
  "success": true,
  "article_id": "42",
  "url": "https://yoursite.com/blog/10-chien-luoc-seo-hieu-qua-nam-2025",
  "status": "draft"
}
```

| Trường | Bắt buộc | Mô tả |
|--------|----------|-------|
| `success` | ✅ | Phải là `true` |
| `article_id` | ✅ | ID bài viết trong DB của bạn |
| `url` | ✅ | URL đầy đủ của bài trên website |
| `status` | ⬜ | Trạng thái thực tế đã lưu |

### ❌ Lỗi xác thực — HTTP 401

```json
{ "success": false, "error": "Unauthorized", "message": "Invalid or missing Authorization header" }
```

### ❌ Lỗi dữ liệu — HTTP 422

```json
{ "success": false, "error": "Validation failed", "message": "Field 'slug' is required" }
```

### ❌ Lỗi server — HTTP 500

```json
{ "success": false, "error": "Internal server error", "message": "Database connection failed" }
```

> **Lưu ý**: AutoSEO sẽ **retry tối đa 3 lần** nếu nhận HTTP 5xx. Không retry với 4xx.

---

## 5. Code mẫu theo từng stack

### Next.js (App Router — TypeScript)

```typescript
// app/api/autoseo/articles/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

const AUTOSEO_SECRET = process.env.AUTOSEO_SECRET_KEY!;

export async function POST(req: NextRequest) {
  // 1. Xác thực
  const authHeader = req.headers.get('authorization');
  if (authHeader !== `Bearer ${AUTOSEO_SECRET}`) {
    return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
  }

  // 2. Parse body
  const body = await req.json();
  const { job_id, title, content_html, slug, meta, schema_markup, faq, publish_mode } = body;

  // 3. Kiểm tra slug trùng
  const existing = await db.articles.findBySlug(slug);
  if (existing) {
    return NextResponse.json({ success: false, error: 'Slug already exists' }, { status: 422 });
  }

  // 4. Lưu vào DB
  const article = await db.articles.create({
    source_job_id:    job_id,
    title,
    content:          content_html,
    slug,
    meta_title:       meta.title_tag,
    meta_description: meta.meta_description,
    schema_markup:    JSON.stringify(schema_markup),
    faq:              JSON.stringify(faq ?? []),
    status:           publish_mode === 'published' ? 'published' : 'draft',
    published_at:     publish_mode === 'published' ? new Date() : null,
  });

  const url = `${process.env.NEXT_PUBLIC_SITE_URL}/blog/${slug}`;
  return NextResponse.json({ success: true, article_id: String(article.id), url, status: article.status }, { status: 201 });
}
```

---

### Express.js (Node.js)

```javascript
// routes/autoseo.js
const express = require('express');
const router = express.Router();
const AUTOSEO_SECRET = process.env.AUTOSEO_SECRET_KEY;

function verifyAutoSEO(req, res, next) {
  if (req.headers['authorization'] !== `Bearer ${AUTOSEO_SECRET}`) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }
  next();
}

router.post('/api/autoseo/articles', verifyAutoSEO, async (req, res) => {
  try {
    const { job_id, title, content_html, slug, meta, schema_markup, faq, publish_mode } = req.body;

    const article = await prisma.article.create({
      data: {
        sourceJobId:     job_id,
        title,
        content:         content_html,
        slug,
        metaTitle:       meta.title_tag,
        metaDescription: meta.meta_description,
        schemaMarkup:    schema_markup,
        faq:             faq ?? [],
        status:          publish_mode === 'published' ? 'PUBLISHED' : 'DRAFT',
      },
    });

    res.status(201).json({
      success:    true,
      article_id: String(article.id),
      url:        `${process.env.SITE_URL}/blog/${slug}`,
      status:     article.status.toLowerCase(),
    });
  } catch (err) {
    console.error('[AutoSEO]', err);
    res.status(500).json({ success: false, error: 'Internal server error' });
  }
});

module.exports = router;
```

---

### Laravel (PHP)

```php
// routes/api.php
Route::post('/autoseo/articles', [AutoSEOController::class, 'store']);
```

```php
// app/Http/Controllers/AutoSEOController.php
<?php
namespace App\Http\Controllers;
use Illuminate\Http\Request;
use App\Models\Article;

class AutoSEOController extends Controller
{
    public function store(Request $request)
    {
        $secret = config('services.autoseo.secret');
        if ($request->header('Authorization') !== "Bearer {$secret}") {
            return response()->json(['success' => false, 'error' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'job_id'       => 'required|string',
            'title'        => 'required|string',
            'content_html' => 'required|string',
            'slug'         => 'required|string|unique:articles,slug',
            'meta'         => 'required|array',
            'publish_mode' => 'required|in:draft,published',
        ]);

        $article = Article::create([
            'source_job_id'    => $data['job_id'],
            'title'            => $data['title'],
            'content'          => $data['content_html'],
            'slug'             => $data['slug'],
            'meta_title'       => $data['meta']['title_tag'],
            'meta_description' => $data['meta']['meta_description'],
            'schema_markup'    => json_encode($request->input('schema_markup')),
            'status'           => $data['publish_mode'],
        ]);

        return response()->json([
            'success'    => true,
            'article_id' => (string) $article->id,
            'url'        => config('app.url') . '/blog/' . $article->slug,
            'status'     => $article->status,
        ], 201);
    }
}
```

---

### Django (Python)

```python
# views.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Article

@csrf_exempt
def autoseo_articles(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    if request.headers.get('Authorization') != f"Bearer {settings.AUTOSEO_SECRET_KEY}":
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    try:
        article = Article.objects.create(
            source_job_id    = data['job_id'],
            title            = data['title'],
            content          = data['content_html'],
            slug             = data['slug'],
            meta_title       = data['meta']['title_tag'],
            meta_description = data['meta']['meta_description'],
            schema_markup    = json.dumps(data.get('schema_markup', {})),
            status           = data.get('publish_mode', 'draft'),
        )
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({
        'success':    True,
        'article_id': str(article.pk),
        'url':        f"{settings.SITE_URL}/blog/{article.slug}",
        'status':     article.status,
    }, status=201)
```

---

## 6. Biến môi trường cần thiết

```env
# Secret key — phải khớp với secret đã nhập trong AutoSEO
AUTOSEO_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxx

# URL website để tạo đường dẫn bài viết
SITE_URL=https://yoursite.com
```

> ⚠️ **Không bao giờ** commit `AUTOSEO_SECRET_KEY` lên Git.

---

## 7. Bảo mật

- **Bearer Token**: Mọi request đều có `Authorization: Bearer <SECRET_KEY>`. Sai → `401`.
- **HTTPS bắt buộc**: Endpoint phải dùng `https://` để tránh lộ Secret Key.
- **Whitelist IP** *(tuỳ chọn)*: Hỏi admin AutoSEO để lấy IP cố định và chặn request từ nơi khác.

---

## 8. Test tích hợp bằng curl

```bash
curl -X POST https://yoursite.com/api/autoseo/articles \
  -H "Authorization: Bearer sk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "test-001",
    "title": "Bài test tích hợp",
    "content_html": "<h1>Test</h1><p>Nội dung test</p>",
    "content_markdown": "# Test\n\nNội dung test",
    "slug": "bai-test-tich-hop",
    "meta": {
      "title_tag": "Bài test tích hợp",
      "meta_description": "Mô tả ngắn cho bài test",
      "primary_keyword": "test",
      "secondary_keywords": []
    },
    "schema_markup": {},
    "faq": [],
    "word_count": 10,
    "language": "vi",
    "publish_mode": "draft",
    "created_at": "2025-06-20T15:00:00Z"
  }'
```

**Kết quả mong đợi:**
```json
{
  "success": true,
  "article_id": "42",
  "url": "https://yoursite.com/blog/bai-test-tich-hop",
  "status": "draft"
}
```

---

## 9. Checklist trước khi bàn giao

- [ ] Endpoint `POST /api/autoseo/articles` đã hoạt động
- [ ] Đúng token → `201` / Sai token → `401` / Slug trùng → `422`
- [ ] HTTPS đã bật
- [ ] `AUTOSEO_SECRET_KEY` đã cấu hình trong `.env`
- [ ] Test `curl` thành công, bài hiển thị đúng trên website
- [ ] Gửi URL endpoint + Secret Key cho admin AutoSEO

---

## 10. Gửi lại cho admin AutoSEO

```
Endpoint URL : https://yoursite.com/api/autoseo/articles
Secret Key   : sk_live_xxxxxxxxxxxxxxxx
```

Admin sẽ nhập vào hệ thống và test 1 bài thực tế để xác nhận tích hợp thành công.
