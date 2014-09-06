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
from wmfphablib import fablib
import ConfigParser

configfile = get_config_file()

def comments_by_task(taskphid):
    #get the comment transactions by task
    coms =  phabdb.comment_transactions_by_task_phid(taskphid)
    final_comments = {}
    if not coms:
        return {}
    for i, c in enumerate(coms):
        comdetail = {}
        log('looking for email by user phid: %s' % (c[2],))
        comdetail['xuserphid'] = c[2]
        comdetail['xuseremail'] = phabdb.email_by_userphid(c[2])
        #for a comment transaction get all records (edits, etc)
        content = phabdb.comment_by_transaction(c[1])
        if len(content) > 1:
            iter = 0
            comver = 0
            while 1:
                if iter == len(content):
                    break
                for edit in content:
                    if edit[6] > comver:
                        comver = edit[6]
                        comdetail['text'] = edit[7]
                        comdetail['created'] = edit[10]
                        comdetail['last_edit'] = edit[11]
                iter += 1
        else:
            fcomment = phabdb.comment_by_transaction(c[1])[0]
            comdetail['text'] = fcomment[7]
            comdetail['created'] = fcomment[10]
            comdetail['last_edit'] = fcomment[11]

        final_comments[i] = comdetail

    return final_comments

def fetch(PHABTICKETID):

    PHABTICKETID = int(PHABTICKETID)

    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'oldfab'
    parser.read(configfile)
    oldfab = Phabricator(parser.get(parser_mode, 'user'),
                         parser.get(parser_mode, 'cert'),
                         parser.get(parser_mode, 'host'))

    log(str(oldfab.user.whoami()))

    #dummy instance of phabapi
    phabm = phabmacros('', '', '')
    #assign newphab instance as self.con for dummyphab
    phabm.con = oldfab

    """
    <Result: {u'authorPHID': u'PHID-USER-qbtllnzb6pwl3ttzqa3m',
                   u'status': u'open',
                     u'phid': u'PHID-TASK-qr3fpbtk6kdx4slhgnsd',
              u'description': u'',
               u'objectName': u'T10',
                    u'title': u'Get icinga alerts into logstash',
            u'priorityColor': u'red',
       u'dependsOnTaskPHIDs': [],
                u'auxiliary': [],
                      u'uri': u'http://fab.wmflabs.org/T10',
                  u'ccPHIDs': [u'PHID-USER-qbtllnzb6pwl3ttzqa3m'],
                 u'isClosed': False,
             u'dateModified': u'1399311492',
                u'ownerPHID': None,
               u'statusName': u'Open',
              u'dateCreated': u'1391716779',
             u'projectPHIDs': [u'PHID-PROJ-5ncvaivs3upngr7ijqy2'],
                       u'id': u'10',
                 u'priority': u'High'}>
    """

    tinfo = oldfab.maniphest.info(task_id=PHABTICKETID).response
    log(tinfo)

    comments = comments_by_task(tinfo['phid'])
    for i, c in comments.iteritems():
        comments[i]['xcommenter'] = dict(oldfab.user.info(phid=c['xuserphid']))
    ordered_comments =  collections.OrderedDict(sorted(comments.items()))
    log(str(ordered_comments))

    """
    <Result: {u'userName': u'bd808',
                  u'phid': u'PHID-USER-qbtllnzb6pwl3ttzqa3m',
              u'realName': u'Bryan Davis',
                 u'roles': [u'admin',u'verified', u'approved', u'activated'],
                 u'image': u'http://fab.wmflabs.org/file/data/fijwoqt62w6atpond4vb/PHID-FILE-37htsfegn7bnlfvzwsts/profile-profile-gravatar',
                   u'uri': u'http://fab.wmflabs.org/p/bd808/'}>
    """

    authorInfo = oldfab.user.info(phid=tinfo['authorPHID'])
    tinfo['xauthor'] = phabdb.email_by_userphid(authorInfo['phid'])
    log('author: ' + tinfo['xauthor'])

    ccs = []
    if tinfo['ccPHIDs']:
        for c in tinfo['ccPHIDs']:
            ccInfo = oldfab.user.info(phid=c)
            ccs.append(phabdb.email_by_userphid(ccInfo['phid']))
    tinfo['xccs'] = ccs
    log('ccs: ' + str(ccs))

    if tinfo['ownerPHID']:
        tinfo['xowner'] = phabdb.email_by_userphid(tinfo['ownerPHID'])
    else:
        tinfo['xowner'] = None

    """
    u'data':
      {u'PHID-PROJ-5ncvaivs3upngr7ijqy2':
        {u'phid': u'PHID-PROJ-5ncvaivs3upngr7ijqy2',
         u'name': u'logstash',
    u'dateCreated': u'1391641549',
      u'members': [u'PHID-USER-65zhggegfvhojb4nynay'],
           u'id': u'3',
    u'dateModified': u'1398282408',
        u'slugs': [u'logstash']}}, u'slugMap': []}>
    """

    project_names = []
    associated_projects = tinfo['projectPHIDs']

    log('associated projects: %s' % (str(tinfo['projectPHIDs'])))
    #if we try to query for an empty list we get back ALLLLLL
    if associated_projects:
        pinfo = oldfab.project.query(phids=associated_projects)
        for p in pinfo['data'].values():
            project_names.append(p['name'])

    saved_projects = [p in fablib.saved for p in project_names]
    if not any(saved_projects):
        print "Skipping %s as it's not in a saved project" % (PHABTICKETID)
        return

    log('project names: ' + str(project_names))
    tinfo['xprojects'] = project_names

    status = tinfo['status']
    if status != 'open':
        creation_priority = ipriority['na']
    else:
        creation_priority = ipriority['unresolved']


    blocked_tasks = phabdb.get_tasks_blocked('PHID-TASK-llxzmfbbcc4adujigg4w')
    tinfo['blocked_tasks'] = blocked_tasks

    pmig = phabdb.phdb(db='fab_migration')
    current = pmig.sql_x("SELECT * from fab_meta where id = %s", PHABTICKETID)
    if current:
        log('updating current record')
        update_values = (creation_priority,
                         json.dumps(tinfo),
                         json.dumps(comments),
                         now(),
                         PHABTICKETID)
        pmig.sql_x("UPDATE fab_meta SET priority=%s, header=%s, comments=%s, modified=%s WHERE id = %s",
                    update_values)
    else:
        log('inserting new record')
        insert_values =  (PHABTICKETID,
                          creation_priority,
                          json.dumps(tinfo),
                          json.dumps(comments),
                          now(),
                          now())

        pmig.sql_x("INSERT INTO fab_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)",
                   insert_values)
    pmig.close()
    return True

