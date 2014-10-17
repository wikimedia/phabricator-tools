#!/bin/bash
python bugzilla_fetch.py $1 -v
python bugzilla_create.py $1 -v
python bugzilla_update_tasks.py $1 -v
python bugzilla_populate_user_relations_comments_table.py $1
python bugzilla_populate_user_relations_table.py $1
python bugzilla_update_user_header.py -m 1
python bugzilla_update_user_comments.py -m 1
