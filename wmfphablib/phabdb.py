#!/usr/bin/env python
import sys
import json
import MySQLdb
import traceback
import syslog
import time
from config import dbhost
from config import phmanifest_user
from config import phmanifest_passwd
from config import phuser_user
from config import phuser_passwd
from config import fabmigrate_db
from config import fabmigrate_user
from config import fabmigrate_passwd

def get_user_relations_last_finish(dbcon):
    #get_user_relations_last_finish(pmig)
    fin = dbcon.sql_x("SELECT max(finish_epoch) from user_relations_jobs", ())
    try:
        return int(fin[0][0])
    except:
        return 1

def user_relations_start(pid, source, start, status, start_epoch, user_count, issue_count, dbcon):
    insert_values = (pid, source, start, status, start_epoch, user_count, issue_count, int(time.time()))
    query = "INSERT INTO user_relations_jobs (pid, source, start, status, start_epoch, user_count, issue_count, modified) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    return dbcon.sql_x(query, insert_values)

def user_relations_finish(pid, finish, status, finish_epoch, completed, failed, dbcon):
    update_values = (finish, status, finish_epoch, completed, failed, int(time.time()), pid)
    return dbcon.sql_x("UPDATE user_relations_jobs SET finish=%s, status=%s, finish_epoch=%s, completed=%s , failed=%s, modified=%s WHERE pid = %s",
                  update_values)

def get_user_relations_priority(user, dbcon):
    return dbcon.sql_x("SELECT priority from user_relations where user = %s", user)

def get_user_relations_comments_priority(user, dbcon):
    return dbcon.sql_x("SELECT priority from user_relations_comments where user = %s", user)

def set_user_relations_priority(priority, user, dbcon):
    """Set user status for data import
    :param priority: int
    :param user: user email
    :param dbcon: db connection
     """
    return dbcon.sql_x("UPDATE user_relations SET priority=%s, modified=%s WHERE user = %s",
                  (priority, time.time(), user))

def set_user_relations_comments_priority(priority, user, dbcon):
    """Set user status for data import
    :param priority: int
    :param user: user email
    :param dbcon: db connection
     """
    return dbcon.sql_x("UPDATE user_relations_comments SET priority=%s, modified=%s WHERE user = %s",
                       (priority, time.time(), user))

def get_user_migration_history(user, dbcon):
    """ get user history from import source
    :param user: user email
    :param dbcon: db connection
    :returns: saved history output
     """
    hq = "SELECT assigned, cc, author, created, modified FROM user_relations WHERE user = %s"
    saved_history = dbcon.sql_x(hq, user)
    if saved_history is None:
        return ()
    return saved_history[0]

def get_user_migration_comment_history(user, dbcon):
    """ get user comment history from import source
    :param user: user email
    :param dbcon: db connection
    :returns: saved history output
     """
    hq = "SELECT issues, created, modified FROM user_relations_comments WHERE user = %s"
    saved_history = dbcon.sql_x(hq, user)
    if saved_history is None:
        return ()
    return saved_history[0]

