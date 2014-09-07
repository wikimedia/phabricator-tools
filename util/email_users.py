import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append('/'.join(path.split('/')[:-1]))
from wmfphablib import phabdb
from user_emails import emails
import smtplib
from email.mime.text import MIMEText


def send_email(src, to, subject, msg):
    s = smtplib.SMTP('polonium.wikimedia.org')
    msg['Subject'] = subject
    msg['From'] = src
    msg['To'] = to
    s.sendmail(src, [to], msg.as_string())
    s.quit()

for r in emails():
    textfile = '/root/body'
    fp = open(textfile, 'rb')
    msg = MIMEText(fp.read())
    fp.close()
    send_email('PhabricatorAnnounce@phabricator.wikimedia.org',
               r,
               'Phabricator in labs update.',
               msg)
    
