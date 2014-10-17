import os
import sys
import syslog
import datetime
import bzlib
import rtlib
import fablib
import time
from util import log
from util import vlog
from util import errorlog
from util import datetime_to_epoch
from util import epoch_to_datetime
from phabapi import phabapi as Phab
from phabdb import phdb
from phabdb import mailinglist_phid
from phabdb import set_project_icon
from config import cfile as configfile

def now():
    return int(time.time())

def tflatten(t_of_tuples):
    return [element for tupl in t_of_tuples for element in tupl]

#import priority status meanings
ipriority = {'creation_failed': 6,
             'creation_success': 7,
             'fetch_failed': 5,
             'na': 0,
             'update_success': 8,
             'update_failed': 9,
             'unresolved': 1}

def return_bug_list():
    if sys.stdin.isatty():
        bugs = sys.argv[1:]
    else:
        bugs = sys.stdin.read().strip('\n').strip().split()

    if '-' in bugs[0]:
        start, stop = bugs[0].split('-')

        bugrange = range(int(start), int(stop) + 1)
        bugs = [str(b) for b in bugrange]

        for arg in sys.argv:
            if arg.startswith('x'):
                sample = int(arg.strip('x'))
                vlog("sample rate found %s" % (sample,))
                bugs = [b for b in bugs if int(b) % sample == 0]
    else:
        bugs = [i for i in bugs if i.isdigit()]
    log("Bugs count: %d" % (len(bugs)))
    return bugs

def save_attachment(name, data):
    f = open(name, 'wb')
    f.write(data)
    f.close()
