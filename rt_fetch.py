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
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import return_bug_list
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
    history = response.get(path="ticket/%s/history?format=l" % (tid,))
    links = response.get(path="ticket/%s/links/show" % (tid,))

    # we get back freeform text and create a dict
    dtinfo = {}
    link_dict = rtlib.links_to_dict(links)
    dtinfo['links'] = link_dict
    for cv in tinfo.strip().splitlines():
        if not cv:
            continue
        cv_kv = re.split(':', cv, 1)
        if len(cv_kv) > 1:
            k = cv_kv[0]
            v = cv_kv[1]
            dtinfo[k.strip()] = v.strip()

    #breaking detailed history into posts
    #23/23 (id/114376/total)
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    comments = [c.rstrip('#').rstrip('--') for c in comments]

    if dtinfo['Status'] == 'resolved':
        creation_priority = ipriority['na']
    else:
        creation_priority = ipriority['unresolved']

    com = json.dumps(comments)
    tinfo = json.dumps(dtinfo)
    print tinfo

    pmig = phdb(db=config.rtmigrate_db)
    insert_values =  (tid, creation_priority, tinfo, com, now(), now())
    pmig.sql_x("INSERT INTO rt_meta \
                (id, priority, header, comments, created, modified) \
                VALUES (%s, %s, %s, %s, %s, %s)",
                insert_values)
    pmig.close()
    return True

def run_fetch(tid, tries=1):
    if tries == 0:
        pmig = phdb(db=config.rtmigrate_db)
        insert_values =  (tid, ipriority['fetch_failed'], '', '', now(), now())
        pmig.sql_x("INSERT INTO rt_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)",
                   insert_values)
        pmig.close()
        elog('failed to grab %s' % (tid,))
        return False
    try:
        return fetch(tid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to grab %s (%s)' % (tid, e))
        return run_fetch(tid, tries=tries)

def main():
    bugs = return_bug_list()
    from multiprocessing import Pool
    pool = Pool(processes=int(config.bz_fetchmulti))
    _ =  pool.map(run_fetch, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
