#!/usr/bin/env python3
"""Write or verify SHA-256 for the task pack's published files."""
import argparse
import hashlib
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--verify',action='store_true')
    a=p.parse_args(); root=a.root.resolve(); checksum=root/'CHECKSUMS.sha256'
    paths=sorted(x for x in root.rglob('*') if x.is_file() and x!=checksum and '__pycache__' not in x.parts and x.suffix!='.pyc')
    actual={str(x.relative_to(root)):digest(x) for x in paths}
    if a.verify:
        expected={line.split('  ',1)[1]:line.split('  ',1)[0] for line in checksum.read_text().splitlines() if line}
        errors=sorted(key for key in set(actual)|set(expected) if actual.get(key)!=expected.get(key))
        if errors:
            print('MISMATCH: '+', '.join(errors)); raise SystemExit(1)
        print(f'Verified {len(actual)} files.')
    else:
        checksum.write_text(''.join(f'{value}  {key}\n' for key,value in actual.items()),encoding='utf-8')
        print(f'Wrote {len(actual)} file checksums.')


if __name__=='__main__':
    main()
