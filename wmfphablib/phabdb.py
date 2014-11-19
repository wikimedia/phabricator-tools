#!/usr/bin/env python
import sys
import os
import json
import MySQLdb
import traceback
import syslog
import time
import util
from config import dbhost
from config import phmanifest_user
from config import phmanifest_passwd
from config import phuser_user
from config import phuser_passwd
from config import fabmigrate_db
from config import fabmigrate_user
from config import fabmigrate_passwd

def get_user_relations_last_finish(dbcon):
    """ get last finish time for update script
    :param dbcon: db connector
    """
    fin = dbcon.sql_x("SELECT max(finish_epoch) \
                      from user_relations_jobs \
                      where \
                      source=bugzilla_update_user_header",
                      ())
    try:
        return int(fin[0][0])
    except:
        return 1

def get_user_relations_comments_last_finish(dbcon):
    """ get last finish time for update script
    :param dbcon: db connector
    """
    fin = dbcon.sql_x("SELECT max(finish_epoch) \
                      from user_relations_jobs \
                      where \
                      source=bugzilla_update_user_comments",
                      ())
    try:
        return int(fin[0][0])
    except:
        return 1

def get_issues_by_priority(dbcon, priority):
    """ get failed creations
    :param dbcon: db connector
    :param priority: int
    :returns: list
    """
    _ = dbcon.sql_x("SELECT id \
                    from bugzilla_meta \
                    where priority=%s",
                    (priority,),
                    limit=None)
    if _ is None:
        return
    f_ = list(util.tflatten(_))
    if f_:
        return f_

def get_failed_creations(dbcon):
    """ get failed creations
    :param dbcon: db connector
    :returns: list
    """
    _ = dbcon.sql_x("SELECT id \
                    from bugzilla_meta \
                    where priority=%s",
                    (6,),
                    limit=None)
    if _ is None:
        return
    f_ = list(util.tflatten(_))
    if f_:
        return f_

def user_relations_start(pid,
                         source,
                         start,
                         status,
                         start_epoch,
                         user_count,
                         issue_count,
                         dbcon):
    """ set entry for user relations
    :param pid: int
    :param source: str of source
    :param start: epoch
    :param status: int
    :param start_epoch: starting epoch
    :param user_count: int
    :param issue_count: int
    :param dbcon: db connector
    """
    insert_values = (pid, source,
                     start, status,
                     start_epoch, user_count,
                     issue_count, int(time.time()))
    query = "INSERT INTO user_relations_jobs \
            (pid, source, start, status, start_epoch, \
            user_count, issue_count, modified) \
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    return dbcon.sql_x(query, insert_values)

def user_relations_finish(pid,
                          finish,
                          status,
                          finish_epoch,
                          completed,
                          failed,
                          dbcon):
    update_values = (finish,
                     status,
                     finish_epoch,
                     completed,
                     failed,
                     int(time.time()),
                     pid)
    return dbcon.sql_x("UPDATE user_relations_jobs \
                       SET finish=%s, \
                       status=%s, \
                       finish_epoch=%s, \
                       completed=%s, \
                       failed=%s, \
                       modified=%s WHERE pid = %s",
                       update_values)

def get_user_relations_priority(user, dbcon):
    """select user relation priority
    :param user: email str
    :param dbcon: db connector
    """
    return dbcon.sql_x("SELECT priority \
                       from user_relations \
                       where user = %s", user)

def get_user_relations_comments_priority(user, dbcon):
    """select user relation comments priority
    :param user: email str
    :param dbcon: db connector
    """
    return dbcon.sql_x("SELECT priority \
                       from user_relations_comments \
                       where user = %s", 
                       user)

def set_user_relations_priority(priority, user, dbcon):
    """Set user status for data import
    :param priority: int
    :param user: user email
    :param dbcon: db connection
     """
    return dbcon.sql_x("UPDATE user_relations \
                       SET priority=%s, modified=%s \
                       WHERE user = %s",
                       (priority, time.time(), user))

def set_user_relations_comments_priority(priority, user, dbcon):
    """Set user status for data import
    :param priority: int
    :param user: user email
    :param dbcon: db connection
     """
    return dbcon.sql_x("UPDATE user_relations_comments \
                        SET priority=%s, modified=%s \
                        WHERE user = %s",
                       (priority, time.time(), user))

def get_user_migration_history(user, dbcon):
    """ get user history from import source
    :param user: user email
    :param dbcon: db connection
    :returns: saved history output
     """
    query = "SELECT assigned, cc, author, created, modified \
         FROM user_relations WHERE user = %s"
    saved_history = dbcon.sql_x(query, user)
    if saved_history is None:
        return ()
    return saved_history[0]

