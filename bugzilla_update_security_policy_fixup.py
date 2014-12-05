#!/usr/bin/env python
import os
import argparse
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
from wmfphablib import bzlib
from wmfphablib import util
from wmfphablib import config
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import ipriority


def update(bid):

    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    pmig = phabdb.phdb(host=config.dbhost,
                       db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    phabm = phabmacros('', '', '')
    phabm.con = phab

    if phabdb.is_bz_security_issue(bid):
        phabdb.add_task_policy_users(bid, users=[userphid])
        print "%s IS SECURITY ISSUE" % (bid,)
        return True
    else:
        print "%s is _NOT_ A VALID ISSUE" % (bid,)
        return False
    pmig.close()

def run_update(bid, tries=1):
    if tries == 0:
        elog('final fail to update %s' % (str(bid),))
        return False
    try:
        return update(user)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to update %s' % (user,))
        return run_update(user, tries=tries)


def main():

    bugs = return_bug_list()
    results = []
    for b in bugs:
        results.append(run_update(b))
    complete = len(filter(bool, results))
    failed = len(results) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
