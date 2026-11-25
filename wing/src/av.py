# -*- coding: utf-8 -*-
BG  =[("#F2E2D5","#D9AC97"),("#F0E6DB","#D2A48F"),("#F4E5D7","#DEB4A0"),("#EEDCCD","#D5A692")]
SKIN=["#F7E8DA","#F3DECD","#F8ECE1","#F1DAC7"]
DARK=["#16223C","#1D2B49","#121C32","#1A2742"]
TOP =["#F7F3EC","#F2ECE2","#FAF6F0","#F4EFE6"]

def extras(k):                       # drawn behind the head
    if k==1:  return '<path d="M19 28h9v26h-9zM52 28h9v26h-9z"/>'                    # bob
    if k==2:  return '<path d="M17 26h10v42H17zM53 26h10v42H53z"/>'                   # long
    if k==3:  return '<path d="M55 24c9 2 14 9 14 18s-5 15-13 18l-5-9c5-2 8-5 8-9s-3-7-8-8z"/>'  # ponytail
    if k==5:  return '<path d="M17 26c-2 14 0 25 5 33l9-4c-4-7-5-17-4-28zM63 26c2 14 0 25-5 33l-9-4c4-7 5-17 4-28z"/>'  # wavy
    return ''
def top(k):                          # drawn in front
    return '<circle cx="40" cy="11" r="9.5"/>' if k==4 else ''

def avatar(i,mono=False):
    b0,b1=(BG[0] if mono else BG[i%4]); s=(SKIN[0] if mono else SKIN[(i+1)%4])
    d=(DARK[0] if mono else DARK[i%4]); t=(TOP[0] if mono else TOP[(i+2)%4]); k=i%6
    u=f"m{i}" if mono else f"a{i}"
    return (f'<svg class="avs" viewBox="0 0 80 80" aria-hidden="true">'
      f'<defs><clipPath id="c{u}"><circle cx="40" cy="40" r="40"/></clipPath>'
      f'<linearGradient id="g{u}" x1=".1" y1="0" x2=".9" y2="1">'
      f'<stop offset="0" stop-color="{b0}"/><stop offset="1" stop-color="{b1}"/></linearGradient></defs>'
      f'<g clip-path="url(#c{u})"><rect width="80" height="80" fill="url(#g{u})"/>'
      f'<path d="M4 80c0-19 16-29 36-29s36 10 36 29z" fill="{t}"/>'
      f'<path d="M33 40h14v16H33z" fill="{s}"/>'
      f'<g fill="{d}">{extras(k)}<ellipse cx="40" cy="30" rx="17.5" ry="19.5"/></g>'
      f'<ellipse cx="40" cy="36" rx="14.5" ry="16" fill="{s}"/>'
      f'<g fill="{d}">{top(k)}</g>'
      f'</g><circle cx="40" cy="40" r="39" fill="none" stroke="rgba(242,239,233,.3)" stroke-width="2"/></svg>')
