#!/usr/bin/env python3
"""Recompute the eight retained speaker-level upper-tail OLS rows."""
from __future__ import annotations
import argparse, hashlib
from pathlib import Path
import pandas as pd
import statsmodels.formula.api as smf
EXPECTED_SHA256 = "50d5962745589d87ede893b33196f20ecf49b395dac94a63eedc40fb55ed0722"
def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args()
    if not a.input.is_file(): raise FileNotFoundError(a.input)
    got=sha256(a.input)
    if got != EXPECTED_SHA256: raise ValueError(f'Wrong upper-tail source hash: {got}; expected {EXPECTED_SHA256}')
    d=pd.read_csv(a.input); rows=[]
    for rate in ['normal','fast']:
      x=d[d.rate.eq(rate)].copy()
      for outcome in ['max_articulationrate','q95_articulationrate','max_speechrate','q95_speechrate']:
        q=x.dropna(subset=[outcome,'co_me_mean_mm_10','height_cm_c']).copy(); r=smf.ols(f'{outcome} ~ co_me_mean_mm_10 + height_cm_c',q).fit(); ci=r.conf_int().loc['co_me_mean_mm_10']
        rows.append({'rate':rate,'outcome':outcome,'slope_per_10mm':float(r.params['co_me_mean_mm_10']),'standard_error':float(r.bse['co_me_mean_mm_10']),'ci_lower':float(ci.iloc[0]),'ci_upper':float(ci.iloc[1]),'p_value':float(r.pvalues['co_me_mean_mm_10']),'n_speakers':len(q),'formula':f'{outcome} ~ co_me_mean_mm_10 + height_cm_c','input_sha256':got})
    out=pd.DataFrame(rows); a.output.parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.output,index=False,float_format='%.17g'); print(out.to_string(index=False))
if __name__=='__main__': main()
