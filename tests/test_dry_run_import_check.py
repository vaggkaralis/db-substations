import pandas as pd

from import_validator import validate_breaker_category
from importers import _map_columns
from strings_proxy import STRINGS as S

ELEM_BREAKER_MT = S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")


def _count_missing_breakers_and_models(df: pd.DataFrame):
    df_mapped = _map_columns(df.copy())

    # determine columns
    breaker_col = None
    model_col = None
    element_col = None
    for c in df_mapped.columns:
        if str(c).strip() == 'Τύπος Διακόπτη':
            breaker_col = c
        if str(c).strip() == 'Model Name':
            model_col = c
        if str(c).strip() == 'Element Type':
            element_col = c

    # heuristics if mapping not exact
    if not breaker_col:
        for c in df_mapped.columns:
            lc = str(c).lower()
            if 'breaker' in lc or 'τύπος' in lc or 'type' in lc:
                breaker_col = c
                break
    if not model_col:
        for c in df_mapped.columns:
            lc = str(c).lower()
            if 'model' in lc or 'μοντέλο' in lc:
                model_col = c
                break
    if not element_col:
        for c in df_mapped.columns:
            lc = str(c).lower()
            if 'element' in lc or 'τύπος' in lc:
                element_col = c
                break

    missing_breaker_rows = 0
    missing_model_rows = 0
    for _, row in df_mapped.iterrows():
        is_breaker = False
        if element_col and pd.notna(row.get(element_col, None)):
            elem_val = str(row.get(element_col)).lower()
            if 'διακόπτης' in elem_val or 'υτ' in elem_val or 'μτ' in elem_val or 'breaker' in elem_val:
                is_breaker = True
        br = None
        if breaker_col and pd.notna(row.get(breaker_col, None)):
            br = str(row.get(breaker_col)).strip()
        if is_breaker and not br:
            missing_breaker_rows += 1
        mn = None
        if model_col and pd.notna(row.get(model_col, None)):
            mn = str(row.get(model_col)).strip()
        if not mn:
            missing_model_rows += 1
    return missing_breaker_rows, missing_model_rows


def test_map_columns_and_models_count():
    # create a dataframe with synonym headers and mixed rows
    data = [
        {'Όνομα': 'B1', 'Τύπος': ELEM_BREAKER_MT, 'Μοντέλο': 'M1', 'Τύπος Διακόπτη': 'SF6'},
        {'Όνομα': 'B2', 'Τύπος': ELEM_BREAKER_MT, 'Μοντέλο': '', 'Τύπος Διακόπτη': ''},
        {'Όνομα': 'T1', 'Τύπος': 'Μετασχηματιστής 150/20KV', 'Μοντέλο': 'TX1'},
    ]
    df = pd.DataFrame(data)

    missing_breakers, missing_models = _count_missing_breakers_and_models(df)

    # Row 2 is a breaker missing breaker type => should count as 1
    assert missing_breakers == 1
    # Row 2 also missing model name => counts as 1; transformer has a model, row1 has a model
    assert missing_models == 1


def test_validate_breaker_category_matches():
    assert validate_breaker_category('SF6')[0] == 'SF6'
    assert validate_breaker_category('sf6')[0] == 'SF6'
    assert validate_breaker_category('Πτωχού Ελαίου')[0] == 'Πτωχού Ελαίου'
    # fuzzy-ish input
    assert validate_breaker_category('ελαίου')[0] in ('Ελαίου', 'Πτωχού Ελαίου')
