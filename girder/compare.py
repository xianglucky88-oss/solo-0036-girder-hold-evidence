from fractions import Fraction

from .editions import read_edition
from .errors import Rejected
from .exact import encode
from .intake import parse_survey
from .trace import evidence


def compare_editions(store, old, new):
    left = read_edition(store, old)["document"]
    right = read_edition(store, new)["document"]
    if left["plan_hash"] != right["plan_hash"]:
        raise Rejected("只可对照相同试验计划的签出版", 409)
    if left["report"]["contract"] != right["report"]["contract"]:
        raise Rejected("两个签出版的归约合同不一致", 409)
    left_survey = parse_survey(left["source"])
    right_survey = parse_survey(right["source"])
    index = {(row["hold"], row["point"]): row for row in left["report"]["responses"]}
    rows = []
    for row in right["report"]["responses"]:
        before = index[row["hold"], row["point"]]
        delta = {key: encode(Fraction(row[key]) - Fraction(before[key])) for key in ("loaded_um", "residual_um")}
        left_evidence = evidence(left_survey, left["report"]["placement"][row["hold"]], before)
        right_evidence = evidence(right_survey, right["report"]["placement"][row["hold"]], row)
        rows.append(dict(hold=row["hold"], point=row["point"], change=delta,
                         evidence_changed=left_evidence != right_evidence))
    return dict(old=old, new=new, rows=rows, graded=_compare_graded(left, right))


def _graded_index(report):
    graded = report.get("graded")
    return {} if graded is None else {(row["level"], row["point"]): row for row in graded["workorder"]}


def _compare_graded(left, right):
    before = _graded_index(left["report"])
    rows = []
    for row in _graded_index(right["report"]).values():
        prior = before.get((row["level"], row["point"]))
        if prior is None:
            continue
        delta = {}
        for key in ("difference_um", "residual_um"):
            delta[key] = None if row[key] is None or prior[key] is None else encode(Fraction(row[key]) - Fraction(prior[key]))
        rows.append(dict(level=row["level"], point=row["point"], change=delta,
                         adopted=row["state"] == "valid", adopted_before=prior["state"] == "valid"))
    return rows