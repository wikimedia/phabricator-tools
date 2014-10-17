import sys
import json
import subprocess

def can_edit_ref():
    f = open('/srv/phab/phabricator/conf/local/local.json', 'r').read()
    settings = json.loads(f)
    try:
        return settings['maniphest.custom-field-definitions']['external_reference']['edit']
    except:
        return False

def runBash(cmd):
   p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
   out = p.stdout.read().strip()
   return out

def translate_json_dict_items(dict_of_j):
    for t in dict_of_j.keys():
        if dict_of_j[t]:
            try:
                dict_of_j[t] = json.loads(dict_of_j[t])
            except (TypeError, ValueError):
                pass
    return dict_of_j

def get_index(seq, attr, value):
    return next(index for (index, d) in enumerate(seq) if d[attr] == value)

def purge_cache():
    return runBash('/srv/phab/phabricator/bin/cache purge --purge-remarkup')
