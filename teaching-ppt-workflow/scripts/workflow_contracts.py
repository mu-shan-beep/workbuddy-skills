# -*- coding: utf-8 -*-
"""Cross-file checks for the current workflow contracts; read-only."""
from pathlib import Path
import re
NUM={'五':5,'六':6,'七':7,'八':8}
def violations(root):
 root=Path(root);t=root/'teaching-ppt-workflow';ref=t/'references'
 def read(p):return p.read_text(encoding='utf-8')
 pack=read(ref/'lesson-pack.md');modes=read(ref/'task-modes.md');qa=read(ref/'qa-and-delivery.md');sm=read(ref/'self-maintenance.md');pro=read(ref/'lesson-pack-prompts.md');main=read(t/'SKILL.md');issues=[]
 section=pack.split('## 教学设计动笔前基线',1)[1].split('\n## ',1)[0]
 count=len(re.findall(r'^\| [①②③④⑤⑥⑦⑧]',section,re.M))
 for label,s in [('基线定义',section),('撰写入口',modes),('复核与登记',sm)]:
  for n in re.findall(r'([五六七八])(?:项|类)(?:基线|取证清单|取证物)',s):
   if NUM[n]!=count:issues.append(f'{label}称{n}项，实际基线表{count}项')
 if 'staged answers' in qa:issues.append('大纲质检仍要求staged answers')
 paragraph=next((l for l in qa.splitlines() if '关键图片素材预检' in l),'')
 if 'Markdown' in main and '仅' not in paragraph:issues.append('Word素材预检未限定适用范围')
 if '用户未限定课时时，据教材任务' in pack:issues.append('缺课时仍自动推导')
 if '课题、作者与学段版本三项' in modes:issues.append('封面仍强制学段版本')
 if re.search(r'^## (?:检查)?制作笔记',pro,re.M):issues.append('人工提示词仍存在制作笔记入口')
 if '；制作笔记仅在另行委托时制作' in read(ref/'workflow.md'):issues.append('停用后仍恢复制作笔记')
 if '一律走「抽读看样本' in pack:issues.append('个案评价动作仍为全局一律要求')
 transcript=read(root/'lesson-transcript'/'SKILL.md')
 if '路径与命名：课题根目录 `<课文>' in transcript:issues.append('逐字稿源稿路径仍为根目录默认')
 return issues
if __name__=='__main__':
 import sys
 result=violations(sys.argv[1]);print('\n'.join(result) if result else 'PASS：跨文件工作流契约一致');raise SystemExit(bool(result))
