# 建模契约

六项写全才开工。契约放在课件 HTML 的 `window.__LESSON_DATA__` 里（也可以是独立的 `lesson.json`），检查器两种都读。

## 模板

```json
{
  "meta": {
    "title": "凸透镜成像规律",
    "subject": "物理",
    "grade": "八年级上",
    "textbook": "人教版",
    "scale": { "unit": "cm", "pxPerUnit": 5.6, "note": "1 格 = 10 cm" },
    "duration": 240,
    "thumb": true,
    "source": "自建",
    "lawCheck": "1/f = 1/u + 1/v；u=30 f=10 → v=15，与作图交点一致"
  },
  "type": "field-wave",
  "kernel": { "kind": "closed-form", "precision": "闭式解，显示 1 位小数", "formula": "1/f = 1/u + 1/v" },
  "carrier": { "kind": "canvas2d", "why": "光路是平面几何，3D 会看不清三条特殊光线" },
  "law": { "name": "边界条件成立", "check": "三条特殊光线交于同一点，Snell 残差 < 1e-6" },
  "model": {
    "consts": [
      { "k": "f0", "v": 10, "unit": "cm", "from": "phys.f_typical" },
      { "k": "h0", "v": 6, "unit": "cm", "from": "定义" }
    ],
    "outputs": [
      { "k": "v", "unit": "cm" },
      { "k": "m", "unit": "倍" }
    ]
  },
  "console": {
    "sliders": [
      { "k": "u", "min": 6, "max": 48, "step": 0.5, "unit": "cm", "label": "物距 u" }
    ],
    "switches": [],
    "charts": 1
  },
  "steps": [
    {
      "tag": "u > 2f",
      "act": { "kind": "slider", "k": "u" },
      "expect": "u = 30 cm 时 v = 15 cm，像高 3 cm，倒立缩小实像",
      "concl": "物距大于二倍焦距，成倒立缩小的实像（照相机）"
    }
  ]
}
```

## 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `meta.subject` `meta.grade` `meta.textbook` | 是 | 口径卡按这三项选，缺一不可 |
| `meta.scale` | 是 | `unit` 与 `note` 必填；有像素换算时给 `pxPerUnit` |
| `meta.thumb` | 是 | 必须 `true`：首帧即缩略图 |
| `meta.source` | 是 | 自建 / 复刻自（仓库 + commit）/ 改编自（书名页） |
| `meta.lawCheck` | 是 | 一条可复述的手算或断言，写清数值 |
| `type` | 是 | `rigid` `media` `micro` `field-wave` `geometry` `process` `stats` `map` `bio-structure` `abstract` 之一 |
| `kernel.kind` | 是 | `symbolic` `closed-form` `numeric` `state-machine` `statistical` |
| `carrier.kind` | 是 | `three` `iso-svg` `canvas2d` `shader` `chart` `video` |
| `carrier.why` | 是 | 一句话解释"为什么不是别的载体" |
| `law.name` `law.check` | 是 | 类型硬律 + 怎么验 |
| `model.consts[]` | 是 | 每项 `k` `v` `unit` `from`；`from` 是口径卡键名或"定义" |
| `model.outputs[]` | 是 | 每个读数都要有 `unit` |
| `console.sliders` | 是 | ≤3，每项有 `k` `min` `max` `unit` |
| `console.switches` | 否 | ≤4 |
| `console.charts` | 否 | ≤1 |
| `steps` | 是 | 3–8 步，每步 `act`（`kind` 属于 slider/toggle/orbit/hold/record/custom）、`expect`、`concl` |

## 验收命令

```bash
node <skill>/scripts/check_model.mjs 课件.html          # 全量检查，任何一项不过退出码 1
node <skill>/scripts/check_model.mjs 课件.html --quiet   # 只打印失败项
```

物理/学科正确性不在检查器里，它查契约与结构；`meta.lawCheck` 那一行才是学科正确性的凭据，必须手算过。

## 三条硬规矩

1. **读数和几何同源**：`model` 里算一次，画面与面板都读它，不许面板另算一份。
2. **步骤数就是课时节奏**：3–8 步，一步一个动作、一句结论；超过 8 步说明该拆成两节。
3. **契约先于代码**：先把这份 JSON 写出来（哪怕只有骨架），再写渲染。
