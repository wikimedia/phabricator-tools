#!/usr/bin/env python
import sys
import traceback
import syslog
import time

cfile = '/etc/phabtools.conf'

import ConfigParser
parser = ConfigParser.SafeConfigParser()
parser.read(cfile)
dbhost = parser.get('general', 'dbhost')
file_upload_timeout = int(parser.get('general', 'file_upload_timeout'))
parser_mode = 'phmanifest'
phmanifest_user = parser.get(parser_mode, 'user')
phmanifest_passwd = parser.get(parser_mode, 'passwd')
parser_mode = 'phuser'
phuser_user = parser.get(parser_mode, 'user')
phuser_passwd = parser.get(parser_mode, 'passwd')
parser_mode = 'fabmigrate'
fabmigrate_db = parser.get(parser_mode, 'db')
fabmigrate_user = parser.get(parser_mode, 'user')
fabmigrate_passwd = parser.get(parser_mode, 'passwd')
fab_multi = int(parser.get(parser_mode, 'multi'))
fab_limit = int(parser.get(parser_mode, 'limit'))
parser_mode = 'phab'
phab_user = parser.get(parser_mode, 'username')
phab_cert = parser.get(parser_mode, 'certificate')
phab_host = parser.get(parser_mode, 'host')
parser_mode = 'bz'
Bugzilla_url = parser.get(parser_mode, 'url')
Bugzilla_login = parser.get(parser_mode, 'Bugzilla_login')
Bugzilla_password = parser.get(parser_mode, 'Bugzilla_password')
parser_mode = 'bzmigrate'
bzmigrate_db = parser.get(parser_mode, 'db')
bzmigrate_user = parser.get(parser_mode, 'user')
bzmigrate_passwd = parser.get(parser_mode, 'passwd')
bz_createmulti = int(parser.get(parser_mode, 'create_multi'))
bz_fetchmulti = int(parser.get(parser_mode, 'fetch_multi'))
bz_updatelimit = int(parser.get(parser_mode, 'update_limit'))
bz_updatemulti = int(parser.get(parser_mode, 'update_multi'))
bz_security = parser.get(parser_mode, 'security')

if __name__ == '__main__':
    print dbhost
    print file_upload_timeout
    print phmanifest_user
    print phmanifest_passwd
    print phuser_user
    print phuser_passwd
    print fabmigrate_db
    print fabmigrate_user
    print fabmigrate_passwd
    print fab_multi
    print phab_user
    print phab_cert
    print phab_host
    print Bugzilla_url
    print Bugzilla_login
    print Bugzilla_password
    print bzmigrate_db
    print bzmigrate_user
    print bzmigrate_passwd
    print bz_createmulti
    print bz_fetchmulti
    print bz_updatelimit
    print bz_updatemulti
    print bz_security
