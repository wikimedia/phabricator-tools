#!/usr/bin/env python
"""

2014 Chase Pettet


This script is a WIP for getting Bugzilla information
with the end goal of it living in phabricator

"""
import multiprocessing
import time
import yaml
import ast
import base64
import json
import sys
import xmlrpclib
import os
import MySQLdb

from wmfphablib import phdb
from wmfphablib import mailinglist_phid
from wmfphablib import set_project_icon
from wmfphablib import phabdb
from wmfphablib import Phab
from wmfphablib import log
from wmfphablib import bzlib
from wmfphablib import datetime_to_epoch
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority
from email.parser import Parser
from wmfphablib import get_config_file
import ConfigParser

configfile = get_config_file()

def fetch(bugid):
    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read(configfile)
    phab = Phab(user=parser.get(parser_mode, 'username'),
                cert=parser.get(parser_mode, 'certificate'),
                host=parser.get(parser_mode, 'host'))
    parser_mode = 'bz'
    server = xmlrpclib.ServerProxy(parser.get(parser_mode, 'url'), use_datetime=True)
    bzdata= open("data/bugzilla.yaml", 'r')
    bzdata_yaml = yaml.load(bzdata)
    tag_keys = bzdata_yaml['keywords_to_tags'].split(' ')
    mlists = bzdata_yaml['assigned_to_lists'].split(' ')
    log("Mailinglists: " + str(mlists))

    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    kwargs = { 'ids': [bugid],
               'Bugzilla_login': parser.get(parser_mode, 'Bugzilla_login'),
               'Bugzilla_password': parser.get(parser_mode, 'Bugzilla_password')}
    attached = server.Bug.attachments(kwargs)['bugs'][bugid]

    #process ticket uploads to map attach id to phab file id
    uploads = {}
    for a in attached:
        if a['is_private']:
            continue
        upload = phab.upload_file(a['file_name'], str(a['data']))
        a['phid'] = upload['phid']
        a['name'] = upload['name']
        a['objectName'] = upload['objectName']
        uploads[a['id']] = a
    log('Attachment count: ' + str(len(uploads.keys())))

    pmig = phdb(db='bugzilla_migration')
    bugid, import_priority, buginfo, com, created, modified = pmig.sql_x("SELECT * FROM bugzilla_meta WHERE id = %s",
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

    # Convert bugzilla source to phabricator
    buginfo['status'] = bzlib.status_convert(buginfo['status'])
    buginfo['priority'] = bzlib.priority_convert(buginfo['priority'])

    with open('dump', 'w') as d:
        d.write(str(json.dumps(buginfo)))

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

    # This value must match the security enforcer extension
    # And the relevant herald rule must be in place.
    if buginfo["product"] == 'Security':
        buginfo["secstate"] = 'security-bug'
    else:
        buginfo["secstate"] = 'none'
    
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

    title = buginfo['summary']

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

        attachment = bzlib.find_attachment_in_comment(c['text'])
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
        phids.append(phab.ensure_project(p[0]))
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
    ticket = phab.task_create(title,
                    full_description,
                    description['bug_id'],
                    buginfo['priority'],
                    buginfo["secstate"],
                    ccPHIDs=ccphids,
                    projects=phids,
                    refcode=bzlib.prepend)

    print "Created: ", ticket['id']

    comment_block = "**%s** `%s` \n\n %s"
    for c in clean_com:
        log('-------------------------------------')
        created = epoch_to_datetime(c['creation_time'])
        comment_body = "**%s** wrote on `%s`\n\n%s" % (c['author'], created, c['text'])
        if 'attachment' in c:
            attached = int(c['attachment'])

            #some comments match the attachment regex but the attachment was deleted
            # by an admin from bugzilla and so is now missing.
            if attached not in uploads:
                comment_body += "\n\n //attachment %s missing in source//" % (attached,)
            else:
                cattached = uploads[int(c['attachment'])]
                comment_body += "\n\n**Attached**: {%s}" % (cattached['objectName'])
        phab.task_comment(ticket['id'], comment_body)

    log(str(ticket['id']) + str(buginfo['status'])) 

    if buginfo['status'] != 'open':
        phab.task_comment(ticket['id'], '//importing issue status//')
        phab.set_status(ticket['id'], buginfo['status'])

    return True

def run_fetch(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db='bugzilla_migration')
        import_priority = pmig.sql_x("SELECT priority FROM bugzilla_meta WHERE id = %s", (bugid,))
        if import_priority:
            log('updating existing record')
            pmig.sql_x("UPDATE bugzilla_meta SET priority=%s WHERE id = %s", (ipriority['creation_failed'],
                                                                              bugid))
        else:
            print "%s does not seem to exist" % (bugid)
        pmig.close()
        print 'failed to grab %s' % (bugid,)
        return False
    try:
        if fetch(bugid):
            print time.time()
            print 'done with %s' % (bugid,)
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (bugid, e)
        return run_fetch(bugid, tries=tries)

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
