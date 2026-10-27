"""Fetch pinned HugeRTE assets and the compatible French community translation."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / 'static' / 'vendor' / 'hugerte'


def package(name, version):
    with urlopen(f'https://registry.npmjs.org/{name}/{version}', timeout=30) as response:
        metadata = json.load(response)
    with urlopen(metadata['dist']['tarball'], timeout=30) as response:
        data = response.read()
    algorithm, expected = metadata['dist']['integrity'].split('-', 1)
    actual = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if actual != expected:
        raise ValueError('Package integrity check failed')
    return metadata, tarfile.open(fileobj=io.BytesIO(data), mode='r:gz')


def main():
    metadata, archive = package('hugerte', '1.0.14')
    ROOT.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in archive.getmembers():
        if not item.isfile() or not item.name.startswith('package/'):
            continue
        relative = Path(item.name[len('package/'):])
        if '..' in relative.parts or relative.is_absolute():
            raise ValueError('Invalid package path')
        # Keep runtime files and licenses, without duplicate unminified scripts.
        if relative.suffix == '.js' and not relative.name.endswith('.min.js'):
            continue
        if relative.suffix in ('.map', '.ts'):
            continue
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(item).read())
        count += 1
    translation, languages = package('tinymce-i18n', '26.10.19')
    raw = languages.extractfile('package/langs6/fr_FR.js').read().decode('utf-8')
    (ROOT / 'langs').mkdir(exist_ok=True)
    (ROOT / 'langs' / 'fr_FR.js').write_text(raw.replace('tinymce.addI18n', 'hugerte.addI18n'), encoding='utf-8')
    for item in languages.getmembers():
        if item.isfile() and Path(item.name).name.lower().startswith('license'):
            (ROOT / ('language-' + Path(item.name).name)).write_bytes(languages.extractfile(item).read())
    (ROOT / 'SOURCES.json').write_text(json.dumps({
        'hugerte': {'version': metadata['version'], 'integrity': metadata['dist']['integrity']},
        'tinymce-i18n': {'version': translation['version'], 'integrity': translation['dist']['integrity'],
                        'file': 'langs6/fr_FR.js', 'adaptation': 'tinymce.addI18n renamed to hugerte.addI18n'},
    }, indent=2), encoding='utf-8')
    print(f'HugeRTE {metadata["version"]}: {count} runtime assets; French translation {translation["version"]}')


if __name__ == '__main__':
    main()
