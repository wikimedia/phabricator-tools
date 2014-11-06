#!/usr/bin/env python
"""

Accepts two arguments:

    starting renumber int
     range [start-finish]

Resorts issues based on reference into a continuous series
"""

import sys
import os
import re
from wmfphablib import phdb
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import config
from wmfphablib import notice
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import bzlib
from wmfphablib import ipriority

def reorder(first, start, end, placeholder=300001):
    pmig = phdb(db=config.bzmigrate_db)
    # range of issues to renumber
    issues = range(int(start), int(end) + 1)
    first_issue = issues[0]
    # number to start new linear renumber at
    newid = int(first)
    print 'starting renumbering at %s with %s' % (first, first_issue)
    pphid = phabdb.get_task_phid_by_id(placeholder)
    if pphid:
        print "placeholder %s not empty (%s)" % (placeholder, pphid)
        return 

    for t in issues:
        print "Reassigning reference: %s to %s" % (t, newid)
        # Find PHID of the first ticket in our lineup
        ref = bzlib.prepend + str(t)
        phid = phabdb.reference_ticket(ref)
        if len(phid) > 1 or not phid:
            newid += 1
            print 'skipping phid %s' % (ref,)
            continue
        else:
            refphid = phid[0]
        print "Reference %s is %s" % (ref, refphid)
        tid = phabdb.get_task_id_by_phid(refphid)
        print "Reference %s is starting at id %s" % (ref, tid)
        existing_task = phabdb.get_task_phid_by_id(int(newid))
        print "Existing task returns %s" % (existing_task,)
        if existing_task:
            print "Squatter task at %s is %s" % (newid, existing_task)
            print "Moving squatter %s to %s" % (existing_task, placeholder)
            phabdb.set_task_id(placeholder, existing_task)      
        phabdb.set_task_id(newid, refphid)
        if existing_task:
            print "fixup setting squatter %s to %s" % (existing_task, tid)
            phabdb.set_task_id(tid, existing_task)
        newid += 1

def main():
    first = sys.argv[1]
    if '-' in sys.argv[2]:
        start, end = sys.argv[2].split('-')
    else:
        start = sys.argv[2]
        end = sys.argv[2]

    reorder(first, start, end)
if __name__ == '__main__':
    main()
