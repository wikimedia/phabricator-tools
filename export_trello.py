#!/usr/bin/env python

#   This is an example script as part of a trac/trello --> phabricator
#   migration.  It may or may not have worked at a particular point in
#   time but could be totally broken by the time you read this.  Even if
#   it did work it is still completely tied to the internal
#   idiosyncrasies of a decade of trac use and migration goals of a
#   single company.  There will never be any documentation.
#
#   YOU SHOULD NOT RUN THIS SCRIPT.
#
#   If you are willing to take COMPLETE RESPONSIBILITY FOR WRECKING YOUR
#   PHABRICATOR INSTALL you should MAYBE consider this script as an
#   EXAMPLE to help your own design.  NO ONE CAN HELP YOU.  If you were
#   not already willing to write such scripts from scratch run away from
#   the dragon now.  It is provided for that purpose and as a
#   demonstration for upstream of a migration to guide feature
#   development that may make that very slightly less painful one day.
#
#   YOU SHOULD NOT RUN THIS SCRIPT.  A DRAGON WILL EAT ALL OF YOUR DATA.
#
#                                                 /===-_---~~~~~~~~~------____
#                                                 |===-~___                _,-'
#                  -==\\                         `//~\\   ~~~~`---.___.-~~
#              ______-==|                         | |  \\           _-~`
#        __--~~~  ,-/-==\\                        | |   `\        ,'
#     _-~       /'    |  \\                      / /      \      /
#   .'        /       |   \\                   /' /        \   /'
#  /  ____  /         |    \`\.__/-~~ ~ \ _ _/'  /          \/'
# /-'~    ~~~~~---__  |     ~-/~         ( )   /'        _--~`
#                   \_|      /        _)   ;  ),   __--~~
#                     '~~--_/      _-~/-  / \   '-~ \
#                    {\__--_/}    / \\_>- )<__\      \
#                    /'   (_/  _-~  | |__>--<__|      |
#                   |0  0 _/) )-~     | |__>--<__|     |
#                   / /~ ,_/       / /__>---<__/      |
#                  o o _//        /-~_>---<__-~      /
#                  (^(~          /~_>---<__-      _-~
#                 ,/|           /__>--<__/     _-~
#              ,//('(          |__>--<__|     /                  .----_
#             ( ( '))          |__>--<__|    |                 /' _---_~\
#          `-)) )) (           |__>--<__|    |               /'  /     ~\`\
#         ,/,'//( (             \__>--<__\    \            /'  //        ||
#       ,( ( ((, ))              ~-__>--<_~-_  ~--____---~' _/'/        /'
#     `~/  )` ) ,/|                 ~-_~>--<_/-__       __-~ _/
#   ._-~//( )/ )) `                    ~~-'_/_/ /~~~~~~~__--~
#    ;'( ')/ ,)(                              ~~~~~~~~~~
#   ' ') '( (/
#     '   '  `                                        

# This script uses a trello enterprise export which even if you have
# an enterprise account is different from what you get by hitting the
# export button on a board.

import argparse
import calendar
import collections
import errno
import json
import logging
import logging.handlers
import os
import pprint
import sys
import time
import traceback

import dateutil.parser
import yaml

##### Utility #####

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

##### Trello's world view #####

# Why doesn't trello just just unix time and why is python's date/time
# handling such a mess?
def parse_trello_ts_str(s):
    d = dateutil.parser.parse(s)
    return calendar.timegm(d.utctimetuple()) 


def s_to_us(ts):
    return ts * 1000000

