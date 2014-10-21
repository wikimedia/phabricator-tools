#!/usr/bin/env python
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
from wmfphablib import config
from wmfphablib import log
from wmfphablib import vlog
import phabricator
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import return_bug_list
from wmfphablib import phdb
from wmfphablib import mailinglist_phid
from wmfphablib import set_project_icon
from wmfphablib import phabdb

def main():

    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    phabm = phabmacros('', '', '')
    phabm.con = phab
    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    server = xmlrpclib.ServerProxy(config.Bugzilla_url, use_datetime=True)

    bzdata = open("data/bugzilla.yaml", 'r')
    bzdata_yaml = yaml.load(bzdata)
    #product = 'Wikimedia'

    kwargs = {
              'Bugzilla_login': config.Bugzilla_login,
              'Bugzilla_password': config.Bugzilla_password}
    products = server.Product.get_selectable_products(kwargs)['ids']
    print products
    for p in products:
        kwargs = { 'ids': p,
                   'Bugzilla_login': config.Bugzilla_login,
                   'Bugzilla_password': config.Bugzilla_password}
        pi = server.Product.get(kwargs)['products'][0]
        print pi['name'], pi['description']
        for c in pi['components']:
            pname = "\n%s-%s\n\n%s" % (pi['name'], c['name'])
            print pname
            #phabm.ensure_project(pname, description=c['description'])
main()
