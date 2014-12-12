#!/usr/bin/env python
import time
import os
import re
import sys
import getpass
import ConfigParser
import json
sys.path.append('/home/rush/python-rtkit/')
from wmfphablib import phabdb
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

    log("fetching issue %s" % (tid,))
    tinfo = response.get(path="ticket/%s" % (tid,))
    history = response.get(path="ticket/%s/history?format=l" % (tid,))
    links = response.get(path="ticket/%s/links/show" % (tid,))
    vlog(tinfo)

    if re.search('\#\sTicket\s\d+\sdoes\snot\sexist.$', tinfo.strip()):
        log("Skipped as source missing for %s" % (tid,))
        return 'missing'

    # some private todo's and such
    if 'You are not allowed to display' in tinfo:
        log("Skipped as access denied for %s" % (tid,))
        return 'denied'

    #breaking detailed history into posts
    #23/23 (id/114376/total)
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    comments = [c.rstrip('#').rstrip('--') for c in comments]

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

    vlog("Enabled queues: %s" % (str(rtlib.enabled)))
    if dtinfo['Queue'] not in rtlib.enabled:
        log("Skipped as disabled queue for %s (%s)" % (str(tid), dtinfo['Queue']))
        return 'disabled'

    com = json.dumps(comments)
    tinfo = json.dumps(dtinfo)

    pmig = phabdb.phdb(db=config.rtmigrate_db,
                       user=config.rtmigrate_user,
                       passwd=config.rtmigrate_passwd)


    creation_priority = ipriority['fetch_success']
    current = pmig.sql_x("SELECT * from rt_meta where id = %s", tid)
    if current:
        update_values =  (creation_priority, tinfo, com, now(), now())
        pmig.sql_x("UPDATE rt_meta SET priority=%s, \
                                       header=%s, \
                                       comments=%s, \
                                       modified=%s \
                                       WHERE id = %s",
                   update_values)
        vlog('update: ' + str(update_values))

    else:
        insert_values =  (tid, creation_priority, tinfo, com, now(), now())

        pmig.sql_x("INSERT INTO rt_meta \
                (id, priority, header, comments, created, modified) \
                VALUES (%s, %s, %s, %s, %s, %s)",
                insert_values)
    pmig.close()
    return True

def run_fetch(tid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.rtmigrate_db,
                       user=config.rtmigrate_user,
                       passwd=config.rtmigrate_passwd)
        insert_values =  (tid, ipriority['fetch_failed'], '', '', now(), now())

        pmig.sql_x("INSERT INTO rt_meta \
                (id, priority, header, comments, created, modified) \
                VALUES (%s, %s, %s, %s, %s, %s)",
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

    pmig = phabdb.phdb(db=config.rtmigrate_db,
                       user=config.rtmigrate_user,
                       passwd=config.rtmigrate_passwd)

    if 'failed' in sys.argv:
        priority = ipriority['fetch_failed']
    else:
        priority = None

    bugs = return_bug_list(dbcon=pmig,
                           priority=priority,
                           table='rt_meta')
    pmig.close()

    from multiprocessing import Pool
    pool = Pool(processes=int(config.bz_fetchmulti))
    _ =  pool.map(run_fetch, bugs)
    vlog(_)
    denied = len([i for i in _ if i == 'denied'])
    disabled = len([i for i in _ if i == 'disabled'])
    missing = len([i for i in _ if i == 'missing'])
    complete = len(filter(bool, [i for i in _ if i not in ['denied', 'disabled', 'missing']]))
    known_bad = denied + disabled + missing
    failed = (len(_) - known_bad) - complete
    print '-----------------------------\n \
          %s Total %s\n \
          known bad %s (denied %s, disabled %s, missing %s)\n\n \
          completed %s, failed %s' % (sys.argv[0],
                                                          len(bugs),
                                                          known_bad,
                                                          denied,
                                                          disabled,
                                                          missing,
                                                          complete,
                                                          failed)

if __name__ == '__main__':
    main()
