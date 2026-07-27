#!/usr/bin/env python3
"""Fail-loud verification of critical minimized repository inputs and canonical counts."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd
EXPECTED={
'data/derived/primary/analysis_dataset_clean.csv':'4492e389789b7126c2b9f15588b682871f374cf917aa6006134c3090bffcf9ed',
'data/derived/secondary/analysis_ready_trials.csv':'10c3eedaf2f91990cc128639cf0475eb1c1583c821171d99a1a26d7dddb7b6e0',
'data/derived/read_speech/read_speech_envelope.csv':'86e0c5c463c63e47992ea431102b107d5c5021592656e61a19f09187cf0f2303',
'data/derived/anatomy/anatomy_measurements.csv':'e157bc168902fd40f6bbde394a1bc3e2c4d1c5d08efa38bcc0cdccb5ffe385fd',
'data/derived/upper_tail/speaker_upper_limits_speech.csv':'50d5962745589d87ede893b33196f20ecf49b395dac94a63eedc40fb55ed0722',
'artisynth/validated/fixed_force_grid.csv':'510f2e249fa2dcf62e8437bce17aefa425f999cbbed5efdbfcb2b4d42af8ebad',
'artisynth/validated/force_capacity_s2_grid.csv':'59f84b7d5f8f1b7e7bc4455af6bacee121e278e1c82eb5d56cc9729424b58d02',
'artisynth/validated/endpoint_comparison.csv':'44cd194dca713b4e8fbebecaf8f77d72687452f5e8f6bccadcdbc783df645508',
}
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def main():
 root=Path(__file__).resolve().parents[1]; out=[]
 for rel,exp in EXPECTED.items():
  p=root/rel
  if not p.is_file(): raise FileNotFoundError(p)
  got=sha(p)
  if got!=exp: raise ValueError(f'Hash mismatch for {rel}: {got} != {exp}')
  out.append({'path':rel,'sha256':got,'status':'PASS'})
 p=pd.read_csv(root/'data/derived/primary/analysis_dataset_clean.csv'); s=pd.read_csv(root/'data/derived/secondary/analysis_ready_trials.csv')
 if (len(p),p.participant_id.nunique())!=(8123,28): raise ValueError('Primary count mismatch')
 if (len(s),s.participant_id.nunique())!=(6134,23): raise ValueError('Secondary parent count mismatch')
 jaw=int(s['ema_cycle_rate_hz'].notna().sum()); jaw_spk=int(s.loc[s['ema_cycle_rate_hz'].notna(),'participant_id'].nunique())
 audio=int(s['audio_mod_dom_hz'].notna().sum()); audio_spk=int(s.loc[s['audio_mod_dom_hz'].notna(),'participant_id'].nunique())
 analysis_ok=int(s['analysis_ok'].astype(str).str.lower().eq('true').sum())
 if (analysis_ok,jaw,jaw_spk,audio,audio_spk)!=(6056,3323,22,5572,23): raise ValueError('Secondary complete-case count mismatch')
 print(json.dumps({'status':'PASS','files':out,'primary_rows':len(p),'primary_speakers':p.participant_id.nunique(),'secondary_rows':len(s),'secondary_speakers':s.participant_id.nunique(),'secondary_analysis_ok':analysis_ok,'jaw_complete_rows':jaw,'jaw_complete_speakers':jaw_spk,'audio_complete_rows':audio,'audio_complete_speakers':audio_spk},indent=2))
if __name__=='__main__': main()
