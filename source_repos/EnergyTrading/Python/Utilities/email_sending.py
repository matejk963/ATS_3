import smtplib
from email.message import EmailMessage

def send_plain_email(recipient, subject, body, smtp_server="smtp.office365.com", smtp_port=587, email_address="algotrading@energytrading.sk", email_login=None, email_password=""):
    if email_login is None:
        email_login = email_address
    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(email_login, email_password)
        smtp.sendmail(email_address, recipient, f"Subject:{subject}\n\n{body}")

def send_html_email(recipient, subject, text_content, html_content, attachment_path=None, smtp_server="smtp.office365.com", smtp_port=587, email_address="algotrading@energytrading.sk", email_login=None, email_password="", ):
    if email_login is None:
        email_login = email_address
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_address
    msg["To"] = recipient
    msg.set_content(text_content)

    msg.add_alternative(html_content, subtype="html")

    if attachment_path:
        with open(attachment_path, "rb") as file:
            msg.add_attachment(file.read(), maintype="application", subtype="octet-stream", filename=attachment_path.split("/")[-1])

    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(email_login, email_password)
        smtp.send_message(msg)