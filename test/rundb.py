import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append('/'.join(path.split('/')[:-1]))
import phabdb
print phabdb.phid_by_custom_field('1001')

#from phabdb import archive_project
#print archive_project('greenproject')

#set project tag and color
#print set_project_icon('MediaWiki_extensions-OAuth', 'briefcase', 'red')

#p = phdb()
#print p.sql_x("SELECT * FROM bugzilla_meta WHERE id = %s", (500,))
#print p.sql_x("INSERT INTO bugzilla_meta (id, header, comments) VALUES (%s, %s, %s)", (999, 'asdf', 'adf'))
