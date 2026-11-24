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
        delta = {}
        for key in ("loaded_um", "residual_um"):
            delta[key] = encode(Fraction(row[key]) - Fraction(before[key]))
        left_evidence = evidence(left_survey, left["report"]["placement"][row["hold"]], before)
        right_evidence = evidence(right_survey, right["report"]["placement"][row["hold"]], row)
        rows.append(dict(hold=row["hold"], point=row["point"], change=delta,
                         evidence_changed=left_evidence != right_evidence))
    return dict(old=old, new=new, rows=rows)
