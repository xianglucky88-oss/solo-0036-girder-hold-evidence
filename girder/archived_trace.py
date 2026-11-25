"""Read trace evidence from the exact inputs and report frozen in an edition."""

from .editions import read_edition
from .errors import Rejected
from .intake import parse_survey
from .retest_survey import build_extended_survey
from .trace import evidence


def _retest_exclusions(document):
    groups = {"retest_position": set(), "retest_reading": set()}
    for event in document.get("retest_journal", {}).get("votes", []):
        group = groups[event["kind"]]
        if event["action"] == "exclude":
            group.add(event["row_id"])
        else:
            group.discard(event["row_id"])
    return groups


def edition_trace(store, edition_id, hold, point):
    edition = read_edition(store, edition_id)
    document = edition["document"]
    survey = parse_survey(document["source"])
    report = document["report"]
    pool = report["responses"] + report.get("retest_responses", [])
    match = next((row for row in pool if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    if hold in report["placement"]:
        result = evidence(survey, report["placement"][hold], match)
    else:
        records = document.get("retest_records", [])
        extended = build_extended_survey(survey.plan, survey.positions, survey.readings,
                                         records, _retest_exclusions(document))
        result = evidence(extended, report["retest_placement"][hold], match,
                          scope="retest", retest_id=hold)
    return result | {
        "edition": edition_id,
        "revision": document["revision"],
        "digest": edition["digest"],
    }
