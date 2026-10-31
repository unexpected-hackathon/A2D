"""화면 HTML과 정적 파일 내용."""

import json
from html import escape

from . import config as c


def layout(title: str, body: str, banner: str = "", extra_head: str = "") -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="JobNest CMS 2.3">
<title>{escape(title)}</title>
{extra_head}
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; color: #1d2433; background: #f6f8fb; }}
  header {{ background: #0b6bcb; color: #fff; padding: 16px 24px; display: flex; gap: 24px; align-items: center; }}
  header a {{ color: #fff; text-decoration: none; }}
  main {{ max-width: 960px; margin: 24px auto; padding: 0 16px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px #0002; }}
  .banner {{ background: #ffb020; color: #222; padding: 8px 24px; font-weight: 600; }}
  footer {{ color: #6b7385; font-size: 13px; text-align: center; padding: 24px; }}
  input, button {{ font: inherit; padding: 8px 10px; }}
  pre {{ background: #111; color: #eee; padding: 16px; overflow-x: auto; font-size: 13px; }}
</style>
</head>
<body>
{banner}
<header><strong>▣ JobNest</strong>
  <a href="/">홈</a><a href="/jobs">채용 공고</a><a href="/apply">지원하기</a><a href="/support">고객센터</a>
</header>
<main>
{body}
</main>
<footer>JobNest는 A2D 시연용 가상 채용·인재 매칭 플랫폼입니다. 모든 데이터는 가짜입니다.</footer>
</body>
</html>"""


def home() -> str:
    d = c.DOMAIN
    body = f"""
<div class="card">
  <h1>나에게 맞는 다음 회사를 찾아보세요</h1>
  <form action="/search"><input name="q" placeholder="직무나 회사 이름"> <button>검색</button></form>
</div>
<div class="card">
  <h2>추천 공고</h2>
  <ul>
    <li><a href="/jobs/backend-3y">백엔드 개발자 (3년 이상) · 가상테크</a></li>
    <li><a href="/jobs/ux-junior">UX 디자이너 (신입) · 샘플랩스</a></li>
    <li><a href="/apply">이력서 등록하고 지원하기</a></li>
  </ul>
  <img src="http://{c.EXT_BUCKET}/banners/hiring-2026.jpg" alt="채용 배너" width="1" height="1">
</div>
<div class="card">
  <h2>바로가기</h2>
  <ul>
    <li><a href="https://{c.HOST_BOOKING}/">기업 채용관리 (위탁 ATS)</a></li>
    <li><a href="https://{c.HOST_PROMO}/">채용 박람회 이벤트 페이지</a></li>
    <li><a href="/login">로그인</a> · <a href="/support">고객센터</a></li>
    <li><a href="https://{c.HOST_API}/api/v1/status">서비스 상태</a></li>
  </ul>
</div>
<script src="/static/js/jquery-1.12.4.min.js"></script>
<script src="/static/js/app.js"></script>
"""
    return layout(f"JobNest - {d}", body)


def simple(title: str, text: str) -> str:
    return layout(title, f'<div class="card"><h1>{escape(title)}</h1><p>{escape(text)}</p></div>')


def login() -> str:
    body = """
<div class="card"><h1>로그인</h1>
<form method="post" action="/login">
  <p><input name="email" placeholder="이메일"></p>
  <p><input name="password" type="password" placeholder="비밀번호"></p>
  <button>로그인</button>
</form></div>"""
    return layout("로그인 - JobNest", body)


def admin_login() -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>JobNest 채용 담당자 콘솔</title>
<style>body{{font-family:system-ui;background:#222;color:#eee;display:grid;place-items:center;height:100vh;margin:0}}
form{{background:#333;padding:32px;border-radius:8px;width:300px}}input,button{{width:100%;margin:6px 0;padding:8px;box-sizing:border-box}}</style>
</head><body>
<form method="post" action="/admin/login">
  <h2>채용 담당자 콘솔</h2>
  <p style="font-size:12px;color:#aaa">JobNest ATS Admin v1.4 · {escape(c.DOMAIN)}</p>
  <input name="username" placeholder="관리자 ID">
  <input name="password" type="password" placeholder="비밀번호">
  <button>로그인</button>
</form></body></html>"""


def staging(host: str) -> str:
    env = host.split(".", 1)[0].upper() if host else "STAGING"
    banner = f'<div class="banner">⚠ {env} 서버 · DEBUG=True · 운영 지원자 DB 복제본 사용 중 (2026-09-30 백업)</div>'
    body = f"""
<div class="card"><h1>JobNest {env}</h1>
<p>배포 전 확인용 서버입니다. 빌드: <code>web@4f2c9e1</code>, 브랜치 <code>release/2026-11</code></p>
<ul>
  <li><a href="/debug/vars">디버그 변수</a></li>
</ul></div>"""
    return layout(f"JobNest {env}", body, banner=banner)


def traceback_page(path: str) -> str:
    """#11: 없는 주소에 디버그 스택 트레이스를 보여 준다."""
    p = escape(path)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Error 500 - Internal Server Error</title></head>
<body style="font-family:monospace">
<h1>Whoops! Unhandled exception while routing {p}</h1>
<pre>Traceback (most recent call last):
  File "/var/www/jobnest/app/router.py", line 88, in dispatch
    page = Page.query.filter_by(slug=slug).one()
  File "/var/www/jobnest/venv/lib/python3.8/site-packages/sqlalchemy/orm/query.py", line 2870, in one
    raise orm_exc.NoResultFound("No row was found for one()")
sqlalchemy.orm.exc.NoResultFound: No row was found for one()

During handling of the above exception, another exception occurred:

  File "/var/www/jobnest/app/views/fallback.py", line 23, in render_legacy
    conn = pymysql.connect(host="10.0.12.5", user="jobnest", db="jobnest_prod")
pymysql.err.OperationalError: (1045, "Access denied for user 'jobnest'@'10.0.12.7' (using password: YES)")
</pre>
<p>PHP/8.1.2 legacy bridge · Apache/2.4.49 (Unix) · DocumentRoot /var/www/jobnest/public</p>
</body></html>"""


def not_found() -> str:
    return simple("페이지를 찾을 수 없습니다", "주소를 다시 확인해 주세요.")


def uploads_index() -> str:
    files = [
        ("resume_0012.pdf", "2026-10-02 11:20", "1.2M"),
        ("resume_0013.pdf", "2026-10-02 11:24", "1.1M"),
        ("career_certificate_0012.pdf", "2026-10-02 11:25", "340K"),
        ("applicants_2026Q3.xlsx", "2026-10-05 09:02", "88K"),
    ]
    rows = "\n".join(
        f'<tr><td><a href="{n}">{n}</a></td><td align="right">{t}</td><td align="right">{s}</td></tr>'
        for n, t, s in files
    )
    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html><head><title>Index of /uploads</title></head><body>
<h1>Index of /uploads</h1>
<table><tr><th>Name</th><th>Last modified</th><th>Size</th></tr><tr><th colspan="3"><hr></th></tr>
<tr><td><a href="/">Parent Directory</a></td><td>&nbsp;</td><td align="right">-</td></tr>
{rows}
<tr><th colspan="3"><hr></th></tr></table>
<address>Apache/2.4.49 (Unix) Server at {escape(c.HOST_WWW)} Port 443</address>
</body></html>"""


def server_status() -> str:
    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html><head><title>Apache Status</title></head><body>
<h1>Apache Server Status for {escape(c.HOST_WWW)} (via 10.0.12.7)</h1>
<dl><dt>Server Version: Apache/2.4.49 (Unix) PHP/8.1.2</dt>
<dt>Server MPM: event</dt><dt>Server Built: Sep 15 2021 08:11:09</dt></dl><hr>
<dl><dt>Current Time: Saturday, 31-Oct-2026 10:00:00 KST</dt>
<dt>Restart Time: Monday, 05-Oct-2026 03:00:12 KST</dt>
<dt>Server uptime: 26 days 6 hours 59 minutes 48 seconds</dt>
<dt>Total accesses: 1832044 - Total Traffic: 41.2 GB</dt></dl>
<table border="0"><tr><th>Client</th><th>VHost</th><th>Request</th></tr>
<tr><td>203.0.113.24</td><td>{escape(c.HOST_WWW)}:443</td><td>GET /mypage/applications HTTP/1.1</td></tr>
<tr><td>198.51.100.7</td><td>{escape(c.HOST_ADMIN)}:443</td><td>POST /admin/login HTTP/1.1</td></tr>
</table></body></html>"""


def actuator_env() -> str:
    return json.dumps(
        {
            "activeProfiles": ["prod"],
            "propertySources": [
                {
                    "name": "systemEnvironment",
                    "properties": {
                        "DB_HOST": {"value": "10.0.12.5"},
                        "DB_USERNAME": {"value": "jobnest"},
                        "DB_PASSWORD": {"value": "J0bN3st!demo-only"},
                        "JWT_SECRET": {"value": "demo-only-jwt-secret-do-not-use"},
                    },
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def robots() -> str:
    return f"""User-agent: *
Disallow: /admin/
Disallow: /uploads/
Disallow: /backup.zip
Disallow: /internal/reports/
Sitemap: https://{c.HOST_WWW}/sitemap.xml
"""


def sitemap() -> str:
    urls = ["/", "/jobs", "/jobs/backend-3y", "/jobs/ux-junior", "/apply", "/support", "/login"]
    items = "\n".join(f"  <url><loc>https://{c.HOST_WWW}{u}</loc></url>" for u in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>
"""


JQUERY_STUB = """/*! jQuery v1.12.4 | (c) jQuery Foundation | jquery.org/license */
/* A2D 시연용 자리표시자: 실제 jQuery 코드는 넣지 않고 버전 표시만 남긴다(#24 식별용). */
window.jQuery = window.$ = function () { return { ready: function (f) { f(); } }; };
window.jQuery.fn = { jquery: "1.12.4" };
"""


def app_js(leak: bool, sourcemap: bool) -> str:
    """#12, #13. leak이면 가짜 비밀키를, sourcemap이면 소스맵 주석을 넣는다."""
    if leak:
        cfg = f"""var JN_CONFIG = {{
  apiBase: "https://{c.HOST_API}",
  // TODO: 서버로 옮기기 (업로드가 급해서 임시로 넣음)
  aws: {{ region: "ap-northeast-2", bucket: "jobnest-resumes", accessKeyId: "{c.FAKE_AWS_KEY_ID}", secretAccessKey: "{c.FAKE_AWS_SECRET}" }},
  payments: {{ stripeKey: "{c.FAKE_STRIPE_SECRET}" }}
}};"""
    else:
        cfg = f"""var JN_CONFIG = {{
  apiBase: "https://{c.HOST_API}",
  uploadUrlEndpoint: "/api/v1/resumes/presign"
}};"""
    js = f"""{cfg}
(function () {{
  function loadJobs() {{
    fetch(JN_CONFIG.apiBase + "/api/v1/jobs").then(function (r) {{ return r.json(); }}).catch(function () {{}});
  }}
  function loadRecentApplicants() {{
    // "최근 지원자" 위젯이 지원자 목록을 통째로 불러온다(#16을 화면 코드로도 찾을 수 있게).
    fetch(JN_CONFIG.apiBase + "/api/v1/applicants?page=1").catch(function () {{}});
  }}
  function loadProfile() {{
    fetch(JN_CONFIG.apiBase + "/api/v1/applicants/me", {{ credentials: "include" }}).catch(function () {{}});
  }}
  document.addEventListener("DOMContentLoaded", function () {{ loadJobs(); loadRecentApplicants(); loadProfile(); }});
}})();
"""
    if sourcemap:
        js += "//# sourceMappingURL=app.js.map\n"
    return js


def app_js_map(leak: bool) -> str:
    src = app_js(leak=leak, sourcemap=False)
    original = (
        "// src/config.ts — 원본 소스 (빌드 시 압축 전)\n"
        "// 내부 API: /internal/reports/export, /admin/api/applicants/export\n" + src
    )
    return json.dumps(
        {
            "version": 3,
            "file": "app.js",
            "sources": ["webpack:///./src/config.ts"],
            "sourcesContent": [original],
            "names": [],
            "mappings": "AAAA",
        },
        ensure_ascii=False,
    )


def bucket_list() -> str:
    keys = [
        ("banners/hiring-2026.jpg", 182311),
        ("resumes/0012.pdf", 902113),
        ("resumes/0013.pdf", 887004),
        ("exports/applicants_2026-09-30.csv", 51220),
        ("backups/jobnest_prod_2026-09-30.sql.gz", 7340032),
    ]
    contents = "\n".join(
        f"  <Contents><Key>{k}</Key><LastModified>2026-10-01T03:00:00.000Z</LastModified>"
        f"<Size>{s}</Size><StorageClass>STANDARD</StorageClass></Contents>"
        for k, s in keys
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>jobnest-resumes</Name><Prefix></Prefix><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>
{contents}
</ListBucketResult>
"""


BUCKET_DENIED = """<?xml version="1.0" encoding="UTF-8"?>
<Error><Code>AccessDenied</Code><Message>Access Denied</Message><RequestId>A2DDEMO000000001</RequestId></Error>
"""

PAGES_404 = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Site not found &middot; GitHub Pages</title></head>
<body><div class="container"><h1>404</h1>
<p><strong>There isn't a GitHub Pages site here.</strong></p>
<p>If you're trying to publish one, <a href="https://docs.github.com/pages/">read the full documentation</a>
to learn how to set up <strong>GitHub Pages</strong> for your repository, organization, or user account.</p>
</div><!-- A2D 시연용: 실제 GitHub 서버가 아니라 시연 DNS가 가리키는 로컬 응답 --></body></html>
"""


def booking() -> str:
    return layout(
        "JobNest 기업 채용관리 (위탁 운영)",
        '<div class="card"><h1>기업 채용관리</h1><p>이 페이지는 채용관리 SaaS 업체 ATSPartner가 운영합니다.</p></div>',
    )
