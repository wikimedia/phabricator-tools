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

def create(tid):
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
    attachments = response.get(path="ticket/%s/attachments/" % (tid,))
    if not attachments:
        raise Exception("no attachment response: %s" % (tid))

    #/#TMP
    history = response.get(path="ticket/%s/history?format=l" % (tid,))
    ##pmig = phdb()
    ##rtid, import_priority, rtinfo, com = pmig.sql_x("SELECT * FROM rt_meta WHERE id = %s",
    ##                                 (tid,))
    ##pmig.close()
    ##rtinfo = json.loads(rtinfo)



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
        #Handle general attachment case:
        # NO: 686318802.html (application/octet-stream / 19.5k),
        # YES: Summary_686318802.pdf (application/unknown / 215.3k),
        extract = re.search('(.*)\.(\S{3,4})\s\((.*)\s\/\s(.*)\)', v)
        #logger.debug(str(extract.groups()))
        print k, v

        # due to goofy email handling of signature/x-header/meta info
        #  it seems they sometimes
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
           raise Exception("no attachment extraction: %s %s (%s)" % (k, v, tid))
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
    for k, v in ainfo_ext.iteritems():
        file_extension = v[1].lower()
        # vendors have this weird habit of capitalizing extension names
        # make sure we can handle the extension type otherwise
        if file_extension not in attachment_types:
            log("%s %s %s" % (tid, v, file_extension))
            raise Exception('unknown extension: %s (%s)' % (v, tid))

        full = "ticket/%s/attachments/%s/content" % (tid, k)
        vcontent = response.get(path=full, headers={'Content-Type': v[2], 'Content-Length': v[3] })
        #PDF's don't react well to stripping header -- fine without it
        if file_extension.strip() == 'pdf':
            sanscontent = ''.join(vcontent.readlines())
        else:
            vcontent = vcontent.readlines()
            sanscontent = ''.join(vcontent[2:])
        upload = phab.upload_file("%s.%s" % (v[0], file_extension), sanscontent)
    exit()

    ptags = []
    ptags.append(rtinfo['Queue'])

    phids = []
    for p in ptags:
        phids.append(phab.ensure_project(p))

    def priority_convert(priority):
        priorities = { '0': 50, '50': 50}
        return priorities[priority.lower()]

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

    if rtinfo['Status'].lower() != 'open':
        close_remark = '//importing issue status//'
        if 'Resolved' in rtinfo and rtinfo['Resolved'] != 'Not set':
            close_remark += "\n Resolved %s" % (rtinfo['Resolved'],)
        phab.task_comment(ticket['id'], close_remark)
        phab.set_status(ticket['id'], status)

    print 'info', rtinfo

def run_create(tid, tries=1):
    if tries == 0:
        print 'failed to grab %s' % (tid,)
        return False
    try:
        if create(tid):
            print time.time()
            print 'done with %s' % (tid,)
            return True
    except Exception as e:
        import traceback
        tries -= 1
        time.sleep(5)
        traceback.print_exc(file=sys.stdout)
        print 'failed to grab %s (%s)' % (tid, e)
        return run_create(tid, tries=tries)

if sys.stdin.isatty():
    bugs = sys.argv[1:]
else:
    bugs = sys.stdin.read().strip('\n').strip().split()

for i in bugs:
    if i.isdigit():
        run_create(i)
