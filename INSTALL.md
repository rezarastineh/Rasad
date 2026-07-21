# راهنمای نصب Rasad روی سرور (از صفر تا اجرا)

فرض: سرور اوبونتو ۲۲.۰۴/۲۴.۰۴ با دسترسی root داری.

---

## ۱) آپدیت سیستم و پکیج‌های پایه

```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git curl wget unzip build-essential ufw
```

## ۲) نصب Docker (برای Postgres و Redis)

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
docker --version
docker compose version
```

## ۳) نصب Go (برای ابزارهای recon)

```bash
cd /tmp
wget https://go.dev/dl/go1.23.4.linux-amd64.tar.gz   # اگه سرور ARM هست: go1.23.4.linux-arm64.tar.gz
rm -rf /usr/local/go
tar -C /usr/local -xzf go1.23.4.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> ~/.bashrc
source ~/.bashrc
go version
```

## ۴) نصب ابزارهای recon

```bash
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/chaos-client/cmd/chaos@latest
go install -v github.com/tomnomnom/assetfinder@latest
go install -v github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest
go install -v github.com/projectdiscovery/asnmap/cmd/asnmap@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/tomnomnom/anew@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
go install -v github.com/tomnomnom/waybackurls@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/incogbyte/shosubgo@latest
go install -v github.com/gwen001/github-subdomains@latest

cp ~/go/bin/* /usr/local/bin/
apt install -y jq curl

# massdns (زبان C، از سورس بیلد می‌شه)
cd /tmp
git clone https://github.com/blechschmidt/massdns.git
cd massdns && make
cp bin/massdns /usr/local/bin/
cd /tmp && rm -rf massdns

# findomain (باینری آماده)
curl -LO https://github.com/findomain/findomain/releases/latest/download/findomain-linux.zip
unzip findomain-linux.zip && chmod +x findomain
mv findomain /usr/local/bin/
rm findomain-linux.zip
```

چک کن همه نصب شدن:
```bash
for t in subfinder chaos assetfinder findomain shuffledns massdns asnmap naabu httpx nuclei anew katana waybackurls dnsx shosubgo github-subdomains jq curl; do
  command -v "$t" >/dev/null 2>&1 && echo "✅ $t" || echo "❌ $t"
done
```
اگه `amass` هم می‌خوای (اختیاریه، نبودش پروژه رو خراب نمی‌کنه): `snap install amass`

## ۵) ساخت یوزر مجزا برای اجرای برنامه (توصیه‌ی امنیتی)

```bash
useradd -m -s /bin/bash rasad
usermod -aG docker rasad
usermod -aG sudo rasad   # اگه می‌خوای بعداً systemd service رو خودش مدیریت کنه
```

## ۶) آپلود پروژه

از روی سیستم خودت (نه سرور):
```bash
scp Rasad_fixed.zip root@<IP-سرور>:/tmp/
```
روی سرور:
```bash
mkdir -p /opt/rasad
unzip -o /tmp/Rasad_fixed.zip -d /opt/rasad
chown -R rasad:rasad /opt/rasad
rm /tmp/Rasad_fixed.zip
```

## ۷) نصب پکیج‌های پایتون

```bash
su - rasad
cd /opt/rasad
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> ⚠️ **نکته‌ی مهم:** توی `requirements.txt` نسخه‌ی `bcrypt` روی `4.0.1` قفل شده. اگه این پین رو حذف کنی یا نسخه‌ی جدیدتر نصب بشه، `passlib==1.7.4` (که برای هش‌کردن پسورد استفاده می‌شه) دیگه نمی‌تونه نسخه‌ی bcrypt رو تشخیص بده (چون از `bcrypt.__about__.__version__` استفاده می‌کنه که در bcrypt ≥4.1 حذف شده) و مدام ارور/وارنینگ می‌ده یا هش پسورد درست کار نمی‌کنه. **این پین رو دست نزن.**

## ۸) تنظیم `.env`

```bash
cd /opt/rasad
cp .env.example .env
nano .env
```
حتماً `SUBSPYDER_DB_PASSWORD` رو با یه پسورد قوی و رندوم عوض کن، و همون مقدار رو دقیقاً توی `docker-compose.yml` هم زیر `POSTGRES_PASSWORD` بذار:
```bash
nano docker-compose.yml
```

## ۹) بالا آوردن Postgres و Redis

```bash
docker compose up -d postgres redis
sleep 3
docker compose ps
```

## ۱۰) ساخت جدول‌ها و یوزر ادمین

```bash
source venv/bin/activate
export $(cat .env | xargs)

# فقط یه‌بار بزن تا جدول‌ها ساخته بشن، بعد Ctrl+C
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

python -m app.create_admin --username admin --email admin@example.com
```


