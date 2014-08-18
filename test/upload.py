import sys
import json
import os
import ConfigParser

from phabricator import Phabricator

def main():


    parser = ConfigParser.SafeConfigParser()
    parser_mode = 'phab'
    parser.read('/etc/gz_fetch.conf')
    phab = Phabricator(username=parser.get(parser_mode, 'username'),
                   certificate=parser.get(parser_mode, 'certificate'),
                   host=parser.get(parser_mode, 'host'))

    import base64
    with open('testimage.jpg') as f:
        encoded = base64.b64encode(f.read())
        print encoded
    #print type(encoded)
    #print phab.file.upload(name='bikeshednoone.jpg', data_base64=encoded, viewPolicy='no-one')
    print phab.file.upload(name='bikeshednoone.jpg', data_base64=encoded, viewPolicy='no-one', canCDN = True)
    #print phab.file.upload(name='bikeshed2phid.jpg', data_base64=encoded, policy='PHID-PROJ-fgvvnafmhvkgn2d5a4rf')
    #print phab.file.upload(name='bikeshed2default.jpg', data_base64=encoded)

main()
