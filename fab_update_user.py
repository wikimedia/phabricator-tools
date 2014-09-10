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
from wmfphablib import ipriority
import ConfigParser


configfile = get_config_file()


def update(user):
    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read(configfile)
    phab = Phabricator(parser.get(parser_mode, 'username'),
                       parser.get(parser_mode, 'certificate'),
                       parser.get(parser_mode, 'host'))

    pmig = phabdb.phdb(db='fab_migration')
    phabm = phabmacros('', '', '')
    phabm.con = phab

    epriority = pmig.sql_x("SELECT priority from user_relations where user = %s", user['user'])
    if epriority and epriority[0] == ipriority['creation_success']:
        log('Skipping %s as already updated' % (user['user']))
        return True

    def sync_assigned(userphid, id):
        refs = phabdb.reference_ticket('fl%s' % (id,))
        if not refs:
            log('reference ticket not found for %s' % ('fl%s' % (id,),))
            return 
        return phab.maniphest.update(phid=refs[0], ownerPHID=userphid)

    def add_cc(userphid, id):
        refs = phabdb.reference_ticket('fl%s' % (id,))
        if not refs:
            log('reference ticket not found for %s' % ('fl%s' % (id,),))
            return
        current = phab.maniphest.query(phids=[refs[0]])
        cclist = current[current.keys()[0]]['ccPHIDs']
        cclist.append(userphid)
        return phab.maniphest.update(ccPHIDs=cclist, phid=refs[0])

    #'author': [409, 410, 411, 404, 412, 458, 405, 406, 444, 407, 408], 'cc': [97, 20, 37, 115, 62, 93, 146, 135, 12, 63, 55, 159, 138, 96, 65, 40, 195, 142, 150, 229, 68, 42, 166, 221, 69, 203, 268, 261, 244, 208, 269, 225, 277, 47, 294, 226, 270, 252, 316, 227, 279, 363, 334, 228, 364, 335, 365, 321, 338, 336, 409, 274, 322, 422, 347, 449, 410, 434, 359, 423, 402, 348, 435, 411, 457, 436, 404, 458, 437, 431, 412, 432, 440, 284, 405, 442, 444, 406, 417, 407, 408], 'created': 1410276037L, 'modified': 1410276060L, 'assigned': [97, 64, 150, 59, 69, 261, 294, 330, 334, 364, 409, 336, 410, 402, 423, 411, 457, 412, 405, 432, 440, 406, 407, 408], 'userphid': 'PHID-USER-4hsexplytovmqmcb7tq2', 'user': u'chase.mp@gmail.com'}
    if user['assigned']:
        for ag in user['assigned']:
             vlog(sync_assigned(user['userphid'], ag))

    if user['author']:
        for a in user['author']:
            vlog(phabm.synced_authored(user['userphid'], a))

    if user['cc']:
        for ccd in user['cc']:
            vlog(add_cc(user['userphid'], ccd))

    current = pmig.sql_x("SELECT * from user_relations where user = %s", user['user'])
    if current:
        pmig.sql_x("UPDATE user_relations SET priority=%s, modified=%s WHERE user = %s",
                  (ipriority['creation_success'], now(), user['user']))
    else:
        log('%s user does not exist to update' % (user['user']))
        return False
    pmig.close()
    return True

def run_update(user, tries=1):
    if tries == 0:
        email = user['user']
        pmig = phabdb.phdb(db='fab_migration')
        current = pmig.sql_x("SELECT * from user_relations where user = %s", email)
        if current:
            pmig.sql_x("UPDATE user_relations SET priority=%s, modified=%s WHERE user = %s",
                      (ipriority['creation_failed'], now(), email))
        else:
            log('%s user does not exist to update' % (email))
        pmig.close()
        log('final fail to update %s' % (user,))
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
    pmig = phabdb.phdb(db='phabricator_user')
    histories = []
    fabdb = phabdb.phdb(db='fab_migration')
    for v in verified:
        vlog(str(v))
        # Get user history from old fab system
        hq = "SELECT assigned, cc, author, created, modified FROM user_relations WHERE user = %s"
        saved_history = fabdb.sql_x(hq, (v[1],))
        if not saved_history:
            log('%s verified email has no saved history' % (v[1],))
            continue
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

def get_users(modtime):
    pmig = phabdb.phdb(db='phabricator_user')
    #Find the task in new Phabricator that matches our lookup
    verified = phabdb.get_verified_emails(modtime=modtime)
    return verified

def get_verified_user(email):
    phid, email, is_verified = phabdb.get_user_email_info(email)
    if is_verified:
        return phid, email
    else:
        log("%s is not a verified email" % (email,))
        return ()

if '@' in sys.argv[1]:
    users = get_verified_user(sys.argv[1])
else:
    users = get_users(sys.argv[1])

histories = get_user_histories(users)
log("Count %s" % (str(len(histories))))
from multiprocessing import Pool
pool = Pool(processes=2)
_ =  pool.map(run_update, histories)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
