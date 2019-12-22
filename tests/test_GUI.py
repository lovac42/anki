import os
import shutil
from os import path


def test_gui():
    if path.exists("tests/notGUI"):
        return
    orig = "tests/support"
    copy = "tests/supportCopy"
    try:
        shutil.rmtree(copy)
    except:
        pass
    shutil.copytree(orig, copy)
    assert os.system(f"./runanki --base {copy} -p TEST") == 0 #i.e. run was ok
    shutil.rmtree(copy)
