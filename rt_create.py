import time
import json
import os
import re
import sys
import getpass
import logging
import ConfigParser
sys.path.append('/home/rush/python-rtkit/')
from wmfphablib import phdb
from wmfphablib import mailinglist_phid
from wmfphablib import set_project_icon
from wmfphablib import phabdb
from wmfphablib import Phab
from wmfphablib import log
from wmfphablib import bzlib
from wmfphablib import datetime_to_epoch
from wmfphablib import epoch_to_datetime
from rtkit import resource
from rtkit import authenticators
from rtkit import errors
from wmfphablib import ipriority


def create(rtid):
    parser = ConfigParser.SafeConfigParser()
    parser.read('/etc/gz_fetch.conf')

    parser_mode = 'phab'
    phab = Phab(user=parser.get(parser_mode, 'username'),
                cert=parser.get(parser_mode, 'certificate'),
                host=parser.get(parser_mode, 'host'))


    parser_mode = 'rt'
    response = resource.RTResource(parser.get(parser_mode, 'url'),
                               parser.get(parser_mode, 'username'),
                               parser.get(parser_mode, 'password'),
                               authenticators.CookieAuthenticator)

    #Ex:
    #id: ticket/8175/attachments\n
    #Attachments: 141490: (Unnamed) (multipart/mixed / 0b),
    #             141491: (Unnamed) (text/html / 23b),
    #             141492: 0jp9B09.jpg (image/jpeg / 117.4k),
    attachments = response.get(path="ticket/%s/attachments/" % (rtid,))
    if not attachments:
        raise Exception("no attachment response: %s" % (rtid))

    #/#TMP
    history = response.get(path="ticket/%s/history?format=l" % (rtid,))

    pmig = phdb(db='rt_migration')
    rrtid, import_priority, rtinfo, com = pmig.sql_x("SELECT * FROM rt_meta WHERE id = %s",
                                     (rtid,))
    pmig.close()
    rtinfo = json.loads(rtinfo)
    comments = json.loads(com)

    comment_dict = {}
    for i, c in enumerate(comments):
        cwork = {}
        comment_dict[i] = cwork
        if not 'Attachments:' in c:
            pass
        attachsplit = c.split('Attachments:')
        if len(attachsplit) > 1:
            body, attached = attachsplit[0], attachsplit[1]
        else:
            body, attached = c, '0'
        comment_dict[i]['text_body'] = body
        comment_dict[i]['attached'] = attached

    #Ticket: 8175\nTimeTaken: 0\n
    #Type: 
    #Create\nField:
    #nData: \nDescription: Ticket created by cpettet\n\n
    #Content: test ticket description\n\n\n
    #Creator: cpettet\nCreated: 2014-08-21 21:21:38\n\n'}
    params = {'id': 'id:(.*)',
              'ticket': 'Ticket:(.*)',
              'timetaken': 'TimeTaken:(.*)',
              'content': 'Content:(.*)',
              'creator': 'Creator:(.*)',
              'description': 'Description:(.*)',
              'created': 'Created:(.*)',
              'ovalue': 'OldValue:(.*)',
              'nvalue': 'NewValue::(.*)'}

    for k, v in comment_dict.iteritems():
        text_body = v['text_body']
        comment_dict[k]['body'] = {}
        for paramkey, regex in params.iteritems():
            value = re.search(regex, text_body)
            if value:
                comment_dict[k]['body'][paramkey] = value.group(1).strip()
            else:
                comment_dict[k]['body'][paramkey] = None

        if 'Content' in text_body:
            content = text_body.split('Content:')[1]
            content = content.split('Creator:')
            comment_dict[k]['body']['content'] = content

        #15475: untitled (18.7k)
        comment_attachments= re.findall('(\d+):\s', v['attached'])
        comment_dict[k]['body']['attached'] = comment_attachments

    #attachments into a dict
    def attach_to_kv(attachments_output):
        attached = re.split('Attachments:', attachments_output, 1)[1]
        ainfo = {}
        for at in attached.strip().splitlines():
            if not at:
                continue
            k, v = re.split(':', at, 1)
            ainfo[k.strip()] = v.strip()
        return ainfo

    ainfo = attach_to_kv(attachments)
    #lots of junk attachments from emailing comments and ticket creation
    ainfo_f = {}
    for k, v in ainfo.iteritems():
        if '(Unnamed)' not in v:
            ainfo_f[k] = v

    #taking attachment text and convert to tuple (name, content type, size)
    ainfo_ext = {}
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    for k, v in ainfo_f.iteritems():
        # Handle general attachment case:
        # NO: 686318802.html (application/octet-stream / 19.5k),
        # YES: Summary_686318802.pdf (application/unknown / 215.3k),
        extract = re.search('(.*)\.(\S{3,4})\s\((.*)\s\/\s(.*)\)', v)
        #logger.debug(str(extract.groups()))
        #print k, v
        # due to goofy email handling of signature/x-header/meta info
        # it seems they sometimes
        # become malformed attachments.  Such as when a response into
        # rt was directed to a mailinglist
        #EX:
        #    ->Attached Message Part (text/plain / 158b)
        #
        #   Private-l mailing list
        #   Private-l@lists.wikimedia.org
        #   https://lists.wikimedia.org/mailman/listinfo/private-l
        if not extract and v.startswith('Attached Message Part'):
            continue
        elif not extract:
           raise Exception("no attachment extraction: %s %s (%s)" % (k, v, rtid))
           continue
        else:
           log(extract.groups())
           ainfo_ext[k] = extract.groups()

    attachment_types = ['pdf',
                        'jpeg',
                        'tgz',
                        'jpg',
                        'png',
                        'xls',
                        'xlsx',
                        'gif',
                        'html',
                        'htm',
                        'txt',
                        'log',
                        'zip',
                        'rtf',
                        'vcf',
                        'eml']

    #Uploading attachment
    dl = []
    #('Quote Summary_686318802', 'pdf', 'application/unknown', '215.3k')
    uploaded = {}
    for k, v in ainfo_ext.iteritems():
        file_extension = v[1].lower()
        # vendors have this weird habit of capitalizing extension names
        # make sure we can handle the extension type otherwise
        if file_extension not in attachment_types:
            log("%s %s %s" % (rtid, v, file_extension))
            raise Exception('unknown extension: %s (%s)' % (v, rtid))
        full = "ticket/%s/attachments/%s/content" % (rtid, k)
        vcontent = response.get(path=full, headers={'Content-Type': v[2], 'Content-Length': v[3] })
        #PDF's don't react well to stripping header -- fine without it
        if file_extension.strip() == 'pdf':
            sanscontent = ''.join(vcontent.readlines())
        else:
            vcontent = vcontent.readlines()
            sanscontent = ''.join(vcontent[2:])

        #{u'mimeType': u'image/jpeg', u'authorPHID': u'PHID-USER-bn2kbod4i7geycrbicns', 
        #u'phid': u'PHID-FILE-ioj2mrujudkrekhl5pkl', u'name': u'0jp9B09.jpg',
        #u'objectName': u'F25786', u'byteSize': u'120305',
        #u'uri': u'http://fabapitest.wmflabs.org/file/data/t7j2qp7l5z4ou5qpbx2u/PHID-FILE-ioj2mrujudkrekhl5pkl/0jp9B09.jpg',
        #u'dateCreated': u'1409345752', u'dateModified': u'1409345752', u'id': u'25786'}
        upload = phab.upload_file("%s.%s" % (v[0], file_extension), sanscontent)
        uploaded[k] = upload

    ptags = []
    ptags.append(rtinfo['Queue'])

    phids = []
    for p in ptags:
        phids.append(phab.ensure_project(p))

    def priority_convert(priority):
        priorities = { '0': 50, '50': 50}
        return priorities.get(priority.lower(), 50)

    def status_convert(status):
        statuses = { 'resolved': 'resolved', 'new': 'open'}
        return statuses[status.lower()]

    priority = priority_convert(rtinfo['Priority'])
    status = status_convert(rtinfo['Status'])

    desc_block = "**Created**: `%s`\n\n**Author:** `%s`\n\n**Description:**\n%s\n" % (rtinfo['Created'],
                                                                                      rtinfo['Creator'],
                                                                                      rtinfo['Subject'])

    desc_tail = '--------------------------'
    desc_tail += "\n**Last Updated**: %s" % (rtinfo['LastUpdated'])

    full_description = desc_block + '\n' + desc_tail
    log("Ticket Info: %s" % (desc_block,))
    ticket = phab.task_create(rtinfo['Subject'],
                    full_description,
                    'rt%s' % sys.argv[1],
                    priority,
                    'none',
                    ccPHIDs=[],
                    projects=phids)

    upfiles = uploaded.keys()

    import collections
    # {'ovalue': u'open',
    # 'description': u"Status changed from 'open' to 'resolved' by robh",
    # 'nvalue': None, 'creator': u'robh', 'attached': [],
    # 'timetaken': u'0', 'created': u'2011-07-01 02:47:24', 
    # 'content': [u' This transaction appears to have no content\n', u'
    #              robh\nCreated: 2011-07-01 02:47:24\n'],
    # 'ticket': u'1000', 'id': u'23192'}
    ordered_comments = collections.OrderedDict(sorted(comment_dict.items()))
    for comment, contents in comment_dict.iteritems():
        dbody = contents['body']

        if dbody['content'] is None and dbody['creator'] is None:
            continue

        if dbody['content'] is None:
            content = 'no content found'
        else:
            content = ''.join(dbody['content'])

        if 'This transaction appears to have no content' in content:
            content = None

        cbody = "**%s** on `%s`\n\n**Description**: %s\n **Message**: %s\n" % (dbody['creator'],
                                          dbody['created'],
                                          dbody['description'],
                                          content or 'no message')

        cbody += "\n--------------------------\n"
        cbody += "New Value: %s\n" % (dbody['nvalue'])
        cbody += "Original Value: %s\n" % (dbody['ovalue'])
        afound = contents['body']['attached']
        cbody_attachments = []
        for a in afound:
            if a in upfiles:
                cbody_attachments.append('{F%s}' % uploaded[a]['id'])
        if cbody_attachments:
            cbody += "\n\n**Attached**:\n"
            cbody += '\n'.join(cbody_attachments)
        phab.task_comment(ticket['id'], cbody)

    if rtinfo['Status'].lower() != 'open':
        close_remark = '//importing issue status//'
        if 'Resolved' in rtinfo and rtinfo['Resolved'] != 'Not set':
            close_remark += "\n Resolved %s" % (rtinfo['Resolved'],)
        phab.task_comment(ticket['id'], close_remark)
        phab.set_status(ticket['id'], status)

    print ticket['id']


def run_create(rtid, tries=1):
    if tries == 0:
        pmig = phabdb.phdb(db='rt_migration')
        import_priority = pmig.sql_x("SELECT priority FROM rt_meta WHERE id = %s", (rtid,))
        if import_priority:
            log('updating existing record')
            pmig.sql_x("UPDATE rt_meta SET priority=%s WHERE id = %s", (ipriority['creation_failed'],
                                                                        rtid))
        else:
            print "%s does not seem to exist" % (rtid)
        pmig.close()
        print 'failed to grab %s' % (rtid,)
        return False
    if tries == 0:
        print 'failed to grab %s' % (rtid,)
        return False
    try:
        if create(rtid):
            print time.time()
            print 'done with %s' % (rtid,)
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (rtid, e)
        return run_create(rtid, tries=tries)

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

for i in bugs:
    if i.isdigit():
        run_create(i)
