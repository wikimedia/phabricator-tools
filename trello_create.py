#!/usr/bin/python
# vim: set fileencoding=UTF-8
#
# Create Phabricator tasks out of cards in a Trello board exported as JSON file.
# This uses WMF's phabricator tooling and independently cburrough's export_trello.py,
# one excuse for messy code.
#
# Steps to run:
#   1. Export all Trello boards from https://trello.com/wikimediafoundation, unzip.
#
#   (You'll do the following config steps twice, first to create tasks on the
#   test Phab host phab-01.wmflabs.org and then for reals on the production Phab
#   host phabricator.wikimedia.org.)
#
#   2. Modify /etc/phabtools.conf for
#      * host= either phab-01.wmflabs.org (test) or phabricator.wikimedia.org (production)
#      * user= trellimport (spage created this user on both test and production)
#   3. Check that data/trello_names_<HOST>.yaml has up-to-date
#      Trello_username: Phab_username, mapping the members of the Trello board
#      you're importing to their Phab username on either the test phab-01 or
#      production phabricator host. (Commit any changes you make)
#   4. Run trello_makePHIDs.py, it creates a new conf/trello-scrub_<HOST>.yaml
#      Check this for missing Phabricator user PHIDs.
#   5. Copy or symlink conf/trello-scrub_<HOST>.yaml to conf/trello-scrub.yaml.
#
#   X  Now you're ready to run trello_create.py
#
#   6. Run trello_create.py specifying the JSON export file of the board you want.
#   6a. Do a verbose dry-run of trello_create.py to a test project on the test host
#       (this doesn't actually create cards), e.g.:
#         python trello_create.py -v -vv --test-run --dry-run \
#             -j trabulous_dir/wikimediafoundation_20150218_083222/boards/flow_backlog/flow_backlog.json \
#             --phab_project 'Flow (test)' \
#             --column 'Send to Phabricator - Collaboration-Team board'
#       Check the command output.
#   6b. Do a test-run of trello_create.py to a test project on the test host (this
#       creates cards named 'TEST RUN: xxx'). Same command-line as above without "--dry-run".
#       Check the created tasks in the test project.
#
#   7. If it looks good, repeat steps 2-5 to configure for the production Phab
#      host phabricator.wikimedia.org.
#
#   8. Run trello_create.py again
#   8a. Do another verbose dry-run of trello_create.py to the actual production phab project
#       (this doesn't actually create cards), e.g.:
#         python -m pdb trello_create.py -v -vv --test-run --dry-run \
#             -j trabulous_dir/wikimediafoundation_20150218_083222/boards/flow_backlog/flow_backlog.json \
#             --phab_project '§Collaboration-Team' \
#             --column 'Send to Phabricator - Collaboration-Team board'
#       Check the command output.
#   8b. Do you feel lucky?
#       Alert the pros in #wikimedia-devtools on IRC...
#       Do the actual run of trello_create.py to the actual production phab project. Same
#       command line as above without "--test-run --dry-run"
#       Capture the standard output and stderr.
#   9. Check the created tasks on phabricator.wikimedia.org
#   10.Save the standard output and stderr of the run somewhere. In particular
#      save the mapping lines
#         Created task: TNNN (PHID-TASK-xxxxxxx) from Trello card xXxXxXxX ('Card NameXxxx')
#       so that an improved version of the tool could improve the migrated
#       cards (set the correct users and timestamps, add comments, and attachments, etc.)
#   11. Party like it's 1999.
#
# Documentation at https://www.mediawiki.org/wiki/Phabricator/Trello_to_Phabricator
# TODO 2015-01-25: log and write out the mapping card_id -> trello Tnnnn; for now use 'Created task:' log lines.
# TODO 2015-02-18: owner and one CC seems to work (see "Table of Contents: No-JS version"), but unknown users are dropped.
# TODO 2015-02-19: do something with attachments!


import argparse
import json
import sys
import yaml

# cburroughs' work
from export_trello import TrelloCard, TrelloDAO, TrelloScrubber, setup_logging

from phabricator import Phabricator
from wmfphablib import Phab as phabmacros	# Cleaner (?), see wmfphablib/phabapi.py
from wmfphablib import config
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import errorlog as elog

