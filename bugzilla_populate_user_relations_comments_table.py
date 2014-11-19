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
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import config
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import tflatten
from wmfphablib import return_bug_list


def populate(bugid):

    def add_comment_ref(owner):    
        """ adds an issue reference to a user or later updating their comments
        """
        ouser = pmig.sql_x("SELECT user FROM user_relations_comments WHERE user = %s", (owner,))
        if ouser:
            jcommed = pmig.sql_x("SELECT issues FROM user_relations_comments WHERE user = %s", (owner,))
            if jcommed and any(tflatten(jcommed)):
                issues = json.loads(jcommed[0][0])
            else:
                issues = []

            if bugid not in issues:
                log("Comment reference %s to %s" % (str(bugid), owner))
                issues.append(bugid)
            pmig.sql_x("UPDATE user_relations_comments SET issues=%s, modified=%s WHERE user = %s", (json.dumps(issues),
                                                                                                     now(),
                                                                                                     owner))
        else:
            issues = json.dumps([bugid])
            insert_values =  (owner,
                              issues,
                              now(),
                              now())

            pmig.sql_x("INSERT INTO user_relations_comments (user, issues, created, modified) VALUES (%s, %s, %s, %s)",
                       insert_values)

    pmig = phabdb.phdb(db=config.bzmigrate_db)
    issue = pmig.sql_x("SELECT id FROM bugzilla_meta WHERE id = %s", bugid)
    if not issue:
        log('issue %s does not exist for user population' % (bugid,))
        return True

    fpriority= pmig.sql_x("SELECT priority FROM bugzilla_meta WHERE id = %s", bugid)
    if fpriority[0] == ipriority['fetch_failed']:
        log('issue %s does not fetched successfully for user population (failed fetch)' % (bugid,))
        return True

    current = pmig.sql_x("SELECT comments, xcomments, modified FROM bugzilla_meta WHERE id = %s", bugid)
    if current:
        comments, xcomments, modified = current[0]
    else:
        log('%s not present for migration' % (bugid,))
        return True

    com = json.loads(comments)
    xcom = json.loads(xcomments)
    commenters = [c['author'] for c in com if c['count'] > 0]
    commenters = set(commenters)
    log("commenters for issue %s: %s" % (bugid, str(commenters)))
    for c in commenters:
        add_comment_ref(c)
    pmig.close()
    return True

def run_populate(bugid, tries=1):
    if tries == 0:
        elog('user relations comments failed to populate %s' % (bugid,))
        return False
    try:
        return populate(bugid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('user relations comments failed to populate %s' % (bugid,))
        return run_populate(bugid, tries=tries)

def main():
    bugs = return_bug_list()
    from multiprocessing import Pool
    pool = Pool(processes=10)
    _ =  pool.map(run_populate, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
