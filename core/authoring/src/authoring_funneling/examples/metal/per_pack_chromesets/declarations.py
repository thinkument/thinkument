"""One declaration per generated Metal chrome pack."""
from dataclasses import dataclass
from pathlib import Path
import re

@dataclass(frozen=True)
class ChromeRow:
    id: str
    chrome_id: str
    label: str
    aesthetics: str
    browser_asset_root: str


CHROMETABLES = (
    ChromeRow('metal_standard','standard','Standard','standard','standard'),
    ChromeRow('metal_compact','compact','Compact','compact','compact'),
)
DEFAULT_CHROME = 'metal_standard'


def chrome_rows():
    rows = {}
    chrome_ids = set()
    for row in CHROMETABLES:
        if row.id in rows:
            raise ValueError(f'Duplicate chrome {row.id!r}.')
        if not row.chrome_id or row.chrome_id in chrome_ids:
            raise ValueError(f'Duplicate or empty chrome ID {row.chrome_id!r}.')
        if not re.fullmatch(r'[a-z][a-z0-9_]*', row.aesthetics):
            raise ValueError('Chrome aesthetic module must be a literal module name.')
        if not re.fullmatch(r'[a-z][a-z0-9_]*', row.browser_asset_root):
            raise ValueError('Chrome browser asset roots must be literal directory names.')
        for suffix in ('js','css'):
            if not (Path(__file__).parent/row.browser_asset_root/('aesthetics.js' if suffix == 'js' else 'styles.css')).is_file():
                raise ValueError(f'Missing aesthetics asset for {row.id!r}.')
        rows[row.id] = row
        chrome_ids.add(row.chrome_id)
    return rows


