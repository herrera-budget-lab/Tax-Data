"""Builds resources/tips/ttoc_census_occ.csv: the Census occupation codes of the occupations that customarily and
regularly received tips (Treasury Tipped Occupation Codes, TTOC), for the SIPP's occupation codes. It is run by hand.

Inputs, all in resources/tips/:
- ttoc_soc.csv: Table 1 to 26 CFR 1.224-1(h) (T.D. 10044, 91 FR 19026, 13 April 2026): each TTOC, its title and
  category, and the 2018 SOC codes the rule says most closely correlate with it (one row per TTOC and SOC code).
  soc_2010 holds the 2010 SOC equivalent where the code changed between the 2010 and 2018 SOC. ttoc_narrower_than_soc
  is 1 where the rule's occupation is narrower than its SOC code (home electricians within electricians, say).
- census_occ_2018.csv and census_occ_2010.csv: the Census Bureau's 2018 and 2010 Census occupation code lists with
  their SOC codes (www2.census.gov/programs-surveys/demo/guidance/industry-occupation/, the 2018 occupation code list
  and crosswalk, and the 2010 occupation codes with crosswalk). The SIPP uses the 2010 list in the 2014 panel
  (reference year 2015) and the 2018 list from the 2018 release (reference year 2017) on.

A Census code's SOC field is a detailed SOC code (35-3011), a group that ends in zeros (35-2010: every 35-201x code;
39-1000: every 39-1xxx code), or a residual with X (25-30XX: the 25-30xx codes not listed on their own). A rule SOC
code matches the Census code with the same detailed code, else the Census code whose group or residual is the most
specific to cover it. match is 'exact' when the Census code is that one detailed SOC code and 'broad' when the Census
code covers other SOC codes too, so it holds workers outside the rule's occupation.

    python -m resources_build.build_ttoc_census_occ
"""
import os

import pandas as pd

from shared import common

DIR = os.path.join(common.RESOURCES, 'tips')


def prefix(field):
    """The SOC prefix a Census code's SOC field covers: the code itself when detailed, else the part before the X or
    before the trailing zeros."""
    major, minor = field.split('-')
    if 'X' in minor:
        return f'{major}-{minor[:minor.index("X")]}'
    if minor.endswith('0'):
        return f'{major}-{minor.rstrip("0")}'
    return field


def match(soc, census):
    """The Census code for one SOC code: the exact one, else the most specific group covering it. None if none does."""
    exact = census[census.census_soc == soc]
    if len(exact):
        assert len(exact) == 1, (soc, exact)
        # A soc_2010 entry can itself be a group (27-2040); the Census code then covers other SOC codes too.
        return exact.iloc[0], ('exact' if prefix(soc) == soc else 'broad')
    cover = census[[soc.startswith(prefix(f)) and f != soc for f in census.census_soc]]
    if not len(cover):
        return None, None
    best = cover.loc[cover.census_soc.map(lambda f: len(prefix(f))).idxmax()]
    return best, 'broad'


def main():
    t = pd.read_csv(os.path.join(DIR, 'ttoc_soc.csv'), dtype=str)
    rows = []
    for vintage, soc_col in [(2018, 'soc'), (2010, 'soc_2010')]:
        census = pd.read_csv(os.path.join(DIR, f'census_occ_{vintage}.csv'), dtype=str)
        census = census[census.census_soc.str.match(r'^\d\d-[\dX]{4}$')]     # drop military and group header rows
        for _, r in t.iterrows():
            for soc in r[soc_col].split(';'):
                c, how = match(soc, census)
                assert c is not None, f'{vintage}: no Census code covers TTOC {r.ttoc} SOC {soc}'
                rows.append({'census_vintage': vintage, 'census_occ': c.census_occ, 'census_title': c.census_title,
                             'census_soc': c.census_soc, 'ttoc': r.ttoc, 'ttoc_title': r.ttoc_title,
                             'ttoc_category': r.ttoc_category, 'soc_2018': r.soc, 'soc_matched': soc, 'match': how,
                             'ttoc_narrower_than_soc': int(r.ttoc_narrower_than_soc)})
    out = pd.DataFrame(rows).drop_duplicates().sort_values(['census_vintage', 'census_occ', 'ttoc'])
    # Every TTOC has at least one Census code in each vintage.
    for v, g in out.groupby('census_vintage'):
        assert set(g.ttoc) == set(t.ttoc), (v, set(t.ttoc) - set(g.ttoc))
    # A Census code is 'precise' when some TTOC matches it exactly and the rule does not define that TTOC more
    # narrowly than its SOC code: everyone in the Census code is in a tipped occupation. Otherwise the code is
    # 'broad': it also holds workers outside the rule's occupations.
    precise = (out.match == 'exact') & (out.ttoc_narrower_than_soc == 0)
    out['census_occ_quality'] = precise.groupby([out.census_vintage, out.census_occ]).transform('any') \
        .map({True: 'precise', False: 'broad'})
    out.to_csv(os.path.join(DIR, 'ttoc_census_occ.csv'), index=False)
    for v, g in out.groupby('census_vintage'):
        q = g.drop_duplicates('census_occ').census_occ_quality.value_counts()
        common.say(f'{v} Census codes: {g.census_occ.nunique()} hold a tipped occupation; {int(q.get("precise", 0))} '
                   f'precise, {int(q.get("broad", 0))} broad')


if __name__ == '__main__':
    main()
