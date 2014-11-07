import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append('/'.join(path.split('/')[:-1]))
from wmfphablib import phabdb
from wmfphablib import util

from wmfphablib import rtlib
for user, email in rtlib.users.iteritems():
    print user, email
    phabdb.create_test_user(user,
                            user,
                            email)
exit()