class TrelloImporter:
	# Map from Trello username to phabricator user.
	userMapPhab01 = {
		'gtisza': 'Tgr',
		"legoktm": "legoktm",
		"matthewflaschen": "mattflaschen",
		"pauginer": None,
		"spage1": "spage",
	}
	userMapPhabWMF = {
		# from mingleterminator.py
		'fflorin': 'Fabrice_Florin',
		'gdubuc': 'Gilles',
		'mholmquist': 'MarkTraceur',
		'gtisza': 'Tgr',
		'pginer': 'Pginer-WMF',
		# From ack username trabulous_dir/flow-current-iteration_lOh4XCy7_fm.json  \
		# | perl -pe 's/^\s+//' | sort | uniq
		# Collaboration-Team members:     Eloquence, DannyH, Pginer-WMF, Spage, Quiddity, Mattflaschen, matthiasmullie, EBernhardson
		"alexandermonk": None,
		"antoinemusso": None,
		"benmq": None,
		"bsitu": None,
		"dannyhorn1": "DannyH",
		"erikbernhardson": "EBernhardson",
		"jaredmzimmerman": None,
		"jonrobson1": None,
		"kaityhammerstein": None,
		"legoktm": None,
		"matthewflaschen": "mattflaschen",
		"matthiasmullie": "matthiasmullie",
		"maygalloway": None,
		"moizsyed_": None,
		"oliverkeyes": None,
		"pauginer": "Pginer-WMF",
		"quiddity1": "Quiddity",
		"shahyarghobadpour": None,
		"spage1": "Spage",
		"wctaiwan": None,
		"werdnum": None,
	}

	def __init__(self, jsonName, args):
		self.jsonName = jsonName
		self.args = args	# FIXME unpack all the args into member variables?
		self.verbose = args.verbose
		if config.phab_host.find('phab-01') != -1:
			self.host = 'phab-01'
		elif config.phab_host.find('phabricator.wikimedia.org') != -1:
			self.host = 'phabricator'
		else:
			self.json_error('Unrecognized host %s in config' % (config.phab_host))
			sys.exit(3)
		self.board = TrelloDAO(self.jsonName)
		trelloBoardName = self.board.get_board_name();
		vlog('Trello board = %s' % (trelloBoardName))


	def connect_to_phab(self):
		self.phab = Phabricator(config.phab_user,
						   config.phab_cert,
						   config.phab_host)

		self.phab.update_interfaces()
		self.phabm = phabmacros('', '', '')
		self.phabm.con = self.phab
		# DEBUG to verify the API connection worked: print phab.user.whoami()
		vlog('Looks like we connected to the phab API \o/')


	def sanity_check(self):
		if not 'cards' in self.trelloJson:
			self.json_error('No cards in input file')
			sys.exit(1)

	def testify(self, str):
		if self.args.test_run:
			str = "TEST Trello_create RUN: " + str

		return str

	def json_error(self, str):
		elog('ERROR: %s in input file %s' % (str, self.jsonName))

	# Determine projectPHID for the project name in which this will create tasks.
	def get_projectPHID(self, phabProjectName):
		# Similar conduit code in trello_makePHIDs.py get_trelloUserPHIDs
		response = self.phab.project.query(names = [phabProjectName])
		for projInfo in response.data.values():
		    if projInfo["name"] == phabProjectName:
			vlog('Phabricator project %s has PHID %s' % (phabProjectName, projInfo["phid"] ) )
			return projInfo["phid"]

		elog('Phabricator project %s not found' % (phabProjectName))
		sys.exit(4)
		return # not reached

	# This is the workhorse
	def createTask(self, card):
		# Default some keys we always pass to createtask.
		taskinfo = {
			'ownerPHID'	: None,
			'ccPHIDs'	  : [],
			'projectPHIDs' : [self.projectPHID],
		}

		taskinfo["title"] = self.testify(card.name)

		# TODO: if Trello board is using scrum for Trello browser extension,
		# could extract story points /\s+\((\d+)\)' from card title to feed into Sprint extension.

		# TODO: process attachments
		# TODO: taskinfo["assignee"]
		desc = self.testify(card.desc)

		if card.checklist_strs:
			desc += '\n' + '\n\n'.join(card.checklist_strs)
		desc_tail = '\n--------------------------'
		desc_tail += '\n**Trello card**: [[ %s | %s ]]\n' % (card.url, card.shortLink)
		# Mention column the same way as the card.final_comment_fields below from export_trello.py.
		desc_tail += '\n * column: %s\n' % (unicode(card.column))
		if len(card.final_comment_fields) > 0:
			s = ''
			s += '\n'
			for key in sorted(card.final_comment_fields):
				s += ' * %s: %s\n' % (str(key), unicode(card.final_comment_fields[key]))
			desc_tail += s

		# TODO: could add additional info (main attachment, etc.) to desc_tail.
		taskinfo["description"] = desc + '\n' + desc_tail
		# TODO: chasemp: what priority?
		taskinfo['priority'] = 50
		# TODO: chasemp: can I put "Trello lOh4XCy7" in "Reference" field?

		# Take the set of members
		idMembers = card.idMembers
		# Get the Trello username for the idMember
		# memberNames = [ TrelloDAO.get_username(id) for id in idMembers if TrelloDAO.get_username(id)]

		# export_trello.py sets names it can't match to 'import-john-doe'
		if not 'FAILED' in card.owner and not card.owner == 'import-john-doe':
			taskinfo['ownerPHID'] = card.owner
		taskinfo['ccPHIDs'] = [u for u in card.subscribers if not 'FAILED' in u and not u == 'import-john-doe']

		# TODO: Add any other members with a PHID to the ccPHIDs
		# TODO: Note remaining Trello members in desc_tail

		# TODO: bugzilla_create.py and wmfphablib/phabapi.py use axuiliary for
		# BZ ref, but it doesn't work for Trello ref?
		taskinfo["auxiliary"] = {"std:maniphest:external_reference":"Trello %s" % (card.shortLink)}

		if self.args.conduit:
			# This prints fields for maniphest.createtask
			print '"%s"\n"%s"\n\n' % (taskinfo["title"].encode('unicode-escape'),
			                          taskinfo["description"].encode('unicode-escape'))
		else:
			if self.args.dry_run:
				log("dry-run to create a task for Trello card %s ('%s')" %
					(card.shortLink, taskinfo["title"]))
			else:
				ticket = self.phab.maniphest.createtask(
											 title = taskinfo['title'],
											 description = taskinfo['description'],
											 projectPHIDs = taskinfo['projectPHIDs'],
											 ownerPHID = taskinfo['ownerPHID'],
											 ccPHIDs = taskinfo['ccPHIDs'],
											 auxiliary = taskinfo['auxiliary']
				)

				log("Created task: T%s (%s) from Trello card %s ('%s')" %
					(ticket['id'], ticket['phid'], card.shortLink, taskinfo["title"]))


			# Here bugzilla_create goes on to log actual creating user and view/edit policy,
			# then set_task_ctime to creation_time.

			# Should I add comments to the card here,
			# or a separate step that goes through action in self.board.blob["actions"]
			# handling type="commentCard"?


	# Here are the types of objects in the "actions" array.
	#     20   "type": "addAttachmentToCard",
	#      9   "type": "addChecklistToCard",
	#      2   "type": "addMemberToBoard",
	#     38   "type": "addMemberToCard",
	#     69   "type": "commentCard",
	#      1   "type": "copyCard",
	#     25   "type": "createCard",
	#      3   "type": "createList",
	#      6   "type": "deleteAttachmentFromCard",
	#     29   "type": "moveCardFromBoard",
	#     18   "type": "moveCardToBoard",
	#      4   "type": "moveListFromBoard",
	#      2   "type": "moveListToBoard",
	#      3   "type": "removeChecklistFromCard",
	#     14   "type": "removeMemberFromCard",
	#      3   "type": "updateBoard",
	#    698   "type": "updateCard",
	#     48   "type": "updateCheckItemStateOnCard",
	#      8   "type": "updateList",
	# def getCardCreationMeta(self, cardId):
		# Look around in JSON for ["actions"] array for member with type:"createCard"
		# with ["card"]["id"] = cardId
		# and use the siblings ["date"] and ["memberCreator"]["id"]

	# def getCardComments(self, cardId):
		# Look around in JSON ["actions"] for member with type:""commentCard"
		# with ["card"]["id"] = cardId
		# and use the siblings ["date"] and ["memberCreator"]["id"]

	def process_cards(self):
		self.connect_to_phab()

		self.projectPHID = self.get_projectPHID(self.args.phab_project);

		# This file has Trello_username: user_PHID mapping created by trello_makePHIDs.py.
		scrubber = TrelloScrubber('conf/trello-scrub.yaml')
		for j_card in self.board.blob["cards"]:
			card = TrelloCard(j_card, scrubber)
			card.figure_stuff_out(self.board)
			if self.args.column and not card.column == self.args.column:
				continue
			# Skip archived cards ("closed" seems to correspond?)
			# But I think archive all cards in column doesn't set this.
			if card.closed:
				continue

			# TODO: skip cards that are bugs
			# TODO: skip cards that already exist in Phab.
			self.createTask(card)


