import anki.decks
from aqt.deck import Deck


class DeckManager(anki.decks.DeckManager):
    def __init__(self, mw, *args, **kwargs):
        self.mw = mw
        super().__init__(*args, **kwargs)

    def _createDeck(self, *args, **kwargs):
        return Deck(self, *args, **kwargs)
