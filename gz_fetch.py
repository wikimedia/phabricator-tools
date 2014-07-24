import json
import datetime
import sys
import xmlrpclib
import subprocess
import os
import re
from email.parser import Parser
import ConfigParser

from phabricator import Phabricator

def log(msg):
    import syslog
    msg = str(msg)
    if '-v' in sys.argv:
        syslog.syslog(msg)
        print '-> ', msg

def main():

    bugid = sys.argv[1]

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

    def comment(task, msg):
        out = phab.maniphest.update(id=task, comments=msg)
        log(out)
        return out

    def set_status(task, status):
        out = phab.maniphest.update(id=task, status=status)
        log(out)
        return out

    def create(title, desc, id, projects):
        out = phab.maniphest.createtask(title=title,
                                        description="%s" % desc,
                                        projectPHIDs=[projects],
                                        auxiliary={"std:maniphest:external_id":"%s" % (id,)})
        log(out)
        return out

    def datetime_to_epoch(date_time):
        return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

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
        statuses = {'new': 'open',
                    'resolved': 'resolved',
                    'need_info': 'needs_info'}
        return statuses[bz_status.lower()]	


    #print dir(server)
    #print server.User.get(kwargs)
    buginfo = server.Bug.get(kwargs)['bugs']	
    #grabbing one bug at a time fo rnow
    buginfo =  buginfo[0]
    com = server.Bug.comments(kwargs)['bugs'][bugid]['comments']

    #have to do for json
    buginfo['last_change_time'] = datetime_to_epoch(buginfo['last_change_time'])
    buginfo['creation_time'] = datetime_to_epoch(buginfo['creation_time'])

    #mask emails for public consumption
    buginfo['cc'] = [c.split('@')[0] for c in buginfo['cc']]

    with open('dump', 'w') as d:
        d.write(str(json.dumps(buginfo)))

    obuginfo = buginfo
    ocom     = com

    #convert bugzilla source to phabricator
    buginfo['status'] = status_convert(buginfo['status'])

    #XXX: fix
    if buginfo["product"] == 'Security':
        print 'do special security stuff here'
        exit(1)

    project = "%s-%s" % (buginfo["product"], buginfo["component"])
    buginfo['project'] = project.lower()
    title = buginfo["summary"]

    clean_com = []
    for c in com:
        clean_c = {}
        clean_c['author'] =  c['author'].split('@')[0]

        if c['author'] != c['creator']:
            clean_c['creator'] =  c['creator'].split('@')[0]

        clean_c['creation_time'] = datetime_to_epoch(c['creation_time'])

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
    desc_block = "Created: %s\nAuthor:%s\nDescription: %s\nBug ID: %s\n" % (decription['creation_time'],
                                                                             decription['author'],
                                                                             decription['text'],
                                                                              decription['bug_id'])

    log(desc_block)
    ticket = create(title, desc_block, decription['bug_id'], phid)
    comment_block = ">%s (%s) \n\n%s"
    for c in clean_com:
        print '-------------------------------------'
        comment(ticket['id'], ">%s (%s) \n\n%s" % (c['author'], c['creation_time'], c['text']))

    log(str(ticket['id']) + str(buginfo['status'])) 

    if buginfo['status'] != 'open':
        comment(ticket['id'], 'importing issue status')
        set_status(ticket['id'], buginfo['status'])
main()
