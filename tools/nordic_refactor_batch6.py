#!/usr/bin/env python3
"""Apply Nordic theme batch 6: visual depth block, animations, flat styles"""
import re
import sys

filepath = sys.argv[1] if len(sys.argv) > 1 else r"d:\文件\服务器实际运行版V4\高炉前端数据\v3-frontend-react\src\styles\global.css"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the visual depth .app block
content = re.sub(
    r'\/\*\s*1\.\s*Cyber-mesh\s*backdrop.*?\*/\s*\.app\s*\{[^}]*\}',
    '/* 1. Nordic Flat Backdrop */\n.app {\n  background: var(--nordic-bg) !important;\n}',
    content,
    flags=re.DOTALL
)

# 2. Replace glassmorphic panel block
content = re.sub(
    r'\/\*\s*2\.\s*Glassmorphic\s*Tactile\s*Panels.*?\*/\s*\.panel\s*\{[^}]*\}',
    '/* 2. Nordic Flat Panels */\n.panel {\n  border: 1px solid var(--nordic-border) !important;\n  border-radius: var(--nordic-radius-md) !important;\n  background: var(--nordic-card-bg) !important;\n  box-shadow: var(--nordic-shadow-md) !important;\n  position: relative !important;\n  transition: border-color 0.3s ease, box-shadow 0.3s ease !important;\n}',
    content,
    flags=re.DOTALL
)

# 3. Remove backdrop-filter from any remaining occurrences
content = content.replace('backdrop-filter: blur(12px) !important;', '')
content = content.replace('backdrop-filter: blur(8px);', '')

# 4. Reduce corner bracket thickness (3px -> 2px)
content = content.replace(
    'border-top: 3px solid var(--nordic-accent)',
    'border-top: 2px solid var(--nordic-accent)'
)
content = content.replace(
    'border-left: 3px solid var(--nordic-accent)',
    'border-left: 2px solid var(--nordic-accent)'
)
content = content.replace(
    'border-bottom: 3px solid var(--nordic-accent)',
    'border-bottom: 2px solid var(--nordic-accent)'
)
content = content.replace(
    'border-right: 3px solid var(--nordic-accent)',
    'border-right: 2px solid var(--nordic-accent)'
)

# 5. Panel-head glowing strip -> flat
content = re.sub(
    r'\.panel-head\s*\{[^}]*height:\s*38px[^}]*\}',
    '.panel-head {\n  height: 36px !important;\n  background: var(--nordic-bg) !important;\n  border-bottom: 1px solid var(--nordic-border) !important;\n  box-shadow: none !important;\n}',
    content,
    flags=re.DOTALL
)

# Remove the comment preceding panel-head if still there
content = content.replace(
    '/* Panel Header Glowing Strip / 面板头部高光渐变与霓虹发光 */',
    '/* Panel Header Flat */'
)

# 6. Panel-title text-shadow -> none
content = re.sub(
    r'(\.panel-title\s*\{[^}]*?)text-shadow:\s*[^;]+;',
    r'\1text-shadow: none !important;',
    content
)

# 7. Panel-title:before text-shadow -> none
content = re.sub(
    r'(\.panel-title:before\s*\{[^}]*?)text-shadow:\s*[^;]+;',
    r'\1text-shadow: none !important;',
    content
)

# 8. Sleek row lists -> flat
content = re.sub(
    r'\.metric-row,\s*\.diag-rank-card,\s*\.score-row,\s*\.rule-hit,\s*\.qa-rule-row,\s*\.qa-var-row,\s*\.chronos-row\s*\{[^}]*\}',
    '.metric-row, .diag-rank-card, .score-row, .rule-hit, .qa-rule-row, .qa-var-row, .chronos-row {\n  border: 1px solid var(--nordic-border) !important;\n  border-left: 3px solid var(--nordic-accent) !important;\n  border-radius: var(--nordic-radius-sm) !important;\n  background: var(--nordic-card-bg) !important;\n  box-shadow: none !important;\n  transition: border-color 0.2s ease !important;\n}',
    content,
    flags=re.DOTALL
)

# 9. Row hover -> simple
content = re.sub(
    r'\.metric-row:hover,\s*\.diag-rank-card:hover,\s*\.score-row:hover,\s*\.rule-hit:hover,\s*\.qa-rule-row:hover,\s*\.qa-var-row:hover,\s*\.chronos-row:hover\s*\{[^}]*\}',
    '.metric-row:hover, .diag-rank-card:hover, .score-row:hover, .rule-hit:hover, .qa-rule-row:hover, .qa-var-row:hover, .chronos-row:hover {\n  border-color: var(--nordic-accent) !important;\n  border-left-color: var(--nordic-accent) !important;\n  background: var(--nordic-accent-light) !important;\n  box-shadow: none !important;\n  transform: none !important;\n}',
    content,
    flags=re.DOTALL
)

# 10. Glassmorphic info cards -> flat
content = re.sub(
    r'\.temp-card,\s*\.state-card,\s*\.suggest-card,\s*\.action-card,\s*\.category,\s*\.qa-response,\s*\.qa-case,\s*\.flow-box\s*\{[^}]*\}',
    '.temp-card, .state-card, .suggest-card, .action-card, .category, .qa-response, .qa-case, .flow-box {\n  border: 1px solid var(--nordic-border) !important;\n  background: var(--nordic-card-bg) !important;\n  box-shadow: var(--nordic-shadow-sm) !important;\n}',
    content,
    flags=re.DOTALL
)

