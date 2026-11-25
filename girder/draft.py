from .intake import parse_survey
from .report import reduce_survey
from .retests import load_retests, load_substitutions, retest_votes
from .review import exclusions
from .runs import snapshot


def materialize(store, run):
    row, journal = snapshot(store, run)
    survey = parse_survey(row["source"])
    with store.transaction() as db:
        records = load_retests(db, run)
        retest_events = retest_votes(db, run)
        confirmed = load_substitutions(db, run)
    report = reduce_survey(survey, exclusions(journal), records, retest_events, confirmed)
    return row, journal, survey, report, dict(votes=retest_events, substitutions=confirmed)


def inspect_draft(store, run):
    row, journal, _, report, retest_journal = materialize(store, run)
    return dict(id=run, revision=row["revision"], input_hash=row["input_hash"], plan=row["source"]["plan"],
                journal=journal, retest_journal=retest_journal, report=report)
