from aqt.qt import *
from aqt import mw
from anki.hooks import addHook
import time
import sys

def test():
    t = Thread(target=myfunc)
    t.start
    browser = mw.onBrowse()
    addCard = mw.onAddCard()
    stats = mw.onStats()
    prefs = mw.onPrefs()
    time.sleep(2)
    # debug= mw.onDebug()
    # debug.close()
    mw.close()
    print("end")
    time.sleep(2)

addHook("profileLoaded", test)

from threading import Thread

def myfunc():
    time.sleep(1)
    browser.close()
    addCard.reject()
    stats.reject()
    prefs.accept()
    mw.close()
    print ("finished sleeping and closing")