# 11. Glowing values -> flat
content = re.sub(
    r'\.metric-value,\s*\.chronos-value,\s*\.score-val,\s*\.diag-rank-value\s*\{[^}]*\}',
    '.metric-value, .chronos-value, .score-val, .diag-rank-value {\n  color: var(--nordic-text) !important;\n  text-shadow: none !important;\n}',
    content,
    flags=re.DOTALL
)

# 12. Metric dot glow -> none
content = re.sub(
    r'\.metric-dot\s*\{[^}]*box-shadow[^}]*\}',
    '.metric-dot {\n  box-shadow: none !important;\n  border: none !important;\n}',
    content,
    flags=re.DOTALL
)

# 13. Nav-btn 3D -> flat
content = re.sub(
    r'\.nav-btn\s*\{[^}]*background:\s*linear-gradient[^}]*\}',
    '.nav-btn {\n  background: var(--nordic-card-bg) !important;\n  border: 1px solid var(--nordic-border) !important;\n  border-radius: var(--nordic-radius-md) !important;\n  color: var(--nordic-text-secondary) !important;\n  transition: border-color 0.2s ease, background 0.2s ease !important;\n}',
    content,
    flags=re.DOTALL
)

# Nav-btn hover
content = re.sub(
    r'\.nav-btn:hover\s*\{[^}]*\}',
    '.nav-btn:hover {\n  border-color: var(--nordic-accent) !important;\n  color: var(--nordic-text) !important;\n  box-shadow: none !important;\n  transform: none !important;\n}',
    content
)

# Nav-btn active
content = re.sub(
    r'\.nav-btn\.active\s*\{[^}]*\}',
    '.nav-btn.active {\n  background: var(--nordic-accent) !important;\n  border-color: var(--nordic-accent) !important;\n  border-top: none !important;\n  color: #fff !important;\n  box-shadow: none !important;\n}',
    content
)

# 14. Seg/forecast/ask buttons -> flat
content = re.sub(
    r'\.seg button,\s*\.forecast-btn,\s*\.ask-btn\s*\{[^}]*\}',
    '.seg button, .forecast-btn, .ask-btn {\n  background: var(--nordic-card-bg) !important;\n  border: 1px solid var(--nordic-border) !important;\n  border-radius: var(--nordic-radius-sm) !important;\n  transition: border-color 0.2s ease !important;\n  color: var(--nordic-text-secondary) !important;\n}',
    content
)

content = re.sub(
    r'\.seg button:hover,\s*\.forecast-btn:hover,\s*\.ask-btn:hover\s*\{[^}]*\}',
    '.seg button:hover, .forecast-btn:hover, .ask-btn:hover {\n  border-color: var(--nordic-accent) !important;\n  box-shadow: none !important;\n}',
    content
)

content = re.sub(
    r'\.seg button\.active\s*\{[^}]*\}',
    '.seg button.active {\n  background: var(--nordic-accent) !important;\n  border-color: var(--nordic-accent) !important;\n  box-shadow: none !important;\n  color: #fff !important;\n}',
    content
)

# 15. Input fields -> flat
content = re.sub(
    r'textarea,\s*\.chat-input\s*\{[^}]*\}',
    'textarea, .chat-input {\n  background: var(--nordic-card-bg) !important;\n  border: 1px solid var(--nordic-border) !important;\n  box-shadow: none !important;\n  transition: border-color 0.2s ease !important;\n}',
    content
)

content = re.sub(
    r'textarea:focus,\s*\.chat-input:focus\s*\{[^}]*\}',
    'textarea:focus, .chat-input:focus {\n  border-color: var(--nordic-accent) !important;\n  box-shadow: none !important;\n}',
    content
)

# 16. Fix scrollbar (had syntax error before)
content = re.sub(
    r'::-webkit-scrollbar-thumb\s*\{[^}]*\}',
    '::-webkit-scrollbar-thumb {\n  background: var(--nordic-accent) !important;\n  border-radius: 4px !important;\n}',
    content
)

# 17. Remove @keyframes animations
content = re.sub(r'@keyframes\s+pulse-alarm\s*\{[^}]*\}', '', content)
content = re.sub(r'@keyframes\s+text-pulse-alarm\s*\{[^}]*\}', '', content)

# 18. Remove animation from .bad
content = re.sub(
    r'\.bad,\s*\.text-bad\s*\{[^}]*animation:\s*text-pulse-alarm[^}]*\}',
    '.bad, .text-bad {\n  color: var(--nordic-red) !important;\n  font-weight: 900 !important;\n}',
    content
)

# 19. Remove animation from .metric-dot.bad
content = re.sub(
    r'\.metric-dot\.bad\s*\{[^}]*animation:\s*pulse-alarm[^}]*\}',
    '.metric-dot.bad {\n  background: var(--nordic-red) !important;\n}',
    content
)

# 20. Handle remaining #ff5a1f brand subtitle color
content = content.replace('#ff5a1f', 'var(--nordic-accent)')

# 21. Handle #bfe8ff (light blue text used in focus-principle)
content = content.replace('#bfe8ff', 'var(--nordic-text-secondary)')

# 22. Handle #74a8d0 (muted blue used in opt-empty)
content = content.replace('#74a8d0', 'var(--nordic-text-muted)')

# 23. Handle #cfe4fb (replay-status color)
content = content.replace('#cfe4fb', 'var(--nordic-text-secondary)')
content = content.replace('#f3fbff', 'var(--nordic-text)')

# 24. Handle #27b9ff (action-card primary border)
content = content.replace('#27b9ff', 'var(--nordic-accent)')

# 25. Remove any empty @keyframes blocks and extra blank lines
content = re.sub(r'@keyframes\s+\w+\s*\{\s*\}', '', content)
content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Batch 6 complete - visual depth block refactored")
