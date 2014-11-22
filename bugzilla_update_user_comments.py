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
from wmfphablib import util
from wmfphablib import bzlib
from wmfphablib import config
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import now
from wmfphablib import return_bug_list
from wmfphablib import ipriority


def update(user):

    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    phabm = phabmacros('', '', '')
    phabm.con = phab

    if phabdb.is_bot(user['userphid']):
        log("%s is a bot no action" % (user['user']))
        return True

    epriority = phabdb.get_user_relations_comments_priority(user['user'], pmig)
    if epriority and len(epriority[0]) > 0:
        if epriority[0][0] == ipriority['update_success']:
            log('Skipping %s as already updated' % (user['user']))
            return True

    if not user['issues']:
        log("%s has no issues to update" % (user['user'],))
        return True

    for i in user['issues']:
        comdetails = pmig.sql_x("SELECT comments, xcomments FROM bugzilla_meta WHERE id = %s", (int(i),))
        jcom, jxcom = comdetails[0]
        coms = json.loads(jcom)
        xcoms = json.loads(jxcom)

        for key, xi in xcoms.iteritems():
            com = coms[util.get_index(coms, "count", int(key))]
            content = com['text']

            if com['is_private']:
                vlog('is private')
                comment_content = bzlib.security_mask
            else:
                vlog('is NOT private')
                comment_content = content + xi['xattached']

            if com["creator"] == user['user']:
                log("Updating comment %s for %s" % (xi['xctransaction'], user['user']))
                phabdb.set_comment_author(xi['xctransaction'], user['userphid'])
                phabdb.set_comment_content(xi['xctransaction'], comment_content)

    current = phabdb.get_user_migration_comment_history(user['user'], pmig)
    if current:
        log(phabdb.set_user_relations_comments_priority(ipriority['update_success'], user['user'], pmig))
    else:
        log('%s user does not exist to update' % (user['user']))
        return False
    pmig.close()
    log(util.purge_cache())
    return True

def run_update(user, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)
        current = phabdb.get_user_migration_history(user['user'], pmig)
        if current:
           log(phabdb.set_user_relations_priority(ipriority['update_failed'], user['user'], pmig))
        else:
            log('%s user does not exist to update' % (user['user']))
        pmig.close()
        elog('final fail to update %s' % (user['user'],))
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

def get_user_histories(verified):
    histories = []
    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    for v in verified:
        vlog(str(v))
        saved_history = phabdb.get_user_migration_comment_history(v[1], pmig)
        if not saved_history:
            log('%s verified email has no saved history' % (v[1],))
            continue
        log('%s is being processed' % (v[1],))
        history = {}
        history['user'] = v[1]
        history['userphid'] = v[0]
        history['issues'] = saved_history[0]
        history['created'] = saved_history[1]
        history['modified'] = saved_history[2]
        histories.append(history)

    pmig.close()
    return [util.translate_json_dict_items(d) for d in histories]


def main():
    parser = argparse.ArgumentParser(description='Updates user header metadata from bugzilla')
    parser.add_argument('-a', action="store_true", default=False)
    parser.add_argument('-e', action="store", dest='email')
    parser.add_argument('-m', action="store", dest="starting_epoch", default=None)
    parser.add_argument('-v', action="store_true", default=False)
    args =  parser.parse_args()

    pmig = phabdb.phdb(db=config.bzmigrate_db,
                       user=config.bzmigrate_user,
                       passwd=config.bzmigrate_passwd)

    if args.a:
        starting_epoch = phabdb.get_user_relations_comments_last_finish(pmig)
        users, finish_epoch = phabdb.get_verified_users(starting_epoch, config.bz_updatelimit)
    elif args.email:
        users = phabdb.get_verified_user(args.email)
        starting_epoch = 0
        finish_epoch = 0
    elif args.starting_epoch:
        users, finish_epoch = phabdb.get_verified_users(args.starting_epoch)
        starting_epoch = args.starting_epoch
    else:
        parser.print_help()
        sys.exit(1)

    if not any(users):
        log("Existing as there are no new verified users")
        sys.exit()

    histories = get_user_histories(filter(bool, users))
    user_count = len(histories)

    icounts = []
    for u in histories:
        c = 0
        if u['issues']:
            c += len(u['issues'])
        icounts.append(c)
    issue_count = sum(icounts)

    log("User Count %s" % (str(user_count)))
    log("Issue Count %s" % (str(issue_count)))

    pid = os.getpid()
    source = util.source_name(sys.argv[0])
    phabdb.user_relations_start(pid,
                                source,
                                int(time.time()),
                                ipriority['na'],
                                starting_epoch,
                                user_count, issue_count, pmig)


    from multiprocessing import Pool

    pool = Pool(processes=int(config.bz_updatemulti))
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

    pm = phabmacros(config.phab_user, config.phab_cert, config.phab_host)
    vlog(util.update_blog(source, complete, failed, user_count, issue_count, pm))

    pmig.close()
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
