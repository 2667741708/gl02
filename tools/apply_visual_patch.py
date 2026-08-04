#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Based on Git version: a6e4855bae0b00669c5b4820b9972ce98f0194f6
Automatically injects the visual depth styling override into the HTML file.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"

CSS_PATCH = """
/*
Based on Git version: a6e4855bae0b00669c5b4820b9972ce98f0194f6
Visual depth and atmospheric visual enhancement (Bilingual commentary)
基于 a6e4855bae0b00669c5b4820b9972ce98f0194f6 版本的视觉立体深度与大气科技大屏感样式重构与增强
*/

/* 1. Cyber-mesh backdrop / 科技背景与矩阵网格 */
.app {
  background: radial-gradient(circle at 50% 0%, rgba(24, 144, 255, 0.15) 0%, transparent 60%),
              radial-gradient(circle at 10% 40%, rgba(0, 240, 255, 0.03) 0%, transparent 40%),
              radial-gradient(circle at 90% 80%, rgba(255, 82, 82, 0.02) 0%, transparent 40%),
              linear-gradient(90deg, rgba(20, 110, 240, 0.025) 1px, transparent 1px),
              linear-gradient(0deg, rgba(20, 110, 240, 0.025) 1px, transparent 1px),
              #030712 !important;
  background-size: 100% 100%, 100% 100%, 100% 100%, 44px 44px, 44px 44px, 100% 100% !important;
}

/* 2. Glassmorphic Tactile Panels / 面板玻璃态与双层投影 */
.panel {
  border: 1px solid rgba(0, 160, 255, 0.45) !important;
  border-radius: 8px !important;
  background: linear-gradient(180deg, rgba(8, 25, 48, 0.88) 0%, rgba(3, 12, 24, 0.94) 100%) !important;
  backdrop-filter: blur(12px) !important;
  box-shadow: inset 0 0 24px rgba(0, 150, 255, 0.12), 0 12px 30px rgba(0, 0, 0, 0.65) !important;
  position: relative !important;
  transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}

/* High-tech Corner Brackets for Panel / 高清面板定位角标 */
.panel::before {
  content: "" !important;
  position: absolute !important;
  top: -1px !important;
  left: -1px !important;
  width: 12px !important;
  height: 12px !important;
  border-top: 3px solid #00f0ff !important;
  border-left: 3px solid #00f0ff !important;
  border-top-left-radius: 6px !important;
  pointer-events: none !important;
  z-index: 5 !important;
}
.panel::after {
  content: "" !important;
  position: absolute !important;
  bottom: -1px !important;
  right: -1px !important;
  width: 12px !important;
  height: 12px !important;
  border-bottom: 3px solid #00f0ff !important;
  border-right: 3px solid #00f0ff !important;
  border-bottom-right-radius: 6px !important;
  pointer-events: none !important;
  z-index: 5 !important;
}

/* Panel Header Glowing Strip / 面板头部高光渐变与霓虹发光 */
.panel-head {
  height: 38px !important;
  background: linear-gradient(90deg, rgba(16, 52, 94, 0.9) 0%, rgba(5, 23, 48, 0.5) 100%) !important;
  border-bottom: 1px solid rgba(0, 240, 255, 0.3) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 2px 8px rgba(0, 0, 0, 0.4) !important;
}

.panel-title {
  font-size: 15px !important;
  color: #f1f8ff !important;
  letter-spacing: 0.6px !important;
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.5) !important;
}

.panel-title:before {
  color: #00f0ff !important;
  text-shadow: 0 0 12px rgba(0, 240, 255, 0.95) !important;
  font-size: 14px !important;
  margin-right: 6px !important;
}

/* 3. Sleek Row Lists & Metric Cards / 极细发光线条及列表行触感 */
.metric-row, .diag-rank-card, .score-row, .rule-hit, .qa-rule-row, .qa-var-row, .chronos-row {
  border: 1px solid rgba(0, 160, 255, 0.3) !important;
  border-left: 4px solid rgba(0, 140, 255, 0.7) !important;
  border-radius: 4px !important;
  background: linear-gradient(90deg, rgba(10, 35, 68, 0.5) 0%, rgba(4, 18, 36, 0.7) 100%) !important;
  box-shadow: inset 0 0 10px rgba(0, 150, 255, 0.05) !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.metric-row:hover, .diag-rank-card:hover, .score-row:hover, .rule-hit:hover, .qa-rule-row:hover, .qa-var-row:hover, .chronos-row:hover {
  border-color: rgba(0, 240, 255, 0.65) !important;
  border-left-color: #00f0ff !important;
  background: linear-gradient(90deg, rgba(18, 58, 108, 0.75) 0%, rgba(8, 30, 60, 0.85) 100%) !important;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.45), inset 0 0 12px rgba(0, 240, 255, 0.15) !important;
  transform: translateX(2px) !important;
}

/* 4. Glassmorphic Static Info Cards / 信息卡片玻璃态质感 */
.temp-card, .state-card, .suggest-card, .action-card, .category, .qa-response, .qa-case, .flow-box {
  border: 1px solid rgba(0, 160, 255, 0.4) !important;
  background: linear-gradient(135deg, rgba(10, 36, 70, 0.7) 0%, rgba(3, 16, 32, 0.85) 100%) !important;
  box-shadow: inset 0 0 18px rgba(0, 150, 255, 0.08), 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}

/* 5. Glowing Micro-components & Metrics / 数据字段霓虹高光 */
.metric-value, .chronos-value, .score-val, .diag-rank-value {
  color: #f1f8ff !important;
  text-shadow: 0 0 8px rgba(0, 240, 255, 0.45) !important;
}

.metric-dot {
  box-shadow: 0 0 10px currentColor, inset 0 1px 2px rgba(255,255,255,0.4) !important;
  border: 1px solid rgba(255,255,255,0.15) !important;
}

/* 6. Tactile 3D Buttons & Tabs / 拟物立体按键与 Tab */
.nav-btn {
  background: linear-gradient(180deg, rgba(14, 40, 78, 0.85) 0%, rgba(4, 16, 32, 0.95) 100%) !important;
  border: 1px solid rgba(0, 160, 255, 0.35) !important;
  border-radius: 6px !important;
  color: #a4c5e8 !important;
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.nav-btn:hover {
  border-color: #00f0ff !important;
  color: #ffffff !important;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.22), inset 0 1px 3px rgba(255,255,255,0.1) !important;
  transform: translateY(-1px) !important;
}

.nav-btn.active {
  background: linear-gradient(180deg, #106ce6 0%, #052a78 100%) !important;
  border-color: #00f0ff !important;
  border-top: 3px solid #00f0ff !important;
  color: #ffffff !important;
  box-shadow: 0 0 25px rgba(0, 160, 255, 0.65), inset 0 0 10px rgba(255, 255, 255, 0.3) !important;
}

.seg button, .forecast-btn, .ask-btn {
  background: linear-gradient(180deg, rgba(14, 45, 88, 0.9) 0%, rgba(4, 18, 38, 0.95) 100%) !important;
  border: 1px solid rgba(0, 160, 255, 0.45) !important;
  border-radius: 4px !important;
  transition: all 0.25s ease !important;
}

.seg button:hover, .forecast-btn:hover, .ask-btn:hover {
  border-color: #00f0ff !important;
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.35) !important;
}

.seg button.active {
  background: linear-gradient(180deg, #106ce6 0%, #042f7d 100%) !important;
  border-color: #00f0ff !important;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.45), 0 0 12px rgba(0, 160, 255, 0.35) !important;
}

/* 7. Input Fields Visual Depth / 输入框三维凹陷阴影 */
textarea, .chat-input {
  background: rgba(2, 10, 20, 0.85) !important;
  border: 1px solid rgba(0, 160, 255, 0.45) !important;
  box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(0, 240, 255, 0.05) !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

textarea:focus, .chat-input:focus {
  border-color: #00f0ff !important;
  box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.65), 0 0 12px rgba(0, 240, 255, 0.4) !important;
}

/* 8. Micro Scrollbars / 科技渐变微型滚动条 */
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #0e5c9f 0%, #00f0ff 100%) !important;
  border-radius: 4px !important;
}
"""

def apply_patch():
    print(f"Loading {HTML_FILE}...")
    if not HTML_FILE.exists():
        print(f"Error: {HTML_FILE} not found.")
        return 1
    
    content = HTML_FILE.read_text(encoding="utf-8")
    
    # Check if patch is already applied
    if "Visual depth and atmospheric visual enhancement" in content:
        print("Style patch is already present in the HTML file.")
        return 0
    
    target = "</style><script type=\"importmap\">"
    if target not in content:
        print(f"Error: Target marker '{target}' not found in the HTML file.")
        return 1
        
    print("Injecting CSS override patch...")
    new_content = content.replace(target, CSS_PATCH + target, 1)
    
    HTML_FILE.write_text(new_content, encoding="utf-8")
    print("Styling patch successfully applied.")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(apply_patch())
