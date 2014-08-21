#!/usr/bin/env python
"""

2014 Chase Pettet


This script is a WIP for getting Bugzilla information
with the end goal of it living in phabricator

"""
import time
import yaml
import ast
import base64
import json
import datetime
import sys
import xmlrpclib
import subprocess
import os
import re
import MySQLdb
from phabdb import phdb
from phabdb import mailinglist_phid
from phabdb import set_project_icon
from email.parser import Parser
import ConfigParser

def log(msg):
    import syslog
    msg = unicode(msg)
    if '-v' in sys.argv:
        try:
            syslog.syslog(msg)
            print '-> ', msg
        except:
            print 'error logging output'

def fetch(bugid):

    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'bz'
    parser.read('/etc/gz_fetch.conf')
    server = xmlrpclib.ServerProxy(parser.get(parser_mode, 'url'), use_datetime=True)

    token_data = server.User.login({'login': parser.get(parser_mode, 'Bugzilla_login'),
                             'password': parser.get(parser_mode, 'Bugzilla_password')})

    token = token_data['token']

    #kwargs = { 'ids': [bugid],
    #           'Bugzilla_login': parser.get(parser_mode, 'Bugzilla_login'),
    #           'Bugzilla_password': parser.get(parser_mode, 'Bugzilla_password')}

    kwargs = { 'ids': [bugid], 'Bugzilla_token': token }

    def datetime_to_epoch(date_time):
        return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

    def status_convert(bz_status):
        """
        UNCONFIRMED (default)   Open + Needs Triage (default)
        NEW     Open
        ASSIGNED                open
        PATCH_TO_REVIEW         open
        NEED_INFO               needs_info
        RESOLVED FIXED          resolved
        RESOLVED INVALID        invalid
        RESOLVED WONTFIX        declined
        RESOLVED WORKSFORME     resolved
        RESOLVED DUPLICATE      closed

        needs_info      stalled
        resolved        closed
        invalid         no historical value will be purged eventually (spam, etc)
        declined        we have decided not too -- even though we could
        """

        statuses = {'new': 'open',
                    'resolved': 'resolved',
                    'reopened': 'open',
                    'closed': 'resolved',
                    'need_info': 'needs_info',
                    'verified': 'resolved',
                    'assigned': 'open',
                    'unconfirmed': 'open',
                    'patch_to_review': 'open'}

        return statuses[bz_status.lower()]


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
    status = status_convert(buginfo['status'])
    if status != 'open':
        import_priority = 0
    else:
        import_priority = 1

    pmig = phdb()
    insert_values =  (bugid, import_priority, json.dumps(buginfo), json.dumps(com))
    pmig.sql_x("INSERT INTO bugzilla_meta (id, priority, header, comments) VALUES (%s, %s, %s, %s)",
               insert_values)
    pmig.close()
    return True

def run_fetch(bugid, tries=3):
    if tries == 0:
        print 'failed to grab %s' % (bugid,)
        return False
    try:
        if fetch(bugid):
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

print bugs
bugs = [i for i in bugs if i.isdigit()]    
print bugs
for i in bugs:
    if run_fetch(i):
        print time.time()
        print 'done with %s' % (i,)
    else:
        pmig = phdb()
        insert_values =  (i, 6, '', '')
        pmig.sql_x("INSERT INTO bugzilla_meta (id, priority, header, comments) VALUES (%s, %s, %s, %s)",
                   insert_values)
        pmig.close()
        print 'failed on %s' % (i,)
