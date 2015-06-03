import os
import sys
import json
from wmfphablib import phabdb
from wmfphablib import util

# Some transaction types are unsafe to reveal as they
# contain hidden information in their history and possible
# unsafe secrets we have dealt with in the UI context
transactions = ['projectcolumn',
                'priority',
                'status',
                'reassign']

data = {}
taskdata = {}
for task in phabdb.get_taskbypolicy():
    id = task[0]
    taskdata[id] = {}

    taskdata[id]['storypoints'] = phabdb.get_storypoints(task[1]) or ''

    taskdata[id]['transactions'] = {}
    for t in transactions:
        taskdata[id]['transactions'][t] = phabdb.get_transactionbytype(task[1], t)

    #('PHID-TASK-uegpsibvtzahh2n4efok', 21L, 'PHID-USER-7t36l5d3llsm5abqfx3u', 1426191381L, 0L, None)
    # There are a few types of edge relationships, some of them we are not going to
    # account for here as the current need is project based data.  Thus if we see a relationship
    # with a project and that project is public then include it.
    edges = phabdb.get_edgebysrc(task[1])
    edge_allowed = [edge for edge in edges \
                    if edge[2].startswith('PHID-PROJ') \
                    and phabdb.get_projectpolicy(edge[2]) == 'public']
    taskdata[id]['edge'] = filter(bool, edge_allowed)

data['task'] = taskdata
data['project'] = {}
data['project']['projects'] = phabdb.get_projectbypolicy(policy='public')
data['project']['columns'] = phabdb.get_projectcolumns()

with open('/srv/dumps/phabricator_public.dump', 'w') as f:
    f.write(json.dumps(data))
