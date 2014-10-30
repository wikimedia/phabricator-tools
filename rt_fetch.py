import time
import os
import re
import sys
import getpass
import ConfigParser
import json
sys.path.append('/home/rush/python-rtkit/')
from wmfphablib import phdb
from wmfphablib import rtlib
from wmfphablib import log
from rtkit import resource
from rtkit import authenticators
from rtkit import errors
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import config


def fetch(tid):

    response = resource.RTResource(config.rt_url,
                                   config.rt_login,
                                   config.rt_passwd,
                                   authenticators.CookieAuthenticator)
  
    tinfo = response.get(path="ticket/%s" % (tid,))
    #log(tinfo)


    #attachments = response.get(path="ticket/%s/attachments/" % (tid,))
    history = response.get(path="ticket/%s/history?format=l" % (tid,))

    links = response.get(path="ticket/%s/links/show" % (tid,))
    link_dict = rtlib.links_to_dict(links)

    #we get back freeform text and create a dict
    dtinfo = {}
    for cv in tinfo.strip().splitlines():
        if not cv:
            continue

        print "=>", cv
        #TimeEstimated: 0
        cv_kv = re.split(':', cv, 1)
        if len(cv_kv) > 1:
            k = cv_kv[0]
            v = cv_kv[1]
            dtinfo[k.strip()] = v.strip()

    #breaking detailed history into posts
    #23/23 (id/114376/total)
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    comments = [c.rstrip('#').rstrip('--') for c in comments]

    #attachments into a dict

    #attached = re.split('Attachments:', attachments, 1)[1]
    #ainfo = {}
    #for at in attached.strip().splitlines():
    #    if not at:
    #        continue
    #    k, v = re.split(':', at, 1)
    #    ainfo[k.strip()] = v.strip()

    #lots of junk attachments from emailing comments and ticket creation
    #ainfo_f = {}
    #for k, v in ainfo.iteritems():
    #    if '(Unnamed)' not in v:
    #        ainfo_f[k] = v

    #taking attachment text and convert to tuple (name, content type, size)
    #ainfo_ext = {}
    #comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    #for k, v in ainfo_f.iteritems():
    #    logger.debug('org %s' % v)
    #    extract = re.search('(.*\....)\s\((.*)\s\/\s(.*)\)', v)
        #logger.debug(str(extract.groups()))
    #    if not extract:
    #       logger.debug("%s %s" % (k, v))
    #    else:
    #       ainfo_ext[k] = extract.groups()

    if dtinfo['Status'] == 'resolved':
        creation_priority = ipriority['na']
    else:
        creation_priority = ipriority['unresolved']

    dtinfo['links'] = link_dict
    print dtinfo
    com = json.dumps(comments)
    tinfo = json.dumps(dtinfo)
    pmig = phdb(db='rt_migration')
    insert_values =  (tid, creation_priority, tinfo, com, now(), now())
    pmig.sql_x("INSERT INTO rt_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)",
               insert_values)
    pmig.close()
    return True

def run_fetch(tid, tries=1):
    if tries == 0:
        pmig = phdb(db='rt_migration')
        insert_values =  (tid, ipriority['fetch_failed'], '', '', now(), now())
        pmig.sql_x("INSERT INTO rt_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)",
                   insert_values)
        pmig.close()
        print 'failed to grab %s' % (tid,)
        return False
    try:
        if fetch(tid):
            print time.time()
            print 'done with %s' % (tid,)
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (tid, e)
        return run_fetch(tid, tries=tries)

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

bugs = [i for i in bugs if i.isdigit()]
print len(bugs)
from multiprocessing import Pool
pool = Pool(processes=8)
_ =  pool.map(run_fetch, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
