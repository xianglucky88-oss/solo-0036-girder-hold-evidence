from .exact import encode
from .phase_samples import summarize_phases


def make_responses(plan, placement, pairs, gaps):
    rows = []
    for hold in plan.holds:
        for point in plan.points:
            phases, values = summarize_phases(pairs, gaps, "hold", hold.id, point.id, plan.minimum_pairs)
            state = "valid"
            displacement = residual = None
            if not placement[hold.id]["valid"]:
                state = "placement"
            elif None in values.values():
                state = "coverage"
            else:
                displacement = values["loaded"] - values["before"]
                residual = values["after"] - values["before"]
            rows.append(dict(hold=hold.id, case=hold.case, point=point.id, state=state, phases=phases,
                             loaded_um=encode(displacement), residual_um=encode(residual),
                             residual_review=None if residual is None else abs(residual) > plan.residual_limit_um))
    return rows
