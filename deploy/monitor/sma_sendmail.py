#!/usr/bin/env python3
"""Send one alert email from the NAS. Used by nas-deadman.sh.

    sma_sendmail.py "<subject>"        # body on stdin

Sends directly via SMTP rather than relying on DSM notifications: DSM was configured, the task
ran, the script exited non-zero — and no mail arrived (2026-09-26). Diagnosing DSM needs root,
and more to the point, an alarm must not depend on a delivery path that cannot be tested.
Credentials come from ~/.sma-deadman-mail.env (chmod 600), never from this file.
"""
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

CONF = os.path.expanduser("~/.sma-deadman-mail.env")


def load_conf() -> dict:
    conf = {}
    try:
        with open(CONF, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k.strip()] = v.strip()
    except OSError as e:
        print(f"cannot read {CONF}: {e}", file=sys.stderr)
        sys.exit(2)
    return conf


def main() -> int:
    subject = sys.argv[1] if len(sys.argv) > 1 else "SM Adviser alert"
    body = sys.stdin.read()
    c = load_conf()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = c.get("MAIL_FROM", c.get("SMTP_USER", ""))
    msg["To"] = c.get("MAIL_TO", "")
    msg.set_content(body + f"\n\n-- \nSM Adviser dead-man's switch · {os.uname().nodename}\n")

    try:
        with smtplib.SMTP(c["SMTP_HOST"], int(c.get("SMTP_PORT", 587)), timeout=30) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.login(c["SMTP_USER"], c["SMTP_PASS"])
            s.send_message(msg)
    except Exception as e:                      # noqa: BLE001 - report, never crash the caller
        print(f"send failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"sent to {msg['To']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
