"""Serial, checkpointed phone execution over an injected authenticated outbound API."""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Protocol

from .localdream import MAX_IMAGE_BYTES

class PhoneCloudAPI(Protocol):
    authenticated: bool
    def claim(self, worker_id, now, *, device_id): ...
    def renew(self, job_id, lease_token): ...
    def upload(self, job, image, result): ...
    def complete(self, job_id, lease_token, result): ...
    def reconcile_artifact(self, job_id, lease_token, result): ...

class PhoneWorker:
    heartbeat_seconds = 30

    def __init__(self, cloud, generator, checkpoint_dir, *, worker_id, device_id, dry_run=True):
        if not worker_id or not device_id or getattr(cloud, 'authenticated', False) is not True:
            raise ValueError('Authenticated paired cloud adapter and worker/device IDs required')
        self.cloud, self.generator = cloud, generator
        self.worker_id, self.device_id, self.dry_run = worker_id, device_id, dry_run
        self.directory = Path(checkpoint_dir)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_path = self.directory / ('device-' + hashlib.sha256(device_id.encode()).hexdigest() + '.lock')

    @staticmethod
    def _ready(state):
        return (isinstance(state, dict) and state.get('online') is True
                and type(state.get('battery')) in (int, float) and 0 <= state['battery'] <= 100
                and type(state.get('charging')) is bool
                and type(state.get('thermal_severity')) is int and 0 <= state['thermal_severity'] < 3
                and (state['battery'] >= 25 or state['charging']))

    def tick(self, device_state):
        if not self._ready(device_state):
            return {'status':'deferred'}
        if self.dry_run:
            return {'status':'dry_run'}
        with self.lock_path.open('a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'status':'busy'}
            try:
                for path in sorted(self.directory.glob('*.json')):
                    saved = json.loads(path.read_text())
                    if saved['job']['device_id'] == self.device_id:
                        return self._deliver(path, saved)
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                job = self.cloud.claim(self.worker_id, now, device_id=self.device_id)
                if job is None:
                    return {'status':'idle'}
                if job.get('kind') != 'image' or job.get('device_id') != self.device_id or job.get('worker_id') != self.worker_id or not job.get('lease_token'):
                    raise ValueError('Invalid fenced image lease')
                stop, lost = threading.Event(), threading.Event()
                def heartbeat():
                    while not stop.wait(self.heartbeat_seconds):
                        try:
                            self.cloud.renew(job['id'], job['lease_token'])
                        except Exception:
                            lost.set()
                            return
                thread = threading.Thread(target=heartbeat, daemon=True)
                thread.start()
                try:
                    generated = self.generator.generate(job['payload']['settings'])
                    image = generated['image']
                    if not isinstance(image, bytes) or len(image) > MAX_IMAGE_BYTES or not (image.startswith(b'\x89PNG\r\n\x1a\n') or image.startswith(b'\xff\xd8\xff')):
                        raise ValueError('Invalid encoded image artifact')
                    result = {k:v for k,v in generated.items() if k != 'image'}
                    result['artifact_hash'] = hashlib.sha256(image).hexdigest()
                    stem = hashlib.sha256(job['id'].encode()).hexdigest()
                    image_path = self.directory / (stem + '.png')
                    path = self.directory / (stem + '.json')
                    self._atomic(image_path, image)
                    saved = {'job':job, 'result':result, 'image_file':image_path.name, 'lease_lost':lost.is_set()}
                    self._save(path, saved)
                finally:
                    stop.set()
                    thread.join()
                if lost.is_set():
                    saved['lease_lost'] = True
                    self._save(path, saved)
                return self._deliver(path, saved)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _atomic(self, path, data):
        temporary = path.with_suffix(path.suffix + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _save(self, path, saved):
        self._atomic(path, json.dumps(saved, sort_keys=True, allow_nan=False).encode())

    def _deliver(self, path, saved):
        job, result = saved['job'], saved['result']
        image_path = self.directory / saved['image_file']
        if image_path.parent != self.directory or image_path.name != saved['image_file']:
            raise ValueError('Unsafe checkpoint image path')
        with image_path.open('rb') as stream:
            image = stream.read(MAX_IMAGE_BYTES + 1)
        if len(image) > MAX_IMAGE_BYTES or hashlib.sha256(image).hexdigest() != result['artifact_hash']:
            raise ValueError('Checkpoint artifact mismatch')
        try:
            if saved.get('lease_lost'):
                raise ValueError('Lease lost')
            if 'uploaded' not in saved:
                receipt = self.cloud.upload(job, image, result)
                saved['uploaded'] = receipt
                self._save(path, saved)
            # Keep completion payload stable across retry for JobStore idempotency.
            completed = self.cloud.complete(job['id'], job['lease_token'], result)
            if completed.get('status') != 'completed':
                raise ValueError('Completion not acknowledged')
        except Exception:
            try:
                self.cloud.reconcile_artifact(job['id'], job['lease_token'], result)
            except Exception:
                pass
            return {'status':'reconciliation_pending', 'job_id':job['id'], 'artifact_hash':result['artifact_hash']}
        path.unlink()
        image_path.unlink()
        return {'status':'completed', 'job_id':job['id'], 'artifact_hash':result['artifact_hash']}
