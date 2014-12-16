#!/usr/bin/env python
import time
import json
import multiprocessing
import sys
import collections
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import rtlib
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import config
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import tflatten
from wmfphablib import return_bug_list


def populate(rtid):

    pmig = phabdb.phdb(db=config.rtmigrate_db,
                       user=config.rtmigrate_user,
                       passwd=config.rtmigrate_passwd)

    issue = pmig.sql_x("SELECT id FROM rt_meta WHERE id = %s", rtid)
    if not issue:
        log('issue %s does not exist for user population' % (rtid,))
        return 'missing'

    fpriority= pmig.sql_x("SELECT priority FROM rt_meta WHERE id = %s", rtid)
    if fpriority[0] == ipriority['fetch_failed']:
        log('issue %s does not fetched successfully for user population (failed fetch)' % (rtid,))
        return True

    current = pmig.sql_x("SELECT priority, header, comments, created, modified FROM rt_meta WHERE id = %s", rtid)
    if current:
        import_priority, buginfo, com, created, modified = current[0]
    else:
        log('%s not present for migration' % (rtid,))
        return True

    header = json.loads(buginfo)
    vlog(str(header))
    relations = {}
    relations['author'] = rtlib.user_lookup(header["Creator"])
    ccusers = header['AdminCc'].split(',') + header['Cc'].split(',')
    relations['cc'] = ccusers
    relations['cc'] = [cc.strip() for cc in relations['cc'] if cc]
    # RT uses a literal nobody for no assigned
    if header['Owner'] == 'Nobody':
        relations['owner'] = ''
    else:
        relations['owner'] = rtlib.user_lookup(header['Owner'])

    for k, v in relations.iteritems():
        if relations[k]:
            relations[k] = filter(bool, v)

    def add_owner(owner):
        ouser = pmig.sql_x("SELECT user FROM user_relations WHERE user = %s", (owner,))
        if ouser:
            jassigned = pmig.sql_x("SELECT assigned FROM user_relations WHERE user = %s", (owner,))
            jflat = tflatten(jassigned)
            if any(jflat):
                assigned = json.loads(jassigned[0][0])
            else:
                assigned = []
            if rtid not in assigned:
                log("Assigning %s to %s" % (str(rtid), owner))
                assigned.append(rtid)
            vlog("owner %s" % (str(assigned),))
            pmig.sql_x("UPDATE user_relations SET assigned=%s, modified=%s WHERE user = %s", (json.dumps(assigned),
                                                                                              now(),
                                                                                              owner))
        else:
            vlog('inserting new record')
            assigned = json.dumps([rtid])
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
            jflat = tflatten(jauthored)
            if any(jflat):
                authored = json.loads(jauthored[0][0])
            else:
               authored = []
            if rtid not in authored:
                authored.append(rtid)
            vlog("author %s" % (str(authored),))
            pmig.sql_x("UPDATE user_relations SET author=%s, modified=%s WHERE user = %s", (json.dumps(authored),
                                                                                        now(),
                                                                                        relations['author']))
        else:
            vlog('inserting new record')
            authored = json.dumps([rtid])
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
            jflat = tflatten(jcc)
            if any(jflat):
               cc = json.loads(jcc[0][0])
            else:
               cc = []
            if rtid not in cc:
                cc.append(rtid)
            vlog("cc %s" % (str(cc),))
            pmig.sql_x("UPDATE user_relations SET cc=%s, modified=%s WHERE user = %s", (json.dumps(cc),
                                                                                        now(),
                                                                                        ccuser))
        else:
            vlog('inserting new record')
            cc = json.dumps([rtid])
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

def run_populate(rtid, tries=1):
    if tries == 0:
        elog('failed to populate for %s' % (rtid,))
        return False
    try:
        return populate(rtid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to populate %s (%s)' % (rtid, e))
        return run_populate(rtid, tries=tries)

def main():
    bugs = return_bug_list()
    result = []
    for b in bugs:
        result.append(run_populate(b))

    missing = len([i for i in result if i == 'missing'])
    complete = len(filter(bool, [i for i in result if i not in ['missing']]))
    failed = (len(result) - missing) - complete
    print '-----------------------------\n \
          %s Total %s (missing %s)\n \
          completed %s, failed %s' % (sys.argv[0],
                                                          len(bugs),
                                                          missing,
                                                          complete,
                                                          failed)

if __name__ == '__main__':
    main()

