import time
import json
import multiprocessing
import sys
import collections
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import get_config_file
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import fablib
import ConfigParser


configfile = get_config_file()


def fetch(PHABTICKETID):

    PHABTICKETID = int(PHABTICKETID)

    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read(configfile)
    phab = Phabricator(parser.get(parser_mode, 'username'),
                       parser.get(parser_mode, 'certificate'),
                       parser.get(parser_mode, 'host'))

    #dummy instance of phabapi
    phabm = phabmacros('', '', '')
    phabm.con = phab

    pmig = phabdb.phdb(db='fab_migration')

    issue = pmig.sql_x("SELECT id FROM fab_meta WHERE id = %s", PHABTICKETID)
    if not issue:
        log('%s not present for migration' % (PHABTICKETID,))
        return True

    exists = phabdb.reference_ticket('%s%s' % (fablib.prepend, PHABTICKETID))
    if exists:
        log('reference ticket %s already exists' % (PHABTICKETID,))
        return True

    tid, import_priority, header, com, created, modified = pmig.sql_x("SELECT * FROM fab_meta WHERE id = %s", PHABTICKETID)

    vlog('priority: %d' % (import_priority,))

    tinfo = json.loads(header)
    comments = json.loads(com)

    proj_phids = []
    for pn in tinfo['xprojects']:
        proj_phids.append(phabm.ensure_project(pn))
    vlog(proj_phids)
    priorities = {"Unbreak Now!": 100,
                  "Needs Triage": 90,
                  "High": 80,
                  "Normal": 50,
                  "Low": 25,
                  "Needs Volunteer": 10,
                  0: 10,
                  '0': 10}

    newticket =  phab.maniphest.createtask(title=tinfo['title'],
                                 description=tinfo['description'],
                                 projectPHIDs=proj_phids,
                                 priority=priorities[tinfo['priority']],
                                 auxiliary={"std:maniphest:external_reference":"fl%s" % (PHABTICKETID,)})

    phabdb.set_task_ctime(newticket['phid'], tinfo['dateCreated'])
    log('setting ctime of %s for %s' % (tinfo['dateCreated'], newticket['phid']))
    log('Created phab ticket %s for %s' % (newticket['id'], PHABTICKETID))
    vlog(newticket)

    #  0 {'xcommenter': {u'userName': u'uvhooligan', 
    #  u'phid': u'PHID-USER-lb2dbts4cdunqxzjqf2d', 
    #  u'realName': u'Un Ver Hooligan', 
    #  u'roles': [u'unverified', u'approved', u'activated'],
    #  u'image': u'http://fabapi.wmflabs.org/res/phabricator/3eb28cd9/rsrc/image/avatar.png',
    #  u'uri': u'http://fabapi.wmflabs.org/p/uvhooligan/'}, 
    #  'created': 1409875492L, 'xuseremail': None, 
    #  'text': 'hi guys I hate email', 'last_edit': 1409875492L,
    #  'xuserphid': 'PHID-USER-lb2dbts4cdunqxzjqf2d'}
    csorted = sorted(comments.values(), key=lambda k: k['created']) 
    for k, v in enumerate(csorted):
        created = epoch_to_datetime(v['created'])
        user = v['xcommenter']['userName']
        comment_body = "**%s** wrote on `%s`\n\n%s" % (user, created, v['text'])
        vlog(phabm.task_comment(newticket['id'], comment_body))

    if tinfo["status"] == "wontfix":
        tinfo["status"] = 'resolved'

    if tinfo['status'] != 'open':
        log('set status %s' % (tinfo['status']))
        vlog(phabm.task_comment(newticket['id'], '//importing issue status//'))
        vlog(phabm.set_status(newticket['id'], tinfo['status']))

    log('setting modtime of %s for %s' % (tinfo['dateModified'], newticket['phid']))
    phabdb.set_task_mtime(newticket['phid'], tinfo['dateModified'])
    pmig.close()
    return True

def run_fetch(fabid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db='fab_migration')
        import_priority = pmig.sql_x("SELECT priority FROM fab_meta WHERE id = %s", (fabid,))
        if import_priority:
            log('updating existing record')
            pmig.sql_x("UPDATE fab_meta SET priority=%s, modified=%s WHERE id = %s", (ipriority['creation_failed'],
                                                                                     now(),
                                                                                     fabid))
        else:
            print "%s does not seem to exist" % (fabid)
        pmig.close()
        print 'failed to grab %s' % (fabid,)
        return False
    try:
        if fetch(fabid):
            try:
                pmig = phabdb.phdb(db='fab_migration')
                pandmupdate = "UPDATE fab_meta SET priority=%s, modified=%s WHERE id = %s"
                pmig.sql_x(pandmupdate, (ipriority['creation_success'],
                                         now(),
                                         fabid))
                print time.time()
                print 'done with %s' % (fabid,)
            except:
                return False
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (fabid, e)
        return run_fetch(fabid, tries=tries)


bugs =  return_bug_list()
print len(bugs)
from multiprocessing import Pool
pool = Pool(processes=2)
_ =  pool.map(run_fetch, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
