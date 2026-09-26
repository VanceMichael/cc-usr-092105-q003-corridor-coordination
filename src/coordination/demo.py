"""构造一条跨省通道的演示场景。

名称和编号仅用于说明字段关系，不对应现实中的个人、企业或业务记录。
"""

from datetime import date

from .engine import CoordinationPlatform
from .model import (
    Approval,
    Attachment,
    Blocker,
    Commitment,
    CommitmentStatus,
    Condition,
    ConditionCategory,
    CorridorNode,
    Evidence,
    EvidenceKind,
    Milestone,
    NodeKind,
    StandardConflict,
)

AS_OF = date(2026, 9, 26)


def build_demo_platform() -> CoordinationPlatform:
    platform = CoordinationPlatform()

    # 沿线城市与产业节点
    platform.register_node(
        CorridorNode("N-CITY-1", "云州市", NodeKind.CITY, "SEG-跨江", "东省")
    )
    platform.register_node(
        CorridorNode("N-IND-1", "临港算力园", NodeKind.INDUSTRY, "SEG-跨江", "东省")
    )
    platform.register_node(
        CorridorNode("N-CITY-2", "岚山市", NodeKind.CITY, "SEG-跨江", "西省")
    )

    # 条件：用地、用海、用能、标准规则、算力通信、风险韧性
    platform.register_condition(Condition(
        "C-LAND-01", "跨江段用地预审", ConditionCategory.LAND, "SEG-跨江", "PV-2026A",
        node_id="N-CITY-1",
        required_signatories=frozenset({"东省自然资源厅", "西省自然资源厅"}),
    ))
    platform.register_condition(Condition(
        "C-SEA-01", "桥位用海报批", ConditionCategory.SEA, "SEG-跨江", "PV-2026A",
    ))
    platform.register_condition(Condition(
        "C-ENG-01", "算力园用能指标", ConditionCategory.ENERGY, "SEG-跨江", "PV-2026A",
        node_id="N-IND-1",
    ))
    platform.register_condition(Condition(
        "C-STD-01", "桥梁荷载标准衔接", ConditionCategory.STANDARD, "SEG-跨江", "PV-2026A",
    ))
    platform.register_condition(Condition(
        "C-CC-01", "沿线通信管沟配套", ConditionCategory.COMPUTE_COMM, "SEG-跨江", "PV-2026A",
    ))
    platform.register_condition(Condition(
        "C-RISK-01", "防洪影响韧性评估", ConditionCategory.RISK, "SEG-跨江", "PV-2026A",
        node_id="N-CITY-2",
    ))

    # 部门承诺：正式放行必须附范围、期限与正式文件
    platform.record_commitment(Commitment(
        "CM-LAND-1", "东省自然资源厅", "东省", "C-LAND-01",
        scope="跨江段东岸红线内用地", valid_until=date(2027, 12, 31),
    ))
    platform.mark_formal_release(
        "CM-LAND-1",
        scope="跨江段东岸红线内用地",
        valid_until=date(2027, 12, 31),
        evidence=[Evidence(EvidenceKind.OFFICIAL_DOCUMENT, "东自然资函〔2026〕41号", date(2026, 9, 10))],
        as_of=AS_OF,
    )
    # 用能只有口头赞同加一段视频发言，不能算正式放行
    platform.record_commitment(Commitment(
        "CM-ENG-1", "东省能源局", "东省", "C-ENG-01",
        scope="", valid_until=date(2027, 6, 30),
        evidence=[Evidence(EvidenceKind.VIDEO_STATEMENT, "协调会视频第3段", date(2026, 9, 20))],
    ))
    # 通信配套的正式放行期限已过
    platform.record_commitment(Commitment(
        "CM-CC-1", "西省通信管理局", "西省", "C-CC-01",
        scope="西省境内管沟共建", valid_until=date(2026, 6, 30),
        status=CommitmentStatus.FORMAL,
        evidence=[Evidence(EvidenceKind.OFFICIAL_DOCUMENT, "西通管函〔2026〕7号", date(2026, 3, 15))],
    ))

    # 标准冲突进入裁决流程
    platform.file_conflict(StandardConflict(
        "ADJ-01", "C-STD-01",
        standard_a="东省桥梁荷载规范（城-A级）",
        standard_b="西省桥梁荷载规范（公-Ⅰ级）",
        regions=("东省", "西省"),
    ))

    # 会签：东省已签，西省未签
    platform.cosign("C-LAND-01", "东省自然资源厅")

    # 审批
    platform.register_approval(Approval(
        "AP-01", "工程可行性研究报告批复", ["C-LAND-01", "C-ENG-01", "C-SEA-01"],
    ))
    platform.register_approval(Approval(
        "AP-02", "初步设计批复", ["C-STD-01", "C-CC-01", "C-RISK-01"],
    ))

    # 里程碑：M1 → M2 → M3 是关键路径，M4 有时差
    platform.register_milestone(Milestone(
        "M1", "工可批复", "SEG-跨江", 60, date(2026, 10, 2),
        required_conditions=["C-LAND-01", "C-ENG-01", "C-SEA-01"],
    ))
    platform.register_milestone(Milestone(
        "M2", "初步设计批复", "SEG-跨江", 90, date(2026, 12, 1),
        depends_on=["M1"], required_conditions=["C-STD-01", "C-CC-01"],
    ))
    platform.register_milestone(Milestone(
        "M3", "跨江段开工", "SEG-跨江", 30, date(2027, 3, 1),
        depends_on=["M2"],
    ))
    platform.register_milestone(Milestone(
        "M4", "防洪评估备案", "SEG-跨江", 20, date(2027, 3, 1),
        required_conditions=["C-RISK-01"],
    ))

    # 堵点：B-01 卡在关键路径上，B-02 不在
    platform.register_blocker(Blocker("B-01", "C-ENG-01", "用能指标未纳入省级年度计划"))
    platform.register_blocker(Blocker("B-02", "C-RISK-01", "防洪评估专题尚未送审"))

    # 附件：用海坐标属敏感件，只向东省开放
    platform.register_attachment(Attachment(
        "AT-01", "C-SEA-01", "桥位用海界址点坐标", sensitive=True,
        allowed_regions=frozenset({"东省"}),
    ))
    platform.register_attachment(Attachment(
        "AT-02", "C-LAND-01", "用地预审公开示意图",
    ))

    return platform
