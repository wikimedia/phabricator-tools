#!/usr/bin/env python
import multiprocessing
import time
import yaml
import ast
import json
import sys
import xmlrpclib
import os
import re
from phabricator import Phabricator
from wmfphablib import Phab as phabmacros
from wmfphablib import return_bug_list
from wmfphablib import phdb
from wmfphablib import now
from wmfphablib import mailinglist_phid
from wmfphablib import set_project_icon
from wmfphablib import phabdb
from wmfphablib import Phab
from wmfphablib import log
from wmfphablib import notice
from wmfphablib import vlog
from wmfphablib import errorlog as elog
from wmfphablib import bzlib
from wmfphablib import config
from wmfphablib import bzlib
from wmfphablib import util
from wmfphablib import datetime_to_epoch
from wmfphablib import epoch_to_datetime
from wmfphablib import ipriority

def create(bugid):
    phab = Phabricator(config.phab_user,
                       config.phab_cert,
                       config.phab_host)

    phabm = phabmacros('', '', '')
    phabm.con = phab

    pmig = phdb(db=config.bzmigrate_db)

    current = pmig.sql_x("SELECT priority, \
                          header, \
                          comments, \
                          created, \
                          modified \
                          FROM bugzilla_meta WHERE id = %s",
                          (bugid,))
    if current:
        import_priority, buginfo, com, created, modified = current[0]
    else:    
        elog('%s not present for migration' % (bugid,))
        return False

    def get_ref(id):
        refexists = phabdb.reference_ticket('%s%s' % (bzlib.prepend,
                                                      id))
        if refexists:
            return refexists

    if get_ref(bugid):
        log('reference ticket %s already exists' % (bugid,))
        #return True

    buginfo = json.loads(buginfo)
    com = json.loads(com)
    bugid = int(bugid)
    vlog(bugid)
    vlog(buginfo)

    def is_sensitive(name):
        return name.strip().lower().startswith('security')

    buginfo["secstate"] = 'none'
    # And the relevant herald rule must be in place.
    if is_sensitive(buginfo["product"]):
        buginfo["secstate"] = 'security-bug'
        log("found security-bug issue %s" % (bugid,))

        #this allows testing while respecting security queue
        if config.bz_security.lower() != 'true':
            log("ignoring security issue %s" % (bugid,))
            return True

    server = xmlrpclib.ServerProxy(config.Bugzilla_url, use_datetime=True)
    token_data = server.User.login({'login': config.Bugzilla_login,
                                    'password': config.Bugzilla_password})

    token = token_data['token']
    #http://www.bugzilla.org/docs/tip/en/html/api/Bugzilla/WebService/Bug.html#attachments
    kwargs = { 'ids': [bugid], 'Bugzilla_token': token }

    bzdata= open("data/bugzilla.yaml", 'r')
    bzdata_yaml = yaml.load(bzdata)
    tag_keys = bzdata_yaml['keywords_to_tags'].split(' ')
    mlists = bzdata_yaml['assigned_to_lists'].split(' ')
    vlog("Mailinglists: " + str(mlists))

    attached = server.Bug.attachments(kwargs)['bugs'][str(bugid)]
    vlog("bz attached items %s" % (str(attached)))

    #process ticket uploads to map attach id to phab file id
    uploads = {}
    for a in attached:
        if a['is_private']:
            continue
        vlog("processing bz attachment %s" % (str(a)))

        upload = phabm.upload_file(a['file_name'], a['data'].data)
        a['phid'] = upload['phid']
        a['name'] = upload['name']
        a['objectName'] = upload['objectName']
        uploads[a['id']] = a
    log('%s attachment count: %s' % (bugid, str(len(uploads.keys()))))
    vlog("phab upload details: %s" % (str(uploads)))

    #list of projects to add to ticket
    ptags = []

    #mask emails for public consumption
    buginfo['cc'] = [c.split('@')[0] for c in buginfo['cc']]

    # Convert bugzilla source to phabricator
    buginfo['status'] = bzlib.status_convert(buginfo['status'],
                                             buginfo['resolution'])
    buginfo['priority'] = bzlib.priority_convert(buginfo['priority'])

    if '-d' in sys.argv:
        with open('dump', 'w') as d:
            d.write(str(json.dumps(buginfo)))

    if buginfo['status'].lower() == 'patch_to_review':
        ptags.append(('patch_to_review', 'tags', 'green'))

    if buginfo['status'] == 'verified':
        ptags.append(('verified', 'tags'))

    if buginfo['cf_browser'] not in ['---', "Other"]:
        btag = "Browser_Support_%s" % (buginfo['cf_browser'].replace(' ', '-'),)
        log('Adding browser tag: %s' % (btag,))
        ptags.append((btag, 'tags'))

    if buginfo['target_milestone'] != '---':
        log('Creating milestone: %s' % (buginfo['target_milestone'],))
        ptags.append((buginfo['target_milestone'], 'truck'))

    #set defaults to be overridden by sec if needed
    buginfo['viewPolicy'] = 'public'
    buginfo['editPolicy'] = 'users'
    buginfo['project'] = bzlib.sanitize_project_name(buginfo["product"],
                                                     buginfo["component"])
    vlog(buginfo['project'])
    ptags.append((buginfo['project'], None))

    title = buginfo['summary']

    clean_com = []
    for c in com:
        if not isinstance(c, dict):
            c = ast.literal_eval(c)
        clean_c = bzlib.build_comment(c)
        clean_com.append(clean_c)

    log('project: ' + buginfo['project'])

    # strip out comment 0 as description
    description = clean_com[0]
    del clean_com[0]

    created = epoch_to_datetime(description['creation_time'])
    desc_block = "**Author:** `%s`\n\n**Description:**\n%s\n" % (description['author'],
                                                                 description['text'])

    # https://phabricator.wikimedia.org/T694
    desc_tail = '--------------------------'
    desc_tail += "\n**Version**: %s" % (buginfo['version'])
    desc_tail += "\n**Severity**: %s" % (buginfo['severity'] or 'none')

    if buginfo['op_sys'] != 'All':
        desc_tail += "\n**OS**: %s" % (buginfo['op_sys'])

    if "platform" in buginfo and buginfo['platform'] != 'All':
        desc_tail += "\n**Platform**: %s" % (buginfo['platform'])

    if buginfo['whiteboard']:
        desc_tail += "\n**Whiteboard**: %s" % (buginfo['whiteboard'])

    if buginfo['url']:
        desc_tail += "\n**URL**: %s" % (buginfo['url'])

    if buginfo['see_also']:
        desc_tail += "\n**See Also**:\n%s" % ('\n'.join(buginfo['see_also']))

    if 'attachment' in description:
        attached = int(description['attachment'])
        if attached in uploads:
            cattached = uploads[int(description['attachment'])]
            desc_tail += "\n\n**Attached**: {%s}" % (cattached['objectName'])

    full_description = desc_block + '\n' + desc_tail

    keys = buginfo['keywords']
    for k in keys:
        if k in tag_keys:
            if k == 'ops':
                k = 'operations'
            ptags.append((k, 'tags'))

    def project_security_settings(pname):
        if is_sensitive(pname):
            ephid = phabdb.get_project_phid('security')
            edit = ephid
        else:
            edit = 'public'
        view = 'public'
        return edit, view

    phids = []
    for p in ptags:
        edit, view = project_security_settings(p[0])
        phid = phabm.ensure_project(p[0], edit=edit, view=view)
        phids.append(phid)
        if p[1] is not None:
            vlog("setting project %s icon to %s" % (p[0], p[1]))
            set_project_icon(p[0], icon=p[1])

    log("ptags: " + str(ptags))
    vlog("phids: " + str(phids))

    #buginfo'assigned_to': u'wikibugs-l@lists.wikimedia.org'
    assignee = buginfo['assigned_to']

    ccphids = []
    if assignee in mlists:
        ccphids.append(mailinglist_phid(assignee))

    vlog("Ticket Info: %s" % (desc_block,))
    ticket =  phab.maniphest.createtask(title=buginfo['summary'],
                                 description=full_description,
                                 projectPHIDs=phids,
                                 ccPHIDs=ccphids,
                                 priority=buginfo['priority'],
                                 viewPolicy = buginfo['viewPolicy'],
                                 editPolicy = buginfo['editPolicy'],
                                 auxiliary={"std:maniphest:external_reference":"bz%s" % (bugid,),
                                            "std:maniphest:security_topic":"%s" % (buginfo["secstate"],)})

    log("Created task: T%s (%s)" % (ticket['id'], ticket['phid']))
    botphid = phabdb.get_phid_by_username(config.phab_user)
    phabdb.set_task_title_transaction(ticket['phid'],
                                      botphid,
                                      buginfo['viewPolicy'],
                                      buginfo['editPolicy'])

    phabdb.set_task_ctime(ticket['phid'],
                          int(buginfo['creation_time'].split('.')[0]))

    fmt_comments = {}
    for c in clean_com:
        fmt_comment = {}
        created = epoch_to_datetime(c['creation_time'])
        comment_header = "**%s** wrote:\n\n" % (c['author'],)
        comment_body = c['text']
        attachments = ''
        if 'attachment' in c:
            attached = int(c['attachment'])
            #some comments match the attachment regex but the attachment was deleted
            # by an admin from bugzilla and so is now missing.
            if attached not in uploads:
                attachments += "\n\n //attachment %s missing in source//" % (attached,)
            else:
                cattached = uploads[int(c['attachment'])]
                attachments += "\n\n**Attached**: {%s}" % (cattached['objectName'])
        fmt_comment['xpreamble'] = comment_header
        fmt_comment['xattached'] = attachments
        phabm.task_comment(ticket['id'], comment_header + comment_body + attachments)
        ctransaction = phabdb.last_comment(ticket['phid'])
        phabdb.set_comment_time(ctransaction, c['creation_time'])
        fmt_comment['xctransaction'] = ctransaction
        fmt_comments[c['count']] = fmt_comment

    if buginfo['status'] != 'open':
        log("setting status for T%s to %s" % (ticket['id'], buginfo['status']))
        phabdb.set_issue_status(ticket['phid'], buginfo['status'])

    phabdb.set_task_mtime(ticket['phid'], int(buginfo['last_change_time'].split('.')[0]))
    xcomments = json.dumps(fmt_comments)
    pmig.sql_x("UPDATE bugzilla_meta SET xcomments=%s WHERE id = %s", (xcomments, bugid))
    pmig.sql_x("UPDATE bugzilla_meta SET priority=%s, modified=%s WHERE id = %s",
               (ipriority['creation_success'], now(), bugid))
    pmig.close()
    return True


