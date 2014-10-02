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
from wmfphablib import config
from wmfphablib import vlog
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import ipriority


def update(user):
    vlog(user)
    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    pmig = phabdb.phdb(db=config.fabmigrate_db,
                       user=config.fabmigrate_user,
                       passwd=config.fabmigrate_passwd)

    phabm = phabmacros('', '', '')
    phabm.con = phab

    epriority = phabdb.get_user_relations_priority(user['user'], pmig)
    if epriority and epriority[0] == ipriority['creation_success']:
        log('Skipping %s as already updated' % (user['user']))
        return True

    def sync_assigned(userphid, id):
        refs = phabdb.reference_ticket('fl%s' % (id,))
        if not refs:
            log('reference ticket not found for %s' % ('fl%s' % (id,),))
            return 
        current = phab.maniphest.query(phids=[refs[0]])
        if current[current.keys()[0]]['ownerPHID']:
            log('current owner found for => %s' % (str(id),))
            return current

        log('assigning %s to %s' % (str(id), userphid))
        return phab.maniphest.update(phid=refs[0], ownerPHID=userphid)


    def add_cc(userphid, id):
        refs = phabdb.reference_ticket('fl%s' % (id,))
        if not refs:
            log('reference ticket not found for %s' % ('fl%s' % (id,),))
            return
        current = phab.maniphest.query(phids=[refs[0]])
        cclist = current[current.keys()[0]]['ccPHIDs']
        cclist.append(userphid)
        log('updating cc list for issue %s with %s' % (str(id), userphid))
        return phab.maniphest.update(ccPHIDs=cclist, phid=refs[0])

    # 'author': [409, 410, 411, 404, 412],
    # 'cc': [221, 69, 203, 268, 261, 8],
    # 'created': 1410276037L,
    # 'modified': 1410276060L,
    # 'assigned': [97, 64, 150, 59, 6],
    # 'userphid': 'PHID-USER-4hsexplytovmqmcb7tq2',
    # 'user': u'chase.mp@xxx.com'}

    if user['assigned']:
        for ag in user['assigned']:
             vlog(sync_assigned(user['userphid'], ag))

    if user['author']:
        for a in user['author']:
            vlog(phabm.synced_authored(user['userphid'], a))

    if user['cc']:
        for ccd in user['cc']:
            vlog(add_cc(user['userphid'], ccd))

    current = phabdb.get_user_migration_history(user['user'], pmig)
    if current:
        log(phabdb.set_user_relations_priority(ipriority['update_success'], user['user'], pmig))
    else:
        log('%s user does not exist to update' % (user['user']))
        return False
    pmig.close()
    return True

def run_update(user, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.fabmigrate_db,
                       user=config.fabmigrate_user,
                       passwd=config.fabmigrate_passwd)
        current = phabdb.get_user_migration_history(user['user'], pmig)
        if current:
           log(phabdb.set_user_relations_priority(ipriority['update_failed'], user['user'], pmig))
        else:
            log('%s user does not exist to update' % (user['user']))
        pmig.close()
        log('final fail to update %s' % (user['user'],))
        return False
    try:
        if update(user):
            log('%s done with %s' % (str(int(time.time())), user,))
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        log('failed to update %s (%s)' % (user, e))
        return run_update(user, tries=tries)

def get_user_histories(verified):
    histories = []
    pmig = phabdb.phdb(db=config.fabmigrate_db,
                       user=config.fabmigrate_user,
                       passwd=config.fabmigrate_passwd)
    #print 'verified', verified
    for v in verified:
        vlog(str(v))
        # Get user history from old fab system
        saved_history = phabdb.get_user_migration_history(v[1], pmig)
        if not saved_history:
            log('%s verified email has no saved history' % (v[1],))
            continue
        log('%s is being processed' % (v[1],))
        history = {}
        history['user'] = v[1]
        history['userphid'] = v[0]
        history['assigned'] = saved_history[0]
        history['cc'] = saved_history[1]
        history['author'] = saved_history[2]
        history['created'] = saved_history[3]
        history['modified'] = saved_history[4]
        histories.append(history)

    # types of history are broken into a dict
    # many of these are json objects we need decode
    for i, user in enumerate(histories):
    #for email, item in histories.iteritems():
        for t in user.keys():
            if user[t]:
                try:
                    user[t] = json.loads(user[t])
                except (TypeError, ValueError):
                    pass
    pmig.close()
    return histories

def get_verified_users(modtime, limit=None):
    #Find the task in new Phabricator that matches our lookup
    verified = phabdb.get_verified_emails(modtime=modtime, limit=limit)
    create_times = [v[2] for v in verified]
    try:
        newest = max(create_times)
    except ValueError:
        newest = modtime
    return verified, newest

def get_verified_user(email):
    phid, email, is_verified = phabdb.get_user_email_info(email)
    log("Single verified user: %s, %s, %s" % (phid, email, is_verified))
    if is_verified:
        return [(phid, email)]
    else:
        log("%s is not a verified email" % (email,))
        return [()]

def last_finish():
    pmig = phabdb.phdb(db=config.fabmigrate_db,
                       user=config.fabmigrate_user,
                       passwd=config.fabmigrate_passwd)
    pmig.close()
    ftime = phabdb.get_user_relations_last_finish(pmig)
    return ftime or 1

def main():
    parser = argparse.ArgumentParser(description='Updates user metadata from fab')
    parser.add_argument('-a', action="store_true", default=False)
    parser.add_argument('-e', action="store", dest='email')
    parser.add_argument('-m', action="store", dest="starting_epoch", default=None)
    parser.add_argument('-v', action="store_true", default=False)
    args =  parser.parse_args()

    pmig = phabdb.phdb(db=config.fabmigrate_db,
                       user=config.fabmigrate_user,
                       passwd=config.fabmigrate_passwd)

    if args.a:
        starting_epoch = phabdb.get_user_relations_last_finish(pmig)
        users, finish_epoch = get_verified_users(starting_epoch, config.fab_limit)
    elif args.email:
        users = get_verified_user(args.email)
        starting_epoch = 0
        finish_epoch = 0
    elif args.starting_epoch:
        users, finish_epoch = get_verified_users(args.starting_epoch)
        starting_epoch = args.starting_epoch
    else:
        parser.print_help()
        sys.exit(1)


    histories = get_user_histories(users)
    user_count = len(histories)

    icounts = []
    for u in histories:
        c = 0
        if u['cc']:
            c += len(u['cc'])
        if u['author']:
            c += len(u['author'])
        if u['assigned']:
            c += len(u['assigned'])
        icounts.append(c)
    issue_count = sum(icounts)

    log("User Count %s" % (str(user_count)))
    log("Issue Count %s" % (str(issue_count)))

    if user_count == 0:
        log("Existing as there are no new verified users")
        sys.exit()


    pid = os.getpid()
    phabdb.user_relations_start(pid,
                                int(time.time()),
                                0,
                                starting_epoch,
                                user_count, issue_count, pmig)
    from multiprocessing import Pool
    pool = Pool(processes=config.fab_multi)
    _ =  pool.map(run_update, histories)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    phabdb.user_relations_finish(pid,
                                 int(time.time()),
                                 ipriority['update_success'],
                                 finish_epoch,
                                 complete,
                                 failed,
                                 pmig)
    print 'completed %s, failed %s' % (complete, failed)
    pmig.close()

if __name__ == '__main__':
    main()
