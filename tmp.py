#!/usr/bin/env python3

import os

while 1:
    if os.system("./tools/tests.sh") != 0:
        break
    if os.system("git rebase --continue") != 0:
        break
    os.system("isort -rc -y -s runanki -s aqt/forms")
