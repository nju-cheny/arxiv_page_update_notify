import os, json, ssl, re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

import requests
from bs4 import BeautifulSoup

# =====================
# 配置
# =====================
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = str(SCRIPT_DIR / "state.json")   # 和 py 同目录

LIST_URL = os.getenv("ARXIV_LIST_URL", "https://arxiv.org/list/cond-mat/new")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.exmail.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
USER = os.getenv("SMTP_USER", "")
PASS = os.getenv("SMTP_PASS", "")
MAIL_TO = os.getenv("MAIL_TO", "")  # 逗号分隔  # 多个用逗号

FROM_NAME = "arXiv Watcher"
SUBJECT = "[arXiv cond-mat/new] Page updated"

# 测试模式：1=强制发送一封测试邮件（不等页面更新）
TEST_MODE = os.getenv("TEST_MODE", "0").strip() == "1"

UA = {"User-Agent": "Mozilla/5.0 arxiv-page-update-watch"}

# =====================
# 工具
# =====================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_email(subject: str, body: str):
    to_list = [x.strip() for x in MAIL_TO.split(",") if x.strip()]

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = formataddr((str(Header(FROM_NAME, "utf-8")), USER))
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = Header(subject, "utf-8")

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
        s.login(USER, PASS)
        s.sendmail(USER, to_list, msg.as_string())

def fetch_version(html: str):
    """
    返回一个“版本字符串”，优先用 'Showing new listings for ...' 那行。
    如果找不到，就退而求其次用第一个 arXiv id。
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    m = re.search(r"Showing new listings for (.+)", text)
    if m:
        return "date:" + m.group(1).strip()

    # fallback：用第一个 /abs/xxxx.xxxxx
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/abs/"):
            arxiv_id = href[len("/abs/"):].split("?")[0].split("#")[0].strip()
            if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", arxiv_id):
                return "first_id:" + arxiv_id

    return None

def main():
    print("URL:", LIST_URL)
    print("STATE_FILE:", STATE_FILE)
    state = load_state()
    old_ver = state.get("version")

    r = requests.get(LIST_URL, headers=UA, timeout=25)
    print("HTTP:", r.status_code, "bytes:", len(r.content))
    r.raise_for_status()

    new_ver = fetch_version(r.text)
    print("old_ver:", old_ver)
    print("new_ver:", new_ver)

    # 测试模式：强制发送，但不更新 state（避免影响真实监控）
    if TEST_MODE:
        body = f"TEST MODE\nTime: {datetime.now()}\nURL: {LIST_URL}\nold_ver: {old_ver}\nnew_ver: {new_ver}"
        send_email(SUBJECT + " (TEST)", body)
        print("Test email sent.")
        return

    # 第一次运行：只记录，不发
    if old_ver is None:
        state["version"] = new_ver
        save_state(state)
        print("Initialized state (no email).")
        return

    # 版本变化：发邮件，并更新 state
    if new_ver and new_ver != old_ver:
        body = f"Page updated!\nTime: {datetime.now()}\nURL: {LIST_URL}\nold: {old_ver}\nnew: {new_ver}"
        send_email(SUBJECT, body)
        print("Update email sent.")
        state["version"] = new_ver
        save_state(state)
        return

    print("No update.")

if __name__ == "__main__":
    main()
