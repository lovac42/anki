# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import aqt
from anki.consts import *
from anki.lang import _
from anki.sound import clearAudioQueue
from aqt.utils import askUserDialog, openLink, shortcut, tooltip


class Overview:
    "Deck overview."

    def __init__(self, mw):
        self.mw = mw
        self.web = mw.web
        self.bottom = aqt.toolbar.BottomBar(mw, mw.bottomWeb)

    def show(self):
        clearAudioQueue()
        self.web.resetHandlers()
        self.web.onBridgeCmd = self._linkHandler
        self.mw.setStateShortcuts(self._shortcutKeys())
        self.refresh()

    def refresh(self):
        self.mw.col.reset()
        self._renderPage()
        self._renderBottom()
        self.mw.web.setFocus()

    # Handlers
    ############################################################

    def _linkHandler(self, url):
        if url == "study":
            self.mw.onReview()
            if self.mw.state == "overview":
                tooltip(_("No cards are due yet."))
        elif url == "anki":
            print("anki menu")
        elif url == "opts":
            self.mw.onDeckConf()
        elif url == "cram":
            deck = self.mw.col.decks.current()
            self.mw.onCram("'deck:%s'" % deck.getName())
        elif url == "refresh":
            self.mw.col.decks.current().rebuildDyn()
            self.mw.reset()
        elif url == "empty":
            self.mw.col.sched.emptyDyn(self.col.decks.current())
            self.mw.reset()
        elif url == "decks":
            self.mw.moveToState("deckBrowser")
        elif url == "review":
            openLink(aqt.appShared+"info/%s?v=%s"%(self.sid, self.sidVer))
        elif url == "studymore":
            self.onStudyMore()
        elif url == "unbury":
            self.onUnbury()
        elif url.lower().startswith("http"):
            openLink(url)
        return False

    def _shortcutKeys(self):
        return [
            ("o", self.mw.onDeckConf),
            ("r", self.onRebuildKey),
            ("e", self.onEmptyKey),
            ("c", self.onCustomStudyKey),
            ("u", self.onUnbury)
        ]

    def _filteredDeck(self):
        return self.mw.col.decks.current().isDyn()

    def onRebuildKey(self):
        if self._filteredDeck():
            self.mw.col.decks.current().rebuildDyn()
            self.mw.reset()

    def onEmptyKey(self):
        if self._filteredDeck():
            self.mw.col.sched.emptyDyn(self.mw.col.decks.current())
            self.mw.reset()

    def onCustomStudyKey(self):
        if not self._filteredDeck():
            self.onStudyMore()

    def onUnbury(self):
        if self.mw.col.schedVer() == 1:
            self.mw.col.sched.unburyCardsForDeck()
            self.mw.reset()
            return

        sibs = self.mw.col.sched.haveBuriedSiblings()
        man = self.mw.col.sched.haveManuallyBuried()

        if sibs and man:
            opts = [_("Manually Buried Cards"),
                    _("Buried Siblings"),
                    _("All Buried Cards"),
                    _("Cancel")]

            diag = askUserDialog(_("What would you like to unbury?"), opts)
            diag.setDefault(0)
            ret = diag.run()
            if ret == opts[0]:
                self.mw.col.sched.unburyCardsForDeck(type="manual")
            elif ret == opts[1]:
                self.mw.col.sched.unburyCardsForDeck(type="siblings")
            elif ret == opts[2]:
                self.mw.col.sched.unburyCardsForDeck(type="all")
        else:
            self.mw.col.sched.unburyCardsForDeck(type="all")

        self.mw.reset()

    # HTML
    ############################################################

    def _renderPage(self):
        but = self.mw.button
        deck = self.mw.col.decks.current()
        self.sid = deck.get("sharedFrom")
        if self.sid:
            self.sidVer = deck.get("ver", None)
            shareLink = '<a class=smallLink href="review">Reviews and Updates</a>'
        else:
            shareLink = ""
        self.web.stdHtml(self._body % dict(
                deck=deck.getName(),
                shareLink=shareLink,
                desc=self._desc(deck),
                table=self._table()
            ),
                         css=["overview.css"],
                         js=["jquery.js", "overview.js"])

    def _desc(self, deck):
        if deck.isDyn():
            desc = _("""\
This is a special deck for studying outside of the normal schedule.""")
            desc += " " + _("""\
Cards will be automatically returned to their original decks after you review \
them.""")
            desc += " " + _("""\
Deleting this deck from the deck list will return all remaining cards \
to their original deck.""")
        else:
            desc = deck.get("desc", "")
        if not desc:
            return "<p>"
        if deck.isDyn():
            dyn = "dyn"
        else:
            dyn = ""
        return '<div class="descfont descmid description %s">%s</div>' % (
                dyn, desc)

    def _table(self):
        counts = list(self.mw.col.sched.counts())
        finished = not sum(counts)
        if self.mw.col.schedVer() == 1:
            for index in range(len(counts)):
                if counts[index] >= 1000:
                    counts[index] = "1000+"
        but = self.mw.button
        if finished:
            return '<div style="white-space: pre-wrap;">%s</div>' % (
                self.mw.col.sched.finishedMsg())
        else:
            footList = [
                (_("New"), "new", counts[0]),
                (_("Learning"), "learn", counts[1]),
                (_("To Review"), "rev", counts[2])]
            return (f'''
<table width=400 cellpadding=5>
  <tr>
    <td align=center valign=top>
      <table cellspacing=5>'''+
        "\n".join(f'''
        <tr>
          <td>
            {string}:
          </td>
          <td>
            <b><font color={self.mw.col.conf.get("colors", defaultColors)[color]}>{nb}</font></b>
          </td>
        </tr>''' for string, color, nb in footList)+
f'''
      </table>
    </td>
    <td align=center>
    {but("study", _("Study Now"), id="study",extra=" autofocus")}
    </td>
  </tr>
</table>''')


    _body = """
<center>
<h3>%(deck)s</h3>
%(shareLink)s
%(desc)s
%(table)s
</center>
"""

    # Bottom area
    ######################################################################

    def _renderBottom(self):
        links = [
            ["O", "opts", _("Options")],
        ]
        if self.mw.col.decks.current().isDyn():
            links.append(["R", "refresh", _("Rebuild")])
            links.append(["E", "empty", _("Empty")])
        else:
            links.append(["C", "studymore", _("Custom Study")])
            #links.append(["F", "cram", _("Filter/Cram")])
        if self.mw.col.sched.haveBuried():
            links.append(["U", "unbury", _("Unbury")])
        buf = ""
        for link in links:
            if link[0]:
                link[0] = _("Shortcut key: %s") % shortcut(link[0])
            buf += """
<button title="%s" onclick='pycmd("%s")'>%s</button>""" % tuple(link)
        self.bottom.draw(buf)
        self.bottom.web.onBridgeCmd = self._linkHandler

    # Studying more
    ######################################################################

    def onStudyMore(self):
        import aqt.customstudy
        aqt.customstudy.CustomStudy(self.mw)
