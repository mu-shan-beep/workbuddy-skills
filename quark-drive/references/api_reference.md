# 夸克网盘网页端 API 参考（抓包提取）

> 均为 `https://drive-pc.quark.cn/1/clouddrive/` 下的接口（转存 save 例外，在 drive-h）。
> 通用参数 `?pr=ucpro&fr=pc&uc_param_str=`。鉴权全靠 Cookie，无需签名。
> 返回统一结构：`{"code": 0, "message": "ok", "data": {...}}`，code=0 为成功。

## 1. 分享转存（别人的 → 我的）

### 1.1 取 stoken
`POST /share/sharepage/token`
```json
{"pwd_id": "分享链接/s/后的id", "passcode": "提取码,无则空串"}
```
`data.stoken` 后续转存要用。

### 1.2 提交转存任务
`POST https://drive-h.quark.cn/1/clouddrive/share/sharepage/save`（注意域名是 drive-h）
```json
{"pwd_id": "...", "stoken": "...", "pdir_fid": "0", "to_pdir_fid": "目标目录fid",
 "pdir_save_all": true, "scene": "link"}
```
`data.task_id`。偶发被拒（code 41008 等），带 bx-ua/bx-umidtoken/bx_et 风控头重试可过。

### 1.3 轮询任务
`GET /task?task_id=xxx&retry_index=N`（N 从 0 递增，每次间隔 ~1.5s）
- `data.status`: `2`=成功；`3`=终态失败（顶层 code/message 给原因，如 41009 分享文件已删除）；`<0`=失败；其他=进行中
- 终态失败重试无意义（死链），应归档跳过

### 1.4 转存次数限制
member 接口 `data.member.file_save_to_remains` 每日 200 次，按天刷新。

## 2. 创建分享（我的 → 别人）

### 2.1 创建分享任务
`POST /share`
```json
{"fid_list": ["文件或目录fid"], "url_type": 1, "expired_type": 1}
```
- `url_type`: 1=公开链接 2=私密链接
- `expired_type`: 1=永久 2=1天 3=7天 4=30天
- `data.task_id` → 轮询 `/task` → `data.share_id`

### 2.2 查询分享信息（只回显，不生成密码）
`POST /share/password`
```json
{"share_id": "..."}
```
返回 `data.share_url` 等回显信息。⚠️ 实测此接口**不生成也不修改密码**（n8n 工作流靠它拿密码是误解）。
要私密分享：创建时（2.1）用 `url_type=2` + 4 位 `passcode`，服务端不会随机生成，缺 passcode 报 41000。

### 2.3 修改分享
`POST /share/update`
```json
{"pwd_id": "...", "url_type": 2, "expired_type": 1, "passcode": "ab12"}
```
⚠️ 接口吃 `pwd_id`（不是 share_id）。实测返回 ok 但 `url_type/passcode` **不落地**（仅标题等可改）。
改密码/公开互转 = 删掉重分享。

## 3. 文件管理

### 3.1 列目录
`GET /file/sort?pdir_fid=<fid>&_page=1&_size=100&_fetch_total=1&_sort=file_type:asc,updated_at:desc`
`data.list[]` 每项含 `fid / file_name / dir / pdir_fid / created_at / size`；`data._metadata.total` 总数。

### 3.2 容量
`GET /member?...&fetch_share=true`
`data.total_capacity` / `data.use_capacity`（字节）。

### 3.3 新建文件夹
`POST /file`
```json
{"pdir_fid": "父目录fid", "file_name": "名字", "dir_path": "", "dir_init_lock": false}
```
`data.fid`。

### 3.4 删除（异步任务）
`POST /file/delete`
```json
{"action": 2, "filelist": ["fid1", "fid2"], "to_trash": true}
```
- `to_trash: true` 进回收站（可恢复）；`false` 永久删除（不可恢复）
- 返回 `data.task_id` → 轮询 `/task` → `data.affected_file_num` 实际删除数

### 3.5 重命名
`POST /file/rename`
```json
{"fid": "...", "file_name": "新名字"}
```

### 3.6 回收站列表
网页端专用接口（`/trash/file` 等均 404），抓包未命中；删除默认 `to_trash=true` 已保证可恢复，恢复操作走网页回收站即可。

## 5. 搜索

`GET /file/search?q=<URL编码关键词>&_page=1&_size=20`
全盘文件名模糊匹配，`data.list[]` 结构同列目录（含 fid/file_name/dir/size/pdir_fid）。

## 6. 移动

`POST /file/move`
```json
{"action": 1, "filelist": ["fid1"], "to_pdir_fid": "目标目录fid"}
```
异步任务（返回 task_id → 轮询）。

## 7. 分享管理

### 7.1 我的分享列表
`GET /share/mypage/detail?_page=1&_size=50`
不带 share_id 返回全部分享。每项含 `pwd_id / share_id / title / url_type / passcode / share_url / status`（1=有效）。

### 7.2 取消分享
`POST /share/delete`
```json
{"pwd_ids": ["pwd_id1", "pwd_id2"]}
```
注意键名是 pwd_ids（不是 share_ids）。

### 7.3 预览别人分享
`GET /share/sharepage/detail?pwd_id=xxx&pdir_fid=0&stoken=<urlencoded>`
必须先 `POST /share/sharepage/token` 取 stoken，GET 传参（POST 会 405）。逐层浏览子目录传子项 fid 作 pdir_fid。

## 8. 已知摸不到的接口（需真实抓包）

- 回收站列表/恢复/彻底删除（`/trash/*` 全 404）
- 离线下载（磁力/链接离线，路由不在 drive-pc）

## 4. 风控与注意事项

- 每部间隔 ≥2 秒串行，连续异常等 20 秒，批量万次级无风控记录
- Cookie 关键字段：`__pus/__puus/__kp/__kps`，过期表现为全部接口 code!=0 或 302
- 转存同一目录同名自动去重为 `(1)` 后缀，重复转存同一分享会生成重复文件夹
- 死链特征：任务 61 秒内变 status=3 + 41009
