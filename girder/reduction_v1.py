from .alignment import align
from .deflection import make_responses
from .envelopes import make_envelopes
from .placement import assess_placement
from .repeats import summarize_repeats

CONTRACT = "hold-reduction-v1"


def reduce_survey(survey, exclusions):
    placement = assess_placement(survey.plan, survey.positions, exclusions.get("position", set()))
    pairs, gaps, unassigned = align(survey.plan, survey.readings, exclusions.get("reading", set()))
    responses = make_responses(survey.plan, placement, pairs, gaps)
    return dict(contract=CONTRACT, ready=all(row["state"] == "valid" for row in responses), placement=placement,
                responses=responses, repeats=summarize_repeats(survey.plan, responses),
                envelopes=make_envelopes(survey.plan, responses), unassigned_readings=unassigned)
