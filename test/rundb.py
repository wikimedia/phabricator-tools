import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append('/'.join(path.split('/')[:-1]))
from wmfphablib import phabdb
print phabdb.get_tasks_blocked('PHID-TASK-llxzmfbbcc4adujigg4w')
print phabdb.get_tasks_blocked('PHID-TASK-cjibddnd5lsa5n5hdsyx')
exit()
print phabdb.set_tasks_blocked('PHID-TASK-llxzmfbbcc4adujigg4w', 'PHID-TASK-cjibddnd5lsa5n5hdsyx')

#print phabdb.get_blocking_tasks('PHID-TASK-llxzmfbbcc4adujigg4w')
#print phabdb.phid_by_custom_field('fl562')
print 'email', phabdb.email_by_userphid('PHID-USER-nnipdbdictreyx7qhaii')

#get the comment transactions by task
coms =  phabdb.comment_transactions_by_task_phid('PHID-TASK-3eivod3do2vzdviblbfr')

final_comments = {}
for i, c in enumerate(coms):
    comdetail = {}
    comdetail['userphid'] = c[3]
    #for a comment transaction get all records (edits, etc)
    content = phabdb.comment_by_transaction(c[1])
    if len(content) > 1:
        iter = 0
        while 1:
            if iter == len(content):
                break
            comver = 0
            for edit in content:
                if edit[6] > comver:
                    comver = edit[6]
                    comdetail['text'] = edit[7]
                    comdetail['created'] = edit[10]
                    comdetail['last_edit'] = edit[11]
            iter += 1
    else:
        fcomment = phabdb.comment_by_transaction(c[1])[0]
        comdetail['text'] = fcomment[7]
        comdetail['created'] = fcomment[10]
        comdetail['last_edit'] = fcomment[11]


    final_comments[i] = comdetail

print final_comments

#from phabdb import archive_project
#print archive_project('greenproject')

#set project tag and color
#print set_project_icon('MediaWiki_extensions-OAuth', 'briefcase', 'red')

#p = phdb()
#print p.sql_x("SELECT * FROM bugzilla_meta WHERE id = %s", (500,))
#print p.sql_x("INSERT INTO bugzilla_meta (id, header, comments) VALUES (%s, %s, %s)", (999, 'asdf', 'adf'))