class TrelloDAO(object):

    # Trello exports a board as a blob of json.  It's a werid hybrid
    # between 'just make a giant json blob' and 'this looks
    # suspicously like internal represenation'
    def __init__(self, fname):
        with open(fname) as f:
            self.blob = json.load(f)
        self.uid2username = None
        self.column_id2name = None

    def get_board_name(self):
        return self.blob['name']

    def get_board_url(self):
        return self.blob['url']

    def get_usernames(self):
        usernames = []
        for user in self.blob['members']:
            usernames.append(user['username'])
        return sorted(usernames)

    def get_username(self, uid):
        if self.uid2username is None:
            self.uid2username = {}
            for user in self.blob['members']:
                self.uid2username[user['id']] = user['username']
        if uid in self.uid2username:
            return self.uid2username[uid]
        else:
            return 'UNKNOWN_' + uid

    def get_column_name(self, column_id):
        if self.column_id2name is None:
            self.column_id2name = {}
            for t_list in self.blob['lists']:
                self.column_id2name[t_list['id']] = t_list['name']
        return self.column_id2name[column_id]

    # due to cards moving and whatnot constraints like 'there should
    # be a created record for each card' can not be satisfied
    def figure_out_when_card_created(self, card):
        eldest_record = parse_trello_ts_str(card.dateLastActivity)
        has_create_record = False
        for action in self.blob['actions']:
            if action['type'] == 'createCard':
                if action['data']['card']['id'] == card.card_id:
                    change_time = parse_trello_ts_str(action['date'])
                    if change_time < eldest_record:
                        eldest_record = change_time
                        has_create_record = True
        if not has_create_record:
            for action in self.blob['actions']:
                if action['type'] == 'updateCard':
                    if action['data']['card']['id'] == card.card_id:
                        change_time = parse_trello_ts_str(action['date'])
                        if change_time < eldest_record:
                            eldest_record = change_time
        return eldest_record

    def figure_out_first_card_column(self, card):
        for action in self.blob['actions']:
            if action['type'] == 'createCard' and action['data']['card']['id'] == card.card_id:
                if 'list' in action['data']:
                    try:
                        return self.get_column_name(action['data']['list']['id'])
                    except KeyError as e:
                        pass
        # column IDs can be referenced that are not defined
        return 'UNKNOWN'


    def guess_card_reporter(self, card, scrubber):
        reporter = None
        for action in self.blob['actions']:
            if action['type'] == 'createCard':
                if action['data']['card']['id'] == card.card_id:
                    reporter = scrubber.get_phab_uid(self.get_username(action['idMemberCreator']))
        if reporter is None and card.idMembers:
            reporter = scrubber.get_phab_uid(self.get_username(card.idMembers[0]))
        return reporter if reporter else 'import-john-doe'


    def guess_card_owner(self, card, scrubber):
        owner = None
        if card.idMembers:
            owner = scrubber.get_phab_uid(self.get_username(card.idMembers[0]))
        return owner if owner else 'import-john-doe'

    def figure_out_all_subscribers(self, card, scrubber):
        subscriber_ids = set(card.idMembers)
        for action in self.blob['actions']:
            if 'card' in action['data'] and action['data']['card']['id'] == card.card_id:
                subscriber_ids.add(action['idMemberCreator'])
        subscribers = map(lambda s: scrubber.get_phab_uid(self.get_username(s)), subscriber_ids)
        return sorted(subscribers)


    def get_checklist_items(self, card_id):
        for c_list in self.blob['checklists']:
            if c_list['idCard'] == card_id:
                check_items = c_list['checkItems']
                return sorted(check_items, key=lambda e: e['pos'])


    def get_relevant_actions(self, card_id):
        actions = []
        for action in self.blob['actions']:
            if 'card' in action['data'] and action['data']['card']['id'] == card_id:
                if action['type'] in ['commentCard', 'updateCard']:
                    actions.append(action)
        return sorted(actions, key=lambda a: parse_trello_ts_str(a['date']))

class TrelloScrubber(object):

    def __init__(self, conf_file):
        with open(conf_file) as f:
            self.conf = yaml.load(f)


    def get_phab_uid(self, trello_username):
        # trello exports can include user ids that are are not defined
        # as members or anywhere within in the export
        if trello_username.startswith('UNKNOWN_'):
            junk = trello_username.split('UNKNOWN_')[1]
            return self.conf['uid-cheatsheet'][junk]
        else:
            return self.conf['uid-map'][trello_username]


