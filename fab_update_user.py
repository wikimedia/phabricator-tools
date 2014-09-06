import time
import json
import multiprocessing
import sys
import collections
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from wmfphablib import get_config_file
from wmfphablib import now
import ConfigParser


configfile = get_config_file()


def fetch():
    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read(configfile)
    phab = Phabricator(parser.get(parser_mode, 'username'),
                       parser.get(parser_mode, 'certificate'),
                       parser.get(parser_mode, 'host'))
    phabm = phabmacros('', '', '')
    phabm.con = phab

    pmig = phabdb.phdb(db='phabricator_user')
    #Find the task in new Phabricator that matches our lookup
    verified = phabdb.get_verified_emails(modtime=0)
    histories = {}
    fabdb = phabdb.phdb(db='fab_migration')
    hq = "SELECT assigned, cc, author, created, modified FROM user_relations WHERE user = %s"
    for v in verified:
        log(str(v))
        # Get user history from old fab system
        uh = fabdb.sql_x(hq, (v[1],))
        if not uh:
            continue
        histories[v[1]] = {}
        histories[v[1]]['userphid'] = v[0]
        histories[v[1]]['assigned'] = uh[0]
        histories[v[1]]['cc'] = uh[1]
        histories[v[1]]['author'] = uh[2]
        histories[v[1]]['created'] = uh[3]
        histories[v[1]]['modified'] = uh[4]

    # types of history are broken into a dict
    # many of these are json objects we need decode
    for email, item in histories.iteritems():
        for t in item.keys():
            if item[t]:
                try:
                    item[t] = json.loads(item[t])
                except (TypeError, ValueError):
                    pass

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


    # joeuseremail@test.com
    #   {'assigned': u'["25"]',
    #    'cc': u'["25", "15"]', 
    #    'created': 1409880643L, 
    #    'modified': 1409880647L,
    #    'author': u'["25"]'}
    for user, history in histories.iteritems():
        if history['assigned']:
            for ag in history['assigned']:
                 sync_assigned(history['userphid'], ag)

        if history['author']:
            for a in history['author']:
                phabm.synced_authored(history['userphid'], a)

        if history['cc']:
            for ccd in history['cc']:
                add_cc(history['userphid'], ccd)

    pmig.close()
    return True

fetch()