def get_user_migration_comment_history(user, dbcon):
    """ get user comment history from import source
    :param user: user email
    :param dbcon: db connection
    :returns: saved history output
     """
    query = "SELECT issues, created, modified \
             FROM user_relations_comments \
             WHERE user = %s"
    saved_history = dbcon.sql_x(query, user)
    if saved_history is None:
        return ()
    return saved_history[0]

def get_file_id_by_phid(ticketphid):
    """return file id by PHID
    :param ticketphid: str
    :returns: str
    """
    p = phdb(db='phabricator_file',
             user=phuser_user,
             passwd=phuser_passwd)
    _ = p.sql_x("SELECT id \
                from file where phid=%s",
                (ticketphid), limit=1)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def get_bot_blog(botname):
    """ get bot block PHID
    :param botname: str
    :returns: str
    """
    p = phdb(db='phabricator_phame',
             user=phuser_user,
             passwd=phuser_passwd)
    _ = p.sql_x("SELECT phid \
                from phame_blog where name=%s",
                ('%s_updates' % (botname,)),
                limit=1)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def is_bot(userphid):
    """ verify user bot status
    :param userphid: str
    :returns: bool
    """
    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)
    isbot = p.sql_x("SELECT isSystemAgent \
                    from user where phid=%s",
                    (userphid,), limit=1)
    p.close()
    if not isbot:
        raise Exception("user is not a present")
    if int(isbot[0][0]) > 0:
        return True
    return False

def last_comment(phid):
    """get phid of last comment for an issue
    :param phid: str of issue phid
    :returns: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT phid from maniphest_transaction \
             where objectPHID=%s \
             and transactionType='core:comment' \
             ORDER BY dateCreated DESC"
    _ = p.sql_x(query, (phid,), limit=1)
    p.close()
    if not _:
        return ''
    return _[0][0]

def set_issue_status(taskphid, status):
    """ update an issue state
    :param taskphid: str
    :param status: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET status=%s WHERE phid=%s",
             (status, taskphid))
    p.close()

def set_issue_assigned(taskphid, userphid):
    """ update task assignee
    :param taskphid: str
    :param userphid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET ownerPHID=%s WHERE phid=%s",
             (userphid, taskphid))
    p.close()

def set_comment_content(transxphid, content):
    """set manual content for a comment
    :param transxphid: str
    :param userphid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_transaction_comment \
             SET content=%s WHERE transactionPHID=%s",
             (content, transxphid))
    p.close()

def set_transaction_time(transxphid, metatime):

    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_transaction \
             SET dateModified=%s WHERE phid=%s",
             (metatime, transxphid))
    p.sql_x("UPDATE maniphest_transaction \
             SET dateCreated=%s WHERE phid=%s", 
             (metatime, transxphid))
    p.close()

def set_comment_time(transxphid, metatime):
    """set manual epoch modtime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    set_transaction_time(transxphid, metatime)
    p.sql_x("UPDATE maniphest_transaction_comment \
             SET dateModified=%s \
             WHERE transactionPHID=%s",
             (metatime, transxphid))
    p.sql_x("UPDATE maniphest_transaction_comment \
             SET dateCreated=%s \
             WHERE transactionPHID=%s",
             (metatime, transxphid))
    p.close()

def set_comment_author(transxphid, userphid):
    """set manual owner for a comment
    :param transxphid: str
    :param userphid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    p.sql_x("UPDATE maniphest_transaction \
             SET authorPHID=%s \
             WHERE phid=%s",
             (userphid, transxphid))

    p.sql_x("UPDATE maniphest_transaction_comment \
             SET authorPHID=%s \
             WHERE transactionPHID=%s",
             (userphid, transxphid))

def set_task_mtime(taskphid, mtime):
    """set manual epoch modtime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET dateModified=%s \
             WHERE phid=%s",
             (mtime, taskphid))
    p.close()


def set_task_ctime(taskphid, ctime):
    """set manual epoch ctime for task
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET dateCreated=%s \
             WHERE phid=%s", (ctime, taskphid))
    titlexphid = get_task_title_transaction(taskphid)
    set_transaction_time(titlexphid, ctime)

    p.close()

def get_task_description(taskphid):
    """get task description
    :param taskphid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    _ = p.sql_x("SELECT description \
                 from maniphest_task \
                 WHERE phid=%s", (phid,))
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def set_task_description(taskphid, text):
    """set task description
    :param taskphid: str
    :param mtime: int of modtime
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET description=%s \
             WHERE phid=%s", (text, taskphid))
    p.close()

