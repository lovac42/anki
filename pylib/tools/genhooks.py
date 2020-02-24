# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
Generate code for hook handling, and insert it into anki/hooks.py.

To add a new hook:
- update the hooks list below
- run 'make develop'
- send a pull request that includes the changes to this file and hooks.py
"""

import os
from hookslib import Hook, update_file

# Hook/filter list
######################################################################

hooks = [
    Hook(name="card_did_leech", args=["card: Card"], legacy_hook="leech"),
    Hook(name="card_odue_was_invalid"),
    Hook(name="schema_will_change", args=["proceed: bool"], return_type="bool"),
    Hook(
        name="notes_will_be_deleted",
        args=["col: anki.storage._Collection", "ids: List[int]"],
        legacy_hook="remNotes",
    ),
    Hook(
        name="deck_added",
        args=["deck: Dict[str, Any]"],
        legacy_hook="newDeck",
        legacy_no_args=True,
    ),
    Hook(name="media_files_did_export", args=["count: int"]),
    Hook(
        name="exporters_list_created",
        args=["exporters: List[Tuple[str, Any]]"],
        legacy_hook="exportersList",
    ),
    Hook(
        name="search_terms_prepared",
        args=["searches: Dict[str, Callable]"],
        legacy_hook="search",
    ),
    Hook(
        name="note_type_added",
        args=["notetype: Dict[str, Any]"],
        legacy_hook="newModel",
        legacy_no_args=True,
    ),
    Hook(name="sync_stage_did_change", args=["stage: str"], legacy_hook="sync"),
    Hook(name="sync_progress_did_change", args=["msg: str"], legacy_hook="syncMsg"),
    Hook(
        name="bg_thread_progress_callback",
        args=["proceed: bool", "progress: anki.rsbackend.Progress"],
        return_type="bool",
        doc="Warning: this is called on a background thread.",
    ),
    Hook(
        name="tag_added", args=["tag: str"], legacy_hook="newTag", legacy_no_args=True,
    ),
    Hook(
        name="field_filter",
        args=[
            "field_text: str",
            "field_name: str",
            "filter_name: str",
            "ctx: anki.template.TemplateRenderContext",
        ],
        return_type="str",
        doc="""Allows you to define custom {{filters:..}}
        
        Your add-on can check filter_name to decide whether it should modify
        field_text or not before returning it.""",
    ),
    Hook(
        name="note_will_flush",
        args=["note: Note"],
        doc="Allow to change a note before it is added/updated in the database.",
    ),
    Hook(
        name="card_will_flush",
        args=["card: Card"],
        doc="Allow to change a card before it is added/updated in the database.",
    ),
    Hook(
        name="card_did_render",
        args=[
            "output: anki.template.TemplateRenderOutput",
            "ctx: anki.template.TemplateRenderContext",
        ],
        doc="Can modify the resulting text after rendering completes.",
    ),
    Hook(
        name="schedv2_did_answer_review_card",
        args=["card: anki.cards.Card", "ease: int", "early: bool"],
    ),
    Hook(
        name="empty_cards_will_be_deleted",
        args=["cids: List[int]", "col: anki.collection._Collection"],
        return_type="List[int]",
        doc="""Allow to change the list of cards to delete.

        For example, an add-on creating a method to delete only empty
        new cards would be done as follow:
```
from anki.consts import CARD_TYPE_NEW
from anki.utils import ids2str
from aqt import mw

def filter(cids, col):
    return col.db.list(
            f"select id from cards where (type={CARD_TYPE_NEW} and (id in {ids2str(cids)))")

def emptyNewCard():
    hooks.append(filter)
    mw.onEmptyCards()
    hooks.remove(filter)
```""",
    ),
]

if __name__ == "__main__":
    path = os.path.join(os.path.dirname(__file__), "..", "anki", "hooks.py")
    update_file(path, hooks)
