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
import ConfigParser


configfile = get_config_file()


def fetch(fabid):
    ausers = {}
    pmig = phabdb.phdb(db='fab_migration')
    issue = pmig.sql_x("SELECT id FROM fab_meta WHERE id = %s", fabid)

    if not issue:
        log('issue %s does not exist for user population' % (fabid,))
        return True

    fpriority= pmig.sql_x("SELECT priority FROM fab_meta WHERE id = %s", fabid)
    if fpriority[0] == ipriority['fetch_failed']:
        log('issue %s does not fetched successfully for user population (failed fetch)' % (fabid,))
        return True


    tid, import_priority, jheader, com, created, modified = pmig.sql_x("SELECT * FROM fab_meta WHERE id = %s", fabid)
    header = json.loads(jheader)
    vlog(str(header))
    relations = {}
    relations['author'] = header['xauthor']
    relations['cc'] = header['xccs']
    relations['owner'] = header['xowner']

    for k, v in relations.iteritems():
        if relations[k]:
            relations[k] = filter(bool, v)

    def add_owner(owner):    
        ouser = pmig.sql_x("SELECT user FROM user_relations WHERE user = %s", (owner,))
        if ouser:
            jassigned = pmig.sql_x("SELECT assigned FROM user_relations WHERE user = %s", (owner,))

            if jassigned[0]:
                assigned = json.loads(jassigned[0])
            else:
                assigned = []
            if fabid not in assigned:
                log("Assigning %s to %s" % (str(fabid), owner))
                assigned.append(fabid)
            vlog("owner %s" % (str(assigned),))
            pmig.sql_x("UPDATE user_relations SET assigned=%s, modified=%s WHERE user = %s", (json.dumps(assigned),
                                                                                              now(),
                                                                                              owner))
        else:
            vlog('inserting new record')
            assigned = json.dumps([fabid])
            insert_values =  (owner,
                              assigned,
                              now(),
                              now())

            pmig.sql_x("INSERT INTO user_relations (user, assigned, created, modified) VALUES (%s, %s, %s, %s)",
                       insert_values)


    def add_author(author):
        euser = pmig.sql_x("SELECT user FROM user_relations WHERE user = %s", (relations['author'],))
        if euser:
            jauthored = pmig.sql_x("SELECT author FROM user_relations WHERE user = %s", (relations['author'],))
            if jauthored[0]:
                authored = json.loads(jauthored[0])
            else:
               authored = []
            if fabid not in authored:
                authored.append(fabid)
            vlog("author %s" % (str(authored),))
            pmig.sql_x("UPDATE user_relations SET author=%s, modified=%s WHERE user = %s", (json.dumps(authored),
                                                                                        now(),
                                                                                        relations['author']))
        else:
            vlog('inserting new record')
            authored = json.dumps([fabid])
            insert_values =  (relations['author'],
                              authored,
                              now(),
                              now())
            pmig.sql_x("INSERT INTO user_relations (user, author, created, modified) VALUES (%s, %s, %s, %s)",
                       insert_values)


    def add_cc(ccuser):
        eccuser = pmig.sql_x("SELECT user FROM user_relations WHERE user = %s", (ccuser,))
        if eccuser:
            jcc = pmig.sql_x("SELECT cc FROM user_relations WHERE user = %s", (ccuser,))
            if jcc[0]:
               cc = json.loads(jcc[0])
            else:
               cc = []
            if fabid not in cc:
                cc.append(fabid)
            vlog("cc %s" % (str(cc),))
            pmig.sql_x("UPDATE user_relations SET cc=%s, modified=%s WHERE user = %s", (json.dumps(cc),
                                                                                        now(),
                                                                                        ccuser))
        else:
            vlog('inserting new record')
            cc = json.dumps([fabid])
            insert_values =  (ccuser,
                              cc,
                              now(),
                              now())
            pmig.sql_x("INSERT INTO user_relations (user, cc, created, modified) VALUES (%s, %s, %s, %s)",
                   insert_values)

    if relations['author']:
        add_author(relations['author'])

    if relations['owner']:
        add_owner(relations['owner'])

    if relations['cc']:
        for u in filter(bool, relations['cc']):
            add_cc(u)

    pmig.close()
    return True

def run_fetch(fabid, tries=1):
    if tries == 0:
        log('failed to populate for %s' % (fabid,))
        return False
    try:
        if fetch(fabid):
            vlog(str(time.time()))
            log('done with %s' % (fabid,))
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        log('failed to grab %s (%s)' % (fabid, e))
        return run_fetch(fabid, tries=tries)


bugs = return_bug_list()
vlog(bugs)
log("Count %s" % (str(len(bugs))))
from multiprocessing import Pool
pool = Pool(processes=10)
_ =  pool.map(run_fetch, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