def get_emails(modtime=0):
    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT address from user_email"
    _ = pmig.sql_x(query, (), limit=None)
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
        util.vlog("%s already blocking %s" % (blocker,
                                              blocked))
        return
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    insert_values = (blocker, 4, blocked, int(time.time()), 0)
    p.sql_x("INSERT INTO edge \
             (src, type, dst, dateCreated, seq) \
             VALUES (%s, %s, %s, %s, %s)",
             insert_values)

    insert_values = (blocked, 3, blocker, int(time.time()), 0)
    p.sql_x("INSERT INTO edge \
             (src, type, dst, dateCreated, seq) \
             VALUES (%s, %s, %s, %s, %s)",
             insert_values)
    p.close()
    return get_tasks_blocked(blocker)

def phid_hash():
    """get a random hash for PHID building"""
    return os.urandom(20).encode('hex')[:20]

def task_transaction_phid():
    """get a transaction PHID"""
    return 'PHID-XACT-TASK-' + str(phid_hash()[:15])

def gen_user_phid():
    return 'PHID-USER-' + str(phid_hash()[:20])

def get_task_title(phid):
    """get the title of a task by phid
    :param phid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    _ = p.sql_x("SELECT title \
                 from maniphest_task \
                 WHERE phid=%s", (phid,))
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def get_task_title_transaction(phid):
    """ get the transaction of type 'title' for a task
    :param phid: str
    :note: this results in created date / author in UI
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    _ = p.sql_x("SELECT phid \
                 from maniphest_transaction \
                 where objectPHID=%s \
                 and transactionType='title'", (phid,))
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def create_test_user(userName,
                     realName,
                     address):

    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)

    newphid = gen_user_phid()
    passwordSalt = 'xxxxxx'
    passwordHash = 'bcrypt:xxxxx'
    dateCreated = int(time.time())
    dateModified = int(time.time())
    import random
    conduitCertificate = str(random.random()).split('.')[1]
    accountSecret = str(random.random()).split('.')[1]

    p.sql_x("INSERT INTO user \
                 (phid, \
                  userName, \
                  realName, \
                  passwordSalt, \
                  passwordHash, \
                  consoleEnabled, \
                  consoleVisible, \
                  conduitCertificate, \
                  isSystemAgent, \
                  isDisabled, \
                  isAdmin, \
                  isEmailVerified, \
                  isApproved, \
                  accountSecret, \
                  isEnrolledInMultiFactor, \
                  consoleTab, \
                  timezoneIdentifier, \
                  dateCreated, \
                  dateModified) \
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  (newphid,
                  userName,
                  realName,
                  passwordSalt,
                  passwordHash,
                  0,
                  0,
                  conduitCertificate,
                  0,
                  0,
                  0,
                  1,
                  1,
                  accountSecret,
                  0,
                  '',
                  '',
                  dateCreated,
                  dateModified))

    p.sql_x("INSERT INTO user_email \
                 (userPHID, \
                  address, \
                  isVerified, \
                  isPrimary, \
                  verificationCode, \
                  dateCreated, \
                  dateModified) \
                  VALUES (%s, %s, %s, %s, %s, %s, %s)",
                  (newphid,
                   address,
                   1,
                   1,
                   accountSecret,
                   dateCreated,
                   dateModified))
    p.close()

def set_task_title_transaction(taskphid,
                               authorphid,
                               viewPolicy,
                               editPolicy,
                               source='legacy'):
    """creates a title transaction for "created"
       transaction display in UI.
    :param taskphid: str
    :authorphid: str
    :viewPolicy: str
    :editPolicy: str
    :source: valid source type as str
    :note:
        * source must match a valid upstream type
        * this crutches an inconsistency where tasks
          created via the UI are assigned these 
          transactions and via conduit are not.
    """

    existing = get_task_title_transaction(taskphid)
    if existing:
        return

    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    dateCreated = int(time.time())
    dateModified = int(time.time())
    newphid = task_transaction_phid()
    contentSource = json.dumps({"source": source,
                                "params": {"ip":"127.0.0.1"}})
    commentVersion = 0
    title = get_task_title(taskphid)
    oldValue = 'null'

    p.sql_x("INSERT INTO maniphest_transaction \
                 (phid, \
                  authorPHID, \
                  objectPHID, \
                  viewPolicy, \
                  editPolicy, \
                  commentVersion, \
                  transactionType, \
                  oldValue, \
                  newValue, \
                  contentSource, \
                  metadata, \
                  dateCreated, \
                  dateModified) \
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  (newphid,
                  authorphid,
                  taskphid,
                  viewPolicy,
                  editPolicy,
                  commentVersion,
                  'title',
                  oldValue,
                  title,
                  contentSource,
                  json.dumps([]),
                  dateCreated,
                  dateModified))
    p.close()

