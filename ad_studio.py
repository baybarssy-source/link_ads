# -*- coding: utf-8 -*-
"""استوديو إعلانات فيسبوك: صفحة وسيطة مجانية تحوِّل من الإعلان إلى Google Play.

ما تفعله:
- لكل تطبيق «حملة»: الاسم، ورابط المتجر، والأيقونة، وصورة الإعلان، والمزايا، ونصوص إعلان فيسبوك.
- تولّد الصفحة الوسيطة في docs/ فتُنشر مجانًا على GitHub Pages (المصدر: main ← ‎/docs)، ويبقى الرابط يعمل دائمًا.
- «نشر» يفتح «أداة الالتزام» (التزام.bat) لتلتزم وترفع، وعنوان الصفحة يُقرأ وحده من مستودع git.
- تعطيك رابط الإعلان جاهزًا للنسخ، مع مصدر الحملة الذي يظهر في Play Console ← اكتساب المستخدمين.
- نصوص الإعلان بعدّاد للحدّ الذي يظهر كاملًا في فيسبوك، ولكل نصّ زرّ نسخ.
- كل تعديل يُحفظ وحده بعد لحظة (campaigns.json و docs/apps.js).
- «تحديث الإحصاءات»: يقرأ من تقارير Play Console زوّار صفحة المتجر وتنزيلاتها لكل حملة (قراءة فقط)،
  بمفتاح حساب الخدمة نفسه الذي تستعمله أداة النشر ve_up.

التثبيت:  pip install -r المكتبات_المطلوبة.txt   (أو تثبيت_المكتبات.bat)
التشغيل:  python -X utf8 ad_studio.py           (أو «استوديو الإعلانات.bat»)
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QImage, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ui_common import FEEDBACK_CSS, install_wheel_guard

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "docs"                       # GitHub Pages يقبل الجذر أو docs/ فقط
DATA_FILE = ROOT / "campaigns.json"
SETTINGS_FILE = ROOT / "settings.json"
COMMIT_BAT = ROOT / "التزام.bat"

C_BG, C_PANEL, C_EDGE, C_TEXT, C_MUTED = "#15191d", "#1e2429", "#323b43", "#e6ebef", "#93a0ab"
C_ACCENT, C_OK, C_WARN, C_ERR = "#2f9e6f", "#5fd08a", "#e6b34a", "#ef6b6b"

STYLE = f"""
QWidget {{ background:{C_BG}; color:{C_TEXT}; font-family:'Segoe UI','Tahoma'; font-size:14px; }}
QGroupBox {{ border:1px solid {C_EDGE}; border-radius:10px; margin-top:14px; padding:12px 10px 10px; background:{C_PANEL}; }}
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top right; right:12px; padding:0 6px; color:{C_OK}; font-weight:bold; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QListWidget {{
  background:#11151a; border:1px solid {C_EDGE}; border-radius:7px; padding:6px; selection-background-color:{C_ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color:{C_ACCENT}; }}
QListWidget::item {{ padding:9px; border-radius:6px; }}
QListWidget::item:selected {{ background:{C_ACCENT}; color:white; }}
QPushButton {{ background:#2a323a; border:1px solid {C_EDGE}; border-radius:8px; padding:7px 14px; }}
QPushButton#primary {{ background:{C_ACCENT}; border-color:{C_ACCENT}; color:white; font-weight:bold; }}
QPushButton#danger {{ color:{C_ERR}; }}
QPushButton:disabled {{ color:#5d6670; }}
QLabel#hint {{ color:{C_MUTED}; font-size:12px; }}
QLabel#link {{ background:#11151a; border:1px solid {C_ACCENT}; border-radius:7px; padding:8px; color:#9ee6c0; }}
QProgressBar {{ border:1px solid {C_EDGE}; border-radius:6px; text-align:center; background:#11151a; height:16px; }}
QProgressBar::chunk {{ background:{C_ACCENT}; border-radius:5px; }}
QScrollArea {{ border:none; }}
QLabel {{ background:transparent; }}
QScrollBar:vertical {{ background:{C_BG}; width:10px; margin:0; }}
QScrollBar:horizontal {{ background:{C_BG}; height:10px; margin:0; }}
QScrollBar::handle {{ background:{C_EDGE}; border-radius:5px; min-height:30px; min-width:30px; }}
QScrollBar::handle:hover {{ background:#4a5560; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background:none; height:0; width:0; }}
"""

# أزرار الدعوة في إعلانات ميتا (الاسم كما يظهر في مدير الإعلانات)
CTA_OPTIONS = ["تنزيل (Download)", "تثبيت الآن (Install now)", "معرفة المزيد (Learn more)", "استخدام التطبيق (Use app)"]
# الحدّ الذي يظهر كاملًا قبل «عرض المزيد» في أغلب مواضع الإعلان
LIMITS = {"primary": 125, "headline": 40, "description": 30}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")


# ───────────────────────── المنطق (بلا واجهة، يُختبر وحده) ─────────────────────────
def parse_package(text: str) -> str:
    """يقبل رابط المتجر أو اسم الحزمة، ويعيد اسم الحزمة أو ''."""
    text = text.strip()
    m = re.search(r"[?&]id=([A-Za-z0-9_.]+)", text)
    pkg = m.group(1) if m else text
    return pkg if PKG_RE.match(pkg) else ""


def new_app(name: str = "تطبيق جديد") -> dict:
    return {"name": name, "package": "", "tagline": "", "icon": "", "hero": "", "color": "#2f9e6f",
            "features": [], "rating": "", "downloads": "", "redirect": 2,
            "ad": {"primary": "", "headline": "", "description": "", "cta": CTA_OPTIONS[0], "campaign": "launch"}}


def load_data() -> dict:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("repo_url", "")
    data.setdefault("base_url", "")
    data.setdefault("pixel_id", "")
    data.setdefault("contact", "")
    data.setdefault("apps", {})
    return data


def save_data(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_apps_js(data)


def write_apps_js(data: dict) -> None:
    """يكتب site/apps.js من بيانات الحملات (الحقول العامّة وحدها)."""
    public = {}
    for slug, a in data["apps"].items():
        public[slug] = {k: a.get(k) for k in ("name", "package", "tagline", "icon", "hero", "color",
                                               "features", "rating", "downloads", "redirect")}
    first = next(iter(data["apps"]), "")
    js = ("// يولّده «استوديو الإعلانات» تلقائيًّا. لا تعدّله باليد، فسيُكتب فوقه.\n"
          f"window.APPS = {json.dumps(public, ensure_ascii=False, indent=2)};\n"
          f"window.DEFAULT_APP = {json.dumps(first)};\nwindow.REDIRECT_SECONDS = 2;\n"
          f"window.META_PIXEL = {json.dumps(data.get('pixel_id', ''))};\n"
          f"window.CONTACT_EMAIL = {json.dumps(data.get('contact', ''))};\n")
    SITE.mkdir(exist_ok=True)
    (SITE / "apps.js").write_text(js, encoding="utf-8")
    (SITE / ".nojekyll").touch()           # يمنع GitHub من معالجة الملفّات بـ Jekyll


def build_link(base_url: str, slug: str, campaign: str, src: str = "facebook") -> str:
    base = (base_url or "https://USER.github.io/REPO/").rstrip("/") + "/"
    camp = re.sub(r"[^A-Za-z0-9_-]+", "-", campaign or "ad").strip("-") or "ad"
    return f"{base}?app={slug}&src={src}&camp={camp}"


def import_image(src: str, slug: str, kind: str) -> str:
    """ينسخ الصورة إلى site/images بمقاس مناسب للويب، ويعيد مسارها النسبيّ داخل الموقع."""
    img = QImage(src)
    if img.isNull():
        raise ValueError("تعذّر فتح الصورة. اختر ملفّ PNG أو JPG سليمًا.")
    (SITE / "images").mkdir(parents=True, exist_ok=True)
    if kind == "icon":
        img = img.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        rel = f"images/{slug}-icon.png"
        ok = img.save(str(SITE / rel), "PNG")
    else:
        if img.width() > 1080:
            img = img.scaledToWidth(1080, Qt.SmoothTransformation)
        rel = f"images/{slug}-ad.jpg"
        ok = img.convertToFormat(QImage.Format_RGB888).save(str(SITE / rel), "JPG", 86)
    if not ok:
        raise ValueError("تعذّر حفظ الصورة في مجلّد الموقع.")
    return rel


# مقاسات فيسبوك وإنستغرام: الاسم، العرض، الارتفاع، أين يُستعمل
AD_SIZES = [
    ("square-1080x1080", 1080, 1080, "الأخبار في فيسبوك وإنستغرام (الأكثر استعمالًا)"),
    ("portrait-1080x1350", 1080, 1350, "الأخبار في الهاتف (يأخذ مساحة أكبر من الشاشة)"),
    ("story-1080x1920", 1080, 1920, "القصص والريلز"),
    ("landscape-1200x628", 1200, 628, "العمود الجانبي وشبكة الجمهور"),
]
AD_OUT = ROOT / "صور الإعلان"


def make_ad_sizes(src: Path, slug: str) -> list[Path]:
    """يضع الصورة كاملة بلا قصّ في كل مقاس، والفراغ حولها نسخة مكبّرة ضبابية داكنة منها."""
    from PySide6.QtGui import QPainter
    img = QImage(str(src))
    if img.isNull():
        raise ValueError("لا صورة إعلان لهذا التطبيق. اختر صورة الإعلان أوّلًا.")
    out_dir = AD_OUT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, w, h, _ in AD_SIZES:
        canvas = QImage(w, h, QImage.Format_RGB32)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # الخلفية: تغطية كاملة ثم تصغير شديد وتكبير ناعم = ضباب
        cover = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        blur = cover.scaled(max(1, w // 24), max(1, h // 24), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        blur = blur.scaled(cover.width(), cover.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.drawImage((w - blur.width()) // 2, (h - blur.height()) // 2, blur)
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, 165))
        fit = img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawImage((w - fit.width()) // 2, (h - fit.height()) // 2, fit)
        p.end()
        path = out_dir / f"{slug}-{name}.jpg"
        if not canvas.save(str(path), "JPG", 92):
            raise ValueError(f"تعذّر حفظ {path.name}.")
        made.append(path)
    return made


def repo_to_pages(repo_url: str) -> str:
    """https://github.com/USER/REPO  ←  https://USER.github.io/REPO/"""
    m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s]+?)(\.git)?/?$", repo_url.strip())
    if not m:
        return ""
    user, repo = m.group(1), m.group(2)
    if repo.lower() == f"{user.lower()}.github.io":
        return f"https://{user.lower()}.github.io/"
    return f"https://{user.lower()}.github.io/{repo}/"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(s: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ───────────────────────── git والتحقّق من الرابط ─────────────────────────
def git_remote() -> str:
    """رابط مستودع GitHub لهذا المشروع (origin) بصيغة https، أو '' إن لم يُنشأ بعد."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8", creationflags=flags, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.match(r"git@github\.com:(.+?)(\.git)?$", out)
    if m:
        out = f"https://github.com/{m.group(1)}"
    return out.removesuffix(".git").rstrip("/") if out.startswith("https://github.com/") else ""


def _git_out(*args) -> tuple[int, str]:
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           creationflags=flags, timeout=10)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def publish_state() -> str:
    """published: كل ما في الموقع مرفوع · pending: تعديلات لم تُلتزم أو لم تُرفع · norepo: لا مستودع على GitHub."""
    if not git_remote():
        return "norepo"
    code, dirty = _git_out("status", "--porcelain", "--", "docs", "campaigns.json")
    if code != 0 or dirty:
        return "pending"
    code, ahead = _git_out("rev-list", "--count", "@{u}..HEAD")
    if code != 0 or ahead != "0":          # لم يُرفع شيء بعد، أو التزامات تنتظر الرفع
        return "pending"
    return "published"


class CheckWorker(QThread):
    """يتحقّق في الخلفية من أنّ الصفحة المنشورة تستجيب وأنّ فيها آخر الحملات."""
    done = Signal(bool, str)

    def __init__(self, base_url: str, slugs: list[str]):
        super().__init__()
        self.base_url, self.slugs = base_url, slugs

    def run(self):
        status, body = fetch(self.base_url + "apps.js")
        if status != 200:
            self.done.emit(False, f"الصفحة لا تستجيب بعد ({status}). إن كان أوّل نشر ففعّل GitHub Pages"
                                  " (المصدر main ← ‎/docs) من «إعداد الاستضافة»، ثم انتظر دقيقة أو دقيقتين.")
            return
        missing = [s for s in self.slugs if f'"{s}"' not in body]
        if missing:
            self.done.emit(False, "الصفحة تعمل، لكنّ هذه الحملات لم تُرفع بعد: " + "، ".join(missing)
                           + ". التزم وارفع من أداة الالتزام ثم انتظر دقيقة.")
        else:
            self.done.emit(True, "✓ الصفحة منشورة وكل الحملات فيها.")


def fetch(url: str) -> tuple[int | str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ad-studio", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return "بلا اتّصال", ""

# ───────────────────────── إحصاءات الحملات من Play Console ─────────────────────────
# تقرير «أداء صفحة المتجر» الشهري في مخزن تقارير Play (Cloud Storage)، تفصيل «مصدر الزيارة»، وفيه عمود
# «UTM campaign» لكل زيارة جاءت برابط فيه referrer (كرابط صفحتنا). يُحدَّث يوميًّا بتأخير يومين تقريبًا.
STATS_CACHE = ROOT / "stats_cache.json"          # آخر قراءة، تظهر فور فتح الأداة (لا تُرفع)
STATS_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
REPORT_PATH = "stats/store_performance/store_performance_{pkg}_{month}_traffic_source.csv"


def last_months(n: int, today: date | None = None) -> list[str]:
    """['202611', '202610', …] من الشهر الحالي إلى الوراء."""
    d = today or date.today()
    y, m, out = d.year, d.month, []
    for _ in range(max(1, n)):
        out.append(f"{y}{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def normalize_bucket(text: str) -> str:
    """يقبل gs://pubsite_prod_rev_123/ أو الاسم وحده."""
    t = text.strip().removeprefix("gs://").strip("/")
    return t.split("/")[0] if t else ""


def _num(v: str) -> float:
    v = (v or "").strip().replace(",", "").replace("%", "")
    try:
        return float(v)
    except ValueError:
        return 0.0


def parse_store_csv(raw: bytes) -> list[dict]:
    """تقارير Play بترميز UTF-16 غالبًا (وقد تأتي UTF-8). يعيد الصفوف بأسماء أعمدة صغيرة."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def aggregate_campaigns(rows: list[dict]) -> list[dict]:
    """يجمع الزوّار والتنزيلات لكل (مصدر، حملة)، ويرتّبها من الأنجح."""
    agg: dict[tuple[str, str], dict] = {}
    for r in rows:
        camp = r.get("utm campaign", "")
        if not camp:
            continue
        key = (r.get("utm source", "") or "—", camp)
        a = agg.setdefault(key, {"source": key[0], "campaign": camp, "visitors": 0.0, "installs": 0.0,
                                 "first": r.get("date", ""), "last": r.get("date", "")})
        a["visitors"] += _num(r.get("store listing visitors", ""))
        a["installs"] += _num(r.get("store listing acquisitions", ""))
        d = r.get("date", "")
        if d:
            a["first"] = min(a["first"] or d, d)
            a["last"] = max(a["last"] or d, d)
    out = []
    for a in agg.values():
        a["visitors"], a["installs"] = int(a["visitors"]), int(a["installs"])
        a["rate"] = (a["installs"] / a["visitors"] * 100) if a["visitors"] else 0.0
        out.append(a)
    return sorted(out, key=lambda a: (-a["installs"], -a["visitors"]))


def load_stats() -> dict:
    try:
        return json.loads(STATS_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def explain_stats_error(e: Exception) -> str:
    s = str(e)
    if "403" in s:
        return ("رفض Google الوصول إلى التقارير. في Play Console ← المستخدمون والأذونات: أعط حساب الخدمة إذن"
                " «عرض معلومات التطبيق وتنزيل التقارير المجمّعة» على مستوى الحساب كلّه (Global)، ثم انتظر حتى"
                " 24 ساعة ليسري.")
    if "404" in s and "bucket" in s.lower():
        return "لم أجد مخزن التقارير. انسخه من Play Console ← تنزيل التقارير ← «نسخ URI لـ Cloud Storage»."
    if any(w in s.lower() for w in ("timed out", "unable to find the server", "name resolution", "getaddrinfo",
                                     "connection", "ssl")):
        return "لا اتّصال بخوادم Google. تحقّق من الإنترنت أو شغّل VPN ثم أعد المحاولة."
    return f"تعذّرت قراءة التقارير: {s[:300]}"


class StatsWorker(QThread):
    """يقرأ تقرير كل تطبيق لكل شهر ويجمع الحملات. لا يكتب شيئًا في حسابك (صلاحية قراءة فقط)."""
    log = Signal(str, str)
    done = Signal(bool, str, dict)

    def __init__(self, key_path: str, bucket: str, packages: dict[str, str], months: list[str]):
        super().__init__()
        self.key_path, self.bucket, self.packages, self.months = key_path, bucket, packages, months

    def run(self):
        try:
            from google.oauth2 import service_account  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
            from googleapiclient.errors import HttpError  # noqa: PLC0415
        except ImportError:
            self.done.emit(False, "مكتبات Google غير مثبّتة. شغّل «تثبيت_المكتبات.bat» ثم أعد المحاولة.", {})
            return
        try:
            creds = service_account.Credentials.from_service_account_file(self.key_path, scopes=[STATS_SCOPE])
            gcs = build("storage", "v1", credentials=creds, cache_discovery=False)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"تعذّر فتح ملف مفتاح حساب الخدمة: {e}", {})
            return
        result, found_any = {}, False
        for slug, pkg in self.packages.items():
            rows = []
            for month in self.months:
                name = REPORT_PATH.format(pkg=pkg, month=month)
                try:
                    raw = gcs.objects().get_media(bucket=self.bucket, object=name).execute(num_retries=2)
                except HttpError as e:
                    if e.resp.status == 404:
                        self.log.emit(f"{pkg} · {month}: لا تقرير لهذا الشهر بعد", "info")
                        continue
                    self.done.emit(False, explain_stats_error(e), {})
                    return
                except Exception as e:  # noqa: BLE001
                    self.done.emit(False, explain_stats_error(e), {})
                    return
                found_any = True
                rows += parse_store_csv(raw)
            result[slug] = {"package": pkg, "campaigns": aggregate_campaigns(rows)}
            n = sum(c["installs"] for c in result[slug]["campaigns"])
            self.log.emit(f"✓ {pkg}: {len(result[slug]['campaigns'])} حملة، {n} تنزيلًا من الروابط المتتبَّعة", "ok")
        if not found_any:
            self.done.emit(False, "لم أجد أيّ تقرير لهذه التطبيقات في المخزن. تأكّد من رابط المخزن، وأنّ"
                                  " التقارير تظهر في Play Console ← تنزيل التقارير ← الإحصاءات.", {})
            return
        stats = {"fetched": datetime.now().strftime("%Y-%m-%d %H:%M"), "months": self.months, "apps": result}
        self.done.emit(True, "✓ قُرئت الإحصاءات.", stats)


class StatsDialog(QDialog):
    def __init__(self, parent, key_path: str, bucket: str, months: int):
        super().__init__(parent)
        self.setWindowTitle("إعداد إحصاءات Play Console")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        info = QLabel(
            "الأداة تقرأ تقرير «أداء صفحة المتجر» الشهري من مخزن تقارير Play، وفيه الزوّار والتنزيلات لكل"
            " حملة جاءت من رابط الإعلان. <b>قراءة فقط</b>، لا يتغيّر شيء في حسابك.<br><br>"
            f"<b style='color:{C_OK}'>أوّلًا:</b> اختر ملف مفتاح حساب الخدمة (JSON)، وهو نفسه الذي تستعمله أداة"
            " النشر ve_up.<br><br>"
            f"<b style='color:{C_OK}'>ثانيًا:</b> في Play Console ← <b>تنزيل التقارير ← الإحصاءات</b> اضغط"
            " «نسخ URI لـ Cloud Storage» والصقه هنا.<br><br>"
            f"<b style='color:{C_OK}'>ثالثًا (مرّة واحدة):</b> في <b>المستخدمون والأذونات</b> تأكّد أنّ لحساب"
            " الخدمة إذن «عرض معلومات التطبيق وتنزيل التقارير المجمّعة» على مستوى الحساب كلّه.")
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        lay.addWidget(info)
        form = QFormLayout()
        krow = QHBoxLayout()
        self.key = ltr(QLineEdit(key_path))
        self.key.setPlaceholderText("…\\service-account.json")
        self.key.setToolTip("يُحفظ مساره في settings.json على جهازك فقط، ولا يُرفع إلى GitHub")
        krow.addWidget(self.key, 1)
        krow.addWidget(make_btn("اختيار…", "اختر ملف مفتاح حساب الخدمة", self._pick_key))
        form.addRow("مفتاح حساب الخدمة:", krow)
        brow = QHBoxLayout()
        self.bucket = ltr(QLineEdit(bucket))
        self.bucket.setPlaceholderText("gs://pubsite_prod_rev_0123456789/")
        brow.addWidget(self.bucket, 1)
        brow.addWidget(make_btn("فتح Play Console", "افتح «تنزيل التقارير» وانسخ رابط المخزن",
                                lambda: QDesktopServices.openUrl(QUrl("https://play.google.com/console/developers"))))
        form.addRow("مخزن التقارير:", brow)
        self.months = QSpinBox()
        self.months.setRange(1, 12)
        self.months.setValue(months)
        self.months.setSuffix(" أشهر")
        self.months.setToolTip("كم شهرًا إلى الوراء تُقرأ (الشهر الحالي منها)")
        form.addRow("المدّة:", self.months)
        lay.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("حفظ")
        box.button(QDialogButtonBox.Cancel).setText("إلغاء")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _pick_key(self):
        start = str(Path(self.key.text()).parent) if self.key.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "ملف مفتاح حساب الخدمة", start, "JSON (*.json)")
        if path:
            self.key.setText(path)


# ───────────────────────── الواجهة ─────────────────────────
def flash(btn: QPushButton, text: str = "✓ نُسخ", ms: int = 1400):
    """تأكيد ظاهر على الزرّ نفسه ثم يعود نصّه."""
    old = btn.property("orig_text") or btn.text()
    btn.setProperty("orig_text", old)
    btn.setText(text)
    QTimer.singleShot(ms, lambda: btn.setText(old))


def make_btn(text: str, tip: str, slot, obj: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    if obj:
        b.setObjectName(obj)
    b.clicked.connect(slot)
    return b


def open_commit_tool():
    """يفتح «أداة الالتزام» على هذا المشروع (المشغّل نفسه الذي في كل مشاريعك)."""
    if not COMMIT_BAT.exists():
        QMessageBox.warning(None, "أداة الالتزام", "لم أجد «التزام.bat» في مجلّد المشروع.")
        return False
    os.startfile(str(COMMIT_BAT))
    return True


def ltr(w):
    w.setLayoutDirection(Qt.LeftToRight)
    return w


class HostingDialog(QDialog):
    def __init__(self, parent, repo_url: str, base_url: str, pixel_id: str = "", contact: str = ""):
        super().__init__(parent)
        self.setWindowTitle("إعداد الاستضافة المجانية")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        steps = QLabel(
            f"<b>مرّة واحدة فقط:</b><br><br>"
            f"<b style='color:{C_OK}'>أوّلًا:</b> اضغط «فتح أداة الالتزام»، ثم فيها «أنشئ مستودعًا على GitHub»"
            " واجعله <b>عامًّا</b> (Pages مجاني للمستودعات العامّة). الاسم القصير أجمل في الرابط، مثل get.<br><br>"
            f"<b style='color:{C_OK}'>ثانيًا:</b> عد إلى هنا واضغط «قراءة المستودع»، فيُملأ الرابطان وحدهما.<br><br>"
            f"<b style='color:{C_OK}'>ثالثًا:</b> اضغط «تفعيل GitHub Pages»، واختر في Branch الفرع <b>main</b>"
            " والمجلّد <b>docs</b>، ثم Save.<br><br>"
            "بعدها كل تعديل يُنشر بـ«التزم وارفع» في أداة الالتزام، والرابط لا يتغيّر.")
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.RichText)
        lay.addWidget(steps)
        form = QFormLayout()
        self.repo = ltr(QLineEdit(repo_url))
        self.repo.setPlaceholderText("https://github.com/USER/get")
        self.base = ltr(QLineEdit(base_url))
        self.base.setPlaceholderText("يُملأ وحده من رابط المستودع")
        self.base.setToolTip("عنوان الصفحة المنشورة. غيّره فقط إن ربطت دومينًا خاصًّا بالمستودع.")
        self.repo.textChanged.connect(self._auto_base)
        form.addRow("رابط المستودع:", self.repo)
        form.addRow("عنوان الصفحة:", self.base)
        self.pixel = ltr(QLineEdit(pixel_id))
        self.pixel.setPlaceholderText("اختياري: 15 رقمًا تقريبًا")
        self.pixel.setToolTip("معرّف Meta Pixel من مدير الأحداث. يعرّف فيسبوك بمن فتح الصفحة ومن ضغط «حمّل»،"
                              " فيحسّن الاستهداف ويخفض التكلفة. اتركه فارغًا لإيقافه")
        prow = QHBoxLayout()
        prow.addWidget(self.pixel, 1)
        prow.addWidget(make_btn("فتح مدير الأحداث", "تنشئ فيه Pixel (مجّانًا) وتنسخ معرّفه",
                                lambda: QDesktopServices.openUrl(QUrl("https://business.facebook.com/events_manager2"))))
        form.addRow("بكسل ميتا:", prow)
        phint = QLabel("الصفحة ترسل «PageView» عند الفتح و«Lead» عند الذهاب إلى المتجر. اختر «Lead» حدثًا"
                       " للتحسين في الحملة حين تجمع بيانات كافية.")
        phint.setObjectName("hint")
        phint.setWordWrap(True)
        form.addRow("", phint)
        self.contact = ltr(QLineEdit(contact))
        self.contact.setPlaceholderText("support@example.com")
        self.contact.setToolTip("بريد يظهر في صفحة سياسة الخصوصية للتواصل. يُنشر للعموم، فاستعمل بريد الدعم لا الشخصي")
        form.addRow("بريد التواصل:", self.contact)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(make_btn("فتح أداة الالتزام", "تنشئ منها المستودع على GitHub وتلتزم وترفع", open_commit_tool))
        self.btn_read = make_btn("قراءة المستودع", "يقرأ رابط مستودع هذا المشروع من git", self._read_remote)
        row.addWidget(self.btn_read)
        row.addWidget(make_btn("تفعيل GitHub Pages", "يفتح إعدادات Pages للمستودع (بعد أوّل رفع)", self._open_pages))
        row.addStretch()
        lay.addLayout(row)
        sec = QLabel(f"<b style='color:{C_WARN}'>حماية الرابط:</b> لا يعدّل المستودع العامّ أحد غيرك، والخطر الوحيد"
                     " سرقة حساب GitHub. فعّل «التحقّق بخطوتين» مرّة واحدة: Enable two-factor authentication"
                     " ← تطبيق مصادقة على هاتفك ← احفظ رموز الاسترداد في مكان آمن.")
        sec.setWordWrap(True)
        sec.setTextFormat(Qt.RichText)
        lay.addWidget(sec)
        srow = QHBoxLayout()
        srow.addWidget(make_btn("حماية حساب GitHub", "يفتح صفحة أمان الحساب لتفعيل التحقّق بخطوتين",
                                lambda: QDesktopServices.openUrl(QUrl("https://github.com/settings/security"))))
        srow.addStretch()
        lay.addLayout(srow)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("حفظ")
        box.button(QDialogButtonBox.Cancel).setText("إلغاء")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _auto_base(self, text):
        url = repo_to_pages(text)
        if url:
            self.base.setText(url)

    def _read_remote(self):
        url = git_remote()
        if url:
            self.repo.setText(url)
            flash(self.btn_read, "✓ قُرئ")
        else:
            QMessageBox.information(self, "المستودع", "لا مستودع على GitHub لهذا المشروع بعد.\n"
                                    "افتح أداة الالتزام وأنشئه منها، ثم أعد المحاولة.")

    def _open_pages(self):
        repo = self.repo.text().strip().rstrip("/").removesuffix(".git")
        if not repo_to_pages(repo):
            QMessageBox.information(self, "رابط المستودع", "الصق رابط المستودع أوّلًا.")
            return
        QDesktopServices.openUrl(QUrl(repo + "/settings/pages"))


class CountedField(QWidget):
    """حقل نصّ إعلان مع عدّاد للحدّ الظاهر وزرّ نسخ."""
    changed = Signal()

    def __init__(self, limit: int, multiline: bool, tip: str):
        super().__init__()
        self.limit = limit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QPlainTextEdit() if multiline else QLineEdit()
        if multiline:
            self.edit.setFixedHeight(96)
        self.edit.setToolTip(tip)
        (self.edit.textChanged).connect(self._update)
        side = QVBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("hint")
        self.count.setToolTip(f"يظهر أوّل {limit} حرفًا كاملة، وما بعدها خلف «عرض المزيد».")
        self.copy = make_btn("نسخ", "ينسخ هذا النصّ لتلصقه في مدير إعلانات ميتا", self._copy)
        side.addWidget(self.copy)
        side.addWidget(self.count)
        side.addStretch()
        lay.addWidget(self.edit, 1)
        lay.addLayout(side)
        self._update()

    def text(self) -> str:
        return self.edit.toPlainText() if isinstance(self.edit, QPlainTextEdit) else self.edit.text()

    def setText(self, t: str):
        self.edit.blockSignals(True)
        (self.edit.setPlainText if isinstance(self.edit, QPlainTextEdit) else self.edit.setText)(t)
        self.edit.blockSignals(False)
        self._update(emit=False)

    def _update(self, emit=True):
        n = len(self.text())
        color = C_WARN if n > self.limit else C_MUTED
        self.count.setText(f"<span style='color:{color}'>{n}/{self.limit}</span>")
        if emit:
            self.changed.emit()

    def _copy(self):
        if not self.text().strip():
            flash(self.copy, "فارغ")
            return
        QGuiApplication.clipboard().setText(self.text())
        flash(self.copy)


class ImagePicker(QWidget):
    picked = Signal(str)

    def __init__(self, title: str, tip: str, size: tuple[int, int]):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel("لا صورة")
        self.preview.setFixedSize(*size)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(f"border:1px dashed {C_EDGE}; border-radius:8px; color:{C_MUTED};")
        col = QVBoxLayout()
        self.btn = make_btn(title, tip, self._choose)
        self.info = QLabel()
        self.info.setObjectName("hint")
        self.info.setAlignment(Qt.AlignLeading)
        col.addWidget(self.btn, 0, Qt.AlignLeading)
        col.addWidget(self.info)
        col.addStretch()
        lay.addWidget(self.preview)
        lay.addLayout(col, 1)

    def _choose(self):
        start = load_settings().get("last_image_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "اختر صورة", start, "صور (*.png *.jpg *.jpeg *.webp)")
        if path:
            s = load_settings()
            s["last_image_dir"] = str(Path(path).parent)
            save_settings(s)
            self.picked.emit(path)

    def show_image(self, rel: str):
        pm = QPixmap(str(SITE / rel)) if rel else QPixmap()
        if pm.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("لا صورة")
            self.info.setText("")
            return
        self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.info.setText(f"{pm.width()}×{pm.height()}")


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("استوديو إعلانات فيسبوك ← Google Play")
        self.data = load_data()
        self.settings = load_settings()
        self.current: str | None = None
        self.worker: CheckWorker | None = None
        self.stats = load_stats()
        self.stats_worker: StatsWorker | None = None
        self._loading = False
        self.save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save_now)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # الشريط العلوي
        top = QHBoxLayout()
        self.btn_publish = make_btn("نشر على الإنترنت", "يحفظ ويفتح أداة الالتزام لتلتزم وترفع إلى GitHub Pages",
                                    self.publish, "primary")
        self.btn_check = make_btn("تحقّق من النشر", "يتأكّد أنّ الصفحة المنشورة تعمل وفيها كل الحملات",
                                  self.check_online)
        top.addWidget(self.btn_publish)
        top.addWidget(self.btn_check)
        top.addWidget(make_btn("إعداد الاستضافة", "ربط الأداة بمستودع GitHub مرّة واحدة", self.hosting))
        top.addWidget(make_btn("فتح مجلّد الموقع", "يفتح مجلّد docs الذي يُنشر", lambda: os.startfile(SITE)))
        self.host_lbl = QLabel()
        self.host_lbl.setObjectName("hint")
        top.addWidget(self.host_lbl, 1)
        # حالة الحفظ والنشر: الحفظ تلقائي، والنشر بأداة الالتزام
        self.state_lbl = QLabel()
        self.state_lbl.setToolTip("كل تعديل يُحفظ وحده بعد لحظة. «لم يُنشر» يعني أنّ الناس يرون النسخة القديمة"
                                  " حتى تلتزم وترفع من «نشر على الإنترنت»")
        top.addWidget(self.state_lbl)
        root.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # قائمة الحملات
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("التطبيقات")
        lbl.setStyleSheet(f"color:{C_OK}; font-weight:bold;")
        sl.addWidget(lbl)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        sl.addWidget(self.list, 1)
        g = QGridLayout()
        g.addWidget(make_btn("تطبيق جديد", "يضيف حملة لتطبيق آخر", self.add_app, "primary"), 0, 0, 1, 2)
        g.addWidget(make_btn("نسخ", "ينشئ حملة جديدة نسخةً من المحدَّدة", self.dup_app), 1, 0)
        g.addWidget(make_btn("حذف", "يحذف الحملة المحدَّدة من الصفحة", self.del_app, "danger"), 1, 1)
        sl.addLayout(g)
        split.addWidget(side)

        # النموذج داخل منطقة تمرير
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        self.form_lay = QVBoxLayout(form_host)
        scroll.setWidget(form_host)
        split.addWidget(scroll)
        split.setSizes([240, 900])
        self._build_form()

        # السجلّ
        self.log = QTextEdit(readOnly=True)
        self.log.setFixedHeight(110)
        root.addWidget(self.log)
        self.statusBar().showMessage("جاهز")

        self.setStyleSheet(STYLE + FEEDBACK_CSS)
        self._refresh_list(select=self.settings.get("last_app"))
        self._refresh_host()
        self._show_state()
        # بعد الالتزام والرفع في أداة الالتزام تتحدّث الحالة وحدها حين تعود إلى النافذة
        self.state_timer = QTimer(self, interval=4000, timeout=self._poll_state)
        self.state_timer.start()
        geo = self.settings.get("geometry")
        if geo:
            self.resize(*geo)
        else:
            self.resize(1180, 820)

    # ── بناء النموذج ──
    def _build_form(self):
        L = self.form_lay
        # الرابط أوّلًا: هو ما يحتاجه المستخدم في فيسبوك
        box = QGroupBox("رابط الإعلان (ضعه في خانة «رابط الموقع» في فيسبوك)")
        bl = QVBoxLayout(box)
        self.link_lbl = ltr(QLabel())
        self.link_lbl.setObjectName("link")
        self.link_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link_lbl.setWordWrap(True)
        bl.addWidget(self.link_lbl)
        row = QHBoxLayout()
        self.btn_copy_link = make_btn("نسخ الرابط", "ينسخ رابط الإعلان", self.copy_link, "primary")
        row.addWidget(self.btn_copy_link)
        row.addWidget(make_btn("معاينة على الجهاز", "يفتح الصفحة في المتصفّح من الملفّات المحلّية (قبل النشر)",
                               self.preview_local))
        self.btn_online = make_btn("فتح الرابط المنشور", "يفتح الرابط الحقيقي كما سيراه الناس", self.open_online)
        row.addWidget(self.btn_online)
        self.btn_pixel = make_btn("اختبار البكسل", "ينسخ رابط اختبار ويفتح «اختبار الأحداث» في مدير أحداث ميتا،"
                                  " لترى PageView وLead يصلان", self.test_pixel)
        row.addWidget(self.btn_pixel)
        self.btn_copy_all = make_btn("نسخ الإعلان كاملًا", "ينسخ كل نصوص الإعلان والرابط دفعة واحدة",
                                     self.copy_all)
        row.addWidget(self.btn_copy_all)
        row.addStretch()
        bl.addLayout(row)
        L.addWidget(box)

        # بيانات التطبيق
        box = QGroupBox("بيانات التطبيق (تظهر في الصفحة الوسيطة)")
        f = QFormLayout(box)
        self.f_name = QLineEdit()
        self.f_store = ltr(QLineEdit())
        self.f_store.setPlaceholderText("https://play.google.com/store/apps/details?id=…  أو اسم الحزمة")
        self.f_store.setToolTip("الصق رابط التطبيق من Google Play، وتستخرج الأداة اسم الحزمة وحدها")
        self.pkg_lbl = QLabel()
        self.pkg_lbl.setObjectName("hint")
        self.f_slug = ltr(QLineEdit())
        self.f_slug.setToolTip("كلمة قصيرة بحروف إنجليزية صغيرة تظهر في الرابط: ?app=mohaffez")
        self.f_tagline = QLineEdit()
        self.f_tagline.setPlaceholderText("جملة واحدة تحت الاسم")
        self.f_features = QPlainTextEdit()
        self.f_features.setFixedHeight(120)
        self.f_features.setPlaceholderText("ميزة في كل سطر")
        stats = QHBoxLayout()
        self.f_rating = ltr(QLineEdit())
        self.f_rating.setPlaceholderText("4.8")
        self.f_rating.setToolTip("اتركه فارغًا إن لم يكن لك تقييم حقيقي: ميتا ترفض الادّعاءات غير الصحيحة")
        self.f_downloads = QLineEdit()
        self.f_downloads.setPlaceholderText("100 ألف")
        self.f_downloads.setToolTip("يظهر: «أكثر من … تنزيل». اتركه فارغًا إن لم تعرف الرقم الحقيقي")
        stats.addWidget(QLabel("التقييم:"))
        stats.addWidget(self.f_rating)
        stats.addWidget(QLabel("التنزيلات:"))
        stats.addWidget(self.f_downloads, 1)
        look = QHBoxLayout()
        self.btn_color = make_btn("", "لون الزرّ والأيقونة الاحتياطية في الصفحة", self.pick_color)
        self.btn_color.setFixedWidth(120)
        self.f_redirect = QSpinBox()
        self.f_redirect.setRange(0, 10)
        self.f_redirect.setSuffix(" ث")
        self.f_redirect.setToolTip("ثوانٍ قبل فتح المتجر تلقائيًّا على أندرويد. 0 = لا تحويل، الزرّ فقط")
        look.addWidget(QLabel("اللون:"))
        look.addWidget(self.btn_color)
        look.addSpacing(20)
        look.addWidget(QLabel("التحويل التلقائي بعد:"))
        look.addWidget(self.f_redirect)
        look.addStretch()
        f.addRow("اسم التطبيق:", self.f_name)
        f.addRow("رابط المتجر:", self.f_store)
        f.addRow("", self.pkg_lbl)
        f.addRow("مفتاح الرابط:", self.f_slug)
        f.addRow("وصف قصير:", self.f_tagline)
        f.addRow("المزايا:", self.f_features)
        f.addRow("", stats)
        f.addRow("", look)
        L.addWidget(box)

        # الصور
        box = QGroupBox("الصور")
        f = QFormLayout(box)
        self.icon_pick = ImagePicker("اختيار الأيقونة", "أيقونة التطبيق (512×512 مثلًا)، تُصغَّر وحدها", (96, 96))
        self.hero_pick = ImagePicker("اختيار صورة الإعلان",
                                     "الصورة نفسها التي ترفعها في إعلان فيسبوك، فتظهر في الصفحة أيضًا "
                                     "(تطابق الإعلان والصفحة يرفع القبول)", (220, 184))
        self.icon_pick.picked.connect(lambda p: self._image_picked(p, "icon"))
        self.hero_pick.picked.connect(lambda p: self._image_picked(p, "hero"))
        f.addRow("الأيقونة:", self.icon_pick)
        f.addRow("صورة الإعلان:", self.hero_pick)
        self.btn_sizes = make_btn("تجهيز مقاسات فيسبوك", "يصنع من صورة الإعلان 4 مقاسات (مربّع، طولي، قصص، عرضي)"
                                  " دون قصّ شيء منها، ويفتح مجلّدها لترفعها في مدير الإعلانات", self.make_sizes)
        srow = QHBoxLayout()
        srow.addWidget(self.btn_sizes)
        # ⁦…⁩ يعزل الأرقام باتّجاه يسار←يمين فلا ينقلب «1080×1350»
        shint = QLabel(" · ".join(f"{lbl} ⁦{w}×{h}⁩"
                                  for lbl, (_, w, h, _d) in zip(("مربّع", "طولي", "قصص", "عرضي"), AD_SIZES)))
        shint.setObjectName("hint")
        srow.addWidget(shint, 1)
        f.addRow("", srow)
        L.addWidget(box)

        # نصوص الإعلان
        box = QGroupBox("نصوص إعلان فيسبوك (للنسخ إلى مدير الإعلانات)")
        f = QFormLayout(box)
        self.ad_primary = CountedField(LIMITS["primary"], True, "النصّ الأساسي فوق الصورة")
        self.ad_headline = CountedField(LIMITS["headline"], False, "العنوان العريض تحت الصورة")
        self.ad_desc = CountedField(LIMITS["description"], False, "سطر صغير تحت العنوان (قد لا يظهر في كل المواضع)")
        self.ad_cta = QComboBox()
        self.ad_cta.addItems(CTA_OPTIONS)
        self.ad_cta.setToolTip("الزرّ الذي تختاره في إعدادات الإعلان")
        self.ad_camp = ltr(QLineEdit())
        self.ad_camp.setToolTip("اسم قصير بالإنجليزية للحملة، يظهر في Play Console فتعرف أيّ إعلان جلب التنزيلات")
        f.addRow("النصّ الأساسي:", self.ad_primary)
        f.addRow("العنوان:", self.ad_headline)
        f.addRow("الوصف:", self.ad_desc)
        f.addRow("زرّ الإعلان:", self.ad_cta)
        f.addRow("اسم الحملة:", self.ad_camp)
        tip = QLabel("في مدير الإعلانات: الهدف «الزيارات Traffic»، والوجهة «موقع ويب»، والصق الرابط أعلاه.")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        f.addRow("", tip)
        L.addWidget(box)

        # إحصاءات الحملات
        box = QGroupBox("نتائج الحملات (من Play Console)")
        bl = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_stats = make_btn("تحديث الإحصاءات", "يقرأ من Play Console زوّار صفحة المتجر وتنزيلاتها لكل حملة،"
                                  " لكل التطبيقات", self.fetch_stats, "primary")
        row.addWidget(self.btn_stats)
        row.addWidget(make_btn("إعداد الإحصاءات", "مفتاح حساب الخدمة ومخزن التقارير والمدّة", self.stats_setup))
        self.stats_lbl = QLabel()
        self.stats_lbl.setObjectName("hint")
        self.stats_lbl.setWordWrap(True)
        row.addWidget(self.stats_lbl, 1)
        bl.addLayout(row)
        self.stats_table = QTableWidget(0, 5)
        self.stats_table.setHorizontalHeaderLabels(["الحملة", "المصدر", "زوّار صفحة المتجر", "التنزيلات", "نسبة التحويل"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            self.stats_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.stats_table.setMinimumHeight(150)
        self.stats_table.setToolTip("الأنجح أوّلًا. «الزوّار» من فتح صفحة التطبيق في المتجر عبر الرابط، و«التنزيلات»"
                                    " من ثبّته منهم")
        bl.addWidget(self.stats_table)
        shint = QLabel("تظهر هنا الحملات التي جاءت من رابط الإعلان وحدها (فيه utm_campaign). التقرير يتأخّر يومين"
                       " تقريبًا، وGoogle تُخفي الأعداد الصغيرة جدًّا أحيانًا.")
        shint.setObjectName("hint")
        shint.setWordWrap(True)
        bl.addWidget(shint)
        L.addWidget(box)
        L.addStretch()

        for w in (self.f_name, self.f_tagline, self.f_rating, self.f_downloads, self.ad_camp):
            w.textChanged.connect(self._changed)
        self.f_store.textChanged.connect(self._changed)
        self.f_slug.editingFinished.connect(self._rename_slug)
        self.f_features.textChanged.connect(self._changed)
        self.f_redirect.valueChanged.connect(self._changed)
        self.ad_cta.currentIndexChanged.connect(self._changed)
        for w in (self.ad_primary, self.ad_headline, self.ad_desc):
            w.changed.connect(self._changed)

    # ── الإحصاءات ──
    def _app_stats(self, slug: str) -> list[dict] | None:
        """حملات التطبيق من آخر قراءة، بمطابقة اسم الحزمة (فيصمد تغيير مفتاح الرابط)."""
        pkg = parse_package(self.data["apps"].get(slug, {}).get("package", ""))
        for s in self.stats.get("apps", {}).values():
            if pkg and s.get("package") == pkg:
                return s.get("campaigns", [])
        return None

    def _list_text(self, slug: str) -> str:
        name = self.data["apps"][slug].get("name") or slug
        camps = self._app_stats(slug)
        if not camps:
            return name
        return f"{name}\n⬇ {sum(c['installs'] for c in camps)} تنزيلًا · {len(camps)} حملة"

    def _show_stats(self):
        t = self.stats_table
        t.setRowCount(0)
        camps = self._app_stats(self.current) if self.current else None
        if not self.stats:
            self.stats_lbl.setText("لم تُقرأ الإحصاءات بعد. اضغط «إعداد الإحصاءات» مرّة واحدة، ثم «تحديث الإحصاءات».")
            return
        when = "⁦" + self.stats.get("fetched", "") + "⁩"
        months = self.stats.get("months", [])
        span = f"{months[-1][:4]}/{months[-1][4:]} – {months[0][:4]}/{months[0][4:]}" if months else ""
        if camps is None:
            self.stats_lbl.setText(f"آخر قراءة {when}: لا بيانات لهذا التطبيق (اضغط «تحديث الإحصاءات»).")
            return
        if not camps:
            self.stats_lbl.setText(f"آخر قراءة {when} (⁦{span}⁩): لا زيارات من روابط الإعلان بعد.")
            return
        self.stats_lbl.setText(f"آخر قراءة {when} · الأشهر ⁦{span}⁩ · الأنجح أوّلًا")
        best = camps[0]["installs"]
        for c in camps:
            r = t.rowCount()
            t.insertRow(r)
            vals = [c["campaign"], c["source"], f"{c['visitors']:,}", f"{c['installs']:,}", f"{c['rate']:.1f}%"]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setToolTip(f"من {c.get('first', '')} إلى {c.get('last', '')}")
                if r == 0 and best > 0:
                    item.setForeground(QColor(C_OK))
                t.setItem(r, col, item)
        if best > 0:
            t.item(0, 0).setText("★ " + camps[0]["campaign"])

    def stats_setup(self) -> bool:
        s = load_settings()
        d = StatsDialog(self, s.get("stats_key", ""), s.get("stats_bucket", ""), int(s.get("stats_months", 3)))
        d.setStyleSheet(STYLE + FEEDBACK_CSS)
        if d.exec() != QDialog.Accepted:
            return False
        s = load_settings()      # الإعدادات المحلّية وحدها (مسار المفتاح لا يُرفع إلى GitHub)
        s["stats_key"] = d.key.text().strip()
        s["stats_bucket"] = normalize_bucket(d.bucket.text())
        s["stats_months"] = d.months.value()
        save_settings(s)
        self.logmsg("✓ حُفظ إعداد الإحصاءات.", "ok")
        return True

    def fetch_stats(self):
        s = load_settings()
        key, bucket = s.get("stats_key", ""), s.get("stats_bucket", "")
        if not key or not Path(key).is_file() or not bucket:
            if not self.stats_setup():
                return
            s = load_settings()
            key, bucket = s.get("stats_key", ""), s.get("stats_bucket", "")
            if not key or not Path(key).is_file() or not bucket:
                QMessageBox.information(self, "الإحصاءات", "يلزم ملف المفتاح ورابط المخزن معًا.")
                return
        packages = {slug: parse_package(a.get("package", "")) for slug, a in self.data["apps"].items()}
        packages = {k: v for k, v in packages.items() if v}
        if not packages:
            QMessageBox.information(self, "الإحصاءات", "لا تطبيق برابط متجر صحيح.")
            return
        self.btn_stats.setEnabled(False)
        self.btn_stats.setText("جارٍ القراءة…")
        self.logmsg("أقرأ تقارير Play Console…", "info")
        self.stats_worker = StatsWorker(key, bucket, packages, last_months(int(s.get("stats_months", 3))))
        self.stats_worker.log.connect(self.logmsg)
        self.stats_worker.done.connect(self._stats_done)
        self.stats_worker.start()

    def _stats_done(self, ok: bool, msg: str, stats: dict):
        self.btn_stats.setEnabled(True)
        self.btn_stats.setText("تحديث الإحصاءات")
        if not ok:
            self.logmsg(msg, "err")
            flash(self.btn_stats, "✗ لم تُقرأ", 2500)
            QMessageBox.warning(self, "الإحصاءات", msg)
            return
        self.stats = stats
        try:
            STATS_CACHE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        flash(self.btn_stats, "✓ حُدّثت", 2500)
        self.logmsg(msg, "ok")
        self._refresh_list(select=self.current)

    # ── القائمة ──
    def _refresh_list(self, select: str | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        for slug, a in self.data["apps"].items():
            it = QListWidgetItem(self._list_text(slug))
            it.setData(Qt.UserRole, slug)
            it.setToolTip(f"?app={slug} · الرقم: تنزيلات الحملات المتتبَّعة في آخر قراءة للإحصاءات")
            self.list.addItem(it)
        self.list.blockSignals(False)
        slugs = list(self.data["apps"])
        if not slugs:
            self.current = None
            self._set_form_enabled(False)
            return
        idx = slugs.index(select) if select in slugs else 0
        self.list.setCurrentRow(idx)
        self._select(self.list.currentItem(), None)

    def _set_form_enabled(self, on: bool):
        self.form_lay.parentWidget().setEnabled(on)

    def _select(self, item, _prev):
        if item is None:
            return
        self.current = item.data(Qt.UserRole)
        self._set_form_enabled(True)
        self._load_form()

    def _app(self) -> dict:
        return self.data["apps"][self.current]

    def _load_form(self):
        self._loading = True
        a = self._app()
        ad = a.setdefault("ad", new_app()["ad"])
        self.f_name.setText(a.get("name", ""))
        self.f_store.setText(a.get("package", ""))
        self.f_slug.setText(self.current)
        self.f_tagline.setText(a.get("tagline", ""))
        self.f_features.setPlainText("\n".join(a.get("features", [])))
        self.f_rating.setText(a.get("rating", ""))
        self.f_downloads.setText(a.get("downloads", ""))
        self.f_redirect.setValue(int(a.get("redirect", 2)))
        self._paint_color(a.get("color", "#2f9e6f"))
        self.icon_pick.show_image(a.get("icon", ""))
        self.hero_pick.show_image(a.get("hero", ""))
        self.ad_primary.setText(ad.get("primary", ""))
        self.ad_headline.setText(ad.get("headline", ""))
        self.ad_desc.setText(ad.get("description", ""))
        i = self.ad_cta.findText(ad.get("cta", ""))
        self.ad_cta.setCurrentIndex(max(i, 0))
        self.ad_camp.setText(ad.get("campaign", ""))
        self._loading = False
        self._update_pkg_hint()
        self._update_link()
        self._show_stats()

    def _changed(self, *_):
        if self._loading or self.current is None:
            return
        a = self._app()
        a["name"] = self.f_name.text().strip()
        a["package"] = parse_package(self.f_store.text()) or self.f_store.text().strip()
        a["tagline"] = self.f_tagline.text().strip()
        a["features"] = [x.strip() for x in self.f_features.toPlainText().splitlines() if x.strip()]
        a["rating"] = self.f_rating.text().strip()
        a["downloads"] = self.f_downloads.text().strip()
        a["redirect"] = self.f_redirect.value()
        a["ad"] = {"primary": self.ad_primary.text(), "headline": self.ad_headline.text(),
                   "description": self.ad_desc.text(), "cta": self.ad_cta.currentText(),
                   "campaign": self.ad_camp.text().strip()}
        it = self.list.currentItem()
        if it:
            it.setText(self._list_text(self.current))
        self._update_pkg_hint()
        self._update_link()
        self._show_state(saving=True)
        self.save_timer.start()

    def _save_now(self):
        try:
            save_data(self.data)
        except OSError as e:
            self.logmsg(f"تعذّر الحفظ: {e}", "err")
            self.state_lbl.setText(f"<span style='color:{C_ERR}'>✗ لم يُحفظ</span>")
            return
        self._show_state()

    def _show_state(self, saving: bool = False):
        if saving:
            self.state_lbl.setText(f"<span style='color:{C_MUTED}'>… يُحفظ</span>")
            return
        pub = publish_state()
        text = {"published": f"<span style='color:{C_OK}'>✓ محفوظ · منشور</span>",
                "pending": f"<span style='color:{C_WARN}'>✓ محفوظ · لم يُنشر بعد</span>",
                "norepo": f"<span style='color:{C_WARN}'>✓ محفوظ · لا مستودع بعد</span>"}[pub]
        self.state_lbl.setText(text)

    def _update_pkg_hint(self):
        raw = self.f_store.text().strip()
        pkg = parse_package(raw)
        if not raw:
            self.pkg_lbl.setText("<span style='color:%s'>الصق رابط التطبيق من Google Play</span>" % C_WARN)
        elif pkg:
            self.pkg_lbl.setText(f"<span style='color:{C_OK}'>✓ اسم الحزمة: {pkg}</span>")
        else:
            self.pkg_lbl.setText(f"<span style='color:{C_ERR}'>لم أتعرّف على اسم الحزمة في هذا الرابط</span>")

    def _update_link(self):
        if self.current is None:
            return
        self.link_lbl.setText(build_link(self.data["base_url"], self.current, self.ad_camp.text()))
        self.btn_online.setEnabled(bool(self.data["base_url"]))
        self.btn_pixel.setEnabled(bool(self.data["base_url"] and self.data["pixel_id"]))
        self.btn_pixel.setToolTip("ينسخ رابط اختبار ويفتح «اختبار الأحداث» في مدير أحداث ميتا" if
                                  self.btn_pixel.isEnabled() else "يحتاج عنوان الصفحة ومعرّف البكسل في «إعداد الاستضافة»")

    def _rename_slug(self):
        if self._loading or self.current is None:
            return
        new = self.f_slug.text().strip().lower()
        if new == self.current:
            return
        if not SLUG_RE.match(new):
            QMessageBox.warning(self, "مفتاح الرابط", "المفتاح حروف إنجليزية صغيرة وأرقام وشرطة فقط، مثل: mohaffez")
            self.f_slug.setText(self.current)
            return
        if new in self.data["apps"]:
            QMessageBox.warning(self, "مفتاح الرابط", "هذا المفتاح مستعمل لتطبيق آخر.")
            self.f_slug.setText(self.current)
            return
        if QMessageBox.question(self, "تغيير الرابط",
                                "تغيير المفتاح يغيّر رابط الإعلان، والإعلانات القديمة ستفتح التطبيق الافتراضي.\nأتابع؟"
                                ) != QMessageBox.Yes:
            self.f_slug.setText(self.current)
            return
        self.data["apps"] = {(new if k == self.current else k): v for k, v in self.data["apps"].items()}
        self.current = new
        save_data(self.data)
        self._refresh_list(select=new)
        self.logmsg(f"صار مفتاح الرابط: {new}", "ok")

    # ── أفعال ──
    def add_app(self, template: dict | None = None):
        base, n = "app", 1
        while f"{base}{n}" in self.data["apps"]:
            n += 1
        slug = f"{base}{n}"
        self.data["apps"][slug] = template or new_app()
        save_data(self.data)
        self._refresh_list(select=slug)
        self.f_name.setFocus()
        self.f_name.selectAll()
        self.logmsg(f"أُضيف تطبيق جديد ({slug}). غيّر اسمه ومفتاح رابطه.", "ok")

    def dup_app(self):
        if self.current is None:
            return
        copy = json.loads(json.dumps(self._app()))
        copy["name"] = copy.get("name", "") + " (نسخة)"
        self.add_app(copy)

    def del_app(self):
        if self.current is None:
            return
        name = self._app().get("name") or self.current
        if QMessageBox.question(self, "حذف", f"أأحذف «{name}»؟\nرابط إعلانه سيفتح التطبيق الافتراضي بعد النشر."
                                ) != QMessageBox.Yes:
            return
        del self.data["apps"][self.current]
        save_data(self.data)
        self._refresh_list()
        self.logmsg(f"حُذف «{name}».", "warn")

    def _image_picked(self, path: str, kind: str):
        try:
            rel = import_image(path, self.current, kind)
        except ValueError as e:
            QMessageBox.warning(self, "الصورة", str(e))
            return
        self._app()[kind] = rel
        (self.icon_pick if kind == "icon" else self.hero_pick).show_image(rel)
        if kind == "hero":
            # الأصل بدقّته الكاملة يُحفظ لتجهيز مقاسات فيسبوك منه (الصفحة تأخذ نسخة مصغّرة)
            out = AD_OUT / self.current
            out.mkdir(parents=True, exist_ok=True)
            for old in out.glob("original.*"):
                old.unlink()
            (out / ("original" + Path(path).suffix.lower())).write_bytes(Path(path).read_bytes())
        save_data(self.data)
        self.logmsg(f"✓ نُسخت الصورة إلى docs/{rel}", "ok")

    def _hero_source(self) -> Path:
        orig = sorted((AD_OUT / self.current).glob("original.*")) if (AD_OUT / self.current).exists() else []
        return orig[0] if orig else SITE / self._app().get("hero", "")

    def make_sizes(self):
        if not self._app().get("hero"):
            QMessageBox.information(self, "صور الإعلان", "اختر صورة الإعلان أوّلًا.")
            return
        try:
            made = make_ad_sizes(self._hero_source(), self.current)
        except ValueError as e:
            QMessageBox.warning(self, "صور الإعلان", str(e))
            return
        flash(self.btn_sizes, f"✓ جُهّزت {len(made)} صور", 2500)
        self.logmsg(f"✓ جُهّزت {len(made)} صور في «صور الإعلان/{self.current}»: "
                    + "، ".join(d for *_, d in AD_SIZES), "ok")
        os.startfile(str(AD_OUT / self.current))

    def _paint_color(self, c: str):
        self.btn_color.setText(c)
        fg = "#000" if QColor(c).lightness() > 150 else "#fff"
        self.btn_color.setStyleSheet(f"background:{c}; color:{fg}; border-radius:8px;")

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self._app().get("color", "#2f9e6f")), self, "لون التطبيق")
        if c.isValid():
            self._app()["color"] = c.name()
            self._paint_color(c.name())
            self.save_timer.start()

    def copy_link(self):
        QGuiApplication.clipboard().setText(self.link_lbl.text())
        flash(self.btn_copy_link)
        if not self.data["base_url"]:
            self.logmsg("تنبيه: الرابط ناقص لأنّ الاستضافة لم تُعدّ بعد. اضغط «إعداد الاستضافة».", "warn")

    def copy_all(self):
        a = self._app()
        ad = a.get("ad", {})
        text = (f"النصّ الأساسي:\n{ad.get('primary','')}\n\nالعنوان: {ad.get('headline','')}\n"
                f"الوصف: {ad.get('description','')}\nالزرّ: {ad.get('cta','')}\n"
                f"الرابط: {self.link_lbl.text()}")
        QGuiApplication.clipboard().setText(text)
        flash(self.btn_copy_all)

    def preview_local(self):
        self._save_now()
        url = QUrl.fromLocalFile(str(SITE / "index.html"))
        url.setQuery(f"app={self.current}&src=preview")
        QDesktopServices.openUrl(url)
        self.statusBar().showMessage("فُتحت المعاينة. التحويل للمتجر لا يعمل إلا على هاتف أندرويد.", 6000)

    def open_online(self):
        QDesktopServices.openUrl(QUrl(build_link(self.data["base_url"], self.current, "preview", "preview")))

    def test_pixel(self):
        # src=pixeltest: البكسل يعمل (المعاينة preview وحدها تُطفئه) ولا تختلط الزيارة بحملة حقيقية
        url = build_link(self.data["base_url"], self.current, "pixel-test", "pixeltest")
        QGuiApplication.clipboard().setText(url)
        QDesktopServices.openUrl(QUrl(
            f"https://business.facebook.com/events_manager2/list/pixel/{self.data['pixel_id']}/test_events"))
        flash(self.btn_pixel, "✓ نُسخ الرابط", 2500)
        self.logmsg("في «اختبار الأحداث»: الصق الرابط في خانة الموقع واضغط «فتح الموقع»، ثم اضغط «حمّل»"
                    " في الصفحة. يجب أن يظهر PageView ثم Lead خلال ثوانٍ.", "info")

    def hosting(self):
        d = HostingDialog(self, self.data["repo_url"], self.data["base_url"], self.data["pixel_id"],
                          self.data["contact"])
        if d.exec() == QDialog.Accepted:
            contact = d.contact.text().strip()
            if contact and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", contact):
                QMessageBox.warning(self, "بريد التواصل", "البريد غير صحيح، فلم أحفظه.")
                contact = self.data["contact"]
            self.data["contact"] = contact
            self.data["repo_url"] = d.repo.text().strip()
            base = d.base.text().strip()
            self.data["base_url"] = (base.rstrip("/") + "/") if base else ""
            pixel = re.sub(r"\D", "", d.pixel.text())
            if d.pixel.text().strip() and not pixel:
                QMessageBox.warning(self, "Meta Pixel", "معرّف Pixel أرقام فقط. لم أحفظه.")
            self.data["pixel_id"] = pixel
            save_data(self.data)
            self._refresh_host()
            self._update_link()
            self.logmsg("✓ حُفظ إعداد الاستضافة.", "ok")

    def _refresh_host(self):
        # إن أُنشئ المستودع من أداة الالتزام بعد آخر فتح، يُقرأ وحده
        remote = git_remote()
        if remote and remote != self.data["repo_url"]:
            self.data["repo_url"] = remote
            self.data["base_url"] = repo_to_pages(remote)
            save_data(self.data)
            self.logmsg(f"✓ قرأت المستودع من git: {remote}", "ok")
            self._update_link()
        if self.data["base_url"]:
            self.host_lbl.setText(f"تُنشر على: ⁦{self.data['base_url']}⁩")
        else:
            self.host_lbl.setText("<span style='color:%s'>لم تُعدّ الاستضافة بعد ← «إعداد الاستضافة»</span>" % C_WARN)

    def publish(self):
        bad = [a.get("name") or s for s, a in self.data["apps"].items() if not parse_package(a.get("package", ""))]
        if bad:
            QMessageBox.warning(self, "النشر", "هذه التطبيقات بلا رابط متجر صحيح:\n" + "\n".join(bad))
            return
        self._save_now()
        if open_commit_tool():
            flash(self.btn_publish, "✓ فُتحت أداة الالتزام", 2500)
            if self.data["repo_url"]:
                self.logmsg("في أداة الالتزام اضغط «التزم وارفع». بعد دقيقة اضغط هنا «تحقّق من النشر».", "info")
            else:
                self.logmsg("أوّل مرّة: في أداة الالتزام «أنشئ مستودعًا على GitHub» (عامًّا)، ثم عد إلى"
                            " «إعداد الاستضافة» هنا.", "warn")

    def check_online(self):
        if not self.data["base_url"]:
            QMessageBox.information(self, "التحقّق", "لم تُعدّ الاستضافة بعد. اضغط «إعداد الاستضافة».")
            return
        self.btn_check.setEnabled(False)
        self.btn_check.setText("جارٍ التحقّق…")
        self.worker = CheckWorker(self.data["base_url"], list(self.data["apps"]))
        self.worker.done.connect(self._checked)
        self.worker.start()

    def _poll_state(self):
        if self.isActiveWindow() and not self.save_timer.isActive():
            self._show_state()

    def _checked(self, ok: bool, msg: str):
        self.btn_check.setEnabled(True)
        self.btn_check.setText("تحقّق من النشر")
        self.logmsg(msg, "ok" if ok else "warn")
        flash(self.btn_check, "✓ يعمل" if ok else "✗ لم يُنشر بعد", 2500)
    def logmsg(self, text: str, kind: str = "info"):
        color = {"info": C_MUTED, "warn": C_WARN, "err": C_ERR, "ok": C_OK}.get(kind, C_TEXT)
        cur = self.log.textCursor()
        cur.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cur.insertText(text + "\n", fmt)
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def closeEvent(self, e):
        if self.save_timer.isActive():
            self._save_now()
        for wk in (self.worker, self.stats_worker):
            if wk and wk.isRunning():
                wk.wait(3000)
        self.settings = load_settings()
        self.settings["geometry"] = [self.width(), self.height()]
        self.settings["last_app"] = self.current
        save_settings(self.settings)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    install_wheel_guard(app)
    w = Studio()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
