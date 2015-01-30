#!/usr/bin/env python

""""

This script merges two projects in Phab "the hard way"

project_merg.py <old_project> <new_project>

* Projects must pre-exist
* Will not remove the old project completely
* Will strip all tasks from old project and add to new
* Can handle tasks in old project that already have the new project
"""
import os
import sys
from wmfphablib import phabdb
from wmfphablib import log
from wmfphablib import vlog
from wmfphablib import errorlog as elog


def main(oldproject, newproject):
    oldprojectPHID =  phabdb.get_project_phid(oldproject)
    old_tasks = phabdb.get_project_tasks(oldprojectPHID)
    newprojectPHID = phabdb.get_project_phid(newproject)
    for t in old_tasks:
        print phabdb.set_related_project(t, newprojectPHID)
    phabdb.remove_project_tasks(oldprojectPHID)

main(sys.argv[1], sys.argv[2])
