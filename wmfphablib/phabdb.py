#!/usr/bin/env python
import sys
import MySQLdb
import traceback
import syslog

def email_by_userphid(userphid):
    """
    userPHID: PHID-USER-egea763uwv723xifsfya
    address: foo@fastmail.fm
    isVerified: 1

    isPrimary: 1
    verificationCode: zgqynjnpeefgzvxybaojsr2e
    dateCreated: 1409007602
    dateModified: 1409007702

    (563L, \
    'PHID-USER-egea763uwv723xifsfya', \
    u'foo@fastmail.fm', \
    1, \
    1, \
    'zgqynjnpeefgzvxybaojsr2e', \
    1409007602L, \
    1409007702L)
    """
    p = phdb(db="phabricator_user")
    phid = p.sql_x("SELECT * from user_email where userPHID = %s", (userphid))
    #print phid
    if phid:
        email = phid[2]
        verfied = phid[3]
        primary = phid[4]
        if verfied != 1:
            return None
    else:
        print 'no phid for user for email lookup'
        email = ''
    p.close()
    return email

def comment_by_transaction(comment_xact):
    p = phdb(db="phabricator_maniphest")
    comtx = p.sql_x("SELECT * from maniphest_transaction_comment where transactionPHID = %s",
                   comment_xact, limit=None)
    p.close()
    return comtx

def comment_transactions_by_task_phid(taskphid):
    p = phdb(db="phabricator_maniphest")
    coms = p.sql_x("SELECT * from maniphest_transaction where objectPHID = %s AND transactionType = 'core:comment'",
                   taskphid, limit=None)
    p.close()
    return coms


def phid_by_custom_field(custom_value):
    p = phdb(db="phabricator_maniphest")
    phid = p.sql_x("SELECT * from maniphest_customfieldstringindex WHERE indexValue = %s",
                  (custom_value))
    if phid:
        phid = phid[1]
    p.close()
    return phid

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
    def sql_x(self, statement, arguments, limit=1):
        x = self.conn.cursor()
        try:
            x.execute(statement, arguments)
            if statement.startswith('SELECT'):
                r = x.fetchall()
                if r:
                    if limit:
                        return r[0]
                    else:
                        return r
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print e
            print 'rollback!'
            self.conn.rollback()
        else:
            self.conn.commit()

    def close(self):
        self.conn.close()

