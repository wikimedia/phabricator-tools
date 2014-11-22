#!/usr/bin/env python
import multiprocessing
import time
import yaml
import ast
import json
import sys
import xmlrpclib
import os
import re
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import return_bug_list
from wmfphablib import phdb
from wmfphablib import now
from wmfphablib import mailinglist_phid
from wmfphablib import set_project_icon
from wmfphablib import phabdb
from wmfphablib import Phab
from wmfphablib import log
from wmfphablib import notice
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import bzlib
from wmfphablib import config
from wmfphablib import bzlib
from wmfphablib import util
from wmfphablib import datetime_to_epoch
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority

def create(bugid):
    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    phabm = phabmacros('', '', '')
    phabm.con = phab

    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    current = pmig.sql_x("SELECT priority, \
                          header, \
                          comments, \
                          created, \
                          modified \
                          FROM bugzilla_meta WHERE id = %s",
                          (bugid,))
    if current:
        import_priority, buginfo, com, created, modified = current[0]
    else:    
        elog('%s not present for migration' % (bugid,))
        return False

    def get_ref(id):
        refexists = phabdb.reference_ticket('%s%s' % (bzlib.prepend,
                                                      id))
        if refexists:
            return refexists[0]

    buginfo = json.loads(buginfo)
    com = json.loads(com)
    bugid = int(bugid)
    vlog(bugid)
    vlog(buginfo)

    ticket = get_ref(bugid)
    print 'TICKET ', ticket

    def is_sensitive(name):
        return name.strip().lower().startswith('security')

    def project_security_settings(pname):
        if is_sensitive(pname):
            ephid = phabdb.get_project_phid('security')
            edit = ephid
        else:
            edit = 'users'
        view = 'public'
        return edit, view

    server = xmlrpclib.ServerProxy(config.Bugzilla_url, use_datetime=True)
    token_data = server.User.login({'login': config.Bugzilla_login,
                                    'password': config.Bugzilla_password})

    token = token_data['token']
    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    kwargs = { 'ids': [bugid], 'Bugzilla_token': token }

    #list of projects to add to ticket
    ptags = []

    if buginfo['status'] == 'VERIFIED':
        vlog("Adding 'verified' to %s" % (ticket,))
        ptags.append(('verified', 'tags'))

    if buginfo['status'].lower() == 'patch_to_review':
        vlog("Adding 'Patch-For-Review' to %s" % (ticket,))
        ptags.append(('Patch-For-Review', 'tags', 'green'))

    log("status recognized as %s" % (buginfo['status'],))

    phids = []
    for p in ptags:
        edit, view = project_security_settings(p[0])
        phid = phabm.ensure_project(p[0], edit=edit, view=view)
        phids.append(phid)
        if p[1] is not None:
            vlog("setting project %s icon to %s" % (p[0], p[1]))
            set_project_icon(p[0], icon=p[1])

    for phid in phids:
        phabdb.set_related_project(ticket, phid)

    pmig.close()
    return True


def run_create(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

        import_priority = pmig.sql_x("SELECT priority \
                                      FROM bugzilla_meta \
                                      WHERE id = %s", (bugid,))
        if import_priority:
            pmig.sql_x("UPDATE bugzilla_meta \
                        SET priority=%s \
                        WHERE id = %s", (ipriority['update_failed'],
                                         bugid))
        else:
            elog("%s does not seem to exist" % (bugid))
        pmig.close()
        elog('failed to create %s' % (bugid,))
        return False
    try:
        return create(bugid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to create %s (%s)' % (bugid, e))
        return run_create(bugid, tries=tries)

def main():
    bugs = return_bug_list()
    from multiprocessing import Pool
    pool = Pool(processes=int(config.bz_createmulti))
    _ =  pool.map(run_create, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
