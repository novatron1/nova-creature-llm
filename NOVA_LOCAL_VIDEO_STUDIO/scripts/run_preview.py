"""Submit, wait for, and collect a local ComfyUI preview; no media leaves localhost."""
import argparse
import json
from pathlib import Path
import shutil
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
API = 'http://127.0.0.1:8190'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image', default=str(ROOT/'inputs/images/lil_ammo_reference.jpg'))
    p.add_argument('--engine', choices=['animatelcm','wan'], default='wan')
    p.add_argument('--frames', type=int)
    p.add_argument('--width', type=int, default=384)
    p.add_argument('--height', type=int, default=480)
    p.add_argument('--steps', type=int)
    p.add_argument('--seed', type=int, default=20260923)
    p.add_argument('--prompt')
    p.add_argument('--timeout', type=int, default=1800)
    args = p.parse_args()
    wan = args.engine == 'wan'
    args.frames = args.frames if args.frames is not None else (17 if wan else 16)
    args.steps = args.steps if args.steps is not None else (20 if wan else 6)
    multiple = 32 if wan else 8
    if args.width % multiple or args.height % multiple or min(args.width,args.height) < 64:
        p.error(f'Width and height must be multiples of {multiple}, at least 64.')
    if wan and (args.frames % 4 != 1 or not 5 <= args.frames <= 33):
        p.error('Wan requires 4n+1 frames, from 5 to 33 for this bounded preset.')
    if not wan and not 8 <= args.frames <= 16:
        p.error('Use 8 to 16 frames for this bounded GPU preset.')
    source = Path(args.image).resolve()
    if not source.is_file():
        p.error(f'Reference image missing: {source}')
    info = requests.get(API+'/object_info', timeout=15)
    info.raise_for_status()
    graph_file = 'lil_ammo_wan_api.json' if wan else 'lil_ammo_i2v_api.json'
    graph = json.loads((ROOT/'workflows'/graph_file).read_text())
    missing = {n['class_type'] for n in graph.values()} - info.json().keys()
    if missing:
        raise RuntimeError(f'Missing nodes: {missing}')
    dest = ROOT/'input'/source.name
    dest.parent.mkdir(exist_ok=True)
    if source != dest.resolve():
        shutil.copy2(source,dest)
    graph['56' if wan else '5']['inputs']['image'] = dest.name
    if wan:
        graph['55']['inputs'].update(width=args.width,height=args.height,length=args.frames)
    else:
        graph['6']['inputs'].update(width=args.width,height=args.height,batch_size=args.frames)
    graph['3' if wan else '11']['inputs'].update(steps=args.steps,seed=args.seed)
    if args.prompt:
        graph['6' if wan else '3']['inputs']['text'] = args.prompt
    start = time.monotonic()
    r = requests.post(API+'/prompt',json={'prompt':graph,'client_id':'nova-studio'},timeout=30)
    if not r.ok:
        raise RuntimeError(r.text)
    pid = r.json()['prompt_id']
    print(f'Queued {pid}; {args.width}x{args.height}, {args.frames} frames',flush=True)
    while time.monotonic()-start < args.timeout:
        h = requests.get(API+'/history/'+pid,timeout=15).json().get(pid)
        if h:
            (ROOT/'logs'/f'{pid}.json').write_text(json.dumps(h,indent=2))
            if h['status']['status_str'] != 'success':
                errors = [m[1].get('exception_message','') for m in h['status']['messages'] if m[0]=='execution_error']
                raise RuntimeError('; '.join(errors) or h['status']['status_str'])
            artifacts = []
            for output in h['outputs'].values():
                for values in output.values():
                    if isinstance(values,list):
                        artifacts.extend(v for v in values if isinstance(v,dict) and str(v.get('filename','')).endswith('.mp4'))
            if not artifacts:
                raise RuntimeError('ComfyUI completed without an MP4: '+str(h['outputs']))
            for artifact in artifacts:
                file = ROOT/'output'/artifact.get('subfolder','')/artifact['filename']
                target = ROOT/'outputs/previews'/artifact['filename']
                target.parent.mkdir(parents=True, exist_ok=True)
                if file.is_file():
                    shutil.copy2(file,target)
                else:
                    # Some managed ComfyUI workers expose SaveVideo results through
                    # /view while their output directory is isolated or cleaned.
                    response = requests.get(API+'/view', params={
                        'filename': artifact['filename'],
                        'subfolder': artifact.get('subfolder',''),
                        'type': artifact.get('type','output'),
                    }, timeout=60)
                    response.raise_for_status()
                    target.write_bytes(response.content)
                print(f'MP4: {target}',flush=True)
            print(f'Elapsed: {time.monotonic()-start:.1f} seconds',flush=True)
            return
        time.sleep(3)
    raise TimeoutError(f'Job {pid} still running; inspect {API} before submitting again.')

if __name__ == '__main__':
    main()
