# 青榆口述史字幕交班台账

青榆市口述史资料馆接收制作组提供的已分词初稿和听校稿。夜班编辑只能读取获准公开的摘录，但省略的字幕仍可能改变旧标注的迁移结果。值班员凭原定稿号领取已签结论和首执。

## 一天的交班

1. 编目员导入初稿，取得固定修订号及具名词位。
2. 听校员交来更正稿，编目员另建修订并保留初稿。
3. 档案员按旧、新顺序选定同一稿件的两个修订号。
4. 档案员在各自许可范围内圈定包括端点的公开摘录。
5. 白班按摘录号发件，夜班验封实收并取得实收回执。
6. 源库关闭后，编辑凭件号提交无确认核定，收到定稿及首执。
7. 编辑从授权原录确认词位对应后，对同一件提交独立核定，并领取本次的定稿和首执。
8. 下一班凭原定稿号领取原结果，源稿更正和离线库重开均保留原账。

## Python 接口

使用 Python 3.11 标准库。源端用一个 `sqlite3.Connection` 构造 `RevisionStore` 和 `ExcerptStore`，按此顺序调用 `initialize()`。离线端用另一连接构造 `ReceiptStore` 和 `ArchiveStore` 并分别初始化。连接由调用方关闭。存储写入口管理自身事务，调用时连接须处于空闲状态。初始化只补建结构，样例由演示显式导入。证据封套由发行端经可信渠道交付，摘要用于核对内容完整性与身份绑定。

| 阶段 | 入口与结果 |
| --- | --- |
| I1 导入 | `revisions.importer.import_revision(store, manuscript_id, revision_id, segments)` 返回 `Revision`。每段为 `SourceSegment(segment_id, order, words)`，原段编号在同一修订内唯一，`order` 是严格递增的非负整数。词项是按原值比较的非空字符串，空段可用空序列表示。`store.get(revision_id)` 返回固定修订或 `None`。 |
| I2 摘录 | `excerpts.selection.select_excerpt(revisions, excerpts, excerpt_id, revision_id, permission, first_word_id, last_word_id)` 返回固定 `Excerpt`。`PublicationPermission(permission_id, revision_id, first_word_id, last_word_id)` 描述馆内许可闭区间。所选端点必须都在该区间内。`excerpts.get(excerpt_id)` 返回摘录或 `None`。 |
| I3 发行及实收 | `issue.publish.publish_packet(revisions, excerpts, old_excerpt_id, new_excerpt_id, *, packet_id=None)` 返回 V1 JSON 文本封套。离线端 `ReceiptStore.accept(envelope)` 返回原实收或新实收。`get_received(packet_id)` 返回带固定正文、封套和实收记录的 `ReceivedPacket`，未知号返回 `None`。 |
| I4 核定 | `review.submit.submit_review(receipts, archive, request)` 返回 `ArchiveEntry`。`ReviewRequest(packet_id, annotations, confirmations=())` 含至少一条 `OldAnnotation(annotation_id, word_id)`，同一请求的标注号须唯一。`Confirmation(old_word_id, new_word_id)` 引用本件两侧公开词位，重复的同一对合并为一个约束。`entry.report.details` 返回包含裁决、请求和件出处的 JSON 对象。 |
| I5 领取 | `archive.read.read_report(archive, report_id)` 返回原 `ArchiveEntry`，未知号返回 `None`。 |

词位号由固定修订号和零基整稿词序组成，段内词序也从零开始。公开词位携带原段号及段内词序。两稿的配对必须原值相同、严格保序且一对一。每个未配对词项计 1，两稿相加得到精确整数代价。一次请求的全部确认共同约束一条完整对齐。每条标注的目标按新版原序去重，任一最优对齐使它未匹配或匹配到片段外时，`can_have_no_public_landing` 为真。按请求顺序输出标注。件号与账号可用于固定引用，业务代价与结论只依赖指定输入和确认。

非法导入、许可、摘录和请求引用返回 `ValueError`。无相容对齐返回 `NoCompatibleAlignment`，错件或损坏封套返回 `EnvelopeMismatch`，两者是 `ValueError` 的子类。签存失败抛出 SQLite 错误，报告和成功首执共同回滚。完整原文、片段外词项及其逐词编码保存在源库。定稿快照随原首执共同提交，历史领取读取已有快照。

## 核验与演示

```text
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 由运行控制台在物化项目时提供。直接运行完整测试包可用 `python3 -B -m unittest discover -s tests -t .`。演示使用自动清理的独立临时库和 `sample_subtitles.json`。样例无确认时签出代价 2，旧 A 可无公开落点。确认两版的 A 后签出代价 4 和新版 A。最后重开离线库，按原号领回两份定稿和原首执。