def run_fetch(fabid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db='fab_migration')
        import_priority = pmig.sql_x("SELECT priority FROM fab_meta WHERE id = %s", (fabid,))
        if import_priority:
            log('updating existing record')
            pmig.sql_x("UPDATE fab_meta SET priority=%s modified=%s WHERE id = %s", (ipriority['fetch_failed'],
                                                                                    now(),
                                                                                    fabid))
        else:
            insert_values =  (fabid, ipriority['fetch_failed'], 'nan', 'nan', now(), now())
            pmig.sql_x("INSERT INTO fab_meta (id, priority, header, comments, created, modified) VALUES (%s, %s, %s, %s, %s, %s)",
                   insert_values)
        pmig.close()
        print 'failed to grab %s' % (fabid,)
        return False
    try:
        if fetch(fabid):
            print time.time()
            print 'done with %s' % (fabid,)
            return True
    except Exception as e:
        tries -= 1
        time.sleep(5)
        import traceback
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (fabid, e)
        return run_fetch(fabid, tries=tries)


if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

bugs = [i for i in bugs if i.isdigit()]
print len(bugs)
from multiprocessing import Pool
pool = Pool(processes=10)
_ =  pool.map(run_fetch, bugs)
complete = len(filter(bool, _))
failed = len(_) - complete
print 'completed %s, failed %s' % (complete, failed)
