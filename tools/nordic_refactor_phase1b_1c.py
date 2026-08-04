#!/usr/bin/env python3
"""Nordic refactoring: light-theme.css + product-shell.css"""
import re, sys

base = r"d:\文件\服务器实际运行版V4\高炉前端数据\v3-frontend-react\src\styles"

# ============================================================
# light-theme.css replacements
# ============================================================
print("Processing light-theme.css...")
with open(f"{base}/light-theme.css", 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace :root variable block
old_root = r':root\s*\{[^}]*--bg-app[^}]*--blur-radius:\s*blur\([^)]*\);\s*\}'
new_root = """:root {
  --bg-app: var(--nordic-bg);
  --bg-panel: var(--nordic-card-bg);
  --bg-panel-hover: var(--nordic-card-bg);
  --bg-nav: var(--nordic-card-bg);
  --bg-nav-active: var(--nordic-accent);

  --border-glass: 1px solid var(--nordic-border);
  --border-nav: 1px solid var(--nordic-border);

  --text-primary: var(--nordic-text);
  --text-secondary: var(--nordic-text-secondary);
  --text-muted: var(--nordic-text-muted);
  --text-accent: var(--nordic-accent);
  --text-inverse: #ffffff;

  --shadow-glass: var(--nordic-shadow-md);
  --shadow-active: none;

  --blur-radius: none;
}"""
content = re.sub(old_root, new_root, content, flags=re.DOTALL)

# 2. Remove all backdrop-filter references
content = re.sub(r'backdrop-filter:\s*var\(--blur-radius\)\s*!important;?', '', content)
content = re.sub(r'backdrop-filter:\s*var\(--blur-radius\);?', '', content)
content = re.sub(r'backdrop-filter:\s*blur\([^)]*\)\s*!important;?', '', content)
content = re.sub(r'backdrop-filter:\s*blur\([^)]*\);?', '', content)
content = re.sub(r'-webkit-backdrop-filter:\s*blur\([^)]*\);?', '', content)

# 3. Replace var(--bg-app) with var(--nordic-bg)
content = content.replace('var(--bg-app)', 'var(--nordic-bg)')
content = content.replace('var(--bg-panel)', 'var(--nordic-card-bg)')
content = content.replace('var(--bg-panel-hover)', 'var(--nordic-card-bg)')
content = content.replace('var(--bg-nav)', 'var(--nordic-card-bg)')
content = content.replace('var(--bg-nav-active)', 'var(--nordic-accent)')
content = content.replace('var(--border-glass)', '1px solid var(--nordic-border)')
content = content.replace('var(--border-nav)', '1px solid var(--nordic-border)')
content = content.replace('var(--text-primary)', 'var(--nordic-text)')
content = content.replace('var(--text-secondary)', 'var(--nordic-text-secondary)')
content = content.replace('var(--text-muted)', 'var(--nordic-text-muted)')
content = content.replace('var(--text-accent)', 'var(--nordic-accent)')
content = content.replace('var(--text-inverse)', '#fff')
content = content.replace('var(--shadow-glass)', 'var(--nordic-shadow-md)')
content = content.replace('var(--shadow-active)', 'none')
content = content.replace('var(--blur-radius)', 'none')
content = content.replace('var(--nu-glow)', 'none')

# 4. Replace any hardcoded dark colors
content = content.replace('#0f172a', 'var(--nordic-text)')
content = content.replace('#334155', 'var(--nordic-text-secondary)')
content = content.replace('#64748b', 'var(--nordic-text-muted)')
content = content.replace('#0ea5e9', 'var(--nordic-accent)')
content = content.replace('#0284c7', 'var(--nordic-accent)')

# 5. Remove border-radius > 6px
content = content.replace('border-radius: 12px', 'border-radius: var(--nordic-radius-md)')
content = content.replace('border-radius: 8px', 'border-radius: var(--nordic-radius-md)')

# 6. Remove hover transforms
content = re.sub(r'transform:\s*translateX\(4px\);?', 'transform: none;', content)
content = re.sub(r'transform:\s*translateY\(-1px\);?', 'transform: none;', content)
content = re.sub(r'transform:\s*translateX\(4px\)\s*!important;?', 'transform: none !important;', content)
content = re.sub(r'transform:\s*translateY\(-1px\)\s*!important;?', 'transform: none !important;', content)

# 7. Clean up empty properties
content = content.replace('backdrop-filter: none;', '')
content = content.replace('-webkit-backdrop-filter: none;', '')

with open(f"{base}/light-theme.css", 'w', encoding='utf-8') as f:
    f.write(content)
print("light-theme.css done")

# ============================================================
# product-shell.css replacements
# ============================================================
print("Processing product-shell.css...")
with open(f"{base}/product-shell.css", 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace :root variable block
old_product_root = r':root\s*\{[^}]*--product-bg[^}]*--product-violet[^}]*;\s*\}'
new_product_root = """:root {
  --product-bg: var(--nordic-bg);
  --product-bg-soft: var(--nordic-bg);
  --product-panel: var(--nordic-card-bg);
  --product-panel-strong: var(--nordic-card-bg);
  --product-line: var(--nordic-border);
  --product-line-hot: var(--nordic-accent);
  --product-text: var(--nordic-text);
  --product-muted: var(--nordic-text-muted);
  --product-cyan: var(--nordic-cyan);
  --product-green: var(--nordic-green);
  --product-amber: var(--nordic-amber);
  --product-red: var(--nordic-red);
  --product-violet: var(--nordic-accent);
}"""
content = re.sub(old_product_root, new_product_root, content, flags=re.DOTALL)

# 2. Remove backdrop-filter references in product-shell
content = re.sub(r'backdrop-filter:\s*blur\([^)]*\)\s*!important;?', '', content)
content = re.sub(r'backdrop-filter:\s*blur\([^)]*\);?', '', content)
content = re.sub(r'-webkit-backdrop-filter:\s*blur\([^)]*\);?', '', content)

# 3. Replace box-shadows with Nordic versions
# Remove inset glow shadows
content = re.sub(r'box-shadow:\s*inset[^;]+;\s*', 'box-shadow: none;', content)
content = re.sub(r'box-shadow:\s*0\s+\d+px\s+\d+px\s+rgba\(0,\s*0,\s*0,\s*0\.\d+\)[^;]*;', 'box-shadow: var(--nordic-shadow-md);', content)

# 4. Replace linear-gradient backgrounds with solid colors
content = re.sub(
    r'background:\s*linear-gradient\(180deg,\s*var\(--product-panel\)[^)]*\)\s*!important;',
    'background: var(--nordic-card-bg) !important;',
    content
)
content = re.sub(
    r'background:\s*linear-gradient\([^)]*var\(--product-[^)]+\)[^)]*\)',
    'background: var(--nordic-card-bg)',
    content
)

# 5. Simplify borders
content = re.sub(
    r'border:\s*1px solid var\(--product-line\)',
    'border: 1px solid var(--nordic-border)',
    content
)
content = re.sub(
    r'border-bottom:\s*1px solid var\(--product-line\)',
    'border-bottom: 1px solid var(--nordic-border)',
    content
)

# 6. Replace any remaining hex colors with Nordic tokens
replacements = {
    '#0b1116': 'var(--nordic-bg)',
    '#111b22': 'var(--nordic-bg)',
    '#e7eef2': 'var(--nordic-text)',
    '#a9bbc4': 'var(--nordic-text-muted)',
    '#19c6d3': 'var(--nordic-accent)',
    '#2fe0b2': 'var(--nordic-green)',
    '#f4b740': 'var(--nordic-amber)',
    '#e95b5b': 'var(--nordic-red)',
}
for old, new in replacements.items():
    content = content.replace(old, new)

# 7. Clean any double semicolons
content = content.replace(';;', ';')

with open(f"{base}/product-shell.css", 'w', encoding='utf-8') as f:
    f.write(content)
print("product-shell.css done")
print("Phase 1B-C complete!")
