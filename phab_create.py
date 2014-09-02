import time
import json
import multiprocessing
import sys
import collections
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority


def fetch(PHABTICKETID):

    PHABTICKETID = int(PHABTICKETID)
    phab = Phabricator(username='Rush',
                   certificate="7xboqo5pc6ubg6s37raf5fvmw4ltwg2eu4brh23k5fskgegkcbojix44r2rtt6eter3sktkly3vqspmfjy2n6kjzsis63od2ns7ayek3xby5xlyydczc3rhrtdb3xugkgfg3dxrbvnxjw3jnzmdm6cf3mpmca3hsfrf7aujbufimh3lk4u6uz4nefukarwsefkbccjfgn7gmuxeueouh4ldehvwdcvakbxmrmdri3stgw5sfvukib4yngf23etp",
                   host = "http://fabapitest.wmflabs.org/api/")
    log(str(phab.user.whoami()))
    #dummy instance of phabapi
    phabm = phabmacros('', '', '')
    phabm.con = phab

    pmig = phabdb.phdb(db='fab_migration')
    tid, import_priority, header, com = pmig.sql_x("SELECT * FROM fab_meta WHERE id = %s", PHABTICKETID)
    pmig.close()

    log('priority: %d' % (import_priority,))

    tinfo = json.loads(header)
    comments = json.loads(com)

    proj_phids = []
    for pn in tinfo['xprojects']:
        proj_phids.append(phabm.ensure_project(pn))

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

    print 'Created', newticket['id']

    #0 {'text': 'comtask_com1', 'last_edit': 1409324924L, 'user': u'foo@wikimedia.org', 'created': 1409324924L}
    for k, v in comments.iteritems():
        created = epoch_to_datetime(v['created'])
        user = v['user'].split('@')[0]
        comment_body = "**%s** wrote on `%s`\n\n%s" % (user, created, v['text'])
        phabm.task_comment(newticket['id'], comment_body)
    return True

def run_fetch(fabid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db='fab_migration')
        import_priority = pmig.sql_x("SELECT priority FROM fab_meta WHERE id = %s", (fabid,))

        if import_priority:
            log('updating existing record')
            pmig.sql_x("UPDATE fab_meta SET priority=%s WHERE id = %s", (ipriority['creation_failed'],
                                                                         fabid))
        else:
            print "%s does not seem to exist" % (fabid)
        pmig.close()
        print 'failed to grab %s' % (fabid,)
        return False
    try:
        if fetch(fabid):
            print time.time()
            print 'done with %s' % (fabid,)
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (fabid, e)
        return run_fetch(fabid, tries=tries)


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
