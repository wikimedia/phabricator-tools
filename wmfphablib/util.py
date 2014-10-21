import itertools
import re
import os
import sys
import json
import subprocess
import config
import time
import datetime
import syslog
import phabdb
import bzlib

def bzbug_ref_translate(text):
    mentioned_bugs = find_bug_refs(text)
    phabrefs = {}
    for b in mentioned_bugs:
        bugint = re.search('\d+', b).group(0)
        reft = phabdb.reference_ticket('%s%s' % (bzlib.prepend, bugint))
        if reft:
            phabrefs[b] = reft
    refdict = {k: v[0] for k, v in phabrefs.iteritems() if v is not None}
    taskid = lambda x: phabdb.get_task_id_by_phid(x)
    newrefs = {k: "T%s" % (taskid(v),) for k, v in refdict.iteritems()}
    return replace_bug_refs(text, newrefs)

def replace_bug_refs(text, bug_translations):
    # {u'Bug1': 'T6', u'Bug 100': 'T121'}
    for bug, ticket in bug_translations.iteritems():
        text = re.sub(bug , ticket, text, re.IGNORECASE)
    return text

def find_bug_refs(text):

    # there are nicer ways to do this seemingly but
    # all attempts resulted in an outlier so here it is
    bug_matches = ['bug\d+',
                   'bug\s+?\d+',
                   'bug\s?\#\d+',
                   'bug\s+\#\d+', 
                   'bug\s+\#\s?\d+', 
                   'bug\s+\#\s+\d+', 
                   'bug\#\s?\d+',
                   'bug\#\s+\d+',
                   'bug\#\d+']
    bugs = []
    for regex in bug_matches:
        bugs.append(re.findall(regex, text, re.IGNORECASE))
    return list(itertools.chain.from_iterable(bugs))

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
