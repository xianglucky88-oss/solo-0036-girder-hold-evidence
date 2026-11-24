"""Read trace evidence from the exact inputs and report frozen in an edition."""

from .editions import read_edition
from .intake import parse_survey
from .trace import explain


def edition_trace(store, edition_id, hold, point):
    edition = read_edition(store, edition_id)
    document = edition["document"]
    survey = parse_survey(document["source"])
    trace = explain(survey, document["report"], hold, point)
    return trace | {
        "edition": edition_id,
        "revision": document["revision"],
        "digest": edition["digest"],
    }
