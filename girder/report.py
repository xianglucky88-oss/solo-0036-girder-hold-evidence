from .reduction_v1 import reduce_survey as _legacy
from .retest_reduction import CONTRACT, reduce_with_retests
from .retest_survey import build_retest_holds
from .retests import retest_exclusions
from .windows import WindowIndex


def reduce_survey(survey, exclusion_state, records=(), retest_vote_events=(), confirmed=()):
    """兼容无补测的旧入口；有补测登记时进入 v2 归约合同。"""
    if not records:
        return _legacy(survey, exclusion_state)
    plan = survey.plan
    WindowIndex(list(plan.holds) + build_retest_holds(plan, records))
    return reduce_with_retests(survey, plan, records, exclusion_state,
                               retest_exclusions(retest_vote_events), confirmed)


__all__ = ["CONTRACT", "reduce_survey"]
