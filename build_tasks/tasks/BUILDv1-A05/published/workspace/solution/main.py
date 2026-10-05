#!/usr/bin/env python3
"""BUILDv1-A05: build, test and install OpenSSL (linux-x86_64) from the frozen
source archive, then independently consume the installed SDK from outside the
source tree (EVP digest/signature checks, local TLS handshake, negative cases).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from buildkit import Session, digest

PROFILE_TESTS = 'test_rsa test_dsa'
TLS_PORT = '14433'

CONSUMER_C = r'''#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/opensslv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char *slurp(const char *p, size_t *n) {
    FILE *f = fopen(p, "rb");
    unsigned char *b;
    long s;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    s = ftell(f);
    if (s < 0) { fclose(f); return NULL; }
    rewind(f);
    b = malloc((size_t)s + 1);
    if (!b) { fclose(f); return NULL; }
    if (fread(b, 1, (size_t)s, f) != (size_t)s) { fclose(f); free(b); return NULL; }
    fclose(f);
    *n = (size_t)s;
    return b;
}

int main(int argc, char **argv) {
    static const unsigned char want[32] = {
        0xb9,0x4d,0x27,0xb9,0x93,0x4d,0x3e,0x08,0xa5,0x2e,0x52,0xd7,0xda,0x7d,0xab,0xfa,
        0xc4,0x84,0xef,0xe3,0x7a,0x53,0x80,0xee,0x90,0x88,0xf7,0xac,0xe2,0xef,0xcd,0xe9};
    unsigned char md[32];
    unsigned int mdlen = 0;
    EVP_MD_CTX *c, *v;
    EVP_PKEY *pk;
    FILE *kf;
    size_t mlen = 0, slen = 0;
    unsigned char *msg, *sig;
    int ok = 0;

    printf("OpenSSL %s\n", OpenSSL_version(OPENSSL_VERSION));
    if (argc != 4) { fprintf(stderr, "usage: %s pub.pem msg sig\n", argv[0]); return 2; }

    c = EVP_MD_CTX_new();
    if (!c) return 1;
    if (EVP_DigestInit_ex(c, EVP_sha256(), NULL) != 1 ||
        EVP_DigestUpdate(c, "hello world", 11) != 1 ||
        EVP_DigestFinal_ex(c, md, &mdlen) != 1) { EVP_MD_CTX_free(c); return 1; }
    EVP_MD_CTX_free(c);
    if (mdlen != 32 || memcmp(md, want, 32) != 0) {
        fprintf(stderr, "sha256 mismatch\n");
        return 1;
    }
    printf("sha256(hello world) OK\n");

    kf = fopen(argv[1], "r");
    if (!kf) { fprintf(stderr, "no pubkey\n"); return 1; }
    pk = PEM_read_PUBKEY(kf, NULL, NULL, NULL);
    fclose(kf);
    if (!pk) { fprintf(stderr, "bad pubkey\n"); return 1; }

    msg = slurp(argv[2], &mlen);
    sig = slurp(argv[3], &slen);
    if (!msg || !sig) { EVP_PKEY_free(pk); free(msg); free(sig); return 1; }

    v = EVP_MD_CTX_new();
    if (v && EVP_DigestVerifyInit(v, NULL, EVP_sha256(), NULL, pk) == 1)
        ok = EVP_DigestVerify(v, sig, slen, msg, mlen) == 1;
    if (v) EVP_MD_CTX_free(v);
    EVP_PKEY_free(pk);
    free(msg);
    free(sig);
    if (ok) { printf("signature verify OK\n"); return 0; }
    printf("signature verify FAILED\n");
    return 1;
}
'''

TLS_SH = r'''#!/bin/bash
set -eu
INSTALL="$1"; WORK="$2"; PORT="$3"
export LD_LIBRARY_PATH="$INSTALL/lib"
export OPENSSL_CONF="$INSTALL/ssl/openssl.cnf"
O="$INSTALL/bin/openssl"
mkdir -p "$WORK"
cd "$WORK"
rm -f key.pem cert.pem server.log client.log
"$O" req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 2 -nodes \
     -subj "/CN=localhost" >/dev/null 2>&1
"$O" s_server -accept "$PORT" -cert cert.pem -key key.pem -quiet -www >server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
sleep 2
set +e
"$O" s_client -connect "127.0.0.1:$PORT" -CAfile cert.pem -servername localhost \
     -verify_return_error -no_ign_eof </dev/null >client.log 2>&1
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  echo "s_client exit $RC"
  cat client.log
  exit 1
fi
grep -Eq 'Verify return code: 0|Verification: OK' client.log
echo "TLS handshake and verification OK"
'''

HELP = """usage: main.py <command> [options]

