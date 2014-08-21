import yaml
import os
import re
import sys
import getpass
import logging
import ConfigParser
sys.path.append('/home/rush/python-rtkit/')
from rtkit import resource
from rtkit import authenticators
from rtkit import errors
from rtkit import set_logging

set_logging('debug' if '-v' in sys.argv else 'info')
logger = logging.getLogger('rtkit')

#u = getpass.getpass(prompt='username? ')
#print 'You entered:', u
#p = getpass.getpass()

parser = ConfigParser.SafeConfigParser()
parser_mode = 'rt'
parser.read('/etc/gz_fetch.conf')
response = resource.RTResource(parser.get(parser_mode, 'url'),
                               parser.get(parser_mode, 'username'),
                               parser.get(parser_mode, 'password'),
                               authenticators.CookieAuthenticator)
TICKET = sys.argv[1]
yaml_file = 'data.yaml'

try:
    tinfo = response.get(path="ticket/%s" % (TICKET,))
    attachments = response.get(path="ticket/%s/attachments/" % (TICKET,))
    history = response.get(path="ticket/%s/history?format=l" % (TICKET,))

    #we get back freeform text and create a dict
    dtinfo = {}
    for cv in tinfo.strip().splitlines():
        if not cv:
            continue
        #TimeEstimated: 0
        k, v = re.split(':', cv, 1)
        dtinfo[k.strip()] = v.strip()

    #breaking detailed history into posts
    #23/23 (id/114376/total)
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    comments = [c.rstrip('#').rstrip('--') for c in comments]

    #attachments into a dict
    attached = re.split('Attachments:', attachments, 1)[1]
    ainfo = {}
    for at in attached.strip().splitlines():
        if not at:
            continue
        k, v = re.split(':', at, 1)
        ainfo[k.strip()] = v.strip()

    #lots of junk attachments from emailing comments and ticket creation
    ainfo_f = {}
    for k, v in ainfo.iteritems():
        if '(Unnamed)' not in v:
            ainfo_f[k] = v

    #taking attachment text and convert to tuple (name, content type, size)
    ainfo_ext = {}
    comments = re.split("\d+\/\d+\s+\(id\/.\d+\/total\)", history)
    for k, v in ainfo_f.iteritems():
        logger.debug('org %s' % v)
        extract = re.search('(.*\....)\s\((.*)\s\/\s(.*)\)', v)
        #logger.debug(str(extract.groups()))
        if not extract:
           logger.debug("%s %s" % (k, v))
        else:
           ainfo_ext[k] = extract.groups()

    def save_attachment(name, data):
        f = open(name, 'wb')
        f.write(data)
        f.close()

    #SAVING ATTACHMENTS TO DISK
    dl = []
    for k, v in ainfo_ext.iteritems():
        try:
            full = "ticket/%s/attachments/%s/content" % (TICKET, k)
            print full
            vcontent = response.get(path=full, headers={'Content-Type': v[1], 'Content-Length': v[2] })
            path = os.path.join('attachments', v[0])
            save_attachment(path, vcontent)
            dl.append(path)
        except Exception as e:
            logging.error(str(e))

    TICKET_INFO = (dtinfo, dl, comments)
    with open(yaml_file, 'w') as outfile:
        outfile.write( yaml.dump(TICKET_INFO, default_flow_style=True) )

    print 'info', dtinfo
    print 'downloaded', dl
    print 'comments', len(comments)
    print 'written to', yaml_file
    sys.exit(0)
except resource.errors.RTResourceError as e:
    logger.error(e.response.status_int)
    logger.error(e.response.status)
    logger.error(e.response.parsed)
