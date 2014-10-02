#!/usr/bin/env python
"""

WIP for fetching information about products to migrate
as project state to phabricator

"""


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
from phabdb import archive_project
from wmfphablib import config
import phabricator
from phabricator import Phabricator

def log(msg):
    import syslog
    msg = unicode(msg)
    if '-v' in sys.argv:
        try:
            syslog.syslog(msg)
            print '-> ', msg
        except:
            print 'error logging output'

def main(bugid):

    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    server = xmlrpclib.ServerProxy(config.Bugzilla_url, use_datetime=True)

    kwargs = { 'names': 'Wikimedia',
               'Bugzilla_login': config.Bugzilla_login,
               'Bugzilla_password': config.Bugzilla_password}

    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    attached = server.Product.get(kwargs)['products']
    print attached
    

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

for i in bugs:
    if i.isdigit():
        main(i)