Commands:
  doctor --input DIR                    verify source archive, tools, perl deps
  run    --input DIR --output DIR [--jobs N]
                                        configure, build_sw, official tests,
                                        install_sw/install_ssldirs, consume SDK

Profile: core  (build_sw + TESTS="test_rsa test_dsa")
"""


def version_string(src):
    data = {}
    for line in (Path(src) / 'VERSION.dat').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, val = line.split('=', 1)
            data[key.strip()] = val.strip().strip('"')
    return f"{data['MAJOR']}.{data['MINOR']}.{data['PATCH']}"


def doctor(input_dir):
    inp = Path(input_dir)
    missing = []
    man = inp / 'manifest.json'
    if not man.is_file():
        print(json.dumps({'ready': False, 'missing': ['manifest.json']}, indent=2))
        return 78
    try:
        manifest = json.loads(man.read_text())
    except Exception as exc:
        print(json.dumps({'ready': False, 'missing': [f'manifest.json:{exc}']}, indent=2))
        return 78
    src = manifest.get('source', {})
    archive = inp / src.get('filename', 'source.tar.gz')
    if not archive.is_file():
        missing.append(f'source_archive:{archive}')
    elif digest(archive) != src.get('sha256'):
        missing.append(f'source_archive_checksum_mismatch:{archive}')
    for tool in ('gcc', 'make', 'ld', 'ar', 'ranlib', 'perl', 'bash'):
        if shutil.which(tool) is None:
            missing.append(f'tool:{tool}')
    if shutil.which('perl'):
        for module in ('Test::More', 'FindBin', 'File::Copy', 'File::Compare', 'Time::Local'):
            probe = subprocess.run(['perl', '-M' + module, '-e', '1'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if probe.returncode:
                missing.append(f'perl_module:{module}')
    print(json.dumps({'ready': not missing, 'missing': missing}, indent=2))
    return 78 if missing else 0


def _consumer_binary(s, cc='gcc'):
    work = s.consumer
    work.mkdir(parents=True, exist_ok=True)
    src = work / 'consumer.c'
    src.write_text(CONSUMER_C)
    binary = work / 'consumer'
    s.run([cc, '-O2', '-Wall', '-o', str(binary), str(src),
           '-I', str(s.install / 'include'),
           '-L', str(s.install / 'lib'),
           '-lssl', '-lcrypto',
           '-Wl,-rpath,' + str(s.install / 'lib')],
          cwd=work, phase='consumer', name='compile_consumer', timeout=600)
    return binary


def _consume(s, binary, ver):
    env = {'LD_LIBRARY_PATH': str(s.install / 'lib'),
           'OPENSSL_CONF': str(s.install / 'ssl' / 'openssl.cnf')}
    o = s.install / 'bin' / 'openssl'
    msg = s.consumer / 'message.txt'
    tampered = s.consumer / 'tampered.txt'
    key = s.consumer / 'key.pem'
    pub = s.consumer / 'pub.pem'
    sig = s.consumer / 'sig.bin'
    msg.write_text('signed payload\n')
    tampered.write_text('tampered payload\n')

    s.run([str(o), 'genpkey', '-algorithm', 'RSA',
           '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
          cwd=s.consumer, phase='consumer', name='genkey', env=env)
    s.run([str(o), 'rsa', '-in', str(key), '-pubout', '-out', str(pub)],
          cwd=s.consumer, phase='consumer', name='pubout', env=env)
    s.run([str(o), 'dgst', '-sha256', '-sign', str(key), '-out', str(sig), str(msg)],
          cwd=s.consumer, phase='consumer', name='sign', env=env)

    positive = s.run([str(binary), str(pub), str(msg), str(sig)],
                     cwd=s.consumer, phase='consumer', name='consumer_verify',
                     env=env, timeout=120)
    text = positive.read_text()
    if 'signature verify OK' not in text or ver not in text:
        raise RuntimeError('positive consumer verification failed')

    neg = s.run([str(binary), str(pub), str(tampered), str(sig)],
                cwd=s.consumer, phase='consumer_negative', name='consumer_tampered',
                env=env, timeout=120, check=False)
    if 'signature verify FAILED' not in neg.read_text():
        raise RuntimeError('tampered message did not fail verification')

    tls = s.consumer / 'tls_check.sh'
    tls.write_text(TLS_SH)
    s.run(['bash', str(tls), str(s.install), str(s.consumer / 'tls_run'), TLS_PORT],
          cwd=s.consumer, phase='consumer', name='tls_handshake',
          env=env, timeout=300)

    ldd = s.run(['ldd', str(binary)], cwd=s.consumer, phase='consumer',
                name='ldd_consumer', env=env, timeout=60)
    if str(s.install / 'lib') + '/libcrypto' not in ldd.read_text():
        raise RuntimeError('consumer did not resolve libcrypto from the install prefix')

    moved = []
    for lib in sorted((s.install / 'lib').glob('libcrypto.so*')):
        hidden = lib.with_name(lib.name + '.hidden')
        lib.rename(hidden)
        moved.append((hidden, lib))
    try:
        gone = s.run([str(binary), str(pub), str(msg), str(sig)],
                     cwd=s.consumer, phase='consumer_negative',
                     name='consumer_missing_artifact', env=env, check=False, timeout=120)
        out = gone.read_text()
        if ver in out and 'signature verify OK' in out:
            raise RuntimeError('consumer succeeded after required install artifact removal')
    finally:
        for hidden, lib in moved:
            hidden.rename(lib)

    return {'tls_script': str(tls), 'positive_log': str(positive)}


def run(input_dir, output_dir, jobs):
    s = Session(input_dir, output_dir, jobs)
    s.prepare()
    ver = version_string(s.src)

    s.run([str(s.src / 'Configure'), 'linux-x86_64',
           '--prefix=' + str(s.install),
           '--openssldir=' + str(s.install / 'ssl'),
           '--libdir=lib'],
          cwd=s.build, phase='configure', name='Configure', timeout=1800)
    s.run(['make', f'-j{s.jobs}', 'build_sw'],
          cwd=s.build, phase='build', name='build_sw', timeout=10800)
    s.run(['make', 'list-tests'],
          cwd=s.build, phase='inventory', name='list-tests', timeout=300)

    s.test('official_test_rsa_and_dsa',
           ['make', f'HARNESS_JOBS={min(s.jobs, 2)}',
            'TESTS=' + PROFILE_TESTS, 'test'],
           cwd=s.build, parser='auto', timeout=7200)

    s.run(['make', 'install_sw'],
          cwd=s.build, phase='install', name='install_sw', timeout=1800)
    s.run(['make', 'install_ssldirs'],
          cwd=s.build, phase='install', name='install_ssldirs', timeout=600)

    binary = _consumer_binary(s)
    evidence = _consume(s, binary, ver)

    s.finish(features={
        'profile': s.manifest.get('profile', 'core'),
        'target': 'linux-x86_64',
        'build_target': 'build_sw',
        'official_tests': PROFILE_TESTS,
        'install_prefix': str(s.install),
        'openssl_version': ver,
        'consumer': 'EVP sha256 digest + RSA-SHA256 verify + local TLS handshake',
        'negative_cases': ['tampered_message', 'missing_install_artifact'],
        'consumer_evidence': evidence,
    })
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='main.py', description=HELP)
    sub = parser.add_subparsers(dest='command')
    p_doctor = sub.add_parser('doctor')
    p_doctor.add_argument('--input', required=True)
    p_run = sub.add_parser('run')
    p_run.add_argument('--input', required=True)
    p_run.add_argument('--output', required=True)
    p_run.add_argument('--jobs', type=int, default=4)
    if not argv:
        parser.print_help()
        return 0
    ns = parser.parse_args(argv)
    if ns.command == 'doctor':
        return doctor(ns.input)
    if ns.command == 'run':
        return run(ns.input, ns.output, ns.jobs)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
