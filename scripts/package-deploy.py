"""Create source-only deployment bundle. Excludes secrets, teacher data and environments."""
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'dist-deploy'
out.mkdir(exist_ok=True)
files = ['server', 'web', 'gpu', 'scripts', 'deploy', 'docs', 'tests', 'README.md',
         'pyproject.toml', 'uv.lock', 'package.json', 'package-lock.json', 'tsconfig.json',
         'vite.config.ts', 'index.html', '.env.example', 'Dockerfile', 'compose.yaml', '.dockerignore']
with tarfile.open(out / 'teacher-studio-source.tar.gz', 'w:gz') as archive:
    for entry in files:
        path = root / entry
        paths = [path] if path.is_file() else sorted(path.rglob('*'))
        for p in paths:
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.suffix=='.pyc':
                continue
            archive.add(p, arcname='teacher-studio/'+str(p.relative_to(root)), recursive=False)
print(out / 'teacher-studio-source.tar.gz')