class TrelloCard(object):

    # [u'attachments',  Never used on board
    #  u'labels',  Rarely used color stuff
    #  u'pos',  Physical position, ridiculous LOE to port so ignoring
    #  u'manualCoverAttachment',  Duno but it's always false
    #  u'id',  unique id
    #  u'badges',   something about fogbugz integration?
    #  u'idBoard',  parent board id
    #  u'idShort',  "short" and thus not unique uid
    #  u'due',  rarely used durdate
    #  u'shortUrl',  pre-shorted url
    #  u'closed',  boolean for if it's archived
    #  u'subscribed',  boolean, no idea what it means
    #  u'email',  no idea, always none
    #  u'dateLastActivity',  2014-04-22T14:09:49.917Z
    #  u'idList',  it's an id, not sure exactly how it works
    #  u'idMembersVoted',  never used
    #  u'idMembers',  # Whose face shows up next to it
    #  u'checkItemStates',  Something to do with checklists?
    #  u'desc',  # description field
    #  u'descData',  Almost always None, probably not important
    #  u'name', # title
    #  u'shortLink',  # some short linky thing
    #  u'idAttachmentCover',  Always None
    #  u'url',  # link back to trello
    #  u'idChecklists']   # a bunch of ids for checklists?

    def __init__(self, blob, scrubber):
        self.scrubber = scrubber
        self.card_id = blob['id']
        self.labels = blob['labels']
        self.idBoard = blob['idBoard']
        self.due = blob['due']
        self.closed = blob['closed']
        self.dateLastActivity = blob['dateLastActivity']
        self.idList = blob['idList']
        self.idMembers = blob['idMembers']
        self.desc = blob['desc']
        self.name = blob['name']
        self.url = blob['url']
        self.idChecklists = blob['idChecklists']
        self.checklists = blob['checklists']
        
        self.change_history = []
        self.column = None
        self.final_comment_fields = {}


    def figure_stuff_out(self, dao):
        self.board_name = dao.get_board_name()
        self.create_time_s = dao.figure_out_when_card_created(self)
        self.column = dao.figure_out_first_card_column(self)
        self.reporter = dao.guess_card_reporter(self, self.scrubber)
        self.owner = dao.guess_card_owner(self, self.scrubber)
        self.subscribers = dao.figure_out_all_subscribers(self, self.scrubber)
        self.build_checklist_comment(dao)

        for action in dao.get_relevant_actions(self.card_id):
            self.handle_change(action, dao)

        if self.labels:
            self.final_comment_fields['labes'] = sorted(map(lambda k: k['color'], self.labels))
        if self.due:
            self.final_comment_fields['due'] = self.due

    def build_checklist_comment(self, dao):
        if not self.idChecklists:
            return None
        s = ''
        if self.checklists is None:
            log.warning('Failed to find checklist %s for card %s' % self.card_id)
            return
        for checklist in self.checklists:
            s += 'Checklist: \n'
            for item in checklist['checkItems']:
                s+= ' * [%s] %s \n' % ('x' if item['state'] == 'complete' else '', item['name'])
                s += '\n'
        change = {'type': 'comment', 'author': self.owner,
                  'comment': s,
                  'change_time_us': s_to_us(parse_trello_ts_str(self.dateLastActivity))}
        self.change_history.append(change)

    def make_final_comment(self):
        s = 'Trello Board: %s `%s` \n' % (self.board_name, self.idBoard)
        s += "Trello Card: `%s` %s \n" % (self.card_id, self.url)
        if len(self.final_comment_fields) > 0:
            s += '\nExtra Info:\n'
            for key in sorted(self.final_comment_fields):
                s += ' * `%s`: `%s`\n' % (str(key), unicode(self.final_comment_fields[key]))
        return {'comment': s, 'ts_us': None}

    def handle_change(self, j_change, dao):
        if j_change['type'] == 'updateCard' and 'listBefore' in j_change['data']:
            change = {'type': 'custom-field',
                      'author': self.scrubber.get_phab_uid(dao.get_username(j_change['idMemberCreator'])),
                      'key': 'std:maniphest:' + 'addthis:import-trello-column',
                      'val': dao.get_column_name(j_change['data']['listAfter']['id']),
                      'change_time_us': s_to_us(parse_trello_ts_str(j_change['date']))}
            self.change_history.append(change)
            self.column = dao.get_column_name(j_change['data']['listBefore']['id'])
        elif j_change['type'] == 'commentCard':
            change = {'type': 'comment',
                      'author': self.scrubber.get_phab_uid(dao.get_username(j_change['idMemberCreator'])),
                      'comment': j_change['data']['text'],
                      'change_time_us': s_to_us(parse_trello_ts_str(j_change['date']))}
            self.change_history.append(change)
        elif j_change['type'] == 'updateCard' and 'closed' in j_change['data']['card']:
            phab_status = 'resolved' if j_change['data']['card']['closed'] else 'open'
            change = {'type': 'status', 'author': self.owner,
                      'status': phab_status,
                      'change_time_us': s_to_us(parse_trello_ts_str(j_change['date']))}
            self.change_history.append(change)
            self.closed = not j_change['data']['card']['closed']
        elif j_change['type'] == 'updateCard' and 'old' in j_change['data'] and 'name' in j_change['data']['old']:
            comment = 'Title change:\n * old: %s \n * new: %s' % (j_change['data']['old']['name'], j_change['data']['card']['name'])
            change = {'type': 'comment',
                      'author': self.scrubber.get_phab_uid(dao.get_username(j_change['idMemberCreator'])),
                      'comment': comment,
                      'change_time_us': s_to_us(parse_trello_ts_str(j_change['date']))}
            self.change_history.append(change)
        elif j_change['type'] == 'updateCard' and 'old' in j_change['data'] and 'desc' in j_change['data']['old']:
            comment = 'Desc change\n\n=== Old === \n\n %s \n\n=== New === \n\n %s' % (j_change['data']['old']['desc'], j_change['data']['card']['desc'])
            change = {'type': 'comment',
                      'author': self.scrubber.get_phab_uid(dao.get_username(j_change['idMemberCreator'])),
                      'comment': comment,
                      'change_time_us': s_to_us(parse_trello_ts_str(j_change['date']))}
            self.change_history.append(change)
        elif j_change['type'] == 'updateCard' and 'old' in j_change['data'] and 'due' in j_change['data']['old']:
            pass # Will just use the final due date
        elif j_change['type'] == 'updateCard' and 'old' in j_change['data'] and 'pos' in j_change['data']['old']:
            pass # just moving cards around in a list
        else:
            print j_change
            log.warn('Unknown change condition type:%s id:%s for card %s' % (j_change['type'], j_change['id'], self.card_id))

    def to_transform_dict(self, import_project, task_id):
        transform = {}
        transform['must-preserve-id'] = False if task_id is None else True
        transform['import-project'] = import_project
        transform['base'] = {
            'ticket-id': self.card_id if task_id is None else task_id,
            'create-time-us': s_to_us(self.create_time_s),
            'owner': self.owner,
            'reporter':  self.reporter,
            'summary': self.name,
            'description': self.desc,
            'priority': 50,
            }
        transform['init-custom'] = {}
        transform['init-custom']['std:maniphest:' + 'addthis:import-trello-column'] = self.column
        transform['changes'] = sorted(self.change_history, key=lambda d: d['change_time_us'])
        transform['final-comment'] = self.make_final_comment()
        transform['final-subscribers'] = self.subscribers

        return transform



