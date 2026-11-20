"""Replaceable SMTP/local mail boundary. Never log a token or message body."""
import html
import os
from pathlib import Path
from email.message import EmailMessage
import smtplib
import ssl
import uuid


def send(to, subject, text, link=None):
    origin=os.environ.get('CTRLTEA_PUBLIC_ORIGIN','http://localhost:8765').rstrip('/')
    body=text + ('\n\n'+origin+'/#'+link if link else '')
    message=EmailMessage()
    message['From']=os.environ.get('CTRLTEA_MAIL_FROM','Ctrl+Tea <noreply@example.invalid>')
    message['To']=to;message['Subject']='Ctrl+Tea — '+subject
    message.set_content('Ctrl+Tea\n\n'+body+'\n\nإذا لم تطلب هذه العملية، تجاهل الرسالة.')
    message.add_alternative('<html lang="ar" dir="rtl"><body style="font-family:sans-serif;background:#faf5ed;padding:32px"><h1 style="color:#8b3f25">Ctrl+Tea</h1><p>'+html.escape(text)+'</p>'+(f'<p><a href="{html.escape(origin+"/#"+link,quote=True)}">متابعة الطلب الآمن</a></p>' if link else '')+'<p>إذا لم تطلب هذه العملية، تجاهل الرسالة.</p></body></html>',subtype='html')
    mode=os.environ.get('CTRLTEA_MAIL_PROVIDER','local')
    if mode=='local':
        root=Path(os.environ['CTRLTEA_MAIL_SINK']).resolve();root.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=root/(uuid.uuid4().hex+'.eml')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(message.as_bytes())
    elif mode=='smtp':
        host=os.environ['CTRLTEA_SMTP_HOST'];port=int(os.environ.get('CTRLTEA_SMTP_PORT','587'))
        if not os.environ.get('CTRLTEA_MAIL_FROM') or 'example.invalid' in message['From']:
            raise ValueError('Configure a verified sender before using SMTP')
        with smtplib.SMTP(host,port,timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.environ.get('CTRLTEA_SMTP_USER'):
                smtp.login(os.environ['CTRLTEA_SMTP_USER'],os.environ['CTRLTEA_SMTP_PASSWORD'])
            smtp.send_message(message)
    else:raise ValueError('Unsupported mail provider')
