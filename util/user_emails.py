import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append('/'.join(path.split('/')[:-1]))
from wmfphablib import phabdb

def emails():
    email_tuples =  phabdb.get_emails()
    return [e[0] for e in email_tuples]

if __name__ == '__main__':
    print verified_emails()
