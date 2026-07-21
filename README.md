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

### ساخت اولین ادمین

از داخل خود سایت نمی‌شه کسی رو ادمین کرد؛ این کار عمداً فقط از خط فرمان روی سرور ممکنه، تا یک کاربر عادی نتونه خودش رو ادمین کنه:

```bash
source venv/bin/activate
python -m app.create_admin --username admin --email admin@example.com
# رمز عبور رو ازت می‌پرسه (یا با --password هم می‌شه داد)
```

اگه یوزرنیمی که دادی از قبل وجود داشته باشه، فقط ادمینش می‌کنه (و اگه `--password` هم بدی رمزش عوض می‌شه)، وگرنه یک کاربر ادمین جدید می‌سازه.

## پیش‌نیازها روی VPS

این ابزارهای CLI باید از قبل نصب و در `PATH` باشن. هرکدوم نبود، همون بخش خودکار skip می‌شه و توی لاگ جاب هم گزارش می‌شه:

```
subfinder, chaos, assetfinder, findomain, amass, shuffledns, massdns,
asnmap, naabu, httpx, nuclei, anew, katana, waybackurls,
shosubgo, github-subdomains, jq, curl
dnsx (اختیاری — اگه نصب باشه، ستون IP هر ساب‌دامین توی فاز DNS Resolve پر می‌شه)
```

بعلاوه:
- Python 3.11+
- PostgreSQL (یا از `docker-compose.yml` پیوست استفاده کن)
- Redis (برای Celery)

## نصب

```bash
git clone <your-repo> subspyder && cd subspyder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# مقادیر .env رو ویرایش کن و SUBSPYDER_SECRET_KEY رو حتما به یک مقدار تصادفی طولانی تغییر بده

# اگه Postgres/Redis نداری:
docker compose up -d
```

متغیرهای `.env` رو قبل از اجرا export کن یا با `export $(cat .env | xargs)` بارگذاری کن (یا اگه خواستی خودت python-dotenv اضافه کن).

## اجرا

```bash
# ۱) وب‌سرور
uvicorn app.main:app --host 0.0.0.0 --port 8000

# ۲) ورکر Celery (توی ترمینال جدا)
celery -A app.celery_app worker --loglevel=info

# ۳) فقط بار اول: ساخت ادمین
python -m app.create_admin --username admin --email admin@example.com
```

بعدش برو به `http://<ip-vps>:8000`:

- به‌عنوان کاربر عادی: ثبت‌نام کن، تارگت بساز، اسکوپ رو وارد کن (خارج از اسکوپ / وایلدکارت داخل اسکوپ / دامنه‌ی عادی)، از بخش «API Key ها» کلیدهای شخصی خودت رو وارد کن، و از صفحه‌ی نتایج روی «اجرای اسکن کامل» بزن — هر ۵ فاز خودکار پشت سر هم اجرا می‌شن.
- به‌عنوان ادمین (بعد از لاگین با اکانتی که با `create_admin` ساختی): از سایدبار برو توی «کاربران» یا «پلن‌ها».

## کلیدهای API و provider-config.yaml خودِ subfinder

از بخش «API Key ها»، هر کاربر می‌تونه کلیدهای شخصی خودش رو برای این سورس‌ها وارد کنه:

- مشترک بین subfinder و یک ابزار مستقل دیگه: Chaos، GitHub (هم سورس `github` توی subfinder، هم ابزار `github-subdomains`)، Shodan (هم سورس `shodan` توی subfinder، هم ابزار `shosubgo`).
- فقط سورس subfinder: BeVigil، DigitalYama، PugRecon، ZoomEye (`zoomeyeapi`)، و FOFA که چون کلید ترکیبی `email:key` می‌خواد دو فیلد جدا برای ایمیل و کلید داره.
- ابزارهای خارج از subfinder: C99.nl و Censys (id/secret) — این‌ها مستقیم با `curl` صدا زده می‌شن و ربطی به provider-config.yaml ندارن.

هر بار فاز اول (جمع‌آوری پسیو) اجرا می‌شه، تابع `build_subfinder_provider_config` توی `app/tasks/tool_utils.py` از روی کلیدهای ذخیره‌شده‌ی همون کاربر یک فایل `subfinder-provider-config.yaml` اختصاصی می‌سازه (داخل workspace همون کاربر/تارگت) و با فلگ `-pc` به subfinder می‌ده. یعنی لازم نیست کسی دستی فایل `~/.config/subfinder/provider-config.yaml` رو روی سرور ویرایش کنه؛ هر کاربر کلیدهای خودش رو از پنل وارد می‌کنه. اگه کاربری هیچ‌کدوم از این کلیدها رو وارد نکرده باشه، این فایل اصلاً ساخته نمی‌شه و subfinder فقط با سورس‌های بدون کلید (crtsh، hackertarget، ...) اجرا می‌شه.

shosubgo (ابزار جدا برای گرفتن ساب‌دامین از Shodan) از قبل توی فاز اول یکپارچه‌ست — همون کلید Shodan که توی پنل وارد می‌کنی هم برای سورس `shodan` توی subfinder و هم برای اجرای `shosubgo -d <domain> -s <key>` استفاده می‌شه. اگه باینری `shosubgo` روی سرور نصب و در `PATH` نباشه، اون بخش خودکار skip می‌شه.


## نکات امنیتی

ورودی‌های کاربر (نام تارگت، دامنه‌های اسکوپ) قبل از استفاده در دستورات شل اعتبارسنجی می‌شن (`app/validators.py`) و با `shlex.quote` کوت می‌شن تا امکان Command Injection نباشه. اگه ابزار جدیدی به پایپ‌لاین اضافه می‌کنی، همین الگو رو برای هر مقدار ورودی کاربر رعایت کن.

API-key های کاربران توی دیتابیس فعلاً به‌صورت متن ساده ذخیره می‌شن، نه رمزنگاری‌شده. چون این پنل قراره روی سروری اجرا بشه که چند نفر بهش دسترسی دارن، پیشنهاد جدی می‌کنم ستون `ApiKey.key_value` رو با `cryptography.Fernet` و یک کلید سرورمحور (مثلا توی یک فایل جدا با دسترسی `600`) رمزنگاری کنی — این تغییر هنوز اعمال نشده، به‌عنوان قدم بعدی گذاشته شده.

این پنل روی سرورت دستورات CLI امنیتی (subfinder, nuclei, ...) رو اجرا می‌کنه؛ فقط برای دامنه‌هایی استفاده کن که مجاز به تستشون هستی (طبق قوانین برنامه‌ی باگ‌بانتی یا اجازه‌ی کتبی).

توی پروژه‌ی واقعی، پسورد دیتابیس پیش‌فرض توی `docker-compose.yml` و `.env.example` رو عوض کن و پورت‌های Postgres/Redis رو بیرون expose نکن مگر لازم باشه.

دسترسی ادمین فقط از طریق اسکریپت `app/create_admin.py` (روی خود سرور) قابل اعطاست، نه از وب. یک ادمین موجود می‌تونه از پنل کاربر دیگه‌ای رو ادمین/غیرادمین کنه، اما اولین ادمین باید از CLI ساخته بشه.

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
