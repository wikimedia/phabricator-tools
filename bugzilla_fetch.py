#!/usr/bin/env python
import time
import yaml
import json
import sys
import xmlrpclib
import os
import datetime
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import bzlib
from wmfphablib import config
from wmfphablib import epoch_to_datetime
from wmfphablib import datetime_to_epoch
from wmfphablib import phabdb
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import return_bug_list


def fetch(bugid):

    pmig = phabdb.phdb(db=config.bzmigrate_db)
    server = xmlrpclib.ServerProxy(config.Bugzilla_url, use_datetime=True)
    token_data = server.User.login({'login': config.Bugzilla_login,
                                    'password': config.Bugzilla_password})

    token = token_data['token']
    kwargs = { 'ids': [bugid], 'Bugzilla_token': token }

    #grabbing one bug at a time for now
    buginfo = server.Bug.get(kwargs)['bugs']	
    buginfo =  buginfo[0]
    com = server.Bug.comments(kwargs)['bugs'][str(bugid)]['comments']
    bug_id = com[0]['bug_id']

    #have to do for json
    buginfo['last_change_time'] = datetime_to_epoch(buginfo['last_change_time'])
    buginfo['creation_time'] = datetime_to_epoch(buginfo['creation_time'])

    if 'flags' in buginfo:
        for flag in buginfo['flags']:
            for k, v in flag.iteritems():
                if isinstance(v, datetime.datetime):
                    flag[k] = datetime_to_epoch(v)

    for c in com:
        c['creation_time'] = datetime_to_epoch(c['creation_time'])
        c['time'] = datetime_to_epoch(c['time'])

    # set ticket status for priority import
    status = bzlib.status_convert(buginfo['status'])

    if status != 'open':
        creation_priority = ipriority['na']
    else:
        creation_priority = ipriority['unresolved']

    current = pmig.sql_x("SELECT * from bugzilla_meta where id = %s", bugid)
    if current:
        update_values = (creation_priority,
                         json.dumps(buginfo),
                         json.dumps(com),
                         now(),
                         bugid)
        vlog('update: ' + str(update_values))
        pmig.sql_x("UPDATE bugzilla_meta SET priority=%s, header=%s, comments=%s, modified=%s WHERE id = %s",
                   update_values)
    else:
        insert_values =  (bugid, creation_priority, json.dumps(buginfo), json.dumps(com), now(), now())
        vlog('insert: ' + str(insert_values))
        sql = "INSERT INTO bugzilla_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)"
        pmig.sql_x(sql,
                   insert_values)
    pmig.close()
    return True

def run_fetch(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.bzmigrate_db)
        current = pmig.sql_x("SELECT * from bugzilla_meta where id = %s", bugid)
        if current:
            update_values =  (ipriority['fetch_failed'], '', '', now(), bugid)
            pmig.sql_x("UPDATE bugzilla_meta SET priority=%s, header=%s, comments=%s modified=%s WHERE id = %s",
                       update_values)
        else:
            insert_values =  (bugid, ipriority['fetch_failed'], '', '', now(), now())
            pmig.sql_x("INSERT INTO bugzilla_meta (id, priority, header, comments, modified, created) VALUES (%s, %s, %s, %s, %s, %s)",
                       insert_values)
            pmig.close()
        elog('failed to grab %s' % (bugid,))
        return False
    try:
        return fetch(bugid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to fetch %s (%s)' % (bugid, e))
        return run_fetch(bugid, tries=tries)


def main():

    bugs = return_bug_list()
    from multiprocessing import Pool
    pool = Pool(processes=10)
    _ =  pool.map(run_fetch, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
