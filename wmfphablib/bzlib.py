import re

prepend = 'bz'
security_mask = '//**content hidden as private in Bugzilla**//'

# Some issues are just missing instead of constant failures we skip
missing = [15368, 15369, 15370, 15371, 15372, 15373, 15374]

def sanitize_project_name(product, component):
    """ translate bz product/component into valid project
    :param product: str
    :param component: str
    """
    component_separator = '-'
    product = re.sub('\s', '-', product)
    product = product.replace('_', '-')
    component = re.sub('\s', '-', component)
    component = component.replace('_', '-')
    component = component.replace('/', '-or-')
    return  "%s%s%s" % (product,
                         component_separator,
                         component)

def build_comment(c, secstate):
    """ takes a native bz comment dict and outputs
    a dict ready for processing into phab
    """

    # these indicate textual metadata history and should be
    # preserved as literal
    dupe_literals = ['This bug has been marked as a duplicate of bug',
                     'This bug has been marked as a duplicate of',
                     'has been marked as a duplicate of this bug']

    clean_c = {}
    clean_c['author'] =  c['author'].split('@')[0]
    clean_c['creation_time'] = str(c['creation_time'])
    clean_c['creation_time'] = int(float(c['creation_time']))
    if c['author'] != c['creator']:
        clean_c['creator'] =  c['creator'].split('@')[0]

    clean_c['count'] = c['count']
    if c['count'] == 0:
        clean_c['bug_id'] = c['bug_id']

    if c['is_private'] and secstate == 'none':
        c['text'] = security_mask

    attachment = find_attachment_in_comment(c['text'])
    if attachment:
        clean_c['attachment'] = attachment

    fmt_text = []
    text = c['text'].splitlines()
    for t in text:
        if t.startswith('Created attachment'):
            continue
        elif '***' in t and any(map(lambda l: l in t, dupe_literals)):
            fmt_text.append('%%%{0}%%%'.format(t))
        else:               
            fmt_text.append(t)
    c['text'] = '\n'.join(fmt_text)
    clean_c['text'] = c['text']
    return clean_c

def find_attachment_in_comment(text):
    """Find attachment id in bz comment
    :param text: str
    :note: one attach per comment is possible
    """
    a = re.search('Created\sattachment\s(\d+)', text)
    if a:
        return a.group(1)
    else:
        return ''

def status_convert(bz_status, bz_resolution):
    """ convert status values from bz to phab terms

    UNCONFIRMED (default)   Open + Needs Triage (default)
    NEW     Open
    ASSIGNED                open
    PATCH_TO_REVIEW         open
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
    """convert see also listing to T123 refs in phab
    """
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
