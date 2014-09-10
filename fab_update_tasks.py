import sys
import time
import json
import multiprocessing
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import fablib
from wmfphablib import ipriority


def update(id):
    fabdb = phabdb.phdb(db='fab_migration')

    epriority = fabdb.sql_x("SELECT priority from task_relations where id = %s", id)
    if epriority and epriority[0] == ipriority['creation_success']:
        log('Skipping %s as blockers already updated' % (id,))
        return True

    hq = "SELECT header FROM fab_meta WHERE id = %s"
    header = fabdb.sql_x(hq, (id,))
    if not header:
       vlog('no header found for %s' % (id,))
       return True

    def extref(ticket):
        refid = phabdb.reference_ticket("%s%s" % (fablib.prepend, ticket))
        if not refid:
            return ''
        return refid[0]

    blocker_ref = extref(id)
    tinfo = json.loads(header[0])
    vlog(tinfo)
    for b in tinfo['xblocking']:
        blocked_ref = extref(b)
        log("%s is blocking %s" % (blocker_ref, blocked_ref))
        if blocked_ref:
            log(phabdb.set_blocked_task(blocker_ref, blocked_ref))
        else:
            log('%s is missing blocker %s' % (blocked_ref, blocker_ref))

    blocks = phabdb.get_tasks_blocked(blocker_ref)
    log('%s is blocking %s' % (blocker_ref, str(blocks)))
    current = fabdb.sql_x("SELECT * from task_relations where id = %s", id)
    if current:
        fabdb.sql_x("UPDATE task_relations SET priority=%s, blocks=%s, modified=%s WHERE id = %s",
                   (ipriority['creation_success'], json.dumps(blocks), now(), id))
    else:
        sql = "INSERT INTO task_relations (id, priority, blocks, modified) VALUES (%s, %s, %s, %s)"
        fabdb.sql_x(sql, (id, ipriority['creation_success'], json.dumps(blocks), now()))
    fabdb.close()
    return True
 

def run_update(fabid, tries=1):
    if tries == 0:
        log('final fail to grab %s' % (fabid,))
        pmig = phabdb.phdb(db='fab_migration')
        current = pmig.sql_x("SELECT * from task_relations where id = %s", fabid)
        if current:
            pmig.sql_x("UPDATE task_relations SET priority=%s, blocks=%s, modified=%s WHERE id = %s",
                      (ipriority['creation_failed'], json.dumps([]), now(), fabid))
        else:
            sql = "INSERT INTO task_relations (id, priority, blocks, modified) VALUES (%s, %s, %s, %s)"
            pmig.sql_x(sql, (fabid, ipriority['creation_failed'], json.dumps([]), now()))
        pmig.close()
        return False
    try:
        if update(fabid):
            log('%s done with %s' % (str(int(time.time())), fabid,))
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        log('failed to grab %s (%s)' % (fabid, e))
        return run_update(fabid, tries=tries)



bugs = return_bug_list()
log("Count %s" % (str(len(bugs))))
from multiprocessing import Pool
pool = Pool(processes=2)
_ =  pool.map(run_update, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
