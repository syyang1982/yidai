"""Initialize knowledge base with Xiaomi data."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.knowledge.base import KnowledgeBase

kb = KnowledgeBase()

kb.create_company_profile(
    ticker='01810.HK', name='小米集团', market='HK',
    sector='科技/消费电子',
    thesis='核心持仓。看好AI+汽车+IoT生态协同。手机基本盘稳固，汽车业务是第二增长曲线，IoT生态构建护城河。雷军执行力强，战略清晰。'
)

kb.update_company_scores('01810.HK', {
    '盈利': 5, '健康': 5, '现金流': 3,
    '估值': 5, '成长': 5, '股东': 4, '战略': 4,
}, event_date='2026-05-26')

kb.update_company_financials('01810.HK', {
    '营收': '4573亿', '净利': '416亿', 'ROE': '15.6%',
    '毛利率': '22.3%', '净利率': '9.1%', '负债率': '47.6%',
    'PE': '19.4', 'PEG': '0.78',
}, event_date='2026-05-26')

for risk in ['汽车业务盈利拐点未到，资本开支大',
             '现金流因工厂投资承压，FCF缺失',
             '地缘政治风险（印度市场、美国制裁）',
             '手机行业周期性，高端化能否持续']:
    kb.add_risk('01810.HK', risk)

kb.add_lesson('现金流恶化是先行指标，小米2022年OCF下降先于营收下滑', '01810.HK', '现金流')
kb.add_lesson('估值评分和实际价格走势高度相关，PEG<1时往往是好买点', '01810.HK', '估值')
kb.add_lesson('长期持有比频繁交易更有效，小米买入持有+69% vs 策略-41%', '01810.HK', '心理')
kb.add_lesson('季报信号比年报更及时，v2策略回撤降低43%', '01810.HK', '风险管理')

kb.add_principle('好公司+好价格=好投资', '小米PEG<1时买入，长期回报显著')
kb.add_principle('现金流比利润更真实', '小米多次利润正但OCF下降，是预警信号')
kb.add_principle('不要因为短期波动卖出好公司', '小米2022年评分降至C级，但2024年回到A级')

kb.add_journal_entry('01810.HK', '初始建仓', '核心持仓，长期看好AI+汽车+IoT生态', '2021-01-01')

print('✅ 知识库初始化完成')
print()
print(kb.generate_kb_summary())
