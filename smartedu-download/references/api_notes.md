# 国家中小学智慧教育平台 课程包下载 — 技术参考

本文档记录破解与下载课程包资源所用的底层接口与算法，供维护/排错时参考。

## 1. 资源清单接口（公开，无需登录）

```
GET https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/{activityId}.json
```

- `activityId` 来自课程页 URL 的 `activityId=` 参数。
- 返回 JSON，结构：`global_title.zh-CN` 为课程名；`relations.national_course_resource` 为资源数组。
- 每个资源含 `global_title.zh-CN`、`resource_type_code`、`ti_items[]`。
- `ti_items[].ti_format` / `ti_file_flag` 描述格式；`ti_items[].ti_storages[]` 为文件 URL 列表。
- 该接口**无需任何鉴权**，可直接 curl 获取。

### resource_type_code 映射

| code | 含义 | 目标格式 |
|---|---|---|
| `micro_lesson_video` | 视频课程 | mp4 |
| `coursewares` | 课件 | pptx |
| `lesson_plandesign` | 教学设计 | docx |
| `learning_task` | 学习任务单 | docx |
| `after_class_exercise` | 课后练习 | docx |

## 2. 资源文件鉴权（双认证机制）

**重要发现**：视频资源使用 **Bearer 认证**，而密钥服务器使用 **MAC 认证**，两者不能混用。

### 2.1 Bearer 认证（m3u8 索引 + ts 分片）

```
Authorization: Bearer <access_token>
Referer: https://basic.smartedu.cn/
```

用于：
- 拉取 m3u8 播放列表
- 下载 .ts 视频分片

**错误示例**：
- 用 MAC 认证访问 m3u8 → 401
- 用 Bearer 认证访问密钥服务器 → 403「IP 不被允许」

### 2.2 MAC 认证（密钥服务器）

```
X-ND-AUTH: MAC id="<access_token>",nonce="0",mac="0"
Referer: https://basic.smartedu.cn/
```

用于：
- 获取密钥 nonce：`GET {key_uri}/signs`
- 获取加密密钥：`GET {key_uri}?nonce={nonce}&sign={sign}`

### 2.3 文档下载

文档（PDF）同时支持两种认证方式，推荐使用 Bearer：
```
Authorization: Bearer <access_token>
```

## 3. access_token 的获取（来自已登录浏览器）

token 存于 `basic.smartedu.cn` 的 Local Storage，通常在一个值内含：

```json
{"value":"{\"source_token_account_type\":\"person\",...,\"mac_key\":\"p1iTg0JOan\",\"mac_algorithm\":\"hmac-sha-256\",\"access_token\":\"7F938B205F...\",\"refresh_token\":\"7F938B205F...\"}"}
```

取其中 `access_token` 字段即可。

### 自动获取（推荐）

运行本 skill 的 `scripts/token_helper.py`，它会启动本地 HTTP 接收器并生成一段 bookmarklet。用户在已登录平台的页面点击书签，即可自动提取 token 并回传到本地文件，无需手动翻 DevTools。

### 手动获取（兜底）

1. 浏览器打开并登录 `basic.smartedu.cn`。
2. F12 → **Application** → **Local Storage** → `https://basic.smartedu.cn`。
3. 找到值里含 `access_token` 的键，复制其完整 Value（或其中 `access_token` 字段）传给脚本。
4. 若想用 Console：Snippets 面板粘贴运行下面脚本（避开粘贴警告）：

```js
const keys = Object.keys(localStorage);
for (const k of keys) {
  const v = localStorage.getItem(k) || '';
  if (/access_token/i.test(v)) {
    console.log('KEY:', k);
    try {
      console.log('TOKEN:', JSON.parse(JSON.parse(v).value).access_token);
    } catch(e) {
      console.log(v.slice(0, 400));
    }
  }
}
```

- token 有时效（通常数小时），过期后重新取一次即可。

## 4. 视频解密算法（AES-128 加密 HLS）

视频为 `#EXT-X-KEY` 标注的 AES-128 加密 m3u8。密钥**不在** m3u8 里直接给，需经签名换取：

1. 从 m3u8 解析 `URI`（密钥地址）与 `IV`。
2. `GET {URI}/signs` → 取 `nonce` 字段。
3. `sign = MD5(nonce + keyId)[:16]`（keyId 为 URI 最后一段）。
4. `GET {URI}?nonce={nonce}&sign={sign}` → 取 `key` 字段（base64）。
5. `真实密钥 = AES_ECB_decrypt(base64(key), sign)` 后去 padding（16 字节）。
6. 每个 `.ts` 分片用 `真实密钥 + IV` 做 AES-CBC 解密，去 padding。
7. 拼接所有解密后分片 → `ffmpeg -i combined.ts -c copy ... out.mp4`（封装不重编码）。

> 注意：密钥服务器首次请求不带参数会返回 400「Required String parameter 'nonce' is not present」；带 Bearer 会 403「IP 不被允许」。必须走上面的 `signs` → `sign` 流程。

## 5. 文档转换

- **课件 PDF → PPTX**：用 PyMuPDF 逐页 `get_pixmap` 渲染为图片，整页插入幻灯片（视觉与原件一致，但文字不可直接选中编辑）。
- **教学设计/任务单/练习 PDF → DOCX**：用 PyMuPDF 提取每页文本写入段落；纯图页则渲染为图片嵌入。文本可被 Word 编辑。

## 6. 已知限制

- 课件 pptx 为"图片式"，非原生可编辑对象。如需可编辑 pptx 需 OCR/版式还原（暂不支持）。
- token 时效短，跨时段下载需重新取。
- 清晰度默认 720p；360p/480p 通过 `--quality` 切换。
- 依赖联网自动安装：PyMuPDF、python-pptx、python-docx、pycryptodome、imageio-ffmpeg（含 ffmpeg 静态二进制）。

## 7. 需求反馈邮箱

下载互动中收集到的需求，通过 `scripts/feedback.py` 发送（收件人地址已内置，base64 编码，本文档不公开明文）。主题格式：

```
智慧教育平台下载需求反馈 - activityId: <activityId>
```

正文应包含：用户原话摘要、关联 activityId、期望优先级/联系方式。
