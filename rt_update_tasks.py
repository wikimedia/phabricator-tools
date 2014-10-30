#!/usr/bin/env python
import sys
import time
import json
import multiprocessing
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import rtlib
from wmfphablib import ipriority
from wmfphablib import config


def update(bugid):

    pmig = phabdb.phdb(db=config.rtmigrate_db)

    epriority = pmig.sql_x("SELECT priority \
                            from task_relations \
                            where id = %s", bugid)

    if epriority and epriority[0] == ipriority['update_success']:
        log('skipping %s as blockers already updated' % (bugid,))
        return True

    query = "SELECT header FROM rt_meta WHERE id = %s"
    header = pmig.sql_x(query, (bugid,))
    if not header:
       elog('no header found for %s' % (bugid,))
       return False

    def extref(ticket):
        refid = phabdb.reference_ticket("%s%s" % (rtlib.prepend, ticket))
        if not refid:
            return ''
        return refid[0]

    blocker_ref = extref(bugid)
    tinfo = json.loads(header[0][0])

    if 'blocks' not in tinfo['links']:
        log("%s doesn't block anything" % (str(bugid),))
        return True

    for b in tinfo['links']['blocks']:
        blocked_ref = extref(b)
        log("%s is blocking %s" % (blocker_ref,
                                   blocked_ref))
        if blocked_ref:
            log(phabdb.set_blocked_task(blocker_ref,
                                        blocked_ref))
        else:
            log('%s is missing blocker %s' % (blocked_ref,
                                              blocker_ref))

    blocks = phabdb.get_tasks_blocked(blocker_ref)
    vlog('%s is blocking %s' % (blocker_ref, str(blocks)))
    current = pmig.sql_x("SELECT * \
                          from task_relations \
                          WHERE id = %s", bugid)
    if current:
        pmig.sql_x("UPDATE task_relations \
                    SET priority=%s, blocks=%s, modified=%s \
                    WHERE id = %s",
                    (ipriority['update_success'],
                    json.dumps(blocks),
                    now(), bugid))
    else:
        sql = "INSERT INTO task_relations \
               (id, priority, blocks, modified) \
               VALUES (%s, %s, %s, %s)"
        pmig.sql_x(sql, (bugid, ipriority['update_success'],
                   json.dumps(blocks), now()))
    pmig.close()
    return True
 

def run_update(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.rtmigrate_db)
        current = pmig.sql_x("SELECT * from \
                              task_relations \
                              where id = %s", bugid)
        if current:
            pmig.sql_x("UPDATE task_relations \
                        SET priority=%s, \
                        blocks=%s, \
                        modified=%s \
                        WHERE id = %s",
                        (ipriority['creation_failed'],
                        json.dumps([]), now(), bugid))
        else:
            sql = "INSERT INTO task_relations \
                   (id, priority, blocks, modified) \
                   VALUES (%s, %s, %s, %s)"
            pmig.sql_x(sql, (bugid,
                             ipriority['creation_failed'],
                             json.dumps([]),
                             now()))
        pmig.close()
        elog('final fail to update %s' % (bugid,))
        return False
    try:
        return update(bugid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to update %s' % (bugid,))
        return run_update(bugid, tries=tries)

def main():
    bugs = return_bug_list()
    from multiprocessing import Pool
    pool = Pool(processes=int(config.bz_updatemulti))
    _ =  pool.map(run_update, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
