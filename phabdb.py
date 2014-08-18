#!/usr/bin/env python
import sys
import MySQLdb
from email.parser import Parser
import ConfigParser
import traceback
import syslog


def mailinglist_phid(list_email):
    p = phdb(db="phabricator_metamta")
    phid = p.sql_x("SELECT * FROM metamta_mailinglist WHERE email = %s",
                  (list_email))
    if phid:
        phid = phid[1]
    p.close()
    return phid

def archive_project(project):
    p = phdb(db='phabricator_project')
    _ = p.sql_x("UPDATE project SET status=%s WHERE name=%s", (100, project))
    p.close()
    return _

def set_project_icon(project, icon='briefcase', color='blue'):
    """ tag       = tags
        briefcase = briefcase
        people    = users
        truck     = releases
    """

    p = phdb(db='phabricator_project')
    _ = p.sql_x("UPDATE project SET icon=%s, color=%s  WHERE name=%s", ('fa-' + icon, color, project))
    p.close()
    return _

class phdb:
    def __init__(self, host= "localhost",
                       user="root",
                       passwd="labspass",
                       db="phab_migration",
                       charset='utf8',):

        self.conn = MySQLdb.connect(host=host,
                                user=user,
                                passwd=passwd,
                                db=db,
                                charset=charset)
    #print sql_x("SELECT * FROM bugzilla_meta WHERE id = %s", (500,))
    def sql_x(self, statement, arguments):
        x = self.conn.cursor()
        try:
            x.execute(statement, arguments)
            if statement.startswith('SELECT'):
                r = x.fetchall()
                if r:
                    return r[0]
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print e
            print 'rollback!'
            self.conn.rollback()
        else:
            self.conn.commit()

    def close(self):
        self.conn.close()