def run_create(bugid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db=config.bzmigrate_db)
        import_priority = pmig.sql_x("SELECT priority FROM bugzilla_meta WHERE id = %s", (bugid,))
        if import_priority:
            pmig.sql_x("UPDATE bugzilla_meta SET priority=%s WHERE id = %s", (ipriority['creation_failed'],
                                                                              bugid))
        else:
            elog("%s does not seem to exist" % (bugid))
        pmig.close()
        elog('failed to create %s' % (bugid,))
        return False
    try:
        return create(bugid)
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        elog('failed to create %s (%s)' % (bugid, e))
        return run_create(bugid, tries=tries)

def main():

    if not util.can_edit_ref:
        elog('%s reference field not editable on this install' % (bugid,))
        sys.exit(1)

    pmig = phdb(db=config.bzmigrate_db)
    bugs = return_bug_list(dbcon=pmig)
    pmig.close()

    #Serious business
    if 'failed' in sys.argv:
        for b in bugs:
            notice("Removing bugid %s" % (b,))
            log(util.remove_issue_by_bugid(b, bzlib.prepend))

    from multiprocessing import Pool
    pool = Pool(processes=int(config.bz_createmulti))
    _ =  pool.map(run_create, bugs)
    complete = len(filter(bool, _))
    failed = len(_) - complete
    print '%s completed %s, failed %s' % (sys.argv[0], complete, failed)

if __name__ == '__main__':
    main()
