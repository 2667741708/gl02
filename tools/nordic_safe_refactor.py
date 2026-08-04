#!/usr/bin/env python3
"""Nordic refactoring - SAFE color-only approach. No structural changes to CSS."""
import re

BASE = r"d:\文件\服务器实际运行版V4\高炉前端数据\v3-frontend-react\src\styles"

NORDIC_VARS = ":root{--nb:#F4F6F8;--nc:#FFFFFF;--ne:#E5E9F0;--nt:#2E3440;--nt2:#4C566A;--ntm:#8B929D;--na:#5E81AC;--nal:#EBF3FC;--ng:#A3BE8C;--nam:#EBCB8B;--nr:#BF616A;--ncy:#88C0D0;--ns:0 4px 16px rgba(0,0,0,0.02);--nr4:4px;--nr6:6px}"

# Safe color map - only actual color values, no structural CSS
SAFE_COLORS = {
    # Backgrounds
    '#020916': 'var(--nb)', '#020817': 'var(--nb)', '#030712': 'var(--nb)',
    '#020813': 'var(--nb)', '#0b1116': 'var(--nb)', '#031225': 'var(--nb)',
    '#0D111A': 'var(--nb)', '#070706': 'var(--nb)', '#11181b': 'var(--nb)',

    # Cards/panels
    '#1d2124': 'var(--nc)', '#121416': 'var(--nc)',

    # Text primary
    '#dcecff': 'var(--nt)', '#f1f7ff': 'var(--nt)', '#eaf6ff': 'var(--nt)',
    '#f2f8ff': 'var(--nt)', '#f3fbff': 'var(--nt)', '#f4fbff': 'var(--nt)',
    '#eef8ff': 'var(--nt)', '#edf8ff': 'var(--nt)', '#f5fbff': 'var(--nt)',
    '#f0f7ff': 'var(--nt)', '#e9f5ff': 'var(--nt)', '#f8fcff': 'var(--nt)',
    '#f7fbff': 'var(--nt)', '#d9edff': 'var(--nt)', '#f4fbff': 'var(--nt)',

    # Text secondary
    '#c3d4e8': 'var(--nt2)', '#bdd3e8': 'var(--nt2)', '#cfe2f5': 'var(--nt2)',
    '#cfe3f6': 'var(--nt2)', '#c9ddf5': 'var(--nt2)', '#d9eaff': 'var(--nt2)',
    '#d9ecff': 'var(--nt2)', '#d7e9fb': 'var(--nt2)', '#d8e9fb': 'var(--nt2)',
    '#dbeaff': 'var(--nt2)', '#c6dbf1': 'var(--nt2)', '#c4d9ee': 'var(--nt2)',
    '#c8dcef': 'var(--nt2)', '#c6d9ee': 'var(--nt2)',

    # Text muted
    '#8fb8d8': 'var(--ntm)', '#8fa9c4': 'var(--ntm)', '#9db8d4': 'var(--ntm)',
    '#a8c3dd': 'var(--ntm)', '#9fc3e1': 'var(--ntm)', '#a9c3dc': 'var(--ntm)',
    '#9fbdd8': 'var(--ntm)', '#8aa7c5': 'var(--ntm)', '#9abbd8': 'var(--ntm)',
    '#8fb4d5': 'var(--ntm)', '#94b9d8': 'var(--ntm)', '#aac9e7': 'var(--ntm)',
    '#a9c3dc': 'var(--ntm)', '#adc8df': 'var(--ntm)', '#b5c9cf': 'var(--ntm)',
    '#96bddb': 'var(--ntm)', '#94b4d0': 'var(--ntm)', '#9fc5e6': 'var(--ntm)',
    '#a8c8e4': 'var(--ntm)', '#9fb8d4': 'var(--ntm)', '#abc8e4': 'var(--ntm)',

    # Accent blue → Nordic muted blue
    '#12a9ff': 'var(--na)', '#18a8ff': 'var(--na)', '#0d75ff': 'var(--na)',
    '#18d8ff': 'var(--na)', '#26a7ff': 'var(--na)', '#2b9cff': 'var(--na)',
    '#0f58bd': 'var(--na)', '#0a3280': 'var(--na)', '#082d76': 'var(--na)',
    '#0a84ff': 'var(--na)', '#36d1ff': 'var(--na)', '#0ea5e9': 'var(--na)',
    '#0284c7': 'var(--na)', '#106ce6': 'var(--na)', '#1890ff': 'var(--na)',
    '#0a6d8e': 'var(--na)', '#1595be': 'var(--na)', '#159bd0': 'var(--na)',
    '#08769b': 'var(--na)', '#1a6bc0': 'var(--na)', '#36a7ff': 'var(--na)',
    '#1877df': 'var(--na)', '#47b7ff': 'var(--na)', '#176ac5': 'var(--na)',
    '#0b74ff': 'var(--na)', '#1580ef': 'var(--na)', '#126bd8': 'var(--na)',
    '#1267d6': 'var(--na)', '#074ba8': 'var(--na)', '#073887': 'var(--na)',
    '#083a8d': 'var(--na)', '#0f58bd': 'var(--na)',

    # Cyan → Nordic cyan
    '#00f0ff': 'var(--ncy)', '#00FFFF': 'var(--ncy)', '#0FF': 'var(--ncy)',
    '#19c6d3': 'var(--ncy)', '#48d6c2': 'var(--ncy)', '#13c2c2': 'var(--ncy)',
    '#2dd6e8': 'var(--ncy)', '#66ddff': 'var(--ncy)', '#14c8ff': 'var(--ncy)',
    '#1ecbff': 'var(--ncy)', '#1fd2ff': 'var(--ncy)', '#56d6e8': 'var(--ncy)',
    '#17c3ff': 'var(--ncy)', '#19c8ff': 'var(--ncy)', '#22d8ff': 'var(--ncy)',
    '#0bb6ff': 'var(--ncy)', '#56d6e8': 'var(--ncy)',

    # Green → Nordic sage
    '#38e47a': 'var(--ng)', '#35e66e': 'var(--ng)', '#4bd66b': 'var(--ng)',
    '#35df6c': 'var(--ng)', '#2fc96b': 'var(--ng)', '#43d55c': 'var(--ng)',
    '#34df70': 'var(--ng)', '#00FF99': 'var(--ng)', '#00FF00': 'var(--ng)',
    '#30D158': 'var(--ng)', '#78d47c': 'var(--ng)', '#2E7D32': 'var(--ng)',
    '#31d67a': 'var(--ng)', '#2fe0b2': 'var(--ng)', '#33d15e': 'var(--ng)',
    '#45d45a': 'var(--ng)', '#4bd66b': 'var(--ng)', '#35d85d': 'var(--ng)',

    # Amber/Gold → Nordic amber
    '#ffb21b': 'var(--nam)', '#ffb22d': 'var(--nam)', '#ffda28': 'var(--nam)',
    '#ffb237': 'var(--nam)', '#FFD700': 'var(--nam)', '#FFB300': 'var(--nam)',
    '#ffb02f': 'var(--nam)', '#f4b740': 'var(--nam)', '#EF6C00': 'var(--nam)',
    '#ff9f0a': 'var(--nam)', '#facc14': 'var(--nam)', '#ffbc32': 'var(--nam)',
    '#ffa500': 'var(--nam)', '#ffb000': 'var(--nam)', '#ffb323': 'var(--nam)',
    '#ffc42f': 'var(--nam)', '#ffcb40': 'var(--nam)', '#ffba22': 'var(--nam)',

    # Red → Nordic red
    '#ff4f63': 'var(--nr)', '#ff4a5d': 'var(--nr)', '#ff4b60': 'var(--nr)',
    '#ff4057': 'var(--nr)', '#ff5367': 'var(--nr)', '#ff2a44': 'var(--nr)',
    '#FF453A': 'var(--nr)', '#FF4444': 'var(--nr)', '#C62828': 'var(--nr)',
    '#ff6b5e': 'var(--nr)', '#ff5d73': 'var(--nr)', '#ef6b6b': 'var(--nr)',
    '#e95b5b': 'var(--nr)', '#ff4d5b': 'var(--nr)', '#ff425b': 'var(--nr)',
    '#ef4444': 'var(--nr)', '#f04864': 'var(--nr)', '#ff475d': 'var(--nr)',

    # Brand subtitle orange → accent
    '#ff5a1f': 'var(--na)', '#e86f28': 'var(--na)', '#ff9a3c': 'var(--na)',

    # Specific component colors
    '#000040': 'var(--na)',
    '#111827': 'var(--nal)',
    '#4A0000': 'rgba(191,97,106,0.15)',
    '#00AEEF': 'var(--na)',
    '#002B5C': 'var(--na)',
    '#003F5C': 'var(--na)',
    '#005BAC': 'var(--na)',
    '#B0B0B0': 'var(--nb)',
    '#C0C0C0': 'var(--nc)',
    '#EBEBEB': 'var(--nc)',
    '#606060': 'var(--nt2)',
    '#808080': 'var(--ntm)',
    '#bfc8c2': 'var(--nt)',
    '#a6aaa6': 'var(--ntm)',
    '#f4efe4': 'var(--nt)',
    '#fff6e5': 'var(--nt)',
    '#fff4dd': 'var(--nt)',
    '#e7eef2': 'var(--nt)',
    '#91aed1': 'var(--ntm)',
    '#a9bbc4': 'var(--ntm)',
    '#0b1116': 'var(--nb)',
    '#071a31': 'var(--nb)',
    '#04111f': 'var(--nb)',
    '#08233f': 'var(--nc)',
    '#10335a': 'var(--nb)',
    '#1A1A2E': 'var(--nc)',
    '#2A2A3E': 'var(--nal)',
    '#202038': 'var(--nb)',
}

def process_css(filepath):
    print(f"Processing {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add Nordic variables after first <style> or at start of :root
    if '<style>' in content:
        content = content.replace('<style>', '<style>' + NORDIC_VARS, 1)
    elif ':root' in content:
        # For CSS files without <style> tags, add after :root block start
        content = content.replace(':root{', ':root{' + NORDIC_VARS.replace(':root{',''), 1)

    # 2. Apply safe color replacements
    count = 0
    for old, new in SAFE_COLORS.items():
        if old in content:
            content = content.replace(old, new)
            count += 1

    print(f"  {count} color replacements made")

    # 3. Remove text-shadow glow (safe pattern)
    content = re.sub(r'text-shadow:\s*0\s+0\s+\d+px\s+rgba\([^)]+\)[^;]*;', 'text-shadow:none;', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

# Process all three CSS files
for fname in ['global.css', 'light-theme.css', 'product-shell.css']:
    process_css(f"{BASE}/{fname}")

print("Done - safe color refactoring complete")
