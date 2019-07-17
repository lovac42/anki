from aqt.qt import *
from aqt import mw
from anki.hooks import addHook
import os

import time
def test():
    browser = mw.onBrowse()
    browser.close()
    addCard = mw.onAddCard()
    addCard.reject()
    stats = mw.onStats()
    stats.reject()
    debug= mw.onDebug()
    debug.close()
    prefs = mw.onPrefs()
    prefs.accept()
    mw.close()

addHook("profileLoaded", test)
