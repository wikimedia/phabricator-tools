from cStringIO import StringIO
import ast
import base64
import json
import datetime
import sys
import xmlrpclib
import subprocess
import os
import re
import MySQLdb
from email.parser import Parser
import ConfigParser

from phabricator import Phabricator

def log(msg):
    import syslog
    msg = unicode(msg)
    if '-v' in sys.argv:
        try:
            syslog.syslog(msg)
            print '-> ', msg
        except:
            print 'error logging output'

def main(bugid):


    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read('/etc/gz_fetch.conf')
    phab = Phabricator(username=parser.get(parser_mode, 'username'),
                   certificate=parser.get(parser_mode, 'certificate'),
                   host=parser.get(parser_mode, 'host'))

    parser_mode = 'bz'
    server = xmlrpclib.ServerProxy(parser.get(parser_mode, 'url'), use_datetime=True)
    kwargs = { 'ids': [bugid],
               'Bugzilla_login': parser.get(parser_mode, 'Bugzilla_login'),
               'Bugzilla_password': parser.get(parser_mode, 'Bugzilla_password')}


    # 'names'               => 'optional list<string>',
    #print phab.project.query(names=['mediawiki-documentation'])

    def priority_convert(bz_priority):

        rank = {'unprioritized': 90,
                  'immediate':	100,
                  'highest':    100,
                  'high': 	80,
                  'normal':     50,
                  'low': 	25,
                  'lowest':	0}

        return rank[bz_priority.lower()]


    def comment(task, msg):
        out = phab.maniphest.update(id=task, comments=msg)
        log(out)
        return out

    def set_status(task, status):
        out = phab.maniphest.update(id=task, status=status)
        log(out)
        return out

    def create(title, desc, id, projects, priority):
        out = phab.maniphest.createtask(title=title,
                                        description="%s" % desc,
                                        projectPHIDs=[projects],
                                        priority=priority,
                                        auxiliary={"std:maniphest:external_id":"%s" % (id,)})
        log(out)
        return out

    def datetime_to_epoch(date_time):
        return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

    def epoch_to_datetime(epoch):
        import datetime
        return (datetime.datetime.fromtimestamp(int(float(epoch))
               ).strftime('%Y-%m-%d %H:%M:%S'))

    def status_convert(bz_status):
        """
        UNCONFIRMED (default)	Open + Needs Triage (default)
        NEW	Open
        ASSIGNED	        open
        PATCH_TO_REVIEW	        open
        NEED_INFO	        needs_info
        RESOLVED FIXED	        resolved
        RESOLVED INVALID	invalid
        RESOLVED WONTFIX	declined
        RESOLVED WORKSFORME	resolved
        RESOLVED DUPLICATE	closed

        needs_info	stalled
        resolved	closed
        invalid	        no historical value will be purged eventually (spam, etc)
        declined	we have decided not too -- even though we could
        """

        # XXX: verified gets verified project
        statuses = {'new': 'open',
                    'resolved': 'resolved',
                    'reopened': 'open',
                    'closed': 'resolved',
                    'need_info': 'needs_info',
                    'verified': 'resolved',
                    'assigned': 'open',
                    'patch_to_review': 'open'}

        return statuses[bz_status.lower()]	


    buginfo = server.Bug.get(kwargs)['bugs']	
    #grabbing one bug at a time fo rnow
    buginfo =  buginfo[0]
    com = server.Bug.comments(kwargs)['bugs'][bugid]['comments']
    bug_id = com[0]['bug_id']

    #have to do for json
    buginfo['last_change_time'] = datetime_to_epoch(buginfo['last_change_time'])
    buginfo['creation_time'] = datetime_to_epoch(buginfo['creation_time'])

    for c in com:
        c['creation_time'] = datetime_to_epoch(c['creation_time'])
        c['time'] = datetime_to_epoch(c['time'])

    conn = MySQLdb.connect(host= "localhost",
                  user="root",
                  passwd="labspass",
                  db="phab_migration",
                  charset='utf8')

    x = conn.cursor()

    try:

       header = base64.b64encode(json.dumps(buginfo))
       comments = base64.b64encode(json.dumps(com))
       sql = """INSERT INTO bugzilla_meta (id, header, comments) VALUES (%s, '%s', '%s')"""
       x.execute(sql % (bugid, header, comments))
       conn.commit()

       x.execute("SELECT * FROM bugzilla_meta WHERE id = %s" % (bugid,))
       bugid, header, comments  = x.fetchall()[0]
       bugid = int(bugid)
       buginfo = json.loads((base64.b64decode(header)))
       com = json.loads((base64.b64decode(comments)))
       log(bugid)
       log(buginfo)

    except Exception as e:
       import traceback
       traceback.print_exc(file=sys.stdout)
       print e
       print 'rollback!'
       conn.rollback()
    else:
        conn.close()

    #mask emails for public consumption
    buginfo['cc'] = [c.split('@')[0] for c in buginfo['cc']]

    with open('dump', 'w') as d:
        d.write(str(json.dumps(buginfo)))

    #XXX: if is patch_to_review add that project
    #convert bugzilla source to phabricator
    buginfo['status'] = status_convert(buginfo['status'])

    #XXX: fix
    if buginfo["product"] == 'Security':
        print '!!!!!!do special security stuff here'
        return
    
    component_separator = '-'
    buginfo["product"] = buginfo["product"].replace('-', '_')
    buginfo["product"] = buginfo["product"].replace(' ', '_')
    buginfo["component"] = buginfo["component"].replace('/', '_and_')
    buginfo["component"] = buginfo["component"].replace('-', '_')
    buginfo["component"] = buginfo["component"].replace(' ', '_')
    project = "%s%s%s" % (buginfo["product"],
                         component_separator,
                         buginfo["component"])
    buginfo['project'] = project
    print buginfo['project']
    title = buginfo['summary']
    priority = priority_convert(buginfo['priority'])

    clean_com = []
    for c in com:
        if not isinstance(c, dict):
            c = ast.literal_eval(c)
        clean_c = {}
        clean_c['author'] =  c['author'].split('@')[0]

        clean_c['creation_time'] = str(c['creation_time'])
        if c['author'] != c['creator']:
            clean_c['creator'] =  c['creator'].split('@')[0]

        if c['count'] == 0:
            clean_c['bug_id'] = c['bug_id']

        if c['is_private']:
            clean_c['text'] = '_hidden_'
        else:
            clean_c['text'] = c['text']

        clean_com.append(clean_c)

    log('project: ' + buginfo['project'])
    existing_proj = phab.project.query(names=[buginfo['project']])
    if not existing_proj['data']:
        log('need to make: ' + buginfo['project'])
        new_proj = phab.project.create(name=buginfo['project'])
        existing_proj = phab.project.query(names=[buginfo['project']])
        log(str(existing_proj))
        phid = existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
    else:
        phid =  existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
        log(buginfo['project'] + ' exists')

    log(phid)
    # strip out comment 0 as description
    decription = clean_com[0]
    del clean_com[0]

    created = epoch_to_datetime(decription['creation_time'])
    desc_block = "**Created**: `%s`\n\n**Author:** `%s`\n\n**Description:**\n%s\n" % (created, decription['author'], decription['text'])

    log(desc_block)
    ticket = create(title, desc_block, decription['bug_id'], phid, priority)
    comment_block = "**%s** `%s` \n\n %s"
    for c in clean_com:
        #comblock = StringIO()
        #comblock.write("**%s** `%s` \n\n" % (c['author'], created,))
        #comblock.write('%%%')
        #comblock.write('%s' % (c['text'],))
        #comblock.write('%%%')
        #com_formatted = comblock.getvalue()
        log('-------------------------------------')
        created = epoch_to_datetime(c['creation_time'])
        #comment(ticket['id'], com_formatted)
        #comblock.close()    
        comment(ticket['id'], "**%s** `%s` \n\n%s" % (c['author'], created, c['text']))

    log(str(ticket['id']) + str(buginfo['status'])) 

    if buginfo['status'] != 'open':
        comment(ticket['id'], '//importing issue status//')
        set_status(ticket['id'], buginfo['status'])

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

for i in bugs:
    main(i)
    #print type(bugid)
    #print bugid
    #bugid = int(bugid)

print ticket
