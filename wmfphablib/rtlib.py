from rtppl import ppl as users
import re
from datetime import datetime
import util

prepend = 'rt'

def user_lookup(name):
    return users.get(name, None)

def priority_convert(priority):
    priorities = { '0': 50, '50': 50}
    return priorities.get(priority.lower(), 50)

def status_convert(status):
    statuses = { 'resolved': 'resolved',
                 'new': 'open',
                 'open': 'open',
                 'stalled': 'needs_info'}
    return statuses[status.lower()]

def links_to_dict(link_text):
    """ parse rt.wm.o/REST/1.0/ticket/<ticket-id>/links/show
    :param link_text: text of api output
    :returns dict:
    """
    id = '>>>>'
    # http://rt3.fsck.com/Ticket/Display.html?id=11636
    # original author of RT stashes his personal blog link
    # in various places in API return
    link_text = link_text.replace('fsck.com-rt://rt.wikimedia.org/', '')

    #different types of links in 
    link_refs = {'refers_to': 'RefersTo:',
                 'refers_toby': 'ReferredToBy:',
                 'children': 'Members:',
                 'blockers': 'DependsOn',
                 'blocks': 'DependedOnBy'}

    link_refs_callout = []
    for l in link_text.splitlines():
        test = lambda x: l.startswith(x)
        if any(map(test, link_refs.values())):
            link_refs_callout.append('%s%s' % (id, l))
        else:
            link_refs_callout.append(l)

    link_associations = {}
    linkage =  '\n'.join(link_refs_callout).split(id)
    for link_type in linkage:
        for k, v in link_refs.iteritems():
            if v in link_type:
                treg = "ticket/(\d+)"
                links = re.findall(treg, link_type)
                link_associations[k] = links

    return link_associations


def str_to_epoch(rt_style_date_str):
    """ RT stores things as 'Fri Aug 15 19:45:51 2014' """
    date = datetime.strptime(rt_style_date_str, '%a %b %d %H:%M:%S %Y')
    return int(float(util.datetime_to_epoch(date)))
