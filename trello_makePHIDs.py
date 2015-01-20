# Given a manually-maintained .yaml file mapping Trello usernames to Phabricator usernames,
# write out a new "scrub" file  mapping Trello usernames to Phabricator PHIDs
# for later use by export_trello.py.
# Documentation at https://www.mediawiki.org/wiki/Phabricator/Trello_to_Phabricator
import argparse
import json
import os.path
import sys
import yaml

# cburroughs' work
import export_trello

from phabricator import Phabricator
from wmfphablib import config
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import errorlog as elog

class Phidify:

	def __init__(self, args):
		self.args = args	# FIXME unpack all the args into member variables?
		if config.phab_host.find('phab-01') != -1:
                        self.host = 'phab-01'
		elif config.phab_host.find('phabricator.wikimedia.org') != -1:
                        self.host = 'phabricator'
		else:
			self.json_error('Unrecognized host %s in config' % (config.phab_host))
			sys.exit(1)
		self.userMap = 'data/trello_names_' + self.host + '.yaml'
                with open(self.userMap) as f:
                    yam = yaml.load(f)
		self.trelloUserMap = yam['trelloUserMap']
		vlog('Looks like we loaded self.trelloUserMap OK \o/')


	def connect_to_phab(self):
		self.phab = Phabricator(config.phab_user,
						   config.phab_cert,
						   config.phab_host)

		self.phab.update_interfaces()
		# DEBUG to verify the API connection worked: print phab.user.whoami()
		vlog('Looks like we connected to the phab API \o/')

	# Returns dict mapping Trello usernames to phab PHIDs
	def get_trelloUserPHIDs(self, trelloUserMap):
		self.connect_to_phab()
		# trelloUserMap maps trello usernames to phabricator usernames, e.g.
		#  {'spage1': 'spage',  'Tisza': 'Tgr'}
		# We can query to get the PHID of the phab username
		#  {'spage': 'PHID-USER-rwvw2dwvvjiyrlzy4iho',  'Tisza': 'PHID-USER-66kvyuekkkwkqbpze2uk'}
		# we want to return {'spage1' : 'PHID-USER-rwvw2dwvvjiyrlzy4iho'}

		# Get list of unique Phabricator usernames to query, excluding 'None' and empty
		lookupNames = [u for u in set(trelloUserMap.values()) if u]

		vlog('get_trelloUserPHIDs querying Phab for %d usernames: %s ' % (len(lookupNames), lookupNames))
		response = self.phab.user.query(usernames = lookupNames)

		# That conduit query returns an array of users' data, each containing phabUsername and phid.
		# Turn it into a dict.
		phabUserPHIDMap = {}
		for userInfo in response:
			if userInfo["userName"] and userInfo["phid"]:
				phabUserPHIDMap[userInfo["userName"]] = userInfo["phid"]

		# Now create what we want, a dict of trelloUsername -> phid
		trelloUserPHIDMap = {}
		for trelloUsername, phabUsername in trelloUserMap.iteritems():
			if (phabUsername
				and phabUsername in phabUserPHIDMap
				and phabUserPHIDMap[phabUsername]
				and phabUserPHIDMap[phabUsername] != 'None'): # XXX fires?
				trelloUserPHIDMap[trelloUsername] = phabUserPHIDMap[phabUsername]

		return trelloUserPHIDMap

	def writeUserPHIDs(self):
		trelloUserPHIDMap = self.get_trelloUserPHIDs(self.trelloUserMap)
		fname = 'conf/trello-scrub_' + self.host + '.yaml'
		if os.path.exists(fname):
			elog('ERROR: ' + fname + ' already exists')
			sys.exit(2)
		stream = file(fname, 'w')
		trelloScrub = {
			'uid-map': trelloUserPHIDMap,
			'uid-cheatsheet': {}
		}
		# safe_dump() avoids gtisza: !!python/unicode 'PHID-USER-66kvyuekkkwkqbpze2uk'
		yaml.safe_dump( trelloScrub, stream, width=30)
		log('SUCCESS: wrote trello usernames->PHIDs to ' + fname)


def main():
	parser = argparse.ArgumentParser()

	parser.add_argument("-vv", "--verbose-logging", action="store_true",
	                    help="wmfphablib verbose logging")
	args = parser.parse_args()

	phidify = Phidify(args)
	phidify.writeUserPHIDs()

if __name__ == '__main__':
	main()
