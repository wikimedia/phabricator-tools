#!/usr/bin/env python
"""

2014 Chase Pettet


This script is a WIP for getting Bugzilla information
with the end goal of it living in phabricator

"""

import yaml
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
from phabdb import phdb
from phabdb import mailinglist_phid
from phabdb import set_project_icon
from email.parser import Parser
import ConfigParser

import phabricator
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


    bzdata= open("data/bugzilla.yaml", 'r')
    bzdata_yaml = yaml.load(bzdata)
    tag_keys = bzdata_yaml['keywords_to_tags'].split(' ')
    mlists = bzdata_yaml['assigned_to_lists'].split(' ')
    log("Mailinglists: " + str(mlists))


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

    def create(title, desc, id, priority, ccPHIDs=[], projects=[]):
        out = phab.maniphest.createtask(title=title,
                                        description="%s" % desc,
                                        projectPHIDs=projects,
                                        priority=priority,
                                        auxiliary={"std:maniphest:external_id":"%s" % (id,)})
        log(out)
        return out

    def datetime_to_epoch(date_time):
        return str((date_time - datetime.datetime(1970,1,1)).total_seconds())

    def epoch_to_datetime(epoch, timezone='UTC'):
        return str((datetime.datetime.fromtimestamp(int(float(epoch))
               ).strftime('%Y-%m-%d %H:%M:%S'))) + " (%s)" % (timezone,)

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
                    'reopened': 'open',
                    'closed': 'resolved',
                    'need_info': 'needs_info',
                    'verified': 'resolved',
                    'assigned': 'open',
                    'unconfirmed': 'open',
                    'patch_to_review': 'open'}

        return statuses[bz_status.lower()]	

    def ensure_project(project_name):
        """make sure project exists, return phid either way"""

        existing_proj = phab.project.query(names=[project_name])
        if not existing_proj['data']:
            log('need to make: ' + project_name)
            try:
                new_proj = phab.project.create(name=project_name, members=['PHID-USER-wa4idclisnm6aeakk7ur'])
            #XXX: Bug where we have to specify a members array!
            except phabricator.APIError:
                pass

            existing_proj = phab.project.query(names=[project_name])
            log(str(existing_proj))
            phid = existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
        else:
            phid = existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
            log(project_name + ' exists')
        return phid

    def upload_file(name, data):
        #print type(data)
        encoded = base64.b64encode(data)
        return phab.file.upload(name=name, data_base64=encoded)

    #grabbing one bug at a time for now
    buginfo = server.Bug.get(kwargs)['bugs']	
    buginfo =  buginfo[0]
    #print buginfo

    com = server.Bug.comments(kwargs)['bugs'][bugid]['comments']
    bug_id = com[0]['bug_id']

    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    attached = server.Bug.attachments(kwargs)['bugs'][bugid]

    #process ticket uploads to map attach id to phab file id
    uploads = {}
    for a in attached:
        if a['is_private']:
            print 'oh no private!!!!'
        upload = upload_file(a['file_name'], str(a['data']))
        finfo = phab.file.info(phid=upload.response).response
        a['phid'] = finfo['phid']
        a['name'] = finfo['name']
        a['objectName'] = finfo['objectName']
        uploads[a['id']] = a

    log('Attachment count: ' + str(len(uploads.keys())))
    #have to do for json
    buginfo['last_change_time'] = datetime_to_epoch(buginfo['last_change_time'])
    buginfo['creation_time'] = datetime_to_epoch(buginfo['creation_time'])





    for c in com:
        c['creation_time'] = datetime_to_epoch(c['creation_time'])
        c['time'] = datetime_to_epoch(c['time'])

    pmig = phdb()
    insert_values =  (bugid, json.dumps(buginfo), json.dumps(com))
    pmig.sql_x("INSERT INTO bugzilla_meta (id, header, comments) VALUES (%s, %s, %s)",
               insert_values)

    bugid, buginfo, com = pmig.sql_x("SELECT * FROM bugzilla_meta WHERE id = %s",
                                     (bugid,))
    pmig.close()


    buginfo = json.loads(buginfo)
    com = json.loads(com)
    bugid = int(bugid)
    log(bugid)
    log(buginfo)

    #list of projects to add to ticket
    ptags = []

    #mask emails for public consumption
    buginfo['cc'] = [c.split('@')[0] for c in buginfo['cc']]

    with open('dump', 'w') as d:
        d.write(str(json.dumps(buginfo)))

    #XXX: if is patch_to_review add that project
    if buginfo['status'].lower() == 'patch_to_review':
        ptags.append(('patch_to_review', 'tag', 'green'))

    if buginfo['status'] == 'verified':
        ptags.append(('verified', 'tag'))

    if buginfo['cf_browser'] not in ['---', "Other"]:
        log('Adding browser tag: %s' % (buginfo['cf_browser'],))
        ptags.append((buginfo['cf_browser'], 'tag'))

    if buginfo['target_milestone'] != '---':
        log('Creating milestone: %s' % (buginfo['target_milestone'],))
        ptags.append((buginfo['target_milestone'], 'truck'))

    #convert bugzilla source to phabricator
    #verified
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
    log(buginfo['project'])
    ptags.append((buginfo['project'], None))

    priority = priority_convert(buginfo['priority'])
    title = buginfo['summary']

    def find_attachment(text):
        import re
        a = re.search('Created\sattachment\s(\d+)', text)
        if a:
            return a.group(1)
        else:
            return ''

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
            c['text'] = '_hidden_'

        attachment = find_attachment(c['text'])
        if attachment:
            fmt_text = []
            text = c['text'].splitlines()
            for t in text:
                if not t.startswith('Created attachment'):
                    fmt_text.append(t)
            c['text'] = '\n'.join(fmt_text)
            clean_c['attachment'] = attachment

        clean_c['text'] = c['text']
        clean_com.append(clean_c)

    log('project: ' + buginfo['project'])

    # strip out comment 0 as description
    description = clean_com[0]
    del clean_com[0]

    created = epoch_to_datetime(description['creation_time'])
    desc_block = "**Created**: `%s`\n\n**Author:** `%s`\n\n**Description:**\n%s\n" % (created,
                                                                                        description['author'],
                                                                                        description['text'])
    desc_tail = '--------------------------'
    desc_tail += "\n**URL**: %s" % (buginfo['url'].lower() or 'none')
    desc_tail += "\n**Version**: %s" % (buginfo['version'].lower())
    desc_tail += "\n**See Also**: %s" % ('\n'.join(buginfo['see_also']).lower() or 'none')

    if 'alias' in buginfo:    
        desc_tail += "\n**Alias**: %s" % (buginfo['alias'])

    if buginfo["cf_platform"] != "---":
        desc_tail += "\n**Mobile Platform**: %s" % (buginfo["cf_platform"])

    if "rep_platform" in buginfo and buginfo['op_sys'] != 'All':
        desc_tail += "\n**Hardware/OS**: %s/%s" % (buginfo["rep_platform"], buginfo['op_sys'])
    else:
        desc_tail += "\n**Hardware/OS**: %s/%s" % ('unknown', 'unknown')

    full_description = desc_block + '\n' + desc_tail

    keys = buginfo['keywords']
    for k in keys:
        if k in tag_keys:
            ptags.append((k, 'tags'))

    phids = []
    for p in ptags:
        phids.append(ensure_project(p[0]))
        if p[1] is not None:
            if len(p) > 2:
                color = p[2]
            else:
                color = 'blue'
            log("Setting project %s icon to %s" % (p[0], p[1]))
            set_project_icon(p[0], icon=p[1], color=color)

    log("ptags: " + str(ptags))
    log("phids: " + str(phids))

    #buginfo'assigned_to': u'wikibugs-l@lists.wikimedia.org'
    assignee = buginfo['assigned_to']

    ccphids = []
    if assignee in mlists:
        ccphids.append(mailinglist_phid(assignee))

    log("Ticket Info: %s" % (desc_block,))
    ticket = create(title,
                    full_description,
                    description['bug_id'],
                    priority,
                    ccPHIDs=ccphids,
                    projects=phids)

    comment_block = "**%s** `%s` \n\n %s"
    for c in clean_com:
        log('-------------------------------------')
        created = epoch_to_datetime(c['creation_time'])
        comment_body = "**%s** wrote on `%s`\n\n%s" % (c['author'], created, c['text'])
        if 'attachment' in c:
            cattached = uploads[int(c['attachment'])]
            comment_body += "\n\n**Attached**: {%s}" % (cattached['objectName'])
        comment(ticket['id'], comment_body)

    log(str(ticket['id']) + str(buginfo['status'])) 

    if buginfo['status'] != 'open':
        comment(ticket['id'], '//importing issue status//')
        set_status(ticket['id'], buginfo['status'])

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

main('1')
#for i in bugs:
#    if i.isdigit():
#        main(i)
