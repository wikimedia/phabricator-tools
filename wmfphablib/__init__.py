import os
import sys
import syslog
import datetime
import bzwmfphab as bzlib
import rtlib
import fablib
from phabapi import phabapi as Phab
from phabdb import phdb
from phabdb import mailinglist_phid
from phabdb import set_project_icon
import time

def now():
    return int(time.time())

#import priority status meanings
ipriority = {'creation_failed': 6,
             'fetch_failed': 5,
             'na': 0,
             'unresolved': 1}

def datetime_to_epoch(date_time):
    return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

def epoch_to_datetime(epoch, timezone='UTC'):
    return str((datetime.datetime.fromtimestamp(int(float(epoch))
           ).strftime('%Y-%m-%d %H:%M:%S'))) + " (%s)" % (timezone,)

def log(msg):
    msg = unicode(msg)
    if '-v' in sys.argv:
        try:
            syslog.syslog(msg)
            print '-> ', msg
        except:
            print 'error logging output'

def save_attachment(name, data):
    f = open(name, 'wb')
    f.write(data)
    f.close()

def get_config_file():
    configfile = '/etc/gz_fetch.conf'
    if not os.path.exists(configfile):
        print 'no config file: %s' % (configfile,)
        return ''
    return configfile
