#!/usr/bin/env python
"""

2014 Chase Pettet


This script is a WIP for getting Bugzilla information
with the end goal of it living in phabricator

"""
import time
import yaml
import json
import sys
import xmlrpclib
import os
from wmfphablib import log
from wmfphablib import bzlib
from wmfphablib import epoch_to_datetime
from wmfphablib import datetime_to_epoch
from wmfphablib import phabdb
from wmfphablib import ipriority
import ConfigParser

def fetch(bugid):

    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'bz'
    parser.read('/etc/gz_fetch.conf')
    server = xmlrpclib.ServerProxy(parser.get(parser_mode, 'url'), use_datetime=True)

    token_data = server.User.login({'login': parser.get(parser_mode, 'Bugzilla_login'),
                             'password': parser.get(parser_mode, 'Bugzilla_password')})

    token = token_data['token']
    kwargs = { 'ids': [bugid], 'Bugzilla_token': token }

    #grabbing one bug at a time for now
    buginfo = server.Bug.get(kwargs)['bugs']	
    buginfo =  buginfo[0]
    com = server.Bug.comments(kwargs)['bugs'][bugid]['comments']
    bug_id = com[0]['bug_id']

    #have to do for json
    buginfo['last_change_time'] = datetime_to_epoch(buginfo['last_change_time'])
    buginfo['creation_time'] = datetime_to_epoch(buginfo['creation_time'])

    for c in com:
        c['creation_time'] = datetime_to_epoch(c['creation_time'])
        c['time'] = datetime_to_epoch(c['time'])

    # set ticket status for priority import
    status = bzlib.status_convert(buginfo['status'])

    if status != 'open':
        creation_priority = ipriority['na']
    else:
        creation_priority = ipriority['unresolved']

    pmig = phabdb.phdb(db='bugzilla_migration')
    current = pmig.sql_x("SELECT * from bugzilla_meta where id = %s", bugid)
    if current:
        log('updating current record')
        update_values = (creation_priority,
                         json.dumps(buginfo),
                         json.dumps(com),
                         bugid)
        pmig.sql_x("UPDATE bugzilla_meta SET priority=%s, header=%s, comments=%s WHERE id = %s",
                   update_values)
    else:
        log('inserting new record')
        insert_values =  (bugid, creation_priority, json.dumps(buginfo), json.dumps(com))
        pmig.sql_x("INSERT INTO bugzilla_meta (id, priority, header, comments) VALUES (%s, %s, %s, %s)",
               insert_values)
    pmig.close()
    return True

def run_fetch(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb()
        insert_values =  (bugid, ipriority['fetch_failed'], '', '')
        pmig.sql_x("INSERT INTO bugzilla_meta (id, priority, header, comments) VALUES (%s, %s, %s, %s)",
                   insert_values)
        pmig.close()
        print 'failed to grab %s' % (bugid,)
        return False
    try:
        if fetch(bugid):
            print time.time()
            print 'done with %s' % (bugid,)
            return True
    except Exception as e:
        tries -= 1
        time.sleep(5)
        print 'failed to grab %s (%s)' % (bugid, e)
        return run_fetch(bugid, tries=tries)

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

bugs = [i for i in bugs if i.isdigit()]    
print len(bugs)
from multiprocessing import Pool
pool = Pool(processes=10)
_ =  pool.map(run_fetch, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
