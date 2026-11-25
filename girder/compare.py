from fractions import Fraction

from .editions import read_edition
from .errors import Rejected
from .exact import encode
from .intake import parse_survey
from .trace import evidence


def _effective_rows(document):
    report = document["report"]
    if report.get("effective_responses"):
        return report["effective_responses"]
    return report["responses"]


def _evidence_for(document, survey, row):
    report = document["report"]
    origin = row.get("origin", row["hold"])
    match = next(item for item in report["responses"] + report.get("retest_responses", [])
                 if item["hold"] == origin and item["point"] == row["point"])
    placement = report["placement"].get(origin) or report["retest_placement"][origin]
    if origin in report["placement"]:
        return evidence(survey, placement, match)
    from .archived_trace import _retest_exclusions
    from .retest_survey import build_extended_survey
    extended = build_extended_survey(survey.plan, survey.positions, survey.readings,
                                     document.get("retest_records", []), _retest_exclusions(document))
    return evidence(extended, placement, match)


def compare_editions(store, old, new):
    left = read_edition(store, old)["document"]
    right = read_edition(store, new)["document"]
    if left["plan_hash"] != right["plan_hash"]:
        raise Rejected("只可对照相同试验计划的签出版", 409)
    if left["report"]["contract"] != right["report"]["contract"]:
        raise Rejected("两个签出版的归约合同不一致", 409)
    left_survey = parse_survey(left["source"])
    right_survey = parse_survey(right["source"])
    left_rows = {(row["hold"], row["point"]): row for row in _effective_rows(left)}
    rows = []
    for row in _effective_rows(right):
        before = left_rows.get((row["hold"], row["point"]))
        if before is None:
            continue
        delta = {}
        for key in ("loaded_um", "residual_um"):
            delta[key] = encode(Fraction(row[key]) - Fraction(before[key]))
        left_evidence = _evidence_for(left, left_survey, before)
        right_evidence = _evidence_for(right, right_survey, row)
        rows.append(dict(hold=row["hold"], point=row["point"], change=delta,
                         origin_before=before.get("origin", before["hold"]),
                         origin_after=row.get("origin", row["hold"]),
                         evidence_changed=left_evidence != right_evidence))
    return dict(old=old, new=new, rows=rows)
