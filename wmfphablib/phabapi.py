def log(m):
    pass

import base64
import phabricator
from phabricator import Phabricator

class phabapi:

    def __init__(self, user, cert, host):

        if host:
            self.con = Phabricator(username=user,
                                certificate=cert,
                                host=host)
        else:
            self.con = None

    def task_comment(self, task, msg):
        out = self.con.maniphest.update(id=task, comments=msg)
        return out

    def set_status(self, task, status):
        out = self.con.maniphest.update(id=task, status=status)
        return out

    def task_create(self, title, desc, id, priority, security, ccPHIDs=[], projects=[], refcode=''):
        if refcode:
            reference = '%s%s' % (refcode, id)
        else:
            reference = id

        return self.con.maniphest.createtask(title=title,
                                        description="%s" % desc,
                                        projectPHIDs=projects,
                                        priority=priority,
                                        auxiliary={"std:maniphest:external_reference":"%s" % (reference,),
                                                   "std:maniphest:security_topic": security})

    def ensure_project(self, project_name, pmembers=[]):
        """make sure project exists, return phid either way"""

        existing_proj = self.con.project.query(names=[project_name])
        if not existing_proj['data']:
            log('need to make: ' + project_name)
            try:
                new_proj = self.con.project.create(name=project_name, members=pmembers)
            #XXX: Bug where we have to specify a members array!
            except phabricator.APIError:
                pass
            existing_proj = self.con.project.query(names=[project_name])
            log(str(existing_proj))
            phid = existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
        else:
            phid = existing_proj['data'][existing_proj['data'].keys()[0]]['phid']
            log(project_name + ' exists')
        return phid

    def upload_file(self, name, data):
        encoded = base64.b64encode(data)
        upload = self.con.file.upload(name=name, data_base64=encoded)
        return self.con.file.info(phid=upload.response).response
