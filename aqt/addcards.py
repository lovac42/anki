# Copyright: Ankitects Pty Ltd and contributors
# -*- coding: utf-8 -*-
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from typing import List

import aqt.deckchooser
import aqt.editor
import aqt.forms
import aqt.modelchooser
from anki.hooks import addHook, remHook, runHook
from anki.lang import _
from anki.notes import Note
from anki.sound import clearAudioQueue
from anki.utils import htmlToTextLine, isMac
from aqt.main import \
    AnkiQt  # used to be `from aqt import AnkiQt` but this lead to import in errors
from aqt.qt import *
from aqt.utils import (addCloseShortcut, askUser, downArrow, openHelp,
                       restoreGeom, saveGeom, shortcut, showWarning, tooltip)

"""The window obtained from main by pressing A, or clicking on "Add"."""



class AddCards(QDialog):

    def __init__(self, mw: AnkiQt):
        QDialog.__init__(self, None, Qt.Window)
        mw.setupDialogGC(self)
        self.mw = mw
        self.form = aqt.forms.addcards.Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(_("Add"))
        self.setMinimumHeight(300)
        self.setMinimumWidth(400)
        self.setupEditor()
        self.setupButtons()
        self.onReset()
        self.setupChoosers()
        self.history: List[int] = []
        self.previousNote = None
        restoreGeom(self, "add")
        addHook("reset",lambda: self.onResetSameModel)
        addCloseShortcut(self)
        self.show()

    def setupEditor(self):
        self.editor = aqt.editor.Editor(
            self.mw, self.form.fieldsArea, self, True)

    def setupChoosers(self):
        self.modelChooser = aqt.modelchooser.ModelChooser(
            self.mw, self.form.modelArea, addCardWindow=self)
        self.deckChooser = aqt.deckchooser.DeckChooser(
            self.mw, self.form.deckArea)

    def helpRequested(self):
        openHelp("addingnotes")

    def setupButtons(self):
        bb = self.form.buttonBox
        ar = QDialogButtonBox.ActionRole
        # add
        self.addButton = bb.addButton(_("Add"), ar)
        self.addButton.clicked.connect(self.addCards)
        self.addButton.setShortcut(QKeySequence("Ctrl+Return"))
        self.addButton.setToolTip(shortcut(_("Add (shortcut: ctrl+enter)")))
        # close
        self.closeButton = QPushButton(_("Close"))
        self.closeButton.setAutoDefault(False)
        bb.addButton(self.closeButton, QDialogButtonBox.RejectRole)
        # help
        self.helpButton = QPushButton(_("Help"), clicked=self.helpRequested)
        self.helpButton.setAutoDefault(False)
        bb.addButton(self.helpButton,
                                        QDialogButtonBox.HelpRole)
        # history
        button = bb.addButton(
            _("History")+ " "+downArrow(), ar)
        if isMac:
            sc = "Ctrl+Shift+H"
        else:
            sc = "Ctrl+H"
        button.setShortcut(QKeySequence(sc))
        button.setToolTip(_("Shortcut: %s") % shortcut(sc))
        button.clicked.connect(self.onHistory)
        self.historyButton = button

    def setAndFocusNote(self, note):
        """Add note as the content of the editor. Focus in the first element."""
        self.editor.setNote(note, focusTo=0)

    def onModelChange(self):
        oldNote = self.editor.note
        note = self.mw.col.newNote()
        self.previousNote = None
        if oldNote:
            oldFields = list(oldNote.keys())
            newFields = list(note.keys())
            for index, fldType in enumerate(note.model()['flds']):
                fieldName = fldType.getName()
                try:
                    oldFieldName = oldNote.model()['flds'][index].getName()
                except IndexError:
                    oldFieldName = None
                # copy identical fields
                if fieldName in oldFields:
                    note[fieldName] = oldNote[fieldName]
                # set non-identical fields by field index
                elif oldFieldName and oldFieldName not in newFields:
                    try:
                        note.fields[index] = oldNote.fields[index]
                    except IndexError:
                        pass
            self.removeTempNote(oldNote)
        self.editor.setNote(note)

    def onResetSameModel(self, keep=False):
        return self.onReset(model=self.editor.note._model, keep=keep)

    def onReset(self, model=None, keep=False):
        """Create a new note and set it with the current field values.

        keyword arguments
        model -- the model of the note we are adding
        keep -- Whether the old note was saved in the collection. In
        this case, remove non sticky fields. Otherwise remove the last
        temporary note (it is replaced by a new one).
        """
        #Called with keep set to True from  _addCards
        #Called with default keep __init__, from hook "reset"
        #Meaning of the word keep guessed. Not clear.
        oldNote = self.editor.note
        if model is None:
            note = self.mw.col.newNote()
        else:#Difference is here. If model given as argument, it is used
            note = Note(self.mw.col, model=model)
        flds = note.model()['flds']
        # copy fields from old note
        if oldNote:
            if not keep:
                self.removeTempNote(oldNote)
            for index in range(len(note.fields)):
                try:
                    if not keep or flds[index]['sticky']:
                        note.fields[index] = oldNote.fields[index]
                    else:
                        note.fields[index] = ""
                except IndexError:
                    break
        self.setAndFocusNote(note)

    def removeTempNote(self, note):
        if not note or not note.id:
            return
        # we don't have to worry about cards; just the note
        self.mw.col._remNotes([note.id])

    def addHistory(self, note):
        self.history.insert(0, note.id)
        self.history = self.history[:15]
        self.historyButton.setEnabled(True)

    def onHistory(self):
        menu = QMenu(self)
        for nid in self.history:
            if self.mw.col.findNotes("nid:%s" % nid):
                fields = self.mw.col.getNote(nid).fields
                txt = htmlToTextLine(", ".join(fields))
                if len(txt) > 30:
                    txt = txt[:30] + "..."
                action = menu.addAction(_("Edit \"%s\"") % txt)
                action.triggered.connect(lambda button, nid=nid: self.editHistory(nid))
            else:
                action = menu.addAction(_("(Note deleted)"))
                action.setEnabled(False)
        runHook("AddCards.onHistory", self, menu)
        menu.addSeparator()
        a = menu.addAction("Open Browser on 'Added &Today'")
        a.triggered.connect(lambda: self.show_browser_on_added_today())
        menu.exec_(self.historyButton.mapToGlobal(QPoint(0,0)))

    def show_browser_on_added_today(self):
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.form.searchEdit.lineEdit().setText("added:1")
        browser.onSearchActivated()
        if u'noteCrt' in browser.model.activeCols:
            col_index = browser.model.activeCols.index(u'noteCrt')
            browser.onSortChanged(col_index, True)
        browser.form.tableView.selectRow(0)

    def editHistory(self, nid):
        browser = aqt.dialogs.open("Browser", self.mw, f"nid:{nid}")

    def addNote(self, note):
        """check whether first field is not empty, that clozes appear in cloze
        note, and that some card will be generated. In those case, save the
        note and return it. Otherwise show a warning and return None"""
        note.model()['did'] = self.deckChooser.selectedId()
        ret = note.dupeOrEmpty()
        if ret == 1:
            if self.mw.col.conf.get("allowEmptyFirstField", False):
                tooltip(_("The first field is empty."))
            else:
                showWarning(_("The first field is empty."),
                            help="AddItems#AddError")
                return
        if '{{cloze:' in note.model().getTemplate()['qfmt']:
            if not note.model()._availClozeOrds(note.joinedFields(), False, onlyFirst=True):
                if not askUser(_("You have a cloze deletion note type "
                "but have not made any cloze deletions. Proceed?")):
                    return
        cards = self.mw.col.addNote(note)
        if not cards:
            showWarning(_("""\
The input you have provided would make an empty \
question on all cards."""), help="AddItems")
            return
        self.mw.col.clearUndo()
        self.addHistory(note)
        self.mw.requireReset()
        self.previousNote = note
        return note

    def addCards(self):
        """Adding the content of the fields as a new note"""
        #Save edits in the fields, and call _addCards
        self.editor.saveNow(self._addCards)

    def _addCards(self):
        """Adding the content of the fields as a new note.

        Assume that the content of the GUI saved in the model."""
        self.editor.saveAddModeVars()
        if not self.addNote(self.editor.note):
            return
        tooltip(_("Added"), period=500)
        # stop anything playing
        clearAudioQueue()
        self.onResetSameModel(keep=True)
        self.mw.col.autosave()

    def keyPressEvent(self, evt):
        "Show answer on RET or register answer."
        if (evt.key() in (Qt.Key_Enter, Qt.Key_Return)
            and self.editor.tags.hasFocus()):
            evt.accept()
            return
        return QDialog.keyPressEvent(self, evt)

    def reject(self):
        """Close the window.

        If data would be lost, ask for confirmation"""
        self.ifCanClose(self._reject)

    def _reject(self):
        """Close the window.

        Don't check whether data will be lost"""
        remHook('reset', self.onResetSameModel)
        remHook('currentModelChanged', self.onModelChange)
        clearAudioQueue()
        self.removeTempNote(self.editor.note)
        self.editor.cleanup()
        self.modelChooser.cleanup()
        self.deckChooser.cleanup()
        self.mw.maybeReset()
        saveGeom(self, "add")
        aqt.dialogs.markClosed("AddCards")
        QDialog.reject(self)

    def ifCanClose(self, onOk):
        def afterSave():
            ok = (self.editor.fieldsAreBlank(self.previousNote) or
                    askUser(_("Close and lose current input?"), defaultno=True))
            if ok:
                onOk()

        self.editor.saveNow(afterSave)

    def closeWithCallback(self, cb):
        def doClose():
            self._reject()
            cb()
        self.ifCanClose(doClose)
