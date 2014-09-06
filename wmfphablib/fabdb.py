#!/usr/bin/env python
import sys
import MySQLdb
import traceback
import syslog
import phabdb

def get_user_relations(email)
    fabdb = phabdb.phdb(db='fab_migration')
    hq = "SELECT assigned, cc, author, created, modified FROM user_relations WHERE user = %s"
    _ = fabdb.sql_x(hq, (email,))
    if not _:
        return ''
    return _