def get_tasks_blocked(taskphid):
    """ get the tasks I'm blocking
    :param taskphid: str
    :returns: list
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    _ = p.sql_x("SELECT dst \
                 FROM edge \
                 WHERE type = 4 AND src=%s",
                 (taskphid,), limit=None)
    p.close()
    if not _:
        return []
    return [b[0] for b in _]

def get_blocking_tasks(taskphid):
    """ get the tasks blocking me
    :param taskphid: str
    :returns: list
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    _ = p.sql_x("SELECT dst \
                 FROM edge \
                 WHERE type = 3 and dst=%s",
                 (taskphid,), limit=None)
    p.close()
    if not _:
        return ''
    return _

def get_task_id_by_phid(taskid):
    """ get task id by phid
    :param taskid: str
    :returns: str
    """

    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    _ = p.sql_x("SELECT id \
                 from maniphest_task \
                 where phid=%s;",
                 (taskid,), limit=None)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def set_task_id(id, phid):
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    print "UPDATE maniphest_task set id=%s where phid=%s" % (id, phid)
    p.sql_x("UPDATE maniphest_task set id=%s where phid=%s", (id, phid))
    p.close()

def get_task_phid_by_id(taskid):
    """ get task phid by id
    :param taskid: str
    :returns: str
    """

    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    _ = p.sql_x("SELECT phid \
                 from maniphest_task \
                 where id=%s;",
                 (taskid,), limit=None)
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def get_user_relations():
    p = phabdb.phdb(db='fab_migration')
    query = "SELECT assigned, \
          cc, author, created, modified \
          FROM user_relations WHERE user = %s"
    _ = p.sql_x(query, (v[1],))
    p.close()
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

def get_phid_by_username(username):
    """ get phid of user
    :param userame: str
    """
    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT phid \
            from user where username=%s"
    _ = p.sql_x(query, (username,))
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

