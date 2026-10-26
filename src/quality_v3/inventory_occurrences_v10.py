"""Restore unit-level verdict definitions without changing the selector wire.

Exact selectors and validation delegate to [v9](inventory_occurrences_v9.py).
Only development prompts change; no old model output is relabeled or repaired.
"""
import copy

import inventory_occurrences_v9 as CORE

VERSION = CORE.VERSION
PROMPT_REVISION = 'support-occurrence-prompts-v0.10'
REVIEW_VERSION = CORE.REVIEW_VERSION
MAX_ANCHOR_UNITS = CORE.MAX_ANCHOR_UNITS
OCCURRENCE_SCHEMA = copy.deepcopy(CORE.OCCURRENCE_SCHEMA)
GROUP_REVIEW_SCHEMA = copy.deepcopy(CORE.GROUP_REVIEW_SCHEMA)
OccurrenceContractError = CORE.OccurrenceContractError
validate_occurrence_response = CORE.validate_occurrence_response
assemble_inventory = CORE.assemble_inventory
validate_group_reviews = CORE.validate_group_reviews

UNIT_DEFINITIONS = '''本任务裁定单位是当前unit是否完成目标支持断言，不是判断整条fact现实中真假。
supported：此unit完成一处目标关系断言，且所选组提供主体、角色和范围的全部必要依据。
unsupported：此unit不完成该断言，包括无关背景、其他人物的边、仅编号映射/先行词组件、
仅未来条件或明确未确认的拟议登记。无需原文直接否定fact；没有当前支持就可unsupported。
unsupported单元仍可作为别处正组必要前件被引用，前件不是第二处关系断言。
unknown：原文本身的指代、角色、冲突或范围确有歧义，无法裁定它是否完成目标断言；
不能因未明确否认关系、未出现scope标签、未声明某一性别就把全部背景填unknown。
child始终是路径子辈，parent始终是所问父母辈，不能按语句主语/宾语颠倒。
“甲是乙的母亲”和“乙是甲的亲生儿子”都对应child=乙,parent=甲；后者需组内明确甲为女性
才能支持mother，否则只支持parent或角色未决。“女工程师甲。她的亲生儿子是乙。”
可用两unit同组支持乙→甲的mother关系，不能以句法倒装为由说方向相反。
明确生育语境的“甲生下乙”可表达母关系；普通“甲有一女乙/留下儿子乙”不自动证明甲性别。
若原文另有男性/夫妻合称或其他真实角色歧义，仍按组内语境核实，不凭姓名猜性别。
verdict、选择字段和reason应一致：若reason解释本unit不支持目标，写unsupported并留空选择；
不可一边说只否定了另一人的父亲关系，一边给当前目标supported。
'''
OCCURRENCE_PROMPT = UNIT_DEFINITIONS + CORE.OCCURRENCE_PROMPT
GROUP_REVIEW_PROMPT = CORE.GROUP_REVIEW_PROMPT + '''
补充核验口径：scope是当前材料的事实层/说话范围，不要求原文逐字含“登记事实/合成户籍”等
来源类别标签。普通登记直陈或已明确的复核可支持该材料世界的事实；明确戏中、梦中、
将来条件、未确认或已撤销的内容不能作为当前事实，实际相关限定仍须在本组选中原文内。
“甲是乙的母亲”与“乙是甲的亲生儿子”方向可等价；后一形式须本组有甲的女性/母角色依据。
明确生育语境“甲生下乙”可表达母关系，不等于普通“甲有女/留下儿子”从子辈性别猜parent。
无法确定应保留unknown，但不能仅因未见某个scope标签或另一组不可见而否认本组已有的
完整命名主体、关系、角色与语境。所有裁定只依本组，纯身份目录不补关系或性别。
'''


def build_occurrence_requests(request, max_anchor_units=MAX_ANCHOR_UNITS):
    """Keep exact v9 inputs/schema; replace only the documented prompt."""
    requests = CORE.build_occurrence_requests(request, max_anchor_units)
    for item in requests:
        item['skill'] = OCCURRENCE_PROMPT
    return requests


def build_group_review_requests(assembly):
    """Keep isolated inputs/digests; apply the explicit scope/role glossary."""
    requests = CORE.build_group_review_requests(assembly)
    for item in requests:
        item['skill'] = GROUP_REVIEW_PROMPT
    return requests