##### cmds #####

def cmd_foo(args):
    pass


def cmd_print_users(args):
    board = TrelloDAO(args.trello_file)
    pprint.pprint(board.get_usernames())
    
    pass

def cmd_print_user_map_test(args):
    board = TrelloDAO(args.trello_file)
    scrubber = TrelloScrubber('conf/trello-scrub.yaml')
    for user in board.blob['members']:
        print '%s <--> %s <--> %s' % (user['id'], board.get_username(user['id']), scrubber.get_phab_uid(board.get_username(user['id'])))

def cmd_dump_cards(args):
    mkdir_p('out/tickets')
    board = TrelloDAO(args.trello_file)
    scrubber = TrelloScrubber('conf/trello-scrub.yaml')
    task_id = args.start_id
    for j_card in board.blob['cards']:
        card = TrelloCard(j_card, scrubber)
        fname = os.path.join(args.dump_dir, card.card_id + '.json')
        card.figure_stuff_out(board)
        with open(fname, 'w') as f:
            d = card.to_transform_dict(args.phab_project, task_id)
            f.write(json.dumps(d,  sort_keys=True,
                               indent=4, separators=(',', ': ')))
        if task_id is not None:
            task_id += 1

##### main and friends #####

def parse_args(argv):
    def db_cmd(sub_p, cmd_name, cmd_help):
        cmd_p = sub_p.add_parser(cmd_name, help=cmd_help)
        cmd_p.add_argument('--log',
                           action='store', dest='log', default='stdout', choices=['stdout', 'syslog', 'both'],
                           help='log to stdout and/or syslog')
        cmd_p.add_argument('--log-level',
                           action='store', dest='log_level', default='WARNING',
                           choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'],
                           help='log to stdout and/or syslog')
        cmd_p.add_argument('--log-facility',
                           action='store', dest='log_facility', default='user',
                           help='facility to use when using syslog')
        cmd_p.add_argument('--trello-file',
                           action='store', dest='trello_file', required=True,
                           help='trello exported json file')

        return cmd_p

    parser = argparse.ArgumentParser(description="")
    sub_p = parser.add_subparsers(dest='cmd')

    foo_p = db_cmd(sub_p, 'foo', '')
    foo_p.set_defaults(func=cmd_foo)

    print_users_p = db_cmd(sub_p, 'print-users', '')
    print_users_p.set_defaults(func=cmd_print_users)

    print_user_map_test_p = db_cmd(sub_p, 'print-user-map-test', '')
    print_user_map_test_p.set_defaults(func=cmd_print_user_map_test)

    dump_cards_p = db_cmd(sub_p, 'dump-cards', '')
    dump_cards_p.set_defaults(func=cmd_dump_cards)
    dump_cards_p.add_argument('--dump-dir',
                              action='store', dest='dump_dir', default='out/tickets')
    dump_cards_p.add_argument('--phab-project',
                              action='store', dest='phab_project', required=True)
    dump_cards_p.add_argument('--start-id', type=int,
                              action='store', dest='start_id')
    dump_cards_p.set_defaults(func=cmd_dump_cards)

    args = parser.parse_args(argv)
    return args


def setup_logging(handlers, facility, level):
    global log

    log = logging.getLogger('export-trac')
    formatter = logging.Formatter(' | '.join(['%(asctime)s', '%(name)s',  '%(levelname)s', '%(message)s']))
    if handlers in ['syslog', 'both']:
        sh = logging.handlers.SysLogHandler(address='/dev/log', facility=facility)
        sh.setFormatter(formatter)
        log.addHandler(sh)
    if handlers in ['stdout', 'both']:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        log.addHandler(ch)
    lmap = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
        'NOTSET': logging.NOTSET
        }
    log.setLevel(lmap[level])


def main(argv):
    args = parse_args(argv)
    try:
        setup_logging(args.log, args.log_facility, args.log_level)
    except Exception as e:
        print >> sys.stderr, 'Failed to setup logging'
        traceback.print_exc()
        raise e

    args.func(args)


if __name__ == '__main__':
    main(sys.argv[1:])

