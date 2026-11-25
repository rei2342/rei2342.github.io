# -*- coding: utf-8 -*-
import io,sys
sys.path.insert(0,'.')
from gen import ACTS
ROWS=[[it for it in items] for _,_,_,items in ACTS]

def line(items,cls):
    inner=' <s>/</s> '.join(f'<b>{jp}</b>' for no,m,jp,en,sub,st,stl in items)
    return f'<div class="ln {cls}">{inner}</div>'

CSS="""
:root{--paper:#F2EFE9;--accent:#D9AC97;--accent-hi:#F6DCC9;--faint:rgba(242,239,233,.36);
 --line:rgba(242,239,233,.16);--d:'Archivo','Noto Sans JP',sans-serif;--b:'Noto Sans JP','Archivo',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#050B14}
#poster{width:1080px;height:1350px;padding:58px 54px 42px;position:relative;overflow:hidden;color:var(--paper);
 font-family:var(--b);display:flex;flex-direction:column;text-align:center;
 background:radial-gradient(130% 78% at 50% -14%,#32436C 0%,#1A2744 38%,#090F1B 100%)}
#poster::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.34;
 background-image:radial-gradient(rgba(242,239,233,.11) 1px,transparent 1px);background-size:34px 34px}
#poster>*{position:relative;z-index:1}
.hd{display:flex;align-items:center;gap:16px;margin-bottom:34px}
.hd .lg{font-family:var(--d);font-style:italic;font-weight:900;font-size:23px;letter-spacing:-.055em;display:flex;align-items:center;gap:6px}
.hd .lg i{width:7px;height:7px;background:var(--accent);display:block}
.hd .r{flex:1;height:1px;background:var(--line)}
.hd .tag{font-family:var(--d);font-weight:600;font-size:11.5px;letter-spacing:.26em;color:var(--faint)}
h1{font-family:var(--d);font-style:italic;font-weight:900;font-size:138px;line-height:.8;letter-spacing:-.075em}
h1 em{font-style:italic;color:var(--accent)}
.meta{font-weight:900;font-size:19px;letter-spacing:-.03em;margin-top:20px}
.per{font-family:var(--d);font-weight:600;font-size:12px;letter-spacing:.3em;color:var(--faint);margin-top:9px}
.rule{height:1px;background:var(--line);margin:30px 0}
.rule.a{background:linear-gradient(90deg,transparent,rgba(217,172,151,.75),transparent);height:1.5px}

.head{margin:4px 0 2px}
.head .k{font-family:var(--d);font-weight:800;font-size:11.5px;letter-spacing:.42em;color:var(--accent);display:block;margin-bottom:16px}
.head .t{font-family:var(--d);font-style:italic;font-weight:900;font-size:76px;line-height:.92;letter-spacing:-.065em;color:var(--accent-hi);display:block}
.head .s{font-weight:900;font-size:24px;letter-spacing:-.04em;margin-top:18px;display:block}
.head .s i{font-style:normal;color:var(--accent);font-family:var(--d)}

.stack{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;padding:2px 0}
.ln{line-height:1.2;letter-spacing:-.055em;font-weight:900;text-wrap:balance}
.ln s{text-decoration:none;color:var(--accent);font-weight:600;margin:0 .14em;font-size:.56em;vertical-align:.12em}
.t1{font-size:58px}
.t2{font-size:52px}
.t3{font-size:50px}
.t4{font-size:46px}
.ln b{font-weight:900}

.ft{padding-top:20px;border-top:1px solid var(--line);display:flex;align-items:flex-end;justify-content:space-between;gap:18px;text-align:left}
.ft b{display:block;font-weight:900;font-size:19px;letter-spacing:-.045em;margin-bottom:5px}
.ft .l span{font-size:11.5px;color:var(--faint)}
.ft .r{text-align:right;font-family:var(--d);font-weight:700;font-size:14px;letter-spacing:.12em;color:var(--accent)}
.ft .r small{display:block;font-size:10px;letter-spacing:.08em;color:var(--faint);margin-top:5px;font-weight:600}
"""
io.open('typeposter.html','w',encoding='utf-8').write(f'''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,600;0,700;0,800;1,800;1,900&family=Noto+Sans+JP:wght@400;500;700;900&display=swap">
<style>{CSS}</style></head><body>
<div id="poster">
  <div class="hd"><span class="lg">WING<i></i></span><span class="r"></span><span class="tag">歯科衛生士 2.0</span></div>
  <h1>SEASON<em>01</em></h1>
  <div class="meta">12 SESSIONS ＋ 1 EXPEDITION</div>
  <div class="per">2027.1 — 2028.1</div>
  <div class="rule a"></div>
  <div class="head"><span class="k">H E A D L I N E R</span>
    <span class="t">SCANDINAVIAN<br>APPROACH</span>
    <span class="s">スウェーデン現地研修 <i>／</i> 2027.6</span></div>
  <div class="rule a"></div>
  <div class="stack">
    {line(ROWS[0],'t1')}
    {line(ROWS[1],'t2')}
    {line(ROWS[2],'t3')}
    {line(ROWS[3],'t4')}
  </div>
  <div class="ft"><div class="l"><b>第1期メンバー 100名限定</b>
    <span>毎月1回・90分｜講義 → 対談 → ワーク</span></div>
    <div class="r">@wing_dh<small>詳細は LINE にて先行案内</small></div></div>
</div></body></html>''')
print('built')
