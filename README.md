# Rasad Panel

پنل چندکاربره‌ی خودکارسازی Recon / Subdomain Enumeration. یک پایپ‌لاین ۵ فازی داره که زنجیره‌ای اجرا می‌شه، یعنی با یک کلیک همه‌ی مراحل پشت سر هم انجام می‌شن و لازم نیست هر فاز رو دستی تریگر کنی.

فازها به ترتیب:

1. جمع‌آوری پسیو ساب‌دامین (subfinder, chaos, assetfinder, findomain, crt.sh, abuseipdb, amass, c99, shosubgo برای Shodan, github-subdomains)
2. DNS Resolve / Brute-force با shuffledns و massdns، همراه با فیلتر wildcard
3. Tech Detect، از طریق `asnmap | naabu | httpx | nuclei -id tech-detect`
4. HTTPX Probe — پورت، تایتل، Content-Type، تکنولوژی، IP، وب‌سرور، و یک دیف با اجرای قبلی تا ساب‌دامین یا محتوای جدید مشخص بشه
5. Finalize — کراول با Katana و گرفتن URL‌های آرشیوشده با Waybackurls روی ساب‌دامین‌های فعال

وقتی «اجرای اسکن کامل» رو می‌زنی، یک `celery.chain` ساخته می‌شه که فاز بعدی فقط بعد از موفقیت فاز قبلی شروع می‌شه (چون هر فاز به فایل‌های workspace فاز قبل از خودش نیاز داره). وضعیت هر فاز هم به شکل یک نوار پایپ‌لاین توی صفحه‌ی نتایج نشون داده می‌شه.

هر کاربر حساب و فضای جدای خودش رو داره، و هر تارگت هم زیرپوشه و داده‌ی مجزا (اسکوپ، ساب‌دامین‌ها، نتایج).

## پنل ادمین و اشتراک‌ها

ادمین می‌تونه لیست کاربرها رو ببینه، براشون پلن (سقف تعداد تارگت، سقف اسکن هم‌زمان) و تاریخ انقضای اشتراک تعیین کنه، یا کاربری رو مسدود/آزاد کنه و دسترسی ادمین بده یا بگیره. پلن‌ها هم از `/admin/plans` قابل تعریف‌اند، مثلا `Free` با ۲ تارگت و `Pro` با ۲۰ تارگت.

اگه اشتراک کسی منقضی یا غیرفعال بشه، دیگه نمی‌تونه تارگت جدید اضافه کنه یا اسکن جدید بزنه — ولی تارگت‌ها و نتایج قبلیش همچنان قابل مشاهده می‌مونه.


## کلیدهای API و provider-config.yaml خودِ subfinder

از بخش «API Key ها»، هر کاربر می‌تونه کلیدهای شخصی خودش رو برای این سورس‌ها وارد کنه:

- مشترک بین subfinder و یک ابزار مستقل دیگه: Chaos، GitHub (هم سورس `github` توی subfinder، هم ابزار `github-subdomains`)، Shodan (هم سورس `shodan` توی subfinder، هم ابزار `shosubgo`).
- فقط سورس subfinder: BeVigil، DigitalYama، PugRecon، ZoomEye (`zoomeyeapi`)، و FOFA که چون کلید ترکیبی `email:key` می‌خواد دو فیلد جدا برای ایمیل و کلید داره.
- ابزارهای خارج از subfinder: C99.nl و Censys (id/secret) — این‌ها مستقیم با `curl` صدا زده می‌شن و ربطی به provider-config.yaml ندارن.

هر بار فاز اول (جمع‌آوری پسیو) اجرا می‌شه، تابع `build_subfinder_provider_config` توی `app/tasks/tool_utils.py` از روی کلیدهای ذخیره‌شده‌ی همون کاربر یک فایل `subfinder-provider-config.yaml` اختصاصی می‌سازه (داخل workspace همون کاربر/تارگت) و با فلگ `-pc` به subfinder می‌ده. یعنی لازم نیست کسی دستی فایل `~/.config/subfinder/provider-config.yaml` رو روی سرور ویرایش کنه؛ هر کاربر کلیدهای خودش رو از پنل وارد می‌کنه. اگه کاربری هیچ‌کدوم از این کلیدها رو وارد نکرده باشه، این فایل اصلاً ساخته نمی‌شه و subfinder فقط با سورس‌های بدون کلید (crtsh، hackertarget، ...) اجرا می‌شه.

ابزارshosubgo (ابزار جدا برای گرفتن ساب‌دامین از Shodan) از قبل توی فاز اول یکپارچه‌ست — همون کلید Shodan که توی پنل وارد می‌کنی هم برای سورس `shodan` توی subfinder و هم برای اجرای `shosubgo -d <domain> -s <key>` استفاده می‌شه. اگه باینری `shosubgo` روی سرور نصب و در `PATH` نباشه، اون بخش خودکار skip می‌شه.



## ساختار پروژه

```
app/
  main.py              # اپ FastAPI
  config.py            # تنظیمات و مسیر فضای کاربران/تارگت‌ها
  database.py          # اتصال SQLAlchemy
  models.py            # مدل‌های دیتابیس (User, Plan, Target, ScopeEntry, ScanJob, ...)
  auth.py              # هش پسورد + سشن کوکی + get_current_admin
  bootstrap.py         # ساخت پلن پیش‌فرض هنگام استارت‌آپ
  create_admin.py      # اسکریپت CLI برای ساخت/ارتقای ادمین
  validators.py        # اعتبارسنجی ورودی‌های امنیتی
  celery_app.py        # تنظیمات Celery
  routers/              # روت‌های auth, targets, scope, apikeys, scan, admin
  tasks/                 # تسک‌های Celery برای هر فاز پایپ‌لاین
  templates/             # قالب‌های Jinja2
  static/style.css
```
