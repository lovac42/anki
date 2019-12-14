import anki.deck
from anki.consts import *
from anki.errors import DeckRenameError
from anki.hooks import runHook
from anki.lang import _, ngettext
from anki.utils import ids2str
from aqt.qt import *
from aqt.utils import askUser, getOnlyText, showWarning


class Deck(anki.deck.Deck):
    ## Deck Browser
    @staticmethod
    def _options():
        """html cell, to show gear opening options"""
        return f"""
      <td align=center class=opts>
        <a onclick='return pycmd("opts:{self.getId()}");'>
          <img src='/_anki/imgs/gears.svg' class=gears>
        </a>
      </td>"""

    def _renderDeckTree(self, columns):
        """Html used to show the deck tree.

        keyword arguments
        depth -- the number of ancestors, excluding itself
        decks -- A list of decks, to render, with the same parent. See top of this file for detail"""
        if self.isLeaf():
            return ""
        buf = "".join(child._deckRow(columns) for child in self.getChildren())
        return buf

    def _deckRow(self, columns):
        """The HTML for a single deck (and its descendant)

        Keyword arguments:
        """
        if self.isDefault() and not self.getParent().isLeaf() and self.isLeaf():
            # if the default deck is empty, hide it
            if not self.manager.col.db.scalar("select 1 from cards where did = 1 limit 1"):
                return ""
        self.count['due']['due'] = self.count['due']['rev'] + self.count['due']['lrn'] # todo: uses a separate commit for this line
        buf = f"""
  <tr class='{'deck current' if self.getId() == self.manager.col.conf['curDeck'] else 'deck'}' id='{self.getId()}'>"""
        buf += "".join(column.deckRow(self) for column in columns)
        buf += """
  </tr>"""
        # children
        if not self['collapsed']:
            buf += self._renderDeckTree(columns)
        return buf

    def _selDeck(self):
        self.select()
        self.manager.mw.onOverview()

    def _showOptions(self):
        menu = QMenu(self.manager.mw)
        action = menu.addAction(_("Rename"))
        action.triggered.connect(lambda button, deck=self: deck._askAndRename())
        action = menu.addAction(_("Options"))
        action.triggered.connect(lambda button, deck=self: deck._options())
        action = menu.addAction(_("Export"))
        action.triggered.connect(lambda button, deck=self: deck._export())
        action = menu.addAction(_("Delete"))
        action.triggered.connect(lambda button, deck=self: deck._delete())
        runHook("showDeckOptions", menu, self.getId())
        # still passing did, as add-ons have not updated to my fork.
        menu.exec_(QCursor.pos())

    def _export(self):
        self.manager.mw.onExport(deck=self)

    def _askAndRename(self, merge=None):
        # can't be called _rename, as it would conflict with anki/deck.py
        self.manager.mw.checkpoint(_("Rename Deck"))
        oldName = self.getName()
        newName = getOnlyText(_("New deck name:"), default=oldName)
        newName = newName.replace('"', "")
        self._renameOrWarn(newName, merge)

    def _renameOrWarn(self, newName, merge=None):
        oldName = self.getName()
        if not newName or newName == oldName:
            return
        if merge is None:
            alreadyExists = self.manager.byName(newName)
            if alreadyExists:
                merge = askUser(_("The deck %s already exists. Do you want to merge %s in it ?")%(newName, oldName))
        try:
            self.rename(newName, merge=merge)
        except DeckRenameError as e:
            return showWarning(e.description)
        self.manager.mw.deckBrowser.show()

    def _delete(self):
        if self.isDefault():
            return showWarning(_("The default deck can't be deleted."))
        self.manager.mw.checkpoint(_("Delete Deck"))
        if self.isStd():
            dids = self.getDescendantsIds(includeSelf=True)
            cnt = self.manager.mw.col.db.scalar(
                "select count() from cards where did in {0} or "
                "odid in {0}".format(ids2str(dids)))
            if cnt:
                extra = ngettext(" It has %d card.", " It has %d cards.", cnt) % cnt
            else:
                extra = None
        if self.isDyn() or not extra or askUser(
            (_("Are you sure you wish to delete %s?") % self.getName()) +
            extra):
            self.manager.mw.progress.start(immediate=True)
            self.rem(True)
            self.manager.mw.progress.finish()
            self.manager.mw.deckBrowser.show()

    def _dragDeckOnto(self, ontoDeckDid):
        try:
            self.renameForDragAndDrop(ontoDeckDid)
        except DeckRenameError as e:
            return showWarning(e.description)

        self.manager.mw.deckBrowser.show()

    def _collapse(self):
        self.collapse()
        self.manager.mw.deckBrowser._renderPage(reuse=True)
