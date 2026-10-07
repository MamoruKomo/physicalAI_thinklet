#!/usr/bin/env python3
"""Build a dependency-free Android APK using the installed Android SDK and JDK."""
import os
from pathlib import Path
import subprocess
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(os.environ.get('ANDROID_HOME', Path.home() / 'Library/Android/sdk'))
JDK = Path(os.environ.get('JAVA_HOME', '/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home'))

def run(*args):
    subprocess.run([str(x) for x in args], check=True, env={**os.environ, 'JAVA_HOME': str(JDK)})

def main():
    tools = max((SDK / 'build-tools').iterdir(), key=lambda p: tuple(int(x) for x in p.name.split('.')))
    platform = max((SDK / 'platforms').glob('android-*'), key=lambda p: int(p.name.split('-')[1]))
    android = platform / 'android.jar'
    out = ROOT / 'build/camera'
    classes, dex = out / 'classes', out / 'dex'
    if classes.exists(): shutil.rmtree(classes)
    if dex.exists(): shutil.rmtree(dex)
    classes.mkdir(parents=True, exist_ok=True); dex.mkdir(parents=True, exist_ok=True)
    sources = list((ROOT / 'thinklet/src').rglob('*.java'))
    boot = str(tools / 'core-lambda-stubs.jar') + os.pathsep + str(android)
    run(JDK / 'bin/javac', '-source', '8', '-target', '8', '-bootclasspath', boot,
        '-d', classes, *sources)
    run(tools / 'd8', '--lib', android, '--min-api', '27', '--output', dex,
        *classes.rglob('*.class'))
    unsigned = out / 'unsigned.apk'
    run(tools / 'aapt2', 'link', '-I', android, '--manifest', ROOT / 'thinklet/AndroidManifest.xml',
        '--min-sdk-version', '27', '--target-sdk-version', '28', '-o', unsigned)
    with zipfile.ZipFile(unsigned, 'a') as archive:
        archive.write(dex / 'classes.dex', 'classes.dex')
    aligned = out / 'aligned.apk'
    run(tools / 'zipalign', '-f', '4', unsigned, aligned)
    key = ROOT / '.local/debug.keystore'
    key.parent.mkdir(exist_ok=True)
    if not key.exists():
        run(JDK / 'bin/keytool', '-genkeypair', '-keystore', key, '-storepass', 'android',
            '-keypass', 'android', '-alias', 'androiddebugkey', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '10000', '-dname', 'CN=Android Debug,O=Physical AI,C=JP')
    apk = ROOT / 'build/physical-ai-camera.apk'
    run(tools / 'apksigner', 'sign', '--ks', key, '--ks-pass', 'pass:android',
        '--key-pass', 'pass:android', '--out', apk, aligned)
    run(tools / 'apksigner', 'verify', apk)
    print(apk)

if __name__ == '__main__': main()
