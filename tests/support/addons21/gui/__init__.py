from aqt.qt import *
from aqt import mw
from anki.hooks import addHook

import time
def test():
    browser = mw.onBrowse()
    browser.close()
    addCard = mw.onAddCard()
    addCard.close()
    stats = mw.onStats()
    stats.close()
    debug= mw.onDebug()
    debug.close()
    prefs = mw.onPrefs()
    prefs.close()

addHook("profileLoaded", test)