def get_user_email_info(emailaddress):
    """ get data on user email
    :param emailaddress: str
    """
    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT userPHID, address, isVerified \
           from user_email where address=%s"
    _ = p.sql_x(query, emailaddress)
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
    p = phdb(db='phabricator_user',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT userPHID, address, dateModified \
             from user_email \
             WHERE dateModified > %s and isVerified = 1"
    _ = p.sql_x(query, (modtime), limit=limit)
    p.close()
    if not _:
        return []
    return list(_)

def reference_ticket(reference):
    """ Find the new phab ticket id for a reference id
    :param reference: str ref id
    :returns: str of phid
    """
    p = phdb(db='phabricator_maniphest',
             user=phmanifest_user,
             passwd=phmanifest_passwd)
    _ = p.sql_x("SELECT objectPHID \
                 FROM maniphest_customfieldstringindex \
                 WHERE indexValue = %s", reference)
    p.close()
    if not _:
        return ''
    return _[0]

def remove_reference(refname):
    """ delete a custom field reference
    :param refname: str
    """

    p = phdb(db='phabricator_maniphest',
             user=phmanifest_user,
             passwd=phmanifest_passwd)
    _ = p.sql_x("DELETE from \
                 maniphest_customfieldstringindex \
                 WHERE indexValue=%s", (refname,))
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
    """ get a particular comment by trx phid
    :param comment_xact: str
    """

    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    comtx = p.sql_x("SELECT * \
                     from maniphest_transaction_comment \
                     where transactionPHID = %s",
                     comment_xact, limit=None)
    p.close()
    return comtx

def comment_transactions_by_task_phid(taskphid):
    """ get comment transactions for an issue
    :param taskphid: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    coms = p.sql_x("SELECT * \
                    from maniphest_transaction \
                    where objectPHID = %s \
                    AND transactionType = 'core:comment'",
                    taskphid, limit=None)
    p.close()
    return coms


def phid_by_custom_field(custom_value):
    """ get an issue phid by custom field
    :param custom_value: str
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    phid = p.sql_x("SELECT * \
                    from maniphest_customfieldstringindex \
                    WHERE indexValue = %s",
                    (custom_value))
    if phid:
        phid = phid[1]
    p.close()
    return phid

def mailinglist_phid(list_email):
    """get email list phid
    :param list_emai: email str
    """
    p = phdb(db="phabricator_metamta")
    phid = p.sql_x("SELECT * \
                    FROM metamta_mailinglist \
                    WHERE email = %s",
                    (list_email))
    if phid:
        phid = phid[1]
    p.close()
    return phid

def archive_project(project):
    """set a project as archived"""
    p = phdb(db='phabricator_project', user=phuser_user, passwd=phuser_passwd)
    p.sql_x("UPDATE project \
             SET status=%s \
             WHERE name=%s", (100, project))
    p.close()

def set_project_policy(projphid, view, edit):
    """set a project as view policy
    :param projphid: str
    :param view: str
    :param edit: str
    """
    p = phdb(db='phabricator_project',
             user=phuser_user,
             passwd=phuser_passwd)

    p.sql_x("UPDATE project \
             SET viewPolicy=%s, \
             editPolicy=%s \
             WHERE phid=%s", (view,
                              edit,
                              projphid))
    p.close()

def set_project_policy(projphid, view, edit):
    """set a project as view policy
    :param projphid: str
    :param view: str
    :param edit: str
    """
    p = phdb(db='phabricator_project',
             user=phuser_user,
             passwd=phuser_passwd)

    p.sql_x("UPDATE project \
             SET viewPolicy=%s, \
             editPolicy=%s \
             WHERE phid=%s", (view,
                              edit,
                              projphid))
    p.close()

def get_project_phid(project):
    p = phdb(db='phabricator_project',
             user=phuser_user,
             passwd=phuser_passwd)
    _ = p.sql_x("SELECT phid from project \
                 WHERE name=%s", (project))
    p.close()
    if _ is not None and len(_[0]) > 0:
        return _[0][0]

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

    p = phdb(db='phabricator_project',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE project \
             SET icon=%s, color=%s \
             WHERE name=%s",
             ('fa-' + icon, color, project))
    p.close()

def set_task_author(authorphid, id):
    """ set task authorship
    :param authorphid: str
    :param id: str
    :note: stored in a few places
    """
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    p.sql_x("UPDATE maniphest_task \
             SET authorPHID=%s \
             WHERE id=%s", (authorphid, id))

    # Phab natively CC's authors so we do the same
    ticketphid = get_task_phid_by_id(id)

    add_task_cc(ticketphid, authorphid)

    # separately stored transaction for creation of object
    transxphid = get_task_title_transaction(ticketphid)
    p.sql_x("UPDATE maniphest_transaction \
             SET authorPHID=%s \
             WHERE phid=%s",
             (authorphid, transxphid))
    p.close()

def add_task_cc_by_ref(userphid, oldid, prepend):
    """ set user as cc'd by a task
    :param userphid: str
    :param oldid: str
    :param prepend: str
    """
    refs = reference_ticket('%s%s' % (prepend,
                                      oldid))
    if not refs:
        return
    return add_task_cc(refs[0], userphid)

def add_task_cc(ticketphid, userphid):
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)

    # Get json array of subscribers
    query = "SELECT ccPHIDs FROM \
           maniphest_task WHERE phid = %s"
    jcc_list = p.sql_x(query, ticketphid)

    if jcc_list is None:
        util.notice("!Ignoring CC for user %s on issue %s" % (userphid,
                                                              ticketphid))
        return
    cc_list = json.loads(jcc_list[0][0])
    if userphid not in cc_list:
        cc_list.append(userphid)
    p.sql_x("UPDATE maniphest_task \
             SET ccPHIDs=%s \
             WHERE phid=%s", (json.dumps(cc_list), ticketphid))
    final_jcclist = p.sql_x(query, ticketphid)[0]
    set_task_subscriber(ticketphid, userphid)
    p.close()
    return json.loads(final_jcclist[0])

def set_task_subscriber(taskphid, userphid):
    p = phdb(db='phabricator_maniphest',
             user=phuser_user,
             passwd=phuser_passwd)
    query = "SELECT taskPHID, subscriberPHID \
             from maniphest_tasksubscriber \
             where taskPHID=%s and subscriberPHID=%s"
    existing = p.sql_x(query, (taskphid, userphid))
    # Note only bad to do dupe inserts columns are UNIQUE
    if existing is None:
        p.sql_x("INSERT INTO maniphest_tasksubscriber \
                 (taskPHID, subscriberPHID) VALUES (%s, %s)",
                 (taskphid, userphid))
    p.close()


class phdb:
    def __init__(self, host = dbhost,
                       user = phuser_user,
                       passwd = phuser_passwd,
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
