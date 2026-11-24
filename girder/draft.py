from .intake import parse_survey
from .report import reduce_survey
from .review import exclusions
from .runs import snapshot


def materialize(store, run):
    row, journal = snapshot(store, run)
    survey = parse_survey(row["source"])
    report = reduce_survey(survey, exclusions(journal))
    return row, journal, survey, report


def inspect_draft(store, run):
    row, journal, _, report = materialize(store, run)
    return dict(id=run, revision=row["revision"], input_hash=row["input_hash"], plan=row["source"]["plan"],
                journal=journal, report=report)
