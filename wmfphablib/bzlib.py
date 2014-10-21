import re

prepend = 'bz'
security_mask = '_hidden_'

def sanitize_project_name(product, component):
    component_separator = '-'
    product = product.replace('-', '_')
    product = product.replace(' ', '_')
    component = component.replace('/', '_and_')
    component = component.replace('-', '_')
    component = component.replace(' ', '_')

    return  "%s%s%s" % (product,
                         component_separator,
                         component)

def build_comment(c):
    """ takes a native bz comment dict and outputs
    a dict ready for processing into phab
    """
    clean_c = {}
    clean_c['author'] =  c['author'].split('@')[0]
    clean_c['creation_time'] = str(c['creation_time'])
    clean_c['creation_time'] = int(float(c['creation_time']))
    if c['author'] != c['creator']:
        clean_c['creator'] =  c['creator'].split('@')[0]

    clean_c['count'] = c['count']
    if c['count'] == 0:
        clean_c['bug_id'] = c['bug_id']

    if c['is_private']:
        c['text'] = security_mask

    attachment = find_attachment_in_comment(c['text'])
    if attachment:
        fmt_text = []
        text = c['text'].splitlines()
        for t in text:
            if not t.startswith('Created attachment'):
                fmt_text.append(t)
        c['text'] = '\n'.join(fmt_text)
        clean_c['attachment'] = attachment
    clean_c['text'] = c['text']
    return clean_c

def find_attachment_in_comment(text):
    a = re.search('Created\sattachment\s(\d+)', text)
    if a:
        return a.group(1)
    else:
        return ''

def status_convert(bz_status, bz_resolution):
    """
    UNCONFIRMED (default)   Open + Needs Triage (default)
    NEW     Open
    ASSIGNED                open
    PATCH_TO_REVIEW         open
    NEED_INFO               needs_info
    RESOLVED FIXED          resolved
    RESOLVED INVALID        invalid
    RESOLVED WONTFIX        declined
    RESOLVED WORKSFORME     resolved
    RESOLVED DUPLICATE      closed

    needs_info      stalled
    resolved        closed
    invalid         no historical value will be purged eventually (spam, etc)
    declined        we have decided not too -- even though we could
    """

    statuses = {'new': 'open',
                'resolved': 'resolved',
                'reopened': 'open',
                'closed': 'resolved',
                'need_info': 'needs_info',
                'verified': 'resolved',
                'assigned': 'open',
                'unconfirmed': 'open',
                'patch_to_review': 'open'}

    if bz_resolution.lower() in ['wontfix', 'later', 'worksforme']:
        return 'declined'
    elif bz_resolution.lower() in ['invalid']:
        return 'invalid'
    elif bz_resolution.lower() in ['fixed']:
        return 'resolved'
    else:
        return statuses[bz_status.lower()]

def priority_convert(bz_priority):
    """
    "100" : "Unbreak Now!",
    "90"  : "Needs Triage",
    "80"  : "High",
    "50"  : "Normal",
    "25"  : "Low",
    "10"  : "Needs Volunteer",
    """
    priorities = {'unprioritized': 90,
                  'immediate': 100,
                  'highest': 100,
                  'high': 80,
                  'normal': 50,
                  'low': 25,
                  'lowest': 10}
    return priorities[bz_priority.lower()]

def see_also_transform():
    #take see_also urls and transform for phab ref
    from urlparse import urlparse
    see_also = []
    if buginfo['see_also']:
        for sa in buginfo['see_also']:
            parsed = urlparse(sa)
            sabug = parsed.query.split('=')[1]
            sabug_ref = get_ref(sabug)
            if sabug_ref is None:
                continue
            else:
                see_also.append(phabm.ticket_id_by_phid(sabug_ref[0]))

    see_also = ' '.join(["T%s" % (s,) for s in see_also])
    desc_tail += "\n**See Also**: %s" % (see_also or 'none')
