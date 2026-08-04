#!/usr/bin/env python3
"""Nordic refactoring: frontend_dashboard_v3.server.html"""
import re, sys

filepath = sys.argv[1] if len(sys.argv) > 1 else r"d:\文件\服务器实际运行版V4\高炉前端数据\frontend_dashboard_v3.server.html"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Processing {filepath} ({len(content)} chars)...")

# ============================================================
# 1. ADD NORDIC CSS VARIABLES at the start of the first <style>
# ============================================================
nordic_vars = """:root{--nordic-bg:#F4F6F8;--nordic-card-bg:#FFFFFF;--nordic-border:#E5E9F0;--nordic-text:#2E3440;--nordic-text-secondary:#4C566A;--nordic-text-muted:#8B929D;--nordic-accent:#5E81AC;--nordic-accent-light:#EBF3FC;--nordic-green:#A3BE8C;--nordic-green-bg:#F0F5EB;--nordic-amber:#EBCB8B;--nordic-amber-bg:#FDF6EC;--nordic-red:#BF616A;--nordic-red-bg:#F9EDEF;--nordic-cyan:#88C0D0;--nordic-font-zh:'SimSun','宋体',serif;--nordic-font-num:'JetBrains Mono','Consolas',monospace;--nordic-shadow-sm:0 1px 3px rgba(0,0,0,0.03);--nordic-shadow-md:0 4px 16px rgba(0,0,0,0.02);--nordic-radius-sm:4px;--nordic-radius-md:6px}"""

# Insert after first <style> tag
content = content.replace('<style>', '<style>' + nordic_vars, 1)

