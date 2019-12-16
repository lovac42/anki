#!/bin/bash

TOOLS="$(cd "`dirname "$0"`"; pwd)"
mypy $TOOLS/../anki $TOOLS/../aqt
(cd $TOOLS/.. && pytype --config pytype.conf)