def get_bot_blog(botname):
    p = phdb(db='phabricator_phame', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("SELECT phid from phame_blog where name=%s", ('%s_updates' % (botname,)), limit=1)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def is_bot(userphid):
    p = phdb(db='phabricator_user', user=phuser_user, passwd=phuser_passwd)
    isbot = p.sql_x("SELECT isSystemAgent from user where phid=%s", (userphid,), limit=1)
    p.close()
    if not isbot:
        raise Exception("user is not a present")
    if int(isbot[0][0]) > 0:
        return True
    return False

def last_comment(phid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    com = "SELECT phid from maniphest_transaction where objectPHID=%s and transactionType='core:comment' ORDER BY dateCreated DESC"
    _ = p.sql_x(com, (phid,), limit=1)
    p.close()
    if not _:
        return ''
    return _[0][0]

def set_issue_status(taskphid, status):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task SET status=%s WHERE phid=%s", (status, taskphid))
    p.close()

def set_issue_assigned(taskphid, userphid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task SET ownerPHID=%s WHERE phid=%s", (userphid, taskphid))
    p.close()

def set_comment_content(transxphid, content):
    """set manual content for a comment
    :param transxphid: str
    :param userphid: str
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_transaction_comment SET content=%s WHERE transactionPHID=%s", (content, transxphid))
    p.close()
    return

def set_comment_time(transxphid, metatime):
    """set manual epoch modtime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_transaction SET dateModified=%s WHERE phid=%s", (metatime, transxphid))
    p.sql_x("UPDATE maniphest_transaction SET dateCreated=%s WHERE phid=%s", (metatime, transxphid))
    p.sql_x("UPDATE maniphest_transaction_comment SET dateModified=%s WHERE transactionPHID=%s", (metatime, transxphid))
    p.sql_x("UPDATE maniphest_transaction_comment SET dateCreated=%s WHERE transactionPHID=%s", (metatime, transxphid))
    p.close()
    return

def set_comment_author(transxphid, userphid):
    """set manual owner for a comment
    :param transxphid: str
    :param userphid: str
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_transaction SET authorPHID=%s WHERE phid=%s", (userphid, transxphid))
    p.sql_x("UPDATE maniphest_transaction_comment SET authorPHID=%s WHERE transactionPHID=%s", (userphid, transxphid))
    p.close()
    return

def set_task_mtime(taskphid, mtime):
    """set manual epoch modtime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("UPDATE maniphest_task SET dateModified=%s WHERE phid=%s", (mtime, taskphid))
    p.close()
    return _

def set_task_ctime(taskphid, ctime):
    """set manual epoch ctime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("UPDATE maniphest_task SET dateCreated=%s WHERE phid=%s", (ctime, taskphid))
    p.close()
    return _

def get_emails(modtime=0):
    p = phdb(db='phabricator_user', user=phuser_user, passwd=phuser_passwd)
    sql = "SELECT address from user_email"
    _ = pmig.sql_x(sql, (), limit=None)
    pmig.close()
    if not _:
        return ''
    return _

def set_blocked_task(blocker, blocked):
    """sets two tasks in dependent state
    :param blocker: blocking tasks phid
    :param blocked: blocked tasks phid
    """
    blocked_already = get_tasks_blocked(blocker)
    if blocked in blocked_already:
        return
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    insert_values = (blocker, 4, blocked, int(time.time()), 0)
    p.sql_x("INSERT INTO edge (src, type, dst, dateCreated, seq) VALUES (%s, %s, %s, %s, %s)",
            insert_values)

    insert_values = (blocked, 3, blocker, int(time.time()), 0)
    p.sql_x("INSERT INTO edge (src, type, dst, dateCreated, seq) VALUES (%s, %s, %s, %s, %s)",
            insert_values)
    p.close()
    return get_tasks_blocked(blocker)

def get_tasks_blocked(taskphid):
    """ get the tasks I'm blocking
    :param taskphid: str
    :returns: list
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("SELECT dst FROM edge WHERE type = 4 AND src=%s",  (taskphid,), limit=None)
    p.close()
    if not _:
        return []
    return [b[0] for b in _]

def get_blocking_tasks(taskphid):
    """ get the tasks blocking me
    :param taskphid: str
    :returns: list
    """
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("SELECT dst FROM edge WHERE type = 3 and dst=%s",  (taskphid,), limit=None)
    p.close()
    if not _:
        return ''
    return _

def get_task_id_by_phid(taskphid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("SELECT id from maniphest_task where phid=%s;",  (taskphid,), limit=None)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def get_user_relations():
    fabdb = phabdb.phdb(db='fab_migration')
    hq = "SELECT assigned, cc, author, created, modified FROM user_relations WHERE user = %s"
    _ = fabdb.sql_x(hq, (v[1],))
    fabdb.close()
    if not _:
        return ''
    return _

def get_verified_user(email):
    phid, email, is_verified = get_user_email_info(email)
    #log("Single specified user: %s, %s, %s" % (phid, email, is_verified))
    if is_verified:
        return [(phid, email)]
    else:
        #log("%s is not a verified email" % (email,))
        return [()]

def get_user_email_info(emailaddress):
    p = phdb(db='phabricator_user', user=phuser_user, passwd=phuser_passwd)
    sql = "SELECT userPHID, address, isVerified from user_email where address=%s"

    _ = p.sql_x(sql, emailaddress)
    p.close()
    return _[0] or ''

def get_verified_users(modtime, limit=None):
    #Find the task in new Phabricator that matches our lookup
    verified = get_verified_emails(modtime=modtime, limit=limit)
    create_times = [v[2] for v in verified]
    try:
        newest = max(create_times)
    except ValueError:
        newest = modtime
    return verified, newest

def get_verified_emails(modtime=0, limit=None):
    p = phdb(db='phabricator_user', user=phuser_user, passwd=phuser_passwd)
    sql = "SELECT userPHID, address, dateModified from user_email where dateModified > %s and isVerified = 1"
    _ = p.sql_x(sql, (modtime), limit=limit)
    p.close()
    if not _:
        return []
    return list(_)

def reference_ticket(reference):
    """ Find the new phab ticket id for a reference id
    :param reference: str ref id
    :returns: str of phid
    """
    p = phdb(db='phabricator_maniphest', user=phmanifest_user, passwd=phmanifest_passwd)
    _ = p.sql_x("SELECT objectPHID FROM maniphest_customfieldstringindex WHERE indexValue = %s", reference)
    p.close()
    if not _:
        return ''
    return _[0]

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
    p = phdb(db='phabricator_user', user=phuser_user, passwd=phuser_passwd)
    phid = p.sql_x("SELECT * from user_email where userPHID = %s", (userphid))
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
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    comtx = p.sql_x("SELECT * from maniphest_transaction_comment where transactionPHID = %s",
                   comment_xact, limit=None)
    p.close()
    return comtx

def comment_transactions_by_task_phid(taskphid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    coms = p.sql_x("SELECT * from maniphest_transaction where objectPHID = %s AND transactionType = 'core:comment'",
                   taskphid, limit=None)
    p.close()
    return coms


def phid_by_custom_field(custom_value):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
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
    p = phdb(db='phabricator_project', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("UPDATE project SET status=%s WHERE name=%s", (100, project))
    p.close()
    return _

def set_project_icon(project, icon='briefcase', color='blue'):
    """ tag       = tags
        briefcase = briefcase
        people    = users
        truck     = releases
    """
    if icon == 'tags':
        color = 'yellow'
    elif icon == 'people':
        color = 'violet'
    elif icon == 'truck':
        color = 'orange'

    p = phdb(db='phabricator_project', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("UPDATE project SET icon=%s, color=%s WHERE name=%s", ('fa-' + icon, color, project))
    p.close()
    return _

def set_task_author(authorphid, id):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    _ = p.sql_x("UPDATE maniphest_task SET authorPHID=%s WHERE id=%s", (authorphid, id))
    p.close()
    return _

def add_task_cc_by_ref(userphid, oldid):
    refs = reference_ticket('bz%s' % (oldid,))
    if not refs:
        #log('reference ticket not found for %s' % ('bz%s' % (oldid,),))
        return
    return add_task_cc(refs[0], userphid)

def add_task_cc(ticketphid, userphid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    ccq = "SELECT ccPHIDs FROM maniphest_task WHERE phid = %s"
    jcc_list = p.sql_x(ccq, ticketphid)
    #XXXX: TESTING
    #HAD TO PURGE SECURITY TICKETS FOR IGNORE NONE RETURN FOR TESTING ONLY
    if jcc_list is None:
        return
    #####
    cc_list = json.loads(jcc_list[0][0])
    if userphid not in cc_list:
        cc_list.append(userphid)
    p.sql_x("UPDATE maniphest_task SET ccPHIDs=%s WHERE phid=%s", (json.dumps(cc_list), ticketphid))
    final_jcclist = p.sql_x(ccq, ticketphid)[0]
    set_task_subscriber(ticketphid, userphid)
    p.close()
    return json.loads(final_jcclist[0])

def set_task_subscriber(taskphid, userphid):
    p = phdb(db='phabricator_maniphest', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("INSERT INTO maniphest_tasksubscriber (taskPHID, subscriberPHID) VALUES (%s, %s)",
            (taskphid, userphid))
    p.close()


class phdb:
    def __init__(self, host = dbhost,
                       user = "root",
                       passwd = "labspass",
                       db = "phab_migration",
                       charset = 'utf8',):

        self.conn = MySQLdb.connect(host=host,
                                user=user,
                                passwd=passwd,
                                db=db,
                                charset=charset)
    #print sql_x("SELECT * FROM bugzilla_meta WHERE id = %s", (500,))
    def sql_x(self, statement, arguments, limit=1):
        x = self.conn.cursor()
        try:
            if limit and statement.startswith('SELECT'):
                statement += ' limit %s' % (limit,)
            x.execute(statement, arguments)
            if statement.startswith('SELECT'):
                r = x.fetchall()
                if r:
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
