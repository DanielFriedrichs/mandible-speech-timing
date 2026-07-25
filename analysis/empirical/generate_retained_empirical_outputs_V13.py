#!/usr/bin/env python3
"""Rerun retained canonical empirical models from repository-derived inputs.

This scoped V13 runner imports the exact broad canonical generator but executes
only analysis families retained in V12: demographic/female sensitivity, strict
acoustic sensitivity, Co--Me-by-rate interactions, read speech, and availability.
Phase and coupling inputs/outputs are intentionally not packaged.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm

EXPECTED = {
    'primary': '4492e389789b7126c2b9f15588b682871f374cf917aa6006134c3090bffcf9ed',
    'secondary': '10c3eedaf2f91990cc128639cf0475eb1c1583c821171d99a1a26d7dddb7b6e0',
    'read': '86e0c5c463c63e47992ea431102b107d5c5021592656e61a19f09187cf0f2303',
    'anatomy': 'e157bc168902fd40f6bbde394a1bc3e2c4d1c5d08efa38bcc0cdccb5ffe385fd',
}
NUMERIC = ['beta','robust_se','ci_lower','ci_upper','p_value','transformed_effect','transformed_ci_lower','transformed_ci_upper']

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def load_canonical(path: Path):
    spec=importlib.util.spec_from_file_location('canonical_empirical',path)
    if spec is None or spec.loader is None: raise RuntimeError('Could not load canonical generator')
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def write(rows, p): pd.DataFrame(rows).to_csv(p,index=False,float_format='%.17g')

def compare(new_path: Path, ref_path: Path) -> dict:
    n=pd.read_csv(new_path); r=pd.read_csv(ref_path)
    keys=[k for k in ['analysis_family','model_id','outcome','record_type','term','stratum'] if k in n.columns and k in r.columns]
    m=n.merge(r,on=keys,suffixes=('_new','_ref'),how='outer',indicator=True)
    if not (m['_merge']=='both').all(): raise RuntimeError(f'Row-key mismatch for {new_path.name}')
    diffs={}
    for c in NUMERIC:
        a=f'{c}_new'; b=f'{c}_ref'
        if a in m and b in m:
            x=pd.to_numeric(m[a],errors='coerce'); y=pd.to_numeric(m[b],errors='coerce')
            z=(x-y).abs(); diffs[c]=None if z.dropna().empty else float(z.max())
            if diffs[c] is not None and diffs[c] > 1e-10: raise RuntimeError(f'{new_path.name}: {c} differs by {diffs[c]}')
    return {'file':new_path.name,'rows':len(n),'max_abs_diffs':diffs,'status':'PASS'}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repository-root',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args()
    root=a.repository_root.resolve(); out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    paths={
      'primary':root/'data/derived/primary/analysis_dataset_clean.csv',
      'secondary':root/'data/derived/secondary/analysis_ready_trials.csv',
      'read':root/'data/derived/read_speech/read_speech_envelope.csv',
      'anatomy':root/'data/derived/anatomy/anatomy_measurements.csv'}
    for k,p in paths.items():
        if not p.is_file(): raise FileNotFoundError(p)
        got=sha256(p)
        if got != EXPECTED[k]: raise ValueError(f'Wrong {k} hash: {got}; expected {EXPECTED[k]}')
    canon_path=root/'analysis/empirical/generate_canonical_empirical_outputs_CURRENT.py'; canon=load_canonical(canon_path)
    speech=canon.prep_speech(paths['primary']); mech=canon.prep_mechanistic(paths['secondary'])
    # Demographic and female-only models.
    rows=[]
    for outcome in ['log_speechrate','log_articulationrate']:
      specs=[
       ('primary_independence_gee',speech,f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c",'all 28 primary speakers'),
       ('sex_age_adjusted_independence_gee',speech,f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c + C(sex_norm, Treatment(reference='female')) + age_years",'all primary speakers with complete demographic covariates'),
       ('female_only_independence_gee',speech[speech.sex_norm.eq('female')].copy(),f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c",'female speakers only')]
      for model_id,dat,formula,subset in specs:
        res=canon.fit_gee(dat,formula)
        rows += canon.model_rows(result=res,data=dat,output_name='primary_demographic_sensitivity_CURRENT.csv',analysis_family='primary_and_demographic_sensitivity',model_id=model_id,outcome=outcome,formula=formula,input_files=[paths['primary']],original_root=root,script_path=canon_path,status='VERIFIED_CANONICAL',log_outcome=True,sequence_reference='bibibi',subset=subset)
    write(rows,out/'primary_demographic_sensitivity_CURRENT.csv')
    # Strict acoustic.
    counts=mech.loc[mech.audio_mod_dom_hz.notna()].groupby('participant_id').size(); eligible=sorted(counts[counts>=50].index.astype(str)); strict=mech[mech.participant_id.isin(eligible)].copy()
    formula="audio_mod_dom_hz ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c"; res=canon.fit_gee(strict,formula)
    rows=canon.model_rows(result=res,data=strict,output_name='strict_acoustic_50trial_sensitivity_CURRENT.csv',analysis_family='strict_acoustic_50trial_sensitivity',model_id='audio_modulation_minimum_50_valid_trials_independence_gee',outcome='audio_mod_dom_hz',formula=formula,input_files=[paths['secondary']],original_root=root,script_path=canon_path,status='VERIFIED_CANONICAL',log_outcome=False,sequence_reference='bibibi',subset=f'{len(eligible)} speakers with >=50 nonmissing audio_mod_dom_hz values',selection_rule='participant retained when count(nonmissing audio_mod_dom_hz) >= 50; model complete cases thereafter',extra={'eligible_speakers':';'.join(eligible)})
    write(rows,out/'strict_acoustic_50trial_sensitivity_CURRENT.csv')
    # Interactions for retained primary and principal secondary outcomes.
    rows=[]; slopes=[]
    specs=[(speech,paths['primary'],'log_speechrate',False),(speech,paths['primary'],'log_articulationrate',False)]
    for dat,ip,outcome,gated in specs:
      formula=f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c + co_me_mean_mm_10:C(rate, Treatment(reference='fast'))"; res=canon.fit_gee(dat,formula)
      rows += canon.model_rows(result=res,data=dat,output_name='interaction_models_summary_RETAINED_V13.csv',analysis_family='co_me_by_rate_interaction',model_id=f'{outcome}_by_rate_independence_gee',outcome=outcome,formula=formula,input_files=[ip],original_root=root,script_path=canon_path,status='VERIFIED_CANONICAL',log_outcome=outcome.startswith('log_'),sequence_reference='bibibi',subset='analysis_ok and ema_cycles_ok' if gated else 'all primary timing observations',extra={'interaction_type':'Co--Me x instructed rate'})
      it=[t for t in res.params.index if 'co_me_mean_mm_10:C(rate' in t][0]
      for stratum,int_term in [('fast',None),('normal',it)]:
        slopes.append(canon.slope_row(result=res,base_term='co_me_mean_mm_10',interaction_term=int_term,stratum=stratum,outcome=outcome,model_id=f'{outcome}_by_rate_independence_gee',formula=formula,n_obs=int(res.nobs),n_spk=int(len(res.model.group_labels)),input_files=[ip],original_root=root,script_path=canon_path,sequence_reference='bibibi',stratum_type='instructed_rate'))
    write(rows,out/'interaction_models_summary_RETAINED_V13.csv'); write(slopes,out/'interaction_slopes_by_rate_RETAINED_V13.csv')
    # Read speech.
    read=canon.prep_read(paths['read'],paths['anatomy']); formula="audio_mod_dom_hz ~ C(task, Treatment(reference='passage_baseline_noEMA')) + co_me_mean_mm_10 + height_cm_c"; res=canon.fit_gee(read,formula)
    rows=canon.model_rows(result=res,data=read,output_name='read_speech_effects_CURRENT.csv',analysis_family='read_speech',model_id='read_speech_independence_gee',outcome='audio_mod_dom_hz',formula=formula,input_files=[paths['read'],paths['anatomy']],original_root=root,script_path=canon_path,status='VERIFIED_CANONICAL',log_outcome=False,sequence_reference='not applicable',rate_reference='not applicable',subset="status == ok and complete anthropometry",selection_rule="read-speech rows with status 'ok'; inner merge to finalized Co--Me and height",extra={'task_reference':'passage_baseline_noEMA'})
    write(rows,out/'read_speech_effects_CURRENT.csv')
    # Availability logistic GEE (recomputed; compare to accepted compact source with tolerance).
    availability=[]
    for name,flag in [('jaw_cycle_availability',mech.ema_cycles_ok.fillna(False).astype(int)),('audio_mod_availability',mech.audio_mod_dom_hz.notna().astype(int))]:
      x=mech.copy(); x['available']=flag; formula="available ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c"; rr=canon.fit_gee(x,formula,family=sm.families.Binomial()); b=float(rr.params['co_me_mean_mm_10']); ci=rr.conf_int().loc['co_me_mean_mm_10']
      availability.append({'availability_outcome':name,'n_obs':int(rr.nobs),'n_spk':int(len(rr.model.group_labels)),'log_or_per_10mm':b,'or_per_10mm':math.exp(b),'or_ci_low':math.exp(float(ci.iloc[0])),'or_ci_high':math.exp(float(ci.iloc[1])),'p':float(rr.pvalues['co_me_mean_mm_10'])})
    pd.DataFrame(availability).to_csv(out/'ema_audio_availability_bias_models_RECOMPUTED_V13.csv',index=False,float_format='%.17g')
    checks=[]
    for name in ['primary_demographic_sensitivity_CURRENT.csv','strict_acoustic_50trial_sensitivity_CURRENT.csv','interaction_models_summary_RETAINED_V13.csv','interaction_slopes_by_rate_RETAINED_V13.csv','read_speech_effects_CURRENT.csv']:
      checks.append(compare(out/name,root/'results/canonical_empirical'/name))
    pd.DataFrame(checks).to_csv(out/'RETAINED_EMPIRICAL_NUMERICAL_COMPARISON_V13.csv',index=False)
    print('RETAINED EMPIRICAL MODELS: PASS')
if __name__=='__main__': main()
