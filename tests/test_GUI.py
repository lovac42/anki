import aqt
import shutil

def test_gui():
    orig = "tests/support"
    copy = "tests/supportCopy"
    try:
        shutil.rmtree(copy)
    except:
        pass
    shutil.copytree(orig, copy)
    aqt.run(["Anki","--base", copy, "-p", "TEST"])
    shutil.rmtree(copy)
