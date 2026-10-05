"""Losslessly compact completed trial evidence inside this suite only."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parent


def digest_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(4 << 20), b''):
        digest.update(block)
    return digest.hexdigest()


def compact(run: Path) -> None:
    output = run / 'workspace/output'
    if not (run / 'summary.json').exists() or not output.is_dir():
        return
    for install in [output / 'install', output / 'install/install']:
        if not install.is_dir() or (install / 'run.json').exists():
            continue
        parent = install.parent
        existing = parent / 'install.tar.gz'
        archive = existing if existing.exists() else parent / 'failed_install.tar.gz'
        files = {str(path.relative_to(install)): (path.stat().st_size, digest_stream(path.open('rb')))
                 for path in install.rglob('*') if path.is_file() and not path.is_symlink()}
        if not files:
            continue
        if not archive.exists():
            with tarfile.open(archive, 'w:gz', compresslevel=1) as target:
                target.add(install, arcname='install')
        verified = {}
        with tarfile.open(archive) as target:
            for member in target:
                if member.isfile() or member.islnk():
                    stream=target.extractfile(member)
                    size=member.size
                    if member.islnk():
                        size=stream.seek(0,2);stream.seek(0)
                    verified[str(Path(member.name).relative_to('install'))] = (
                        size, digest_stream(stream))
        assert verified == files, 'archive does not preserve complete installed file contents'
        expected_links={str(path.relative_to(install)):str(path.readlink()) for path in install.rglob('*') if path.is_symlink()}
        with tarfile.open(archive) as target:
            archived_links={str(Path(member.name).relative_to('install')):member.linkname for member in target if member.issym()}
        assert expected_links==archived_links,'archive does not preserve installed symlinks'
        (parent / 'controller_storage.json').write_text(json.dumps({
            'archive': archive.name, 'sha256': digest_stream(archive.open('rb')),
            'expanded_file_bytes': sum(size for size, _ in files.values()),
            'files_checked': len(files), 'successful_completion_created': False,
            'reason': 'Lossless removal of redundant expanded installed files',
        }, indent=2))
        shutil.rmtree(install)
        print('SDK_LOSSLESSLY_COMPACTED', run.name, archive.name, len(files), flush=True)
    records = {}
    record_file = output / 'controller_compressed_logs.json'
    if record_file.exists():
        records = json.loads(record_file.read_text())
    for log in output.rglob('logs/*.log'):
        if log.stat().st_size < 8 << 20:
            continue
        original_size = log.stat().st_size
        with log.open('rb') as stream:
            original_hash = digest_stream(stream)
        compressed = log.with_suffix(log.suffix + '.gz')
        with log.open('rb') as source, gzip.open(compressed, 'wb', compresslevel=1) as target:
            shutil.copyfileobj(source, target, 4 << 20)
        with gzip.open(compressed, 'rb') as stream:
            assert digest_stream(stream) == original_hash
        records[str(log.relative_to(output))] = {
            'gzip': str(compressed.relative_to(output)),
            'original_bytes': original_size, 'original_sha256': original_hash,
            'compressed_sha256': digest_stream(compressed.open('rb')),
        }
        record_file.write_text(json.dumps(records, indent=2))
        log.unlink()
        print('LOG_LOSSLESSLY_COMPRESSED', run.name, log.name, original_size, flush=True)


if __name__ == '__main__':
    for task in sorted((ROOT / 'tasks').iterdir()):
        for run in sorted((task / 'runs').glob('*trial*')):
            compact(run)
