import sys
import time
import json
import multiprocessing
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import now


def fetch(id):
    fabdb = phabdb.phdb(db='fab_migration')
    hq = "SELECT header FROM fab_meta WHERE id = %s"
    header = fabdb.sql_x(hq, (id,))
    if not header:
       print 'nope'
       return
    tinfo = json.loads(header[0])
    blockerphid =  tinfo['phid']
    for b in tinfo['blocked_tasks']:
        log(phabdb.set_tasks_blocked(blockerphid, b))

    blocks = phabdb.get_tasks_blocked(blockerphid)
    pmig = phabdb.phdb(db='fab_migration')
    current = pmig.sql_x("SELECT * from task_relations where id = %s", id)
    if current:
        pmig.sql_x("UPDATE task_relations SET blocks=%s, modified=%s WHERE id = %s",
                   (json.dumps(blocks), now(), id))
    else:
        sql = "INSERT INTO task_relations (id, blocks, modified) VALUES (%s, %s, %s)"
        pmig.sql_x(sql, (id, json.dumps(blocks), now()))
    pmig.close()
fetch(sys.argv[1])