def main():
	parser = argparse.ArgumentParser()

	parser.add_argument("-v", "--verbose", action="store_true",
	                    help="increase output verbosity")
	parser.add_argument("-vv", "--verbose-logging", action="store_true",
	                    help="wmfphablib verbose logging")
	parser.add_argument("-j", "--json", required=True,
	                    help="Trello board JSON export file" )
	parser.add_argument("-c", "--conduit", action="store_true",
	                    help="print out lines suitable for conduit maniphest.createtask")
	parser.add_argument("-d", "--dry-run", action="store_true",
	                    help="don't actually add anything to Phabricator")
	parser.add_argument("-l", "--column",
	                    help="Name the one column to import")
	parser.add_argument("-t", "--test-run", action="store_true",
	                    help="prefix titles and description with 'TEST trabuloust TEST' disclaimers")
	# type to handle `--phab_project '§Collaboration-Team'`, from http://stackoverflow.com/questions/24552854
	parser.add_argument("-p", "--phab_project", type=lambda s : unicode(s, sys.stdin.encoding),
	                    required=True,
	                    help="name of Phabricator project for imported tasks")
	args = parser.parse_args()

	# As used in export_trello.py functions.
	setup_logging('stdout', 'user', 'WARNING')
	trell = TrelloImporter(args.json, args)
	trell.process_cards()

if __name__ == '__main__':
	main()
