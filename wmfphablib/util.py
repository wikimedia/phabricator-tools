import os
import sys
import json
import subprocess
import config
import time
import datetime
import syslog

def datetime_to_epoch(date_time):
    return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

def epoch_to_datetime(epoch, timezone='UTC'):
    return str((datetime.datetime.fromtimestamp(int(float(epoch))
           ).strftime('%Y-%m-%d %H:%M:%S'))) + " (%s)" % (timezone,)

def errorlog(msg):
    msg = unicode(msg)
    try:
        syslog.syslog(msg)
        print >> sys.stderr, msg
    except:
        print 'error logging, well...error output'

def log(msg):
    msg = unicode(msg)
    if '-v' in ''.join(sys.argv):
        try:
            syslog.syslog(msg)
            print msg
        except:
            print 'error logging output'

def vlog(msg):
    msg = unicode(msg)
    if '-vv' in ''.join(sys.argv):
        try:
            print '-> ', msg
        except:
            print 'error logging output'

def update_blog(source, complete, failed, user_count, issue_count, apicon):
    title = "%s completed %s / failed %s" % (epoch_to_datetime(time.time()),
                                             complete,
                                             failed)
    print title
    body = "%s:\nUsers updated: %s\nIssues affected: %s" % (source, user_count, issue_count)
    return apicon.blog_update(apicon.user, title, body)

def source_name(path):
    return os.path.basename(path.strip('.py'))

def can_edit_ref():
    f = open('/srv/phab/phabricator/conf/local/local.json', 'r').read()
    settings = json.loads(f)
    try:
        return settings['maniphest.custom-field-definitions']['external_reference']['edit']
    except:
        return False

def runBash(cmd):
   p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
   out = p.stdout.read().strip()
   return out

def translate_json_dict_items(dict_of_j):
    for t in dict_of_j.keys():
        if dict_of_j[t]:
            try:
                dict_of_j[t] = json.loads(dict_of_j[t])
            except (TypeError, ValueError):
                pass
    return dict_of_j

def get_index(seq, attr, value):
    return next(index for (index, d) in enumerate(seq) if d[attr] == value)

def purge_cache():
    return runBash('/srv/phab/phabricator/bin/cache purge --purge-remarkup')
