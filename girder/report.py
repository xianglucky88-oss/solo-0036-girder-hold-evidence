from .alignment import align
from .deflection import make_responses
from .envelopes import make_envelopes
from .graded import evaluate_graded
from .placement import assess_placement, assess_steps
from .repeats import summarize_repeats

CONTRACT = "hold-reduction-v2"


def reduce_survey(survey, exclusions):
    plan = survey.plan
    placement = assess_placement(plan, survey.positions, exclusions.get("position", set()))
    step_placement = assess_steps(plan, survey.positions, exclusions.get("position", set()))
    pairs, gaps, unassigned = align(plan, survey.readings, exclusions.get("reading", set()))
    responses = make_responses(plan, placement, pairs, gaps)
    graded, graded_ready = evaluate_graded(plan, step_placement, pairs, gaps)
    return dict(contract=CONTRACT,
                ready=all(row["state"] == "valid" for row in responses) and graded_ready,
                placement=placement, step_placement=step_placement, responses=responses,
                repeats=summarize_repeats(plan, responses), envelopes=make_envelopes(plan, responses),
                graded=graded, unassigned_readings=unassigned)
