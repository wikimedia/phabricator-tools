import sys
import collections
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import epoch_to_datetime

def comments_by_task(taskphid):
    #get the comment transactions by task
    coms =  phabdb.comment_transactions_by_task_phid(taskphid)
    final_comments = {}
    if not coms:
        return {}
    for i, c in enumerate(coms):
        print c
        comdetail = {}
        comdetail['user'] = phabdb.email_by_userphid(c[2])
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

def main(PHABTICKETID):

    phab = Phabricator(username='Rush',
                   certificate="7xboqo5pc6ubg6s37raf5fvmw4ltwg2eu4brh23k5fskgegkcbojix44r2rtt6eter3sktkly3vqspmfjy2n6kjzsis63od2ns7ayek3xby5xlyydczc3rhrtdb3xugkgfg3dxrbvnxjw3jnzmdm6cf3mpmca3hsfrf7aujbufimh3lk4u6uz4nefukarwsefkbccjfgn7gmuxeueouh4ldehvwdcvakbxmrmdri3stgw5sfvukib4yngf23etp",
                   host = "http://fabapitest.wmflabs.org/api/")
    log(str(phab.user.whoami()))

    #mock new phab for future
    newphab = phab
    #dummy instance of phabapi
    phabm = phabmacros('', '', '')
    #assign newphab instance as self.con for dummyphab
    phabm.con = newphab

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

    tinfo = phab.maniphest.info(task_id=PHABTICKETID)
    comments = comments_by_task(tinfo['phid'])
    ordered_comments =  collections.OrderedDict(sorted(comments.items()))
    log(tinfo)

    """
    <Result: {u'userName': u'bd808',
                  u'phid': u'PHID-USER-qbtllnzb6pwl3ttzqa3m',
              u'realName': u'Bryan Davis',
                 u'roles': [u'admin',u'verified', u'approved', u'activated'],
                 u'image': u'http://fab.wmflabs.org/file/data/fijwoqt62w6atpond4vb/PHID-FILE-37htsfegn7bnlfvzwsts/profile-profile-gravatar',
                   u'uri': u'http://fab.wmflabs.org/p/bd808/'}>
    """

    authorInfo = phab.user.info(phid=tinfo['authorPHID'])
    author = phabdb.email_by_userphid(authorInfo['phid'])
    log('author: ' + author)

    ccs = []
    if tinfo['ccPHIDs']:
        for c in tinfo['ccPHIDs']:
            ccInfo = phab.user.info(phid=c)
            ccs.append(phabdb.email_by_userphid(ccInfo['phid']))
    log('ccs: ' + str(ccs))

    priorities = {"Unbreak Now!": 100,
                  "Needs Triage": 90,
                  "High": 80,
                  "Normal": 50,
                  "Low": 25,
                  "Needs Volunteer": 10}

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
    #if we try to query for an empty list we get back ALLLLLL
    if associated_projects:
        pinfo = phab.project.query(phids=associated_projects)
        for p in pinfo['data'].values():
            project_names.append(p['name'])

    log('project names: ' + str(project_names))

    proj_phids = []
    for pn in project_names:
        proj_phids.append(phabm.ensure_project(pn))

    #            "ccPHIDs": "optional list<phid>",
    #            "ownerPHID": "optional phid",
    #            "projectPHIDs": "optional list<phid>",
    newticket =  newphab.maniphest.createtask(title=tinfo['title'],
                                 description=tinfo['description'],
                                 projectPHIDs=proj_phids,
                                 priority=priorities[tinfo['priority']],
                                 auxiliary={"std:maniphest:external_reference":"fl%s" % (PHABTICKETID,)})

    print 'Created', newticket['id']

    #0 {'text': 'comtask_com1', 'last_edit': 1409324924L, 'user': u'foo@wikimedia.org', 'created': 1409324924L}
    for k, v in ordered_comments.iteritems():
        created = epoch_to_datetime(v['created'])
        comment_body = "**%s** wrote on `%s`\n\n%s" % (v['user'], created, v['text'])
        phabm.task_comment(newticket['id'], comment_body)

main(int(sys.argv[1]))
