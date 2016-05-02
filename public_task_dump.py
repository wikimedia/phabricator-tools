#!/usr/bin/env python
import os
import sys
import json
from wmfphablib import phabdb
from wmfphablib import util
from wmfphablib import config as c

# Some transaction types are unsafe to reveal as they
# contain hidden information in their history and possible
# unsafe secrets we have dealt with in the UI context
transactions = ['core:columns',
                'priority',
                'status',
                'reassign',
                'core:edge']

def dbcon(db):
    return phabdb.phdb(db=db,
                       host=c.dbslave,
                       user=c.phuser_user,
                       passwd=c.phuser_passwd)

mdb = dbcon('phabricator_maniphest')
pdb = dbcon('phabricator_project')

data = {}
taskdata = {}
tasks = phabdb.get_taskbypolicy(mdb)
# cache a list of public phids
task_phids = [id[1] for id in tasks]

for task in tasks:
    id = task[0]
    taskdata[id] = {}
    taskdata[id]['info'] = task
    taskdata[id]['storypoints'] = phabdb.get_storypoints(mdb, task[1]) or ''
    taskdata[id]['transactions'] = {}

    for t in transactions:
                taskdata[id]['transactions'][t] = phabdb.get_transactionbytype(mdb, task[1], t)

    # ('PHID-TASK-uegpsibvtzahh2n4efok', 21L, 'PHID-USER-7t36l5d3llsm5abqfx3u', 1426191381L, 0L, None)
    # There are a few types of edge relationships, we want only publicly available relationships
    edges = phabdb.get_edgebysrc(mdb, task[1])
    if not edges:
        continue

    edge_allowed = []
    for edge in edges:
        if edge[2].startswith('PHID-PROJ'):
            if phabdb.get_projectpolicy(pdb, edge[2]) == 'public':
                edge_allowed.append(edge)
        if edge[2].startswith('PHID-TASK'):
            # we compare to a our known good list of public tasks
            if edge[2] in task_phids:
                edge_allowed.append(edge)
    taskdata[id]['edge'] = filter(bool, edge_allowed)

data['task'] = taskdata
data['project'] = {}
data['project']['projects'] = phabdb.get_projectbypolicy(pdb, policy='public')
data['project']['columns'] = phabdb.get_projectcolumns(pdb)

mdb.close()
pdb.close()

with open('/srv/dumps/phabricator_public.dump', 'w') as f:
    f.write(json.dumps(data))
