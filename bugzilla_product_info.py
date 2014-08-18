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
import ConfigParser

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


    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read('/etc/gz_fetch.conf')
    phab = Phabricator(username=parser.get(parser_mode, 'username'),
                   certificate=parser.get(parser_mode, 'certificate'),
                   host=parser.get(parser_mode, 'host'))

    parser_mode = 'bz'
    server = xmlrpclib.ServerProxy(parser.get(parser_mode, 'url'), use_datetime=True)

    kwargs = { 'names': 'Wikimedia',
               'Bugzilla_login': parser.get(parser_mode, 'Bugzilla_login'),
               'Bugzilla_password': parser.get(parser_mode, 'Bugzilla_password')}

    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    attached = server.Product.get(kwargs)['products']
    print attached
    #print archive_project('greenproject')

    

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

for i in bugs:
    if i.isdigit():
        main(i)
