"""Generate one image through the local ComfyUI worker; no cloud image service."""
import argparse, json, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
API = 'http://127.0.0.1:8190'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prompt', required=True)
    p.add_argument('--seed', type=int, default=20260929)
    args = p.parse_args()
    graph = json.loads((ROOT / 'workflows/local_txt2img_api.json').read_text(encoding='utf-8'))
    graph['2']['inputs']['text'] = args.prompt
    graph['5']['inputs']['seed'] = args.seed
    response = requests.post(API + '/prompt', json={'prompt': graph, 'client_id': 'nova-local-image'}, timeout=30)
    response.raise_for_status()
    prompt_id = response.json()['prompt_id']
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        history = requests.get(API + '/history/' + prompt_id, timeout=30).json().get(prompt_id)
        if history:
            if history.get('status', {}).get('status_str') == 'error':
                raise RuntimeError(json.dumps(history))
            outputs = history.get('outputs', {})
            for value in outputs.values():
                for image in value.get('images', []):
                    params = {'filename': image['filename'], 'subfolder': image.get('subfolder',''), 'type': image.get('type','output')}
                    data = requests.get(API + '/view', params=params, timeout=30)
                    data.raise_for_status()
                    out = ROOT / 'outputs' / 'previews' / ('local_' + Path(image['filename']).name)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data.content)
                    print(out)
                    return
        time.sleep(2)
    raise TimeoutError('Local ComfyUI image generation timed out.')

if __name__ == '__main__':
    main()
