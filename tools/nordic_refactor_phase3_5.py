#!/usr/bin/env python3
"""Nordic refactoring: Phase 3-5 remaining HTML pages"""
import re, os

BASE = r"d:\文件\服务器实际运行版V4\高炉前端数据"
files = [
    f"{BASE}/frontend_dashboard.html",
    f"{BASE}/frontend_award_cockpit.html",
    f"{BASE}/ollama_direct_chat.html",
]

# Backup
for f in files:
    os.system(f'copy "{f}" "{f}.nordic-bak" >nul 2>&1')

# Common Nordic CSS variables to inject
NORDIC_VARS = """:root{--nordic-bg:#F4F6F8;--nordic-card-bg:#FFFFFF;--nordic-border:#E5E9F0;--nordic-text:#2E3440;--nordic-text-secondary:#4C566A;--nordic-text-muted:#8B929D;--nordic-accent:#5E81AC;--nordic-accent-light:#EBF3FC;--nordic-green:#A3BE8C;--nordic-green-bg:#F0F5EB;--nordic-amber:#EBCB8B;--nordic-amber-bg:#FDF6EC;--nordic-red:#BF616A;--nordic-red-bg:#F9EDEF;--nordic-cyan:#88C0D0;--nordic-font-zh:'SimSun','宋体',serif;--nordic-font-num:'JetBrains Mono','Consolas',monospace;--nordic-shadow-sm:0 1px 3px rgba(0,0,0,0.03);--nordic-shadow-md:0 4px 16px rgba(0,0,0,0.02);--nordic-radius-sm:4px;--nordic-radius-md:6px}"""

# Common dark → light color replacements
COLOR_MAP = {
    # Dark backgrounds
    '#030712':'var(--nordic-bg)','#020916':'var(--nordic-bg)','#020817':'var(--nordic-bg)',
    '#0b1116':'var(--nordic-bg)','#031225':'var(--nordic-bg)','#11181b':'var(--nordic-bg)',
    '#070706':'var(--nordic-bg)','#121416':'var(--nordic-card-bg)','#0D111A':'var(--nordic-bg)',
    '#071a31':'var(--nordic-bg)','#04111f':'var(--nordic-bg)',
    # Navy backgrounds
    '#000040':'var(--nordic-accent)','#08233f':'var(--nordic-card-bg)','#10335a':'var(--nordic-bg)',
    '#1A1A2E':'var(--nordic-card-bg)','#2A2A3E':'var(--nordic-accent-light)','#202038':'var(--nordic-bg)',
    # Neon green → sage
    '#00FF00':'var(--nordic-green)','#31d67a':'var(--nordic-green)','#2fe0b2':'var(--nordic-green)',
    '#78d47c':'var(--nordic-green)','#00FF99':'var(--nordic-green)',
    # Neon cyan → muted
    '#00FFFF':'var(--nordic-cyan)','#0FF':'var(--nordic-cyan)','#00f0ff':'var(--nordic-accent)',
    '#19c6d3':'var(--nordic-accent)',
    # Gold/amber
    '#FFD700':'var(--nordic-amber)','#ffb02f':'var(--nordic-amber)','#f4b740':'var(--nordic-amber)',
    '#ffb21b':'var(--nordic-amber)','#facc14':'var(--nordic-amber)',
    # Red
    '#FF4444':'var(--nordic-red)','#ff4f63':'var(--nordic-red)','#ff5d73':'var(--nordic-red)',
    '#ff6b5e':'var(--nordic-red)','#e95b5b':'var(--nordic-red)','#FF453A':'var(--nordic-red)',
    # Blue accents → Nordic
    '#0a84ff':'var(--nordic-accent)','#36d1ff':'var(--nordic-accent)','#26a7ff':'var(--nordic-accent)',
    '#0ea5e9':'var(--nordic-accent)','#0284c7':'var(--nordic-accent)','#12a9ff':'var(--nordic-accent)',
    '#1890ff':'var(--nordic-accent)','#106ce6':'var(--nordic-accent)',
    # Copper/orange → accent
    '#e86f28':'var(--nordic-accent)','#ff9a3c':'var(--nordic-accent)','#ff5a1f':'var(--nordic-accent)',
    # Teal
    '#48d6c2':'var(--nordic-cyan)','#2dd6e8':'var(--nordic-cyan)',
    # Light text → dark
    '#f1f7ff':'var(--nordic-text)','#dcecff':'var(--nordic-text)','#e7eef2':'var(--nordic-text)',
    '#f4efe4':'var(--nordic-text)','#fff6e5':'var(--nordic-text)','#fff4dd':'var(--nordic-text)',
    '#f4fbff':'var(--nordic-text)','#e9f5ff':'var(--nordic-text)',
    # Muted text
    '#91aed1':'var(--nordic-text-muted)','#a9bbc4':'var(--nordic-text-muted)',
    '#a6aaa6':'var(--nordic-text-muted)','#8fb2d2':'var(--nordic-text-muted)',
    # Specifics
    '#bfc8c2':'var(--nordic-text-secondary)','#B0B0B0':'var(--nordic-bg)',
    '#C0C0C0':'var(--nordic-card-bg)','#EBEBEB':'var(--nordic-card-bg)',
    '#606060':'var(--nordic-text-secondary)','#808080':'var(--nordic-text-muted)',
    '#111827':'var(--nordic-accent-light)','#4A0000':'var(--nordic-red-bg)',
    '#00AEEF':'var(--nordic-accent)','#002B5C':'var(--nordic-accent)',
    '#1d2124':'var(--nordic-card-bg)','#bfc8c2':'var(--nordic-text)',
}

