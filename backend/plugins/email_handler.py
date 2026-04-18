"""
Email Sender Plugin Handler
使用 SMTP 發送郵件（支援 TLS/STARTTLS）
config 需要: smtp_host, smtp_port, smtp_user, smtp_password
params: {to, subject, body, is_html}
"""
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


async def run(action: str, params: dict, config: dict) -> dict:
    smtp_host     = config.get("smtp_host", "")
    smtp_port     = int(config.get("smtp_port", 587))
    smtp_user     = config.get("smtp_user", "")
    smtp_password = config.get("smtp_password", "")
    sender        = config.get("sender_email", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return {
            "success": False,
            "error": "缺少 SMTP 設定，請在插件設定中填寫 smtp_host / smtp_user / smtp_password",
        }

    to      = params.get("to", "")
    subject = params.get("subject", "（無主旨）")
    body    = params.get("body", params.get("content", ""))
    is_html = params.get("is_html", False)

    if not to:
        return {"success": False, "error": "缺少 to 參數（收件人 Email）"}
    if not body:
        return {"success": False, "error": "缺少 body 參數（郵件內容）"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to

    part = MIMEText(body, "html" if is_html else "plain", "utf-8")
    msg.attach(part)

    try:
        context = ssl.create_default_context()
        if smtp_port == 465:
            # SSL
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())
        else:
            # STARTTLS（587 / 25）
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(smtp_user, smtp_password)
                server.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())

        logger.info("Email sent to %s via %s", to, smtp_host)
        return {"success": True, "data": {"to": to, "subject": subject, "sent": True}}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "SMTP 認證失敗，請確認帳號密碼"}
    except smtplib.SMTPConnectError:
        return {"success": False, "error": f"無法連線到 {smtp_host}:{smtp_port}"}
    except Exception as e:
        logger.error("Email send error: %s", e, exc_info=True)
        return {"success": False, "error": f"發送失敗: {e}"}
