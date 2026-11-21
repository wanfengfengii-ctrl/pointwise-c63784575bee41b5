# 字幕摘录的离线转授

白班已经按 README 的流程实收原摘录。持件编辑在源库关闭后按馆方委托选段，复审班在独立离线库实收子件，按子件号送审，次班按定稿号领回原账。原发行、实收、核定和领取入口继续适用。

## 馆方委托和子件发行

可信渠道交付一个可用 JSON 表示的 Python 字典，字段为 `delegation_id`、`parent_packet_id`、`parent_body_digest`、`old`、`new`。前两项为非空标识串，摘要为父件实收的 64 位小写十六进制 SHA-256。`old`、`new` 各含 `revision_id`、`first_word_id`、`last_word_id`，均为非空标识串，依原稿词序形成闭区间。完整委托的摘要为 `issue.envelope.canonical_json(delegation)` 的 UTF-8 字节的 SHA-256 小写十六进制串。`transfer_sample.py` 提供两个由馆方分别交付的委托样例。

新增 `issue.publish.publish_delegated_packet(receipts, parent_packet_id, delegation, old_bounds, new_bounds, *, packet_id=None)`，返回 JSON 文本封套。`receipts` 是持件方的 `ReceiptStore`，`old_bounds`、`new_bounds` 各为 `(首词位号, 末词位号)`。用现有词位身份按两侧各自原稿词序选择连续非空子区间，至少一侧严格小于父件片段。委托必须与实际实收父件的件号、正文摘要及两侧有序修订一致，各授权区间位于对应父片段内，所选区间位于对应授权内。仅 V1 实收件可作为父件，子件号与父件号不同。`packet_id=None` 时生成新号。身份或范围非法时抛 `ValueError`，持件方原实收保持完整。

子件封套沿用 V1 的 `version`、`declaration`、`body`、`sha256` 外层字段和正文摘要约定，子件的 `version` 为 2。子件带有自身件号、父件号和父件正文摘要、委托号和委托摘要，以及旧、新顺序的词位身份。每侧词项保留原值、词位号和原段出处。正文和声明中的逐词数据仅限所选两侧，各侧片外词的值、词位号、逐词编码和出处留在持件侧。抽象证据可表达片外对对齐关系的贡献。子件证据的具体表示由实现决定。

## 复审实收和领取

扩展 `ReceiptStore.accept(envelope, *, delegation=None)`。接纳子件时，复审班从可信渠道单独取得馆方委托，复审库只需该委托与子件。核对封套完整性、声明与正文一致、有序修订、两侧范围、父件号及父件正文摘要，并核对完整委托与子件绑定。复审班据馆方委托确认可交付范围，据可信渠道取得的子件使用证据。缺委托、超界、错绑、损坏或同号异件抛 `EnvelopeMismatch`，原实收保持完整。父件和子件共用件号命名空间。同件同委托重投，包括离线库重开后重投，返回原 `PacketReceipt`。`get_received(packet_id)` 按现行接口返回已实收子件及其实收记录，读取时仅使用本库已验收数据。

沿用 `ReviewRequest`、`submit_review` 和 `read_report`。标注只引用子件旧侧词位，确认只引用子件两侧公开词位。全部确认必须共同成立。核定沿用 README 的全稿计价和公开落点语义，片外匹配可以影响代价及有无公开落点，落点按新版原词序返回所选词项的原出处。片外引用抛 `ValueError`，无共同对齐抛 `NoCompatibleAlignment`。子件定稿沿用 V1 字段，并在 `entry.report.details['delegation']` 固定 `parent_packet_id`、`parent_body_digest`、`delegation_id`、`delegation_digest`。定稿与成功首执共同生效。拒绝或签存失败无新定稿或成功首执。重开后以定稿号领取原结果和原首执，旧 V1 定稿仍按原格式领取。

## 样例与运行入口

`transfer_sample.py` 的 `prepare_parent` 用现有接口准备父件，`prepare_reviewer` 初始化另一复审库。`python3 -B transfer_sample.py` 核对样例父件摘要及复审库的初始隔离。

- `late` 的父件完整公开 A X X B 与 X X A B。选段仅含两侧 A。无确认时匹配两个 X 和 B，代价 2，旧 A 无公开落点。确认旧 A 对新版 `late-new:2` 后只有 A 和 B 可配对，代价 4，唯一公开落点为 `late-new:2`，不可无公开落点。
- `tie` 的父件完整公开 A 与 A A。选段仅含旧 A 与新稿首个 A。无确认时代价 1，`tie-new:0` 是公开落点，同时可能没有公开落点。确认首个 A 后代价仍为 1，且该公开落点必有。

保留 `python3 -B check_project.py` 原回归。沿用 `.pointwise-runtime.json` 的 v1 CLI 运行清单及 argv 格式，使 `verify` 运行原回归与转授的联动核验，核验失败返回非零退出码。让 `demo` 实际走一遍 `late` 的关源转授、独立实收、无确认与有确认的定稿及重开领取，显示实际代价、落点、父件与委托出处和原首执。