# ============================================================
# 2. COLOR REPLACEMENTS (systematic hex/rgba mapping)
# ============================================================
replacements = {
    # Backgrounds - dark navy → light
    '#020916': 'var(--nordic-bg)',
    '#020817': 'var(--nordic-bg)',
    '#030712': 'var(--nordic-bg)',
    '#020813': 'var(--nordic-bg)',
    '#0b1116': 'var(--nordic-bg)',
    '#031225': 'var(--nordic-bg)',
    '#041d3a': '#FFFFFF',
    '#041125': 'var(--nordic-bg)',

    # Panel backgrounds - glass dark → white
    'rgba(6,30,58,.96)': '#FFFFFF',
    'rgba(3,17,34,.96)': '#FFFFFF',
    'rgba(7,44,82,.95)': '#F4F6F8',
    'rgba(3,22,44,.75)': '#F4F6F8',
    'rgba(3,13,29,.96)': '#F4F6F8',
    'rgba(1,8,19,.98)': '#F4F6F8',

    # Borders - blue glow → gray
    '#0d5598': 'var(--nordic-border)',
    '#104574': 'var(--nordic-border)',
    '#15548f': 'var(--nordic-border)',

    # Accent colors - neon → muted
    '#12a9ff': 'var(--nordic-accent)',
    '#18a8ff': 'var(--nordic-accent)',
    '#0d75ff': 'var(--nordic-accent)',
    '#18d8ff': 'var(--nordic-accent)',
    '#26a7ff': 'var(--nordic-accent)',
    '#2b9cff': 'var(--nordic-accent)',
    '#0f58bd': 'var(--nordic-accent)',
    '#0a3280': 'var(--nordic-accent)',
    '#082d76': 'var(--nordic-accent)',
    '#0a6d8e': 'var(--nordic-accent)',
    '#1595be': 'var(--nordic-accent)',
    '#159bd0': 'var(--nordic-accent)',
    '#08769b': 'var(--nordic-accent)',
    '#00f0ff': 'var(--nordic-accent)',
    '#0284c7': 'var(--nordic-accent)',
    '#0ea5e9': 'var(--nordic-accent)',
    '#1a6bc0': 'var(--nordic-accent)',
    '#36a7ff': 'var(--nordic-accent)',

    # Status colors
    '#38e47a': 'var(--nordic-green)',
    '#35e66e': 'var(--nordic-green)',
    '#4bd66b': 'var(--nordic-green)',
    '#35df6c': 'var(--nordic-green)',
    '#2fc96b': 'var(--nordic-green)',
    '#43d55c': 'var(--nordic-green)',
    '#34df70': 'var(--nordic-green)',
    '#00FF99': 'var(--nordic-green)',
    '#00FF00': 'var(--nordic-green)',
    '#30D158': 'var(--nordic-green)',
    '#78d47c': 'var(--nordic-green)',
    '#2E7D32': 'var(--nordic-green)',
    '#31d67a': 'var(--nordic-green)',
    '#2fe0b2': 'var(--nordic-green)',

    '#ffb21b': 'var(--nordic-amber)',
    '#ffb22d': 'var(--nordic-amber)',
    '#ffda28': 'var(--nordic-amber)',
    '#ffb237': 'var(--nordic-amber)',
    '#FFD700': 'var(--nordic-amber)',
    '#FFB300': 'var(--nordic-amber)',
    '#ffb02f': 'var(--nordic-amber)',
    '#f4b740': 'var(--nordic-amber)',
    '#EF6C00': 'var(--nordic-amber)',
    '#ff9f0a': 'var(--nordic-amber)',

    '#ff4f63': 'var(--nordic-red)',
    '#ff4a5d': 'var(--nordic-red)',
    '#ff4b60': 'var(--nordic-red)',
    '#ff4057': 'var(--nordic-red)',
    '#ff5367': 'var(--nordic-red)',
    '#ff2a44': 'var(--nordic-red)',
    '#FF453A': 'var(--nordic-red)',
    '#FF4444': 'var(--nordic-red)',
    '#C62828': 'var(--nordic-red)',
    '#ff6b5e': 'var(--nordic-red)',
    '#ff5d73': 'var(--nordic-red)',
    '#ef6b6b': 'var(--nordic-red)',
    '#e95b5b': 'var(--nordic-red)',

    # Cyan → Nordic cyan
    '#48d6c2': 'var(--nordic-cyan)',
    '#19c6d3': 'var(--nordic-cyan)',
    '#13c2c2': 'var(--nordic-cyan)',
    '#2dd6e8': 'var(--nordic-cyan)',
    '#0FF': 'var(--nordic-cyan)',
    '#00FFFF': 'var(--nordic-cyan)',

    # Brand subtitle orange → accent
    '#ff5a1f': 'var(--nordic-accent)',
    '#e86f28': 'var(--nordic-accent)',

    # Text colors - light → dark
    '#dcecff': 'var(--nordic-text)',
    '#f1f7ff': 'var(--nordic-text)',
    '#eaf6ff': 'var(--nordic-text)',
    '#f2f8ff': 'var(--nordic-text)',
    '#f3fbff': 'var(--nordic-text)',
    '#f4fbff': 'var(--nordic-text)',
    '#eef8ff': 'var(--nordic-text)',
    '#edf8ff': 'var(--nordic-text)',
    '#f5fbff': 'var(--nordic-text)',
    '#fff': '#FFFFFF',

    # Text secondary
    '#c3d4e8': 'var(--nordic-text-secondary)',
    '#bdd3e8': 'var(--nordic-text-secondary)',
    '#cfe2f5': 'var(--nordic-text-secondary)',
    '#cfe3f6': 'var(--nordic-text-secondary)',
    '#c9ddf5': 'var(--nordic-text-secondary)',
    '#d9eaff': 'var(--nordic-text-secondary)',

    # Text muted
    '#8fb8d8': 'var(--nordic-text-muted)',
    '#8fa9c4': 'var(--nordic-text-muted)',
    '#9db8d4': 'var(--nordic-text-muted)',
    '#a8c3dd': 'var(--nordic-text-muted)',
    '#9fc3e1': 'var(--nordic-text-muted)',
    '#a9c3dc': 'var(--nordic-text-muted)',
    '#9fbdd8': 'var(--nordic-text-muted)',
    '#8aa7c5': 'var(--nordic-text-muted)',

    # sidebar/header colors
    '#000040': 'var(--nordic-accent)',
    '#003F5C': 'var(--nordic-accent)',
    '#002B5C': 'var(--nordic-accent)',
    '#111827': 'var(--nordic-accent-light)',
    '#1A1A2E': '#FFFFFF',
    '#2A2A3E': 'var(--nordic-accent-light)',
    '#202038': 'var(--nordic-bg)',
    '#4A0000': 'var(--nordic-red-bg)',
    '#00AEEF': 'var(--nordic-accent)',
    '#005BAC': 'var(--nordic-accent)',

    # Chart specific colors
    '#2f8cff': 'var(--nordic-accent)',
    '#33d15e': 'var(--nordic-green)',
    '#ffbc32': 'var(--nordic-amber)',
    '#ff4d5b': 'var(--nordic-red)',
    '#9b5cff': '#B48EAD',
    '#45d45a': 'var(--nordic-green)',
    '#7fb2ff': 'var(--nordic-accent)',
    '#ff425b': 'var(--nordic-red)',
    '#ffb000': 'var(--nordic-amber)',
}

for old, new in replacements.items():
    content = content.replace(old, new)

