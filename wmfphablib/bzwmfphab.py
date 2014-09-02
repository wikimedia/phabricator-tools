import re

def find_attachment_in_comment(text):
    a = re.search('Created\sattachment\s(\d+)', text)
    if a:
        return a.group(1)
    else:
        return ''

def status_convert(bz_status):
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
