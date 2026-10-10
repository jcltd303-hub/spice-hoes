#!/usr/bin/env python3
"""Install the selected finite lip-sync lane in an isolated Colab environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


REVISION = '0a89dec45a0192b824e3cf4daf96c239440c5ed8'
WHEEL_INDEX = 'https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html'


def setup(directory, output_config, *, dry_run=False):
    root = Path(directory).absolute()
    checkout = root / 'MuseTalk'
    venv = root / 'venv'
    python = venv / 'bin/python'
    constraints = root / 'constraints.txt'
    env = dict(os.environ)
    env['PATH'] = str(venv / 'bin') + os.pathsep + env.get('PATH', '')
    env['PIP_CONSTRAINT'] = str(constraints)
    commands = [
        ([sys.executable, '-m', 'pip', 'install', 'uv>=0.8,<1'], None, 180),
        ([sys.executable, '-m', 'uv', 'venv', '--python', '3.10', '--seed', str(venv)], None, 180),
        (['git', 'init', str(checkout)], None, 30),
        (['git', '-C', str(checkout), 'remote', 'add', 'origin', 'https://github.com/TMElyralab/MuseTalk.git'], None, 30),
        (['git', '-C', str(checkout), 'fetch', '--depth', '1', 'origin', REVISION], None, 180),
        (['git', '-C', str(checkout), 'checkout', '--detach', 'FETCH_HEAD'], None, 30),
        ([str(python), '-m', 'pip', 'install', 'torch==2.0.1', 'torchvision==0.15.2',
          'torchaudio==2.0.2', '--index-url', 'https://download.pytorch.org/whl/cu118'], None, 600),
        ([str(python), '-m', 'pip', 'install', '-r', str(checkout / 'requirements.txt')], None, 600),
        ([str(python), '-m', 'pip', 'install', '--no-build-isolation', 'chumpy==0.70'], None, 180),
        ([str(python), '-m', 'pip', 'install', 'mmengine==0.10.7', 'mmcv==2.0.1',
          '--only-binary=mmcv', '--find-links', WHEEL_INDEX], None, 300),
        ([str(python), '-m', 'pip', 'install', 'mmdet==3.1.0', 'mmpose==1.1.0'], None, 300),
        ([str(python), '-c', 'import torch, mmcv, mmdet, mmpose; assert torch.cuda.is_available(), "CUDA unavailable"'], None, 60),
    ]
    if dry_run:
        print(json.dumps({'source_revision': REVISION, 'commands': [c[0] for c in commands],
                          'musetalk_dir': str(checkout), 'musetalk_python': str(python)}))
        return
    if root.exists() or output_config.exists():
        raise FileExistsError('Use a fresh installation directory and configuration path')
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Select an available GPU runtime before installing MuseTalk')
    root.mkdir(parents=True)
    # Keep the upstream inference environment separate from Colab's PyTorch.
    constraints.write_text('numpy==1.23.5\nsetuptools<70\nyapf<0.40.2\n')
    for command, cwd, timeout in commands:
        subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout)

    download = r'''
from pathlib import Path
from huggingface_hub import snapshot_download
import gdown
import urllib.request
models = Path('models')
selections = [
    ('TMElyralab/MuseTalk', models, ['musetalkV15/musetalk.json', 'musetalkV15/unet.pth']),
    ('stabilityai/sd-vae-ft-mse', models / 'sd-vae', ['config.json', 'diffusion_pytorch_model.bin']),
    ('openai/whisper-tiny', models / 'whisper', ['config.json', 'pytorch_model.bin', 'preprocessor_config.json']),
    ('yzd-v/DWPose', models / 'dwpose', ['dw-ll_ucoco_384.pth']),
]
for repo, target, files in selections:
    snapshot_download(repo, local_dir=str(target), allow_patterns=files, endpoint='https://huggingface.co')
face = models / 'face-parse-bisent'
face.mkdir(parents=True, exist_ok=True)
gdown.download(id='154JgKpzCPW82qINcVieuPH3fZ2e0P812', output=str(face / '79999_iter.pth'), quiet=False)
urllib.request.urlretrieve('https://download.pytorch.org/models/resnet18-5c106cde.pth', face / 'resnet18-5c106cde.pth')
required = ['musetalkV15/unet.pth', 'musetalkV15/musetalk.json',
            'sd-vae/config.json', 'sd-vae/diffusion_pytorch_model.bin',
            'whisper/config.json', 'whisper/pytorch_model.bin', 'whisper/preprocessor_config.json',
            'dwpose/dw-ll_ucoco_384.pth', 'face-parse-bisent/79999_iter.pth',
            'face-parse-bisent/resnet18-5c106cde.pth']
for name in required:
    file = models / name
    if not file.is_file() or file.stat().st_size < (1 if name.endswith('.json') else 1024):
        raise RuntimeError('Incomplete MuseTalk weight: ' + name)
'''
    subprocess.run([str(python), '-c', download], cwd=checkout, env=env, check=True, timeout=900)
    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(json.dumps({'musetalk_dir': str(checkout), 'musetalk_python': str(python),
                                         'revision': REVISION}, indent=2))
    print('MuseTalk dependencies and selected weights installed; inference is checked by the worker.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('/content/spice-musetalk'))
    parser.add_argument('--output-config', type=Path, default=Path('/content/spice-musetalk-config.json'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    setup(args.directory, args.output_config, dry_run=args.dry_run)