# ============================================================
# 3. REMOVE GLOW EFFECTS
# ============================================================
# Remove text-shadow glows
content = re.sub(r'text-shadow:\s*0\s+0\s+\d+px\s+rgba\([^)]+\)[^;]*;?', 'text-shadow:none;', content)
content = re.sub(r'text-shadow:\s*0\s+0\s+\d+px\s+[^;]+;?', 'text-shadow:none;', content)

# Remove drop-shadow filters
content = re.sub(r'filter:\s*drop-shadow\([^)]+\)\s*!important;?', '', content)
content = re.sub(r'filter:\s*drop-shadow\([^)]+\);?', '', content)

# Remove box-shadow glow on selected/active elements
content = re.sub(r'box-shadow:\s*0\s+0\s+\d+px\s+rgba\([^)]+\)[^;]*;?', 'box-shadow:none;', content)
content = re.sub(r'box-shadow:\s*0\s+0\s+\d+px\s+#[0-9a-fA-F]+[^;]*;?', 'box-shadow:none;', content)

# ============================================================
# 4. REMOVE ANIMATIONS (sweep, scan, breath, blink)
# ============================================================
content = re.sub(r'@keyframes\s+bfMetricSweep\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+bfChartScan\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+bfMicroBreath\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+blink\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+heatPulse\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+gasRise\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+moltenWave\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+pulse\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+furnaceOrbit\s*\{[^}]*\}', '', content)

# Remove animation references
content = re.sub(r'animation:\s*bfMetricSweep[^;]+;?', '', content)
content = re.sub(r'animation:\s*bfChartScan[^;]+;?', '', content)
content = re.sub(r'animation:\s*bfMicroBreath[^;]+;?', '', content)
content = re.sub(r'animation:\s*blink[^;]+;?', '', content)
content = re.sub(r'animation:\s*heatPulse[^;]+;?', '', content)
content = re.sub(r'animation:\s*gasRise[^;]+;?', '', content)
content = re.sub(r'animation:\s*moltenWave[^;]+;?', '', content)
content = re.sub(r'animation:\s*pulse[^;]+;?', '', content)
content = re.sub(r'animation:\s*furnaceOrbit[^;]+;?', '', content)

# ============================================================
# 5. REPLACE GRADIENTS WITH SOLID COLORS
# ============================================================
# linear-gradient backgrounds → solid
content = re.sub(
    r'background:\s*linear-gradient\([^)]*rgba\([0-9]+,\s*[0-9]+,\s*[0-9]+,\s*[0-9.]+\)[^)]*\)',
    'background:#FFFFFF',
    content
)
content = re.sub(
    r'background:\s*linear-gradient\([^)]*#[0-9a-fA-F]+[^)]*\)',
    'background:#FFFFFF',
    content
)

# radial-gradient backgrounds → transparent/light
content = re.sub(
    r'background:\s*radial-gradient\([^)]+\)',
    'background:transparent',
    content
)

# inset box shadows → none
content = re.sub(r'box-shadow:\s*inset[^;]+;?', 'box-shadow:none;', content)
content = re.sub(r'box-shadow:\s*[^;]*inset[^;]+;?', 'box-shadow:none;', content)

# ============================================================
# 6. NORMALIZE BORDER-RADIUS
# ============================================================
content = re.sub(r'border-radius:\s*12px', 'border-radius:6px', content)
content = re.sub(r'border-radius:\s*8px', 'border-radius:6px', content)
content = re.sub(r'border-radius:\s*18px', 'border-radius:6px', content)

# ============================================================
# 7. CHART RELATED - Update ECharts theme name references
# ============================================================
# Replace theme="bf-dark" with theme="bf-light" (bf-light already uses Nordic colors)
content = content.replace('theme:"bf-dark"', 'theme:"bf-light"')
content = content.replace("theme:'bf-dark'", "theme:'bf-light'")

# ============================================================
# 8. REMOVE bg grid pattern overlays
# ============================================================
content = re.sub(
    r'background-size:\s*\d+px\s*\d+px[^;]*;?',
    '',
    content
)

# ============================================================
# 9. CLEAN UP
# ============================================================
# Clean multiple consecutive semicolons
content = re.sub(r';;;+', ';', content)
content = content.replace(';;', ';')

# Remove empty style blocks
content = re.sub(r'<style>\s*</style>', '', content)

# Clean extra whitespace
content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)

# Remove properties with empty values
content = re.sub(r'filter:\s*;', '', content)
content = re.sub(r'text-shadow:\s*;', '', content)
content = re.sub(r'box-shadow:\s*;', '', content)
content = re.sub(r'animation:\s*;', '', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Main dashboard refactoring complete!")
print(f"Output: {len(content)} chars")
