#!/usr/bin/env python3
"""
align_ports.py — align port brackets in Verilog instantiations for better looking.

Scans every `.v` and `.sv` file under `fpga/src/verilog/` for module
instantiations that use named port connections of the form
`.port_name(signal)` and reformats those connection lines so the
`.port_name` and the right-hand expressions inside the parentheses are
column-aligned. Preserves commas and end-of-line comments. Writes a
file back if any formatting changes were made.

Usage:
    python3 fpga/scripts/align_ports.py
"""
from pathlib import Path
import re

def align_file(p):
    s=p.read_text()
    lines=s.splitlines()
    out_lines=[]
    i=0
    n=len(lines)
    while i<n:
        line=lines[i]
        if '(' in line:
            j=i+1
            while j<n and lines[j].strip()=='' : j+=1
            if j<n and re.match(r'\s*\.', lines[j]):
                start=i
                k=j
                end=None
                while k<n:
                    if re.match(r'\s*\)\s*;?\s*$', lines[k]):
                        end=k
                        break
                    if ');' in lines[k]:
                        end=k
                        break
                    k+=1
                if end is None:
                    out_lines.append(line)
                    i+=1
                    continue
                block = lines[start:end+1]
                port_idxs=[]
                for idx,ln in enumerate(block):
                    if re.match(r'\s*\.', ln):
                        port_idxs.append(idx)
                if not port_idxs:
                    out_lines.extend(block)
                    i=end+1
                    continue
                max_port=0
                max_rhs=0
                parsed={}
                for idx in port_idxs:
                    ln=block[idx]
                    m_comment=re.search(r'//.*$', ln)
                    comment = m_comment.group(0) if m_comment else ''
                    core = ln[:m_comment.start()] if m_comment else ln
                    m=re.match(r'(\s*)\.(\w+)\s*\((.*)\)\s*(,?)\s*$', core)
                    if not m:
                        m=re.match(r'(\s*)\.(\w+)\s*\((.*?)(,?)\s*$', core)
                    if not m:
                        parsed[idx]=(None,None)
                        continue
                    lead,port,rhs,comma = m.group(1),m.group(2),m.group(3).strip(),m.group(4)
                    port_tok='.'+port
                    max_port=max(max_port, len(port_tok))
                    max_rhs=max(max_rhs, len(rhs))
                    parsed[idx]=(lead,port_tok,rhs,comma or '', comment)
                new_block=list(block)
                for idx in port_idxs:
                    entry=parsed.get(idx)
                    if not entry or entry[0] is None:
                        continue
                    lead,port_tok,rhs,comma,comment=entry
                    pad_port = ' '*(max_port - len(port_tok) + 1)
                    pad_rhs = ' '*(max_rhs - len(rhs) )
                    new_ln = f"{lead}{port_tok}{pad_port}({rhs}{pad_rhs}){comma}"
                    if comment:
                        new_ln = new_ln + ' ' + comment
                    new_block[idx]=new_ln
                out_lines.extend(new_block)
                i=end+1
                continue
        out_lines.append(line)
        i+=1
    new='\n'.join(out_lines)+"\n"
    if new!=s:
        p.write_text(new)
        print('formatted', p)
    else:
        print('no changes', p)


def main():
    root=Path(__file__).resolve().parent.parent / 'src' / 'verilog'
    files=sorted(p for ext in ('*.v','*.sv') for p in root.rglob(ext))
    if not files:
        print('no .v or .sv files found under', root)
        return
    for f in files:
        align_file(f)


if __name__=='__main__':
    main()