def process_file(filepath):
    print(f"Processing {os.path.basename(filepath)}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Inject Nordic CSS variables after first <style>
    content = content.replace('<style>', '<style>' + NORDIC_VARS, 1)

    # 2. Apply color replacements
    for old, new in COLOR_MAP.items():
        content = content.replace(old, new)

    # 3. Remove text-shadow glow
    content = re.sub(r'text-shadow:\s*0\s+0\s+\d+px\s+rgba\([^)]+\)[^;]*;?', 'text-shadow:none;', content)
    content = re.sub(r'text-shadow:\s*0\s+0\s+\d+px\s+[^;]+;?', 'text-shadow:none;', content)

    # 4. Remove drop-shadow
    content = re.sub(r'filter:\s*drop-shadow\([^)]+\);?', '', content)

    # 5. Remove backdrop-filter
    content = re.sub(r'backdrop-filter:\s*blur\([^)]*\);?', '', content)
    content = re.sub(r'-webkit-backdrop-filter:\s*blur\([^)]*\);?', '', content)

    # 6. Remove box-shadow glow
    content = re.sub(r'box-shadow:\s*0\s+0\s+\d+px\s+rgba\([^)]+\)[^;]*;?', 'box-shadow:none;', content)

    # 7. Simplify gradients
    content = re.sub(r'background:\s*linear-gradient\([^)]*#[0-9a-fA-F]+[^)]*\)', 'background:var(--nordic-card-bg)', content)
    content = re.sub(r'background:\s*radial-gradient\([^)]+\)', 'background:transparent', content)

    # 8. Remove animations
    content = re.sub(r'@keyframes\s+blink\s*\{[^}]*\}', '', content)
    content = re.sub(r'@keyframes\s+pulse\s*\{[^}]*\}', '', content)
    content = re.sub(r'animation:\s*blink[^;]+;?', '', content)
    content = re.sub(r'animation:\s*pulse[^;]+;?', '', content)

    # 9. Normalize border-radius
    content = re.sub(r'border-radius:\s*18px', 'border-radius:6px', content)
    content = re.sub(r'border-radius:\s*12px', 'border-radius:6px', content)
    content = re.sub(r'border-radius:\s*999px', 'border-radius:6px', content)

    # 10. Replcae rgba glass backgrounds with solid
    content = re.sub(r'rgba\(8,\s*9,\s*9,\s*0\.7\)', 'var(--nordic-card-bg)', content)
    content = re.sub(r'rgba\(7,\s*28,\s*52,\s*0\.82\)', 'var(--nordic-card-bg)', content)
    content = re.sub(r'rgba\(10,\s*42,\s*75,\s*0\.86\)', 'var(--nordic-accent-light)', content)
    content = re.sub(r'rgba\(7,\s*7,\s*6,\s*0\.72\)', 'var(--nordic-card-bg)', content)

    # 11. Clean up
    content = content.replace(';;', ';')
    content = re.sub(r'filter:\s*;', '', content)
    content = re.sub(r'text-shadow:\s*;', '', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Done: {os.path.basename(filepath)}")

for f in files:
    process_file(f)

print("\nPhase 3-5 complete!")
