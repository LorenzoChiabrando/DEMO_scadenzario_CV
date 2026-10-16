from __future__ import annotations

from datetime import date

from src.roster_assignment import (
    assignment_context,
    busy_residents_for_day,
    busy_residents_for_week,
    resident_options,
)

_RESIDENTS = [
    {"nome": "Mario", "cognome": "Rossi", "livello": "Senior", "stato": "Molinette"},
    {"nome": "Anna", "cognome": "Bianchi", "livello": "Junior", "stato": "Molinette"},
    {"nome": "Luca", "cognome": "Verdi", "livello": "Intermediate", "stato": "Altra Sede"},
]


def test_options_list_only_active_residents_sorted_by_surname() -> None:
    options = resident_options(_RESIDENTS, busy={})

    assert [option.label for option in options] == ["Bianchi A.", "Rossi M."]
    assert [option.full_name for option in options] == ["Bianchi Anna", "Rossi Mario"]
    assert [option.level for option in options] == ["Junior", "Senior"]
    assert all(option.available for option in options)


def test_options_mark_busy_residents_with_their_reason() -> None:
    options = resident_options(_RESIDENTS, busy={"rossi m.": "Già in Sala Op. II"})

    rossi = next(option for option in options if option.label == "Rossi M.")
    assert not rossi.available
    assert rossi.conflict == "Già in Sala Op. II"


def test_current_assignment_stays_selectable_even_if_reported_busy() -> None:
    options = resident_options(
        _RESIDENTS, busy={"rossi m.": "Già in Sala Op. II"}, current="Rossi M."
    )

    rossi = next(option for option in options if option.label == "Rossi M.")
    assert rossi.available


def test_unknown_current_assignment_is_kept_as_first_option() -> None:
    options = resident_options(_RESIDENTS, busy={}, current="Demo Z.")

    assert options[0].label == "Demo Z."
    assert options[0].full_name == "Demo Z."
    assert options[0].available


def test_day_conflicts_ignore_own_role_and_guard_type() -> None:
    daily = {
        "Tipo Guardia": "118",
        "Reparto I": "Rossi M.",
        "Sala Op. I": "Bianchi A.",
        "Day Surgery": "",
    }

    busy = busy_residents_for_day(daily, role="Sala Op. I", ward_round="Verdi L.")

    assert busy == {
        "rossi m.": "Già in I Reperibilità",
        "verdi l.": "Già nel Giro Visite",
    }


def test_day_conflicts_do_not_report_the_ward_round_to_itself() -> None:
    busy = busy_residents_for_day({}, role="Giro Visite", ward_round="Verdi L.")

    assert busy == {}


def test_week_conflicts_cover_every_weekday_in_date_order() -> None:
    days = {
        date(2026, 9, 18): {"Reparto II": "Rossi M."},
        date(2026, 9, 16): {"Sala Op. I": "Rossi M.", "Tipo Guardia": "PI"},
        date(2026, 9, 17): {"Giro Visite": "Bianchi A.", "Day Hospital": "Bianchi A."},
    }

    busy = busy_residents_for_week(days)

    assert busy == {
        "rossi m.": "Impegnato il 16/09 in Sala Op. I",
        "bianchi a.": "Impegnato il 17/09 in Day Hospital",
    }


def test_option_search_matches_surname_name_and_label() -> None:
    rossi = resident_options(_RESIDENTS, busy={})[1]

    assert rossi.matches("")
    assert rossi.matches("ros")
    assert rossi.matches("MARIO")
    assert rossi.matches("rossi m.")
    assert not rossi.matches("bianchi")


def test_context_describes_the_day_or_the_ward_round_week() -> None:
    assert assignment_context(date(2026, 9, 15), "Reparto I") == "Mar 15/09/2026 · I Reperibilità"
    assert (
        assignment_context(date(2026, 9, 17), "Giro Visite")
        == "Settimana 14/09 – 18/09/2026 · Giro Visite"
    )
